"""
Audio Cue Service — Pre-generates and caches TTS audio for real-time coaching.

Uses OpenAI's TTS API to generate PCM audio for each coaching cue key.
Audio is stored in memory with a 30-minute TTL and regenerated on the next set.
"""

import asyncio
import logging
import time
from typing import Dict, Optional, Tuple

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# TTL for cached audio (30 minutes)
CACHE_TTL_SECONDS = 30 * 60

# TTS configuration
TTS_MODEL = "gpt-4o-mini-tts"
TTS_VOICE = "marin"
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


class AudioCueService:
    """
    Manages pre-cached TTS audio for low-latency coaching cue playback.

    Call ``cache_cues()`` at the start of each set/exercise to pre-generate
    TTS audio. Then ``get_cue_audio()`` returns cached PCM bytes instantly.
    """

    def __init__(self) -> None:
        self.cache: Dict[str, bytes] = {}
        self.cache_expiry: float = 0.0
        self._client: Optional[AsyncOpenAI] = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI()
        return self._client

    async def cache_cues(self, cues: Dict[str, str]) -> None:
        """
        Pre-generate TTS audio for all provided cue keys concurrently.

        Args:
            cues: Dict of cue_key → cue_identifier (from biomechanics CueCache).
                  Only keys present in CUE_TEXT_MAP will be generated.
        """
        start = time.monotonic()
        keys_to_generate = [k for k in cues if k in CUE_TEXT_MAP]

        if not keys_to_generate:
            logger.warning("[AUDIO CUE] No known cue keys to generate")
            return

        logger.info(f"[AUDIO CUE] Generating TTS for {len(keys_to_generate)} cues...")

        tasks = [
            self._generate_single_cue(key, CUE_TEXT_MAP[key])
            for key in keys_to_generate
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        new_cache: Dict[str, bytes] = {}
        errors = 0
        for result in results:
            if isinstance(result, Exception):
                errors += 1
                logger.error(f"[AUDIO CUE] Generation failed: {result}")
            else:
                key, audio_bytes = result
                new_cache[key] = audio_bytes

        self.cache = new_cache
        self.cache_expiry = time.monotonic() + CACHE_TTL_SECONDS

        elapsed = time.monotonic() - start
        logger.info(
            f"[AUDIO CUE] Cached {len(new_cache)} cues in {elapsed:.2f}s "
            f"({errors} errors)"
        )

    def get_cue_audio(self, cue_key: str) -> Optional[bytes]:
        """Return cached PCM audio bytes for a cue key, or None on miss/expiry."""
        if not self.is_cache_valid():
            return None
        return self.cache.get(cue_key)

    def is_cache_valid(self) -> bool:
        """Check whether the cache is populated and has not expired."""
        return bool(self.cache) and time.monotonic() < self.cache_expiry

    @staticmethod
    def get_cue_text(cue_key: str) -> Optional[str]:
        """Return the spoken text for a cue key (used by Option C fallback)."""
        return CUE_TEXT_MAP.get(cue_key)

    async def _generate_single_cue(self, key: str, text: str) -> Tuple[str, bytes]:
        """Generate TTS audio for a single cue."""
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
