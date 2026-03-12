"""
Generate 10 variants of rep_1 cue audio (count "one") using OpenAI Realtime API.
One-off script to fill the gap from the off-by-one issue in the original generation.
"""

import asyncio
import base64
import json
import os
import struct
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import websockets

REALTIME_WS_URL = "wss://api.openai.com/v1/realtime"

SYSTEM_PROMPT = (
    "You are that is friendly and funny, and you are standing right next "
    "to your athlete on the gym floor. You are generating single coaching cues — "
    "1 to 3 words MAX, NEVER more than 3 words. Each cue must take less than 1.5 seconds to say. "
    "Only say ONE short cue — never chain multiple cues together. "
    "Be creative, nice, supportive, and encouraging. "
    "This is the situation that is currently happening. "
)

CUE_PROMPT = (
    "Say the word 'one' out loud with energy and authority, "
    "like a coach counting the first rep of a set. Just say 'one' — "
    "nothing else, no other numbers, just the single word 'one'."
)

VARIANTS = 10


def pcm_to_wav(pcm_bytes, sample_rate=24000, channels=1, sample_width=2):
    data_size = len(pcm_bytes)
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + data_size, b'WAVE', b'fmt ', 16, 1,
        channels, sample_rate, sample_rate * channels * sample_width,
        channels * sample_width, sample_width * 8, b'data', data_size,
    )
    return header + pcm_bytes


async def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set")
        return

    voice = os.getenv("REALTIME_VOICE", "cedar")
    model = os.getenv("REALTIME_MODEL", "gpt-4o-realtime-preview")

    output_dir = Path(__file__).parent.parent / "src" / "assets" / "cues"
    wav_dir = output_dir / "wav"
    wav_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating {VARIANTS} variants of rep_1 cue")
    print(f"Voice: {voice} | Model: {model}\n")

    url = f"{REALTIME_WS_URL}?model={model}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1",
    }

    async with websockets.connect(url, additional_headers=headers) as ws:
        msg = json.loads(await ws.recv())
        assert msg["type"] == "session.created"
        print("Connected to Realtime API\n")

        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "voice": voice,
                "modalities": ["audio", "text"],
                "instructions": SYSTEM_PROMPT,
                "turn_detection": None,
            }
        }))

        while True:
            msg = json.loads(await ws.recv())
            if msg["type"] == "session.updated":
                break

        for variant in range(VARIANTS):
            filepath = output_dir / f"rep_1_{variant}.pcm"

            if filepath.exists() and filepath.stat().st_size > 0:
                print(f"  [{variant + 1}/{VARIANTS}] rep_1 v{variant} — already exists, skipping")
                continue

            item_id = f"item_rep_1_{variant}"
            await ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "id": item_id,
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": CUE_PROMPT}]
                }
            }))

            await ws.send(json.dumps({
                "type": "response.create",
                "response": {"modalities": ["audio", "text"]}
            }))

            audio_chunks = []
            response_text = ""
            response_item_id = None
            while True:
                msg = json.loads(await ws.recv())
                msg_type = msg["type"]
                if msg_type == "response.audio.delta":
                    audio_chunks.append(base64.b64decode(msg["delta"]))
                elif msg_type == "response.audio_transcript.delta":
                    response_text += msg.get("delta", "")
                elif msg_type == "response.output_item.added":
                    response_item_id = msg.get("item", {}).get("id")
                elif msg_type == "response.done":
                    break
                elif msg_type == "error":
                    print(f"  ERROR: {msg.get('error', msg)}")
                    break

            if audio_chunks:
                audio_bytes = b"".join(audio_chunks)
                filepath.write_bytes(audio_bytes)
                wav_path = wav_dir / f"rep_1_{variant}.wav"
                wav_path.write_bytes(pcm_to_wav(audio_bytes))
                transcript = f' "{response_text.strip()}"' if response_text.strip() else ""
                print(f"  [{variant + 1}/{VARIANTS}] rep_1 v{variant} —{transcript} ({len(audio_bytes):,} bytes)")
            else:
                print(f"  [{variant + 1}/{VARIANTS}] rep_1 v{variant} — FAILED (no audio)")

            for del_id in [item_id, response_item_id]:
                if del_id:
                    await ws.send(json.dumps({
                        "type": "conversation.item.delete",
                        "item_id": del_id,
                    }))

            await asyncio.sleep(0.05)

    print(f"\nDone! Check {output_dir}/rep_1_*.pcm")


if __name__ == "__main__":
    asyncio.run(main())
