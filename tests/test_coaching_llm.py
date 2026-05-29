"""
Standalone LLM coaching prompt test — feed segmented set data to the OpenAI
API and evaluate reply quality, generation time, and latency.

Usage:
    # Test set recap with a plot_data.json (auto-segments + generates report)
    python test_coaching_llm.py output/set_*/set1_plot_data.json

    # Test with an existing report MD
    python test_coaching_llm.py output/set_*/set1_report.md

    # Test exercise recap prompt
    python test_coaching_llm.py output/set_*/set1_plot_data.json --prompt exercise_recap

    # Use a different model
    python test_coaching_llm.py output/set_*/set1_plot_data.json --model gpt-4o

    # Custom instruction override
    python test_coaching_llm.py output/set_*/set1_report.md --instructions "Roast the athlete"

    # Speak the response aloud (matches production TTS)
    python test_coaching_llm.py output/set_*/set1_report.md --speak
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

import numpy as np
import openai
import sounddevice as sd

from biomechanics.analysis import segment_set, write_set_report

# ---------------------------------------------------------------------------
# TTS config (matches production audio_cue_service.py)
# ---------------------------------------------------------------------------
TTS_MODEL = "gpt-4o-mini-tts"
TTS_VOICE = os.getenv("REALTIME_VOICE", "marin")
TTS_SPEED = 1.1
TTS_INSTRUCTIONS = (
    "You are an energetic gym coach giving real-time cues during a workout. "
    "Speak with high energy, urgency, and motivation — like you're right next "
    "to the lifter on the gym floor. Short, punchy, and commanding."
)

# ---------------------------------------------------------------------------
# System prompt (same as production coaching_service.py)
# ---------------------------------------------------------------------------
COACHING_SYSTEM_PROMPT = """You are Nova, an energetic, world-class fitness coach on the Nowva smart squat rack.

Voice & Delivery:
- HIGH energy, motivating, supportive
- SHORT responses only — follow the word limits given
- Sound like a real coach in the gym
— keep it human"""

# ---------------------------------------------------------------------------
# Prompt templates (mirroring coaching_orchestrator.py patterns)
# ---------------------------------------------------------------------------
PROMPT_TEMPLATES = {
    "set_recap": (
        "Your athlete just finished a set. Below is their detailed set analysis.\n\n"
        "{report}\n\n"
        "Give honest feedback (2-4 sentences). "
        "Highlight what went well. If there are inconsistencies or weak reps, "
        "give ONE specific coaching tip for the next set based on the data. "
        "Be encouraging — reference a few numbers"
    ),
    "exercise_recap": (
        "Your athlete just finished their entire exercise. Below is their detailed set analysis.\n\n"
        "{report}\n\n"
        "Give honest, encouraging feedback (3-5 sentences). "
        "Highlight overall performance, progression across reps, and one key takeaway. "
        "End on a high note — they just finished!"
    ),
    "detailed_coaching": (
        "Your athlete just finished a set. Below is their detailed set analysis.\n\n"
        "{report}\n\n"
        "Provide a detailed coaching breakdown:\n"
        "1. Overall assessment (1 sentence)\n"
        "2. What went well (reference specific reps and numbers)\n"
        "3. What to improve (reference specific reps and numbers)\n"
        "4. One cue for the next set (5 words max)\n"
        "Keep it under 6 sentences total."
    ),
}


# ---------------------------------------------------------------------------
# Core test function
# ---------------------------------------------------------------------------
def run_llm_test(
    report_md: str,
    *,
    model: str,
    prompt_type: str = "set_recap",
    custom_instructions: str | None = None,
    temperature: float = 0.8,
    runs: int = 1,
) -> list[dict]:
    """Send the report to the LLM and collect responses with timing.

    Returns list of result dicts, one per run.
    """
    client = openai.OpenAI()

    if custom_instructions:
        user_content = f"{custom_instructions}\n\n{report_md}"
    else:
        template = PROMPT_TEMPLATES.get(prompt_type, PROMPT_TEMPLATES["set_recap"])
        user_content = template.format(report=report_md)

    messages = [
        {"role": "system", "content": COACHING_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    results = []
    for i in range(runs):
        t_start = time.perf_counter()

        # --- Streaming call to measure time-to-first-token ---
        kwargs = dict(model=model, messages=messages, stream=True)
        if temperature is not None:
            kwargs["temperature"] = temperature
        try:
            stream = client.chat.completions.create(**kwargs)
        except openai.BadRequestError as e:
            if "temperature" in str(e):
                # Model doesn't support custom temperature — retry with default
                kwargs.pop("temperature", None)
                stream = client.chat.completions.create(**kwargs)
            else:
                raise

        first_token_time = None
        chunks = []
        for chunk in stream:
            if first_token_time is None:
                first_token_time = time.perf_counter()
            delta = chunk.choices[0].delta
            if delta.content:
                chunks.append(delta.content)

        t_end = time.perf_counter()

        reply = "".join(chunks)
        ttft = (first_token_time - t_start) if first_token_time else 0.0
        total = t_end - t_start

        result = {
            "run": i + 1,
            "model": model,
            "prompt_type": prompt_type,
            "ttft_ms": round(ttft * 1000, 1),
            "total_ms": round(total * 1000, 1),
            "reply_chars": len(reply),
            "reply_words": len(reply.split()),
            "reply": reply,
        }
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# TTS playback
# ---------------------------------------------------------------------------
def speak_reply(text: str, *, voice: str = TTS_VOICE, speed: float = TTS_SPEED) -> dict:
    """Generate TTS audio from the reply and play it through speakers.

    Returns timing dict with tts_ms (API time) and playback_ms.
    """
    client = openai.OpenAI()

    print("  Generating TTS...")
    t_tts_start = time.perf_counter()

    response = client.audio.speech.create(
        model=TTS_MODEL,
        voice=voice,
        input=text,
        speed=speed,
        response_format="pcm",
        instructions=TTS_INSTRUCTIONS,
    )
    pcm_bytes = response.read()
    t_tts_end = time.perf_counter()

    tts_ms = (t_tts_end - t_tts_start) * 1000
    print(f"  TTS generated: {tts_ms:.0f} ms ({len(pcm_bytes) / 1024:.1f} KB)")

    # Play: 24kHz, 16-bit signed mono (matches production)
    audio = np.frombuffer(pcm_bytes, dtype=np.int16)
    duration_s = len(audio) / 24000

    print(f"  Playing ({duration_s:.1f}s)...")
    t_play_start = time.perf_counter()
    sd.play(audio, samplerate=24000, blocksize=2400)
    sd.wait()
    t_play_end = time.perf_counter()

    playback_ms = (t_play_end - t_play_start) * 1000

    return {
        "tts_ms": round(tts_ms, 1),
        "playback_ms": round(playback_ms, 1),
        "audio_duration_s": round(duration_s, 2),
        "audio_size_kb": round(len(pcm_bytes) / 1024, 1),
    }


# ---------------------------------------------------------------------------
# Input handling
# ---------------------------------------------------------------------------
def load_report(input_path: Path, set_number: int = 1) -> str:
    """Load or generate the MD report from the input path."""
    if input_path.suffix == ".md":
        return input_path.read_text()
    elif input_path.suffix == ".json":
        result = segment_set(str(input_path))
        return write_set_report(result, set_number=set_number)
    else:
        raise ValueError(f"Unsupported file type: {input_path.suffix} (expected .json or .md)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Test LLM coaching prompts with segmented set data",
    )
    parser.add_argument("input", type=Path, help="Path to set*_plot_data.json or set*_report.md")
    parser.add_argument("--model", default=os.getenv("LAYER_1_2_4_MODEL", "gpt-4o-mini"),
                        help="OpenAI model to use (default: from LAYER_1_2_4_MODEL env or gpt-4o-mini)")
    parser.add_argument("--prompt", choices=list(PROMPT_TEMPLATES.keys()), default="set_recap",
                        help="Prompt template to use")
    parser.add_argument("--instructions", type=str, default=None,
                        help="Custom instructions (overrides --prompt template)")
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--runs", type=int, default=1, help="Number of runs for latency averaging")
    parser.add_argument("--set-number", type=int, default=1)
    parser.add_argument("--save", type=Path, default=None, help="Save results JSON to this path")
    parser.add_argument("--show-prompt", action="store_true", help="Print the full prompt sent to the LLM")
    parser.add_argument("--speak", action="store_true", help="Speak the reply aloud via TTS (matches production voice)")
    parser.add_argument("--voice", default=TTS_VOICE, help=f"TTS voice (default: {TTS_VOICE})")
    parser.add_argument("--speed", type=float, default=TTS_SPEED, help=f"TTS speed (default: {TTS_SPEED})")
    args = parser.parse_args()

    report_md = load_report(args.input, set_number=args.set_number)

    print(f"{'=' * 60}")
    print(f"  LLM Coaching Test")
    print(f"  Model: {args.model}")
    print(f"  Prompt: {args.prompt}")
    print(f"  Temperature: {args.temperature}")
    print(f"  Runs: {args.runs}")
    print(f"  Input: {args.input}")
    print(f"{'=' * 60}\n")

    if args.show_prompt:
        if args.instructions:
            prompt = f"{args.instructions}\n\n{report_md}"
        else:
            prompt = PROMPT_TEMPLATES[args.prompt].format(report=report_md)
        print(f"--- SYSTEM PROMPT ---\n{COACHING_SYSTEM_PROMPT}\n")
        print(f"--- USER PROMPT ---\n{prompt}\n")
        print(f"{'=' * 60}\n")

    results = run_llm_test(
        report_md,
        model=args.model,
        prompt_type=args.prompt,
        custom_instructions=args.instructions,
        temperature=args.temperature,
        runs=args.runs,
    )

    for r in results:
        print(f"--- Run {r['run']} ---")
        print(f"  TTFT:  {r['ttft_ms']} ms")
        print(f"  Total: {r['total_ms']} ms")
        print(f"  Words: {r['reply_words']}")
        print()
        print(f"  {r['reply']}")
        print()

        if args.speak:
            tts_info = speak_reply(r["reply"], voice=args.voice, speed=args.speed)
            r["tts_ms"] = tts_info["tts_ms"]
            r["playback_ms"] = tts_info["playback_ms"]
            r["audio_duration_s"] = tts_info["audio_duration_s"]
            print(f"  TTS: {tts_info['tts_ms']:.0f} ms | Audio: {tts_info['audio_duration_s']}s")
            print()

    if args.runs > 1:
        avg_ttft = sum(r["ttft_ms"] for r in results) / len(results)
        avg_total = sum(r["total_ms"] for r in results) / len(results)
        avg_words = sum(r["reply_words"] for r in results) / len(results)
        print(f"--- Averages ({args.runs} runs) ---")
        print(f"  Avg TTFT:  {avg_ttft:.1f} ms")
        print(f"  Avg Total: {avg_total:.1f} ms")
        print(f"  Avg Words: {avg_words:.0f}")
        print()

    if args.save:
        output = {
            "model": args.model,
            "prompt_type": args.prompt,
            "temperature": args.temperature,
            "input_file": str(args.input),
            "results": results,
        }
        args.save.parent.mkdir(parents=True, exist_ok=True)
        with open(args.save, "w") as f:
            json.dump(output, f, indent=2)
        print(f"Saved: {args.save}")


if __name__ == "__main__":
    main()
