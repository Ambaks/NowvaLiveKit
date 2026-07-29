"""
Generate pre-cached coaching cue audio with Cartesia (sonic-3).

Uses the same voice the live agent speaks with, so a cached cue is
indistinguishable from something Nova says in the moment. Each cue gets
several hand-written phrasings; AudioCueService picks one at random per
playback, which is what keeps repeated cues from sounding robotic.

Output is 24kHz mono 16-bit PCM WAV — AudioCueService reads the cue files
with that format hardcoded, so anything else plays as noise.

Usage:
    python scripts/tools/generate_cartesia_cues.py              # missing only
    python scripts/tools/generate_cartesia_cues.py --force      # regenerate
    python scripts/tools/generate_cartesia_cues.py --cue stance_wider
    python scripts/tools/generate_cartesia_cues.py --list
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import wave
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
load_dotenv(Path(__file__).parent.parent.parent / ".env")

CUES_WAV_DIR = Path(__file__).parent.parent.parent / "src" / "assets" / "cues" / "wav"

CARTESIA_URL = "https://api.cartesia.ai/tts/bytes"
API_VERSION = "2025-04-16"
MODEL = "sonic-3"
DEFAULT_VOICE_ID = "3e39e9a5-585c-4f5f-bac6-5e4905c51095"

# Must match agent.services.audio_cue_service
SAMPLE_RATE = 24000
NUM_CHANNELS = 1
SAMPLE_WIDTH = 2

# Slight speed variation on top of the wording, so two variants of the same
# idea do not land identically. sonic-3 accepts 0.6-2.0.
VARIANT_SPEEDS = [1.05, 1.0, 1.1]

# cue_key -> phrasings. One WAV per phrasing, chosen at random at playback.
# Keep them short: these fire between reps while the lifter is under load.
CUE_VARIANTS: dict[str, list[str]] = {
    # Spoken once, when the stance monitor arms — carries the why and the fix.
    "stance_explain": [
        "That lean's coming from your stance. Step your feet out wider.",
        "Your stance is too narrow — that's what's tipping you forward. Widen it up.",
        "Feet are a little close together. Widen your stance and that lean goes away.",
    ],
    "stance_wider": [
        "A little wider.",
        "Bit more width.",
        "Keep going wider.",
    ],
    "stance_narrower": [
        "Bring it in a touch.",
        "Little narrower.",
        "Back in slightly.",
    ],
    # Same idea for foot angle.
    "toe_out_explain": [
        "That lean's coming from your feet. Turn your toes out more.",
        "Your toes are too straight — point them out a bit and you'll sit up taller.",
        "Open your feet up. More toe-out will fix that forward lean.",
    ],
    "toe_out_more": [
        "More toe-out.",
        "Turn them out a bit.",
        "Open those feet up.",
    ],
    "toe_out_less": [
        "Ease them back in.",
        "Little less turn-out.",
        "Bring the toes in slightly.",
    ],
    # Shared confirmation once the target is hit.
    "adjust_good": [
        "Right there — hold that.",
        "Perfect, lock that in.",
        "That's the spot.",
    ],
}


def _write_wav(path: Path, pcm_bytes: bytes) -> float:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(NUM_CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_bytes)
    return len(pcm_bytes) / (SAMPLE_RATE * NUM_CHANNELS * SAMPLE_WIDTH)


async def _synthesize(
    session: aiohttp.ClientSession, api_key: str, voice_id: str,
    text: str, speed: float,
) -> bytes:
    payload = {
        "model_id": MODEL,
        "transcript": text,
        "voice": {"mode": "id", "id": voice_id},
        "output_format": {
            "container": "raw",
            "encoding": "pcm_s16le",
            "sample_rate": SAMPLE_RATE,
        },
        "language": "en",
        "generation_config": {"speed": speed},
    }
    async with session.post(
        CARTESIA_URL,
        headers={"X-API-Key": api_key, "Cartesia-Version": API_VERSION},
        json=payload,
        timeout=aiohttp.ClientTimeout(total=60),
    ) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}: {(await resp.text())[:300]}")
        return await resp.read()


async def generate(cue_keys: list[str], force: bool) -> int:
    api_key = os.getenv("CARTESIA_API_KEY")
    if not api_key:
        print("CARTESIA_API_KEY is not set — add it to .env")
        return 1
    voice_id = os.getenv("CARTESIA_VOICE_ID", DEFAULT_VOICE_ID)

    CUES_WAV_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Voice {voice_id} · model {MODEL} · {SAMPLE_RATE}Hz mono")
    print(f"Writing to {CUES_WAV_DIR}\n")

    written = skipped = failed = 0
    async with aiohttp.ClientSession() as session:
        for cue_key in cue_keys:
            for index, text in enumerate(CUE_VARIANTS[cue_key]):
                path = CUES_WAV_DIR / f"{cue_key}_{index}.wav"
                if path.exists() and not force:
                    skipped += 1
                    continue
                speed = VARIANT_SPEEDS[index % len(VARIANT_SPEEDS)]
                try:
                    pcm = await _synthesize(session, api_key, voice_id, text, speed)
                    duration = _write_wav(path, pcm)
                    print(f"  {path.name:26} {duration:4.2f}s  \"{text}\"")
                    written += 1
                except Exception as e:
                    print(f"  {path.name:26} FAILED — {e}")
                    failed += 1

    print(f"\n{written} written, {skipped} already present, {failed} failed")
    if written:
        print("Restart the agent to pick them up.")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="regenerate cues that already exist")
    parser.add_argument("--cue", action="append", dest="cues",
                        help="generate only this cue key (repeatable)")
    parser.add_argument("--list", action="store_true",
                        help="show what would be generated and exit")
    args = parser.parse_args()

    cue_keys = args.cues or list(CUE_VARIANTS)
    unknown = [k for k in cue_keys if k not in CUE_VARIANTS]
    if unknown:
        print(f"Unknown cue key(s): {', '.join(unknown)}")
        print(f"Known: {', '.join(CUE_VARIANTS)}")
        return 1

    if args.list:
        for cue_key in cue_keys:
            print(f"\n{cue_key}")
            for index, text in enumerate(CUE_VARIANTS[cue_key]):
                path = CUES_WAV_DIR / f"{cue_key}_{index}.wav"
                print(f"  [{'x' if path.exists() else ' '}] {path.name:26} \"{text}\"")
        return 0

    return asyncio.run(generate(cue_keys, args.force))


if __name__ == "__main__":
    sys.exit(main())
