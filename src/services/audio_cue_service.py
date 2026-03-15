"""
Audio Cue Service — Loads pre-generated TTS audio for real-time coaching.

Audio files are generated once via scripts/generate_cue_audio.py using the
OpenAI Realtime API (same voice as the voice agent). Multiple variants per
cue are stored on disk as WAV files; this service indexes the paths and picks
a random variant each time for natural-sounding playback.

Playback routes through LiveKit's session.say() so audio reaches the user
via the WebRTC track.

Fallback: if no pre-generated files exist for a cue, generates audio on
the fly via the OpenAI TTS API and plays it through session.say().
"""

import asyncio
import logging
import os
import random
import time
import wave
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional, Tuple

from livekit import rtc
from livekit.agents.utils.audio import audio_frames_from_file
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Directory where pre-generated cue files live
CUES_DIR = Path(__file__).parent.parent / "assets" / "cues"
CUES_WAV_DIR = CUES_DIR / "wav"

# Fallback TTS configuration (only used if pre-generated files are missing)
TTS_MODEL = "gpt-4o-mini-tts"
TTS_VOICE = os.getenv("REALTIME_VOICE", "cedar")
TTS_SPEED = 1.1
TTS_FORMAT = "pcm"  # 24kHz 16-bit mono PCM
TTS_INSTRUCTIONS = (
    "You are an energetic gym coach giving real-time cues during a workout. "
    "Speak with high energy, urgency, and motivation — like you're right next "
    "to the lifter on the gym floor. Short, punchy, and commanding."
)

# Number words for rep cues
_NUMBER_WORDS = {
    1: "One!", 2: "Two!", 3: "Three!", 4: "Four!", 5: "Five!",
    6: "Six!", 7: "Seven!", 8: "Eight!", 9: "Nine!", 10: "Ten!",
    11: "Eleven!", 12: "Twelve!", 13: "Thirteen!", 14: "Fourteen!", 15: "Fifteen!",
    16: "Sixteen!", 17: "Seventeen!", 18: "Eighteen!", 19: "Nineteen!", 20: "Twenty!",
}

# Cue key → spoken text mapping
CUE_TEXT_MAP: Dict[str, str] = {
    # Squat corrections
    "knees_out": "Knees out!",
    "chest_up": "Chest up!",
    "deeper": "Get deeper!",
    "heels_down": "Heels down!",
    "even_it_out": "Even it out!",
    "slow_down": "Slow down!",
    "brace": "Brace your core!",
    # Deadlift corrections
    "hips_through": "Hips through!",
    "flat_back": "Flat back!",
    "lockout": "Lock it out!",
    # Positive reinforcement
    "good_rep": "Good rep!",
    "great_depth": "Great depth!",
    "strong": "Strong!",
    "clean": "Clean!",
    "perfect": "Perfect!",
    # Rep counts
    **{f"rep_{i}": _NUMBER_WORDS[i] for i in range(1, 21)},
}

# Audio format constants
SAMPLE_RATE = 24000
NUM_CHANNELS = 1
SAMPLES_PER_CHUNK = 2048  # ~85ms per chunk at 24kHz


class AudioCueService:
    """
    Indexes pre-generated WAV cue files from disk with random variant selection.
    Plays cues through LiveKit's session.say() for WebRTC delivery.

    Falls back to runtime TTS generation for any cues missing on disk.
    """

    def __init__(self, session) -> None:
        self._session = session  # AgentSession — for session.say()
        # cue_key → list of WAV file paths (one per variant)
        self._disk_cache: Dict[str, List[Path]] = {}
        # cue_key → list of variants, each variant is a list of AudioFrame chunks (in-memory)
        self._memory_cache: Dict[str, List[List[rtc.AudioFrame]]] = {}
        # Runtime-generated fallback cache: cue_key → raw PCM bytes
        self._fallback_cache: Dict[str, bytes] = {}
        self._client: Optional[AsyncOpenAI] = None
        self._disk_loaded: bool = False

        # Eagerly load and pre-read all WAV cues into memory
        self._load_from_disk()

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI()
        return self._client

    def _load_from_disk(self) -> None:
        """Index all pre-generated WAV files from the cues directory."""
        if self._disk_loaded:
            return

        if not CUES_WAV_DIR.exists():
            logger.warning(f"[AUDIO CUE] WAV cues directory not found: {CUES_WAV_DIR}")
            self._disk_loaded = True
            return

        count = 0
        for wav_file in CUES_WAV_DIR.glob("*.wav"):
            # Filename format: {cue_key}_{variant}.wav
            name = wav_file.stem
            # Split on last underscore to get cue_key and variant number
            last_underscore = name.rfind("_")
            if last_underscore == -1:
                continue
            cue_key = name[:last_underscore]
            try:
                int(name[last_underscore + 1:])  # Validate variant is a number
            except ValueError:
                continue

            if cue_key not in self._disk_cache:
                self._disk_cache[cue_key] = []
            self._disk_cache[cue_key].append(wav_file)
            count += 1

        self._disk_loaded = True
        logger.info(
            f"[AUDIO CUE] Indexed {count} pre-generated WAV files "
            f"for {len(self._disk_cache)} cue keys from {CUES_WAV_DIR}"
        )

        # Pre-read all WAV files into memory as AudioFrame lists
        # (audio_frames_from_file is async, so we read WAV files directly here)
        mem_count = 0
        bytes_per_sample = 2  # int16
        chunk_bytes = SAMPLES_PER_CHUNK * NUM_CHANNELS * bytes_per_sample
        for cue_key, paths in self._disk_cache.items():
            self._memory_cache[cue_key] = []
            for wav_path in paths:
                try:
                    with wave.open(str(wav_path), "rb") as wf:
                        pcm_data = wf.readframes(wf.getnframes())
                    frames = []
                    for offset in range(0, len(pcm_data), chunk_bytes):
                        chunk = pcm_data[offset:offset + chunk_bytes]
                        samples = len(chunk) // (NUM_CHANNELS * bytes_per_sample)
                        frames.append(rtc.AudioFrame(
                            data=chunk,
                            sample_rate=SAMPLE_RATE,
                            num_channels=NUM_CHANNELS,
                            samples_per_channel=samples,
                        ))
                    self._memory_cache[cue_key].append(frames)
                    mem_count += 1
                except Exception as e:
                    logger.warning(f"[AUDIO CUE] Failed to pre-load {wav_path}: {e}")
        logger.info(f"[AUDIO CUE] Pre-loaded {mem_count} WAV variants into memory")

    async def cache_cues(self, cues: Dict[str, str]) -> None:
        """
        Ensure cues are available for playback.

        Indexes pre-generated WAV files from disk. For any requested cue keys
        that don't have pre-generated files, falls back to runtime TTS.
        """
        self._load_from_disk()

        # Find cues that need runtime generation (no disk files)
        keys_to_generate = [
            k for k in cues
            if k in CUE_TEXT_MAP and k not in self._disk_cache and k not in self._fallback_cache
        ]

        if not keys_to_generate:
            logger.info(f"[AUDIO CUE] All {len(cues)} cues available (pre-generated)")
            return

        logger.info(
            f"[AUDIO CUE] {len(keys_to_generate)} cues missing from disk, "
            f"generating via TTS fallback..."
        )

        start = time.monotonic()
        tasks = [
            self._generate_single_cue(key, CUE_TEXT_MAP[key])
            for key in keys_to_generate
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        errors = 0
        for result in results:
            if isinstance(result, Exception):
                errors += 1
                logger.error(f"[AUDIO CUE] Fallback generation failed: {result}")
            else:
                key, audio_bytes = result
                self._fallback_cache[key] = audio_bytes

        elapsed = time.monotonic() - start
        logger.info(
            f"[AUDIO CUE] Fallback generated {len(keys_to_generate) - errors} cues "
            f"in {elapsed:.2f}s ({errors} errors)"
        )

    def has_cue(self, cue_key: str) -> bool:
        """Check whether audio is available for a cue key."""
        self._load_from_disk()
        return cue_key in self._memory_cache or cue_key in self._disk_cache or cue_key in self._fallback_cache

    async def play_cue(self, cue_key: str) -> None:
        """Play a cue through LiveKit's session.say()."""
        self._load_from_disk()

        # Prefer in-memory pre-loaded frames (zero disk I/O)
        mem_variants = self._memory_cache.get(cue_key)
        if mem_variants:
            frames = random.choice(mem_variants)
            handle = self._session.say(
                "",
                audio=self._frames_to_async_gen(frames),
                allow_interruptions=False,
                add_to_chat_ctx=False,
            )
            await handle.join()
            return

        # Fall back to disk-based WAV variants (if memory pre-load failed)
        disk_variants = self._disk_cache.get(cue_key)
        if disk_variants:
            wav_path = random.choice(disk_variants)
            audio_source = audio_frames_from_file(
                str(wav_path), sample_rate=SAMPLE_RATE, num_channels=NUM_CHANNELS,
            )
            handle = self._session.say(
                "",
                audio=audio_source,
                allow_interruptions=False,
                add_to_chat_ctx=False,
            )
            await handle.join()
            return

        # Fall back to runtime-generated PCM cache
        pcm_bytes = self._fallback_cache.get(cue_key)
        if pcm_bytes:
            audio_source = self._pcm_to_audio_frames(pcm_bytes)
            handle = self._session.say(
                "",
                audio=audio_source,
                allow_interruptions=False,
                add_to_chat_ctx=False,
            )
            await handle.join()
            return

        logger.warning(f"[AUDIO CUE] No audio available for cue: {cue_key}")

    @staticmethod
    async def _frames_to_async_gen(
        frames: List[rtc.AudioFrame],
    ) -> AsyncGenerator[rtc.AudioFrame, None]:
        """Yield pre-loaded AudioFrame chunks as an async generator."""
        for frame in frames:
            yield frame

    def is_cache_valid(self) -> bool:
        """Check whether any cue audio is available."""
        self._load_from_disk()
        return bool(self._disk_cache) or bool(self._fallback_cache)

    @staticmethod
    def get_cue_text(cue_key: str) -> Optional[str]:
        """Return the spoken text for a cue key (used by fallback)."""
        return CUE_TEXT_MAP.get(cue_key)

    async def _generate_single_cue(self, key: str, text: str) -> Tuple[str, bytes]:
        """Generate TTS audio for a single cue (fallback path)."""
        client = self._get_client()
        response = await client.audio.speech.create(
            model=TTS_MODEL,
            voice=TTS_VOICE,
            input=text,
            instructions=TTS_INSTRUCTIONS,
            response_format=TTS_FORMAT,
            speed=TTS_SPEED,
        )
        audio_bytes = response.read()
        return key, audio_bytes

    @staticmethod
    async def _pcm_to_audio_frames(
        pcm_bytes: bytes,
    ) -> AsyncGenerator[rtc.AudioFrame, None]:
        """Convert raw PCM bytes (24kHz, 16-bit mono) into AudioFrame chunks."""
        bytes_per_sample = 2  # int16
        chunk_bytes = SAMPLES_PER_CHUNK * NUM_CHANNELS * bytes_per_sample
        for offset in range(0, len(pcm_bytes), chunk_bytes):
            chunk = pcm_bytes[offset:offset + chunk_bytes]
            samples = len(chunk) // (NUM_CHANNELS * bytes_per_sample)
            yield rtc.AudioFrame(
                data=chunk,
                sample_rate=SAMPLE_RATE,
                num_channels=NUM_CHANNELS,
                samples_per_channel=samples,
            )
