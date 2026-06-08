"""Quick TTS test — run: python test_tts.py"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

import livekit.agents.utils.http_context as http_ctx
from livekit.plugins import elevenlabs


async def main():
    async with http_ctx.open():
        tts = elevenlabs.TTS(
            voice_id=os.getenv("ELEVENLABS_VOICE_ID"),
            model=os.getenv("ELEVENLABS_VOICE_MODEL"),
            encoding="pcm_24000",
        )
        stream = tts.synthesize("Hello, this is a test from Nova.")
        frame_count = 0
        async for ev in stream:
            frame_count += 1
            print(f"Frame {frame_count}: {ev}")
        print(f"\nDone — got {frame_count} audio frames")


if __name__ == "__main__":
    asyncio.run(main())
