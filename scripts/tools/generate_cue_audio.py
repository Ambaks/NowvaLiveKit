"""
Generate pre-cached coaching cue audio using the OpenAI Realtime API.

Each cue has a detailed scenario prompt that describes the coaching situation,
letting the model naturally produce short, varied cues. 10 variants per cue
give natural variety during workouts.

After generation, builds an HTML review page (src/assets/cues/review.html)
where you can see every prompt sent and listen to each resulting variant.

Usage:
    python scripts/generate_cue_audio.py
    python scripts/generate_cue_audio.py --variants 5 --voice cedar
"""

import argparse
import asyncio
import base64
import json
import os
import struct
import sys
from collections import OrderedDict
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import websockets

REALTIME_WS_URL = "wss://api.openai.com/v1/realtime"

# ── System prompt for the Realtime API session ──────────────────────────
SYSTEM_PROMPT = (
    "You are a coach that is friendly and funny, and you are standing right next "
    "to your athlete on the gym floor. You are generating single coaching cues — "
    "1 to 3 words MAX, NEVER more than 3 words. Each cue must take less than 1.5 seconds to say. "
    "Only say ONE short cue — never chain multiple cues together. "
    "Be creative, nice, supportive, and encouraging. "
    "This is the situation that is currently happening. "
)

# ── Per-cue scenario prompts ───────────────────────────────────────────
# Each prompt describes the exact coaching scenario so the model naturally
# produces a varied but contextually correct cue.

CUE_PROMPTS = OrderedDict()

# ── Squat corrections ──
CUE_PROMPTS["knees_out"] = (
    "You are giving your athlete "
    "corrections during their set of squats. His knees are caving in during the "
    "ascent. "
)
CUE_PROMPTS["chest_up"] = (
    "You are giving your athlete "
    "corrections during their set of squats. His chest is dropping forward and "
    "his upper back is starting to round as he comes out of the hole."
)
CUE_PROMPTS["deeper"] = (
    "You are giving your athlete "
    "corrections during their set of squats. He's cutting his reps short and not "
    "hitting parallel — he needs to get lower. "
)
CUE_PROMPTS["heels_down"] = (
    "You are giving your athlete "
    "corrections during their set of squats. His heels are coming off the ground "
    "and he's shifting forward onto his toes. "
)
CUE_PROMPTS["even_it_out"] = (
    "You are giving your athlete "
    "corrections during their set of squats. He's shifting to one side — his "
    "squat is asymmetric and he's favoring his right leg."
)
CUE_PROMPTS["slow_down"] = (
    "You are giving your athlete "
    "corrections during their set of squats. He's dropping too fast into the hole "
    "and losing control of the eccentric."
)
CUE_PROMPTS["brace"] = (
    "You are giving your athlete "
    "corrections during their set of squats. His core is soft — he's not bracing "
    "properly and his midsection is collapsing under the load."
)

# ── Deadlift corrections ──
CUE_PROMPTS["hips_through"] = (
    "You are giving your athlete "
    "corrections during their set of deadlifts. He's finishing the pull but his "
    "hips are staying behind — he's not driving them through to full lockout. "
   
)
CUE_PROMPTS["flat_back"] = (
    "You are giving your athlete "
    "corrections during their set of deadlifts. His back is rounding during the "
    "pull — his spine is flexing and he's losing his neutral position."
)
CUE_PROMPTS["lockout"] = (
    "You are giving your athlete "
    "corrections during their set of deadlifts. He's getting the bar to the top "
    "but not fully locking out — his hips and knees aren't finishing."
)

# ── Positive reinforcement ──
CUE_PROMPTS["good_rep"] = (
    "Your athlete just "
    "completed a solid rep with good form. Give them a short (1-3 words MAX) "
    "positive reinforcement — let them know that was a good one."
)
CUE_PROMPTS["great_depth"] = (
    "Your athlete just "
    "hit excellent depth on their squat — well below parallel with great control. "
    "Give them a short (1-3 words MAX) positive cue acknowledging that depth."
)
CUE_PROMPTS["strong"] = (
    "Your athlete just "
    "powered through a heavy rep that looked really strong and explosive. Give "
    "them a short (1-3 words MAX) hype cue — pump them up."
)
CUE_PROMPTS["clean"] = (
    "Your athlete just "
    "executed a rep with textbook technique — everything was dialed in. Give "
    "them a short (1-3 words MAX) positive cue about how clean that rep was."
)
CUE_PROMPTS["perfect"] = (
    "Your athlete just "
    "performed a flawless rep — perfect depth, perfect form, great bar speed. "
    "Give them a short (1-3 words MAX) enthusiastic cue to celebrate that rep."
)

# ── Rep counts ──
_NUM_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
    11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
    16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen", 20: "twenty",
}
for i in range(1, 21):
    _word = _NUM_WORDS[i]
    CUE_PROMPTS[f"rep_{i}"] = (
        f"Say the word '{_word}' out loud with energy and authority, "
        f"like a coach counting rep {i} of a set. Just say '{_word}' — "
        f"nothing else, no other numbers, just the single word '{_word}'."
    )

# Category groupings for the review page
CUE_CATEGORIES = OrderedDict([
    ("Squat Corrections", ["knees_out", "chest_up", "deeper", "heels_down", "even_it_out", "slow_down", "brace"]),
    ("Deadlift Corrections", ["hips_through", "flat_back", "lockout"]),
    ("Positive Reinforcement", ["good_rep", "great_depth", "strong", "clean", "perfect"]),
    ("Rep Counts", [f"rep_{i}" for i in range(1, 21)]),
])


# ── Generation ──────────────────────────────────────────────────────────

async def generate_all_cues(voice: str, model: str, variants: int, output_dir: Path):
    """Connect to Realtime API and generate all cue variants."""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    total = len(CUE_PROMPTS) * variants
    generated = 0
    skipped = 0

    print(f"Generating {total} cue audio files ({len(CUE_PROMPTS)} cues x {variants} variants)")
    print(f"Voice: {voice} | Model: {model}")
    print(f"Output: {output_dir}\n")

    url = f"{REALTIME_WS_URL}?model={model}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1",
    }

    async with websockets.connect(url, additional_headers=headers) as ws:
        # Wait for session.created
        msg = json.loads(await ws.recv())
        assert msg["type"] == "session.created", f"Expected session.created, got {msg['type']}"
        print("Connected to Realtime API\n")

        # Configure session
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "voice": voice,
                "modalities": ["audio", "text"],
                "instructions": SYSTEM_PROMPT,
                "turn_detection": None,
            }
        }))

        # Wait for session.updated
        while True:
            msg = json.loads(await ws.recv())
            if msg["type"] == "session.updated":
                break

        for cue_key, prompt in CUE_PROMPTS.items():
            for variant in range(variants):
                filepath = output_dir / f"{cue_key}_{variant}.pcm"

                # Skip if already generated (allows resuming interrupted runs)
                if filepath.exists() and filepath.stat().st_size > 0:
                    skipped += 1
                    generated += 1
                    continue

                # Send the scenario prompt as a user message
                item_id = f"item_{cue_key}_{variant}"
                await ws.send(json.dumps({
                    "type": "conversation.item.create",
                    "item": {
                        "id": item_id,
                        "type": "message",
                        "role": "user",
                        "content": [{
                            "type": "input_text",
                            "text": prompt,
                        }]
                    }
                }))

                # Request response
                await ws.send(json.dumps({
                    "type": "response.create",
                    "response": {
                        "modalities": ["audio", "text"],
                    }
                }))

                # Collect audio deltas until response.done
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
                        print(f"  ERROR on {cue_key} v{variant}: {msg.get('error', msg)}")
                        break

                # Save audio bytes
                if audio_chunks:
                    audio_bytes = b"".join(audio_chunks)
                    filepath.write_bytes(audio_bytes)
                    generated += 1
                    transcript_str = f' "{response_text.strip()}"' if response_text.strip() else ""
                    print(f"  [{generated}/{total}] {cue_key} v{variant} —{transcript_str} ({len(audio_bytes):,} bytes)")
                else:
                    generated += 1
                    print(f"  [{generated}/{total}] {cue_key} v{variant} — FAILED (no audio)")

                # Delete conversation items to prevent context buildup
                for del_id in [item_id, response_item_id]:
                    if del_id:
                        await ws.send(json.dumps({
                            "type": "conversation.item.delete",
                            "item_id": del_id,
                        }))

                await asyncio.sleep(0.05)

    if skipped:
        print(f"\nSkipped {skipped} existing files (delete to regenerate)")
    print(f"Done! {generated} cue files in {output_dir}")


# ── Review page ─────────────────────────────────────────────────────────

def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2) -> bytes:
    """Convert raw PCM bytes to a WAV file in memory."""
    data_size = len(pcm_bytes)
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + data_size,
        b'WAVE',
        b'fmt ',
        16,
        1,  # PCM format
        channels,
        sample_rate,
        sample_rate * channels * sample_width,
        channels * sample_width,
        sample_width * 8,
        b'data',
        data_size,
    )
    return header + pcm_bytes


def build_review_page(output_dir: Path, variants: int, voice: str, model: str):
    """Build an HTML page to review all generated cues with playback."""

    print("\nBuilding review page...")

    # Convert PCM files to WAV for browser playback
    wav_dir = output_dir / "wav"
    wav_dir.mkdir(exist_ok=True)

    for pcm_file in output_dir.glob("*.pcm"):
        wav_file = wav_dir / f"{pcm_file.stem}.wav"
        if not wav_file.exists() or wav_file.stat().st_mtime < pcm_file.stat().st_mtime:
            pcm_bytes = pcm_file.read_bytes()
            wav_file.write_bytes(pcm_to_wav(pcm_bytes))

    # Build cue rows grouped by category
    cue_rows = ""
    for category, keys in CUE_CATEGORIES.items():
        cue_rows += f'<tr class="category-header"><td colspan="{variants + 2}">{category}</td></tr>\n'
        for key in keys:
            prompt = CUE_PROMPTS.get(key, "?")
            # Escape HTML in prompt
            prompt_escaped = prompt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            players = ""
            for v in range(variants):
                wav_path = f"wav/{key}_{v}.wav"
                wav_full = wav_dir / f"{key}_{v}.wav"
                if wav_full.exists():
                    players += f'<td><button onclick="playAudio(\'{wav_path}\', this)">&#9654; v{v}</button></td>'
                else:
                    players += '<td class="missing">—</td>'
            cue_rows += (
                f'<tr>'
                f'<td class="cue-key">{key}</td>'
                f'<td class="prompt">{prompt_escaped}</td>'
                f'{players}'
                f'</tr>\n'
            )

    variant_headers = "".join(f"<th>v{v}</th>" for v in range(variants))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Cue Audio Review — {voice}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 2rem; background: #0a0a0a; color: #e0e0e0; }}
  h1 {{ color: #fff; margin-bottom: 0.5rem; }}
  .meta {{ color: #888; margin-bottom: 1.5rem; font-size: 0.9rem; }}
  .meta span {{ color: #aaa; }}
  .system-prompt {{ background: #1a1a2e; border: 1px solid #333; border-radius: 8px; padding: 1rem; margin-bottom: 2rem; font-size: 0.85rem; white-space: pre-wrap; color: #ccc; }}
  .system-prompt h3 {{ margin-top: 0; color: #7c8aff; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid #1a1a1a; vertical-align: top; }}
  th {{ background: #111; color: #999; font-size: 0.8rem; position: sticky; top: 0; z-index: 1; }}
  .category-header td {{ background: #1a1a2e; color: #7c8aff; font-weight: 600; padding: 12px 10px; font-size: 0.95rem; }}
  .cue-key {{ font-weight: 600; color: #fff; white-space: nowrap; width: 120px; }}
  .prompt {{ color: #999; font-size: 0.8rem; line-height: 1.4; max-width: 500px; }}
  .missing {{ color: #555; }}
  button {{ background: #1e3a2f; color: #4ade80; border: 1px solid #2d5a3f; border-radius: 4px; padding: 4px 10px; cursor: pointer; font-size: 0.8rem; white-space: nowrap; }}
  button:hover {{ background: #2d5a3f; }}
  button.playing {{ background: #4ade80; color: #000; }}
</style>
</head>
<body>
<h1>Cue Audio Review</h1>
<div class="meta">
  Voice: <span>{voice}</span> &nbsp;|&nbsp; Model: <span>{model}</span> &nbsp;|&nbsp;
  Variants: <span>{variants}</span> &nbsp;|&nbsp; Cues: <span>{len(CUE_PROMPTS)}</span>
</div>
<div class="system-prompt">
  <h3>System Prompt (Realtime API Session)</h3>{SYSTEM_PROMPT}
</div>
<table>
<thead>
  <tr><th>Cue Key</th><th>Prompt Sent</th>{variant_headers}</tr>
</thead>
<tbody>
{cue_rows}
</tbody>
</table>
<script>
let currentAudio = null;
let currentBtn = null;
function playAudio(path, btn) {{
  if (currentAudio) {{ currentAudio.pause(); currentAudio = null; }}
  if (currentBtn) {{ currentBtn.classList.remove('playing'); currentBtn = null; }}
  const audio = new Audio(path);
  audio.onended = () => {{ btn.classList.remove('playing'); currentAudio = null; currentBtn = null; }};
  btn.classList.add('playing');
  currentBtn = btn;
  currentAudio = audio;
  audio.play();
}}
</script>
</body>
</html>"""

    review_path = output_dir / "review.html"
    review_path.write_text(html)
    print(f"Review page: {review_path}")
    print(f"Open in browser: file://{review_path.resolve()}")


# ── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate coaching cue audio via OpenAI Realtime API")
    parser.add_argument("--variants", type=int, default=10, help="Variants per cue (default: 10)")
    parser.add_argument("--voice", default=os.getenv("REALTIME_VOICE", "cedar"), help="Voice name (default: REALTIME_VOICE env or cedar)")
    parser.add_argument("--model", default=os.getenv("REALTIME_MODEL", "gpt-4o-realtime-preview"), help="Realtime model")
    args = parser.parse_args()

    output_dir = Path(__file__).parent.parent.parent / "src" / "assets" / "cues"

    asyncio.run(generate_all_cues(
        voice=args.voice,
        model=args.model,
        variants=args.variants,
        output_dir=output_dir,
    ))

    build_review_page(output_dir, args.variants, args.voice, args.model)


if __name__ == "__main__":
    main()
