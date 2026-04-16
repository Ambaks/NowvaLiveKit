"""Measure TTFT against xAI Grok directly, bypassing the LiveKit pipeline.

Runs N streamed calls back-to-back against the same prompt shape as the other
probe scripts. Prints TTFT, total duration, and tokens/sec per call so we can
compare provider-side streaming behavior directly.

Usage:
    python scripts/ttft_probe_grok.py
    python scripts/ttft_probe_grok.py --runs 10
    python scripts/ttft_probe_grok.py --model grok-4-1-fast-reasoning --long
"""

from __future__ import annotations

import argparse
import os
import time

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

SYSTEM_PROMPT = (
    "You are Nova, a friendly AI fitness coach. Keep replies to 2-3 sentences."
)
SHORT_PROMPT = (
    "Hey, welcome back! Greet the user warmly and ask what they want to "
    "achieve with their next training program."
)
LONG_PROMPT = (
    "Write a detailed 200-word explanation of progressive overload in "
    "strength training, covering the core principle, practical examples "
    "across different lifts, common mistakes beginners make, and how to "
    "track it in a training log."
)


def run_once(
    client: OpenAI,
    model: str,
    user_prompt: str,
) -> tuple[float, float, int, int, float, str]:
    start = time.monotonic()
    ttft: float | None = None
    output_tokens = 0
    text_parts: list[str] = []
    text_chunk_count = 0
    last_text_chunk_time: float | None = None

    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        stream=True,
        stream_options={"include_usage": True},
    )

    for chunk in stream:
        usage = getattr(chunk, "usage", None)
        if usage and getattr(usage, "completion_tokens", None) is not None:
            completion_tokens = usage.completion_tokens or 0
            details = getattr(usage, "completion_tokens_details", None)
            reasoning_tokens = getattr(details, "reasoning_tokens", 0) or 0
            # Keep this comparable to the other probes' visible text output count.
            output_tokens = max(completion_tokens - reasoning_tokens, 0)

        if not getattr(chunk, "choices", None):
            continue

        delta = chunk.choices[0].delta
        if getattr(delta, "content", None):
            now = time.monotonic()
            if ttft is None:
                ttft = now - start
            text_chunk_count += 1
            last_text_chunk_time = now
            text_parts.append(delta.content)

    duration = time.monotonic() - start
    # Gap between first and last text chunk - zero means an effectively single burst.
    text_span = (last_text_chunk_time - start - (ttft or 0)) if last_text_chunk_time else 0.0
    return ttft or duration, duration, output_tokens, text_chunk_count, text_span, "".join(text_parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--model", default="grok-4-1-fast-non-reasoning")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=300.0,
        help="HTTP timeout for each streamed request",
    )
    parser.add_argument(
        "--long",
        action="store_true",
        help="use the long-response prompt to force multi-chunk streaming",
    )
    parser.add_argument("--show-text", action="store_true")
    args = parser.parse_args()

    user_prompt = LONG_PROMPT if args.long else SHORT_PROMPT

    api_key = os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY")
    if not api_key:
        raise SystemExit("XAI_API_KEY (or GROK_API_KEY) not set in environment")

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.x.ai/v1",
        timeout=args.timeout_seconds,
    )

    print(
        f"model={args.model}  timeout={args.timeout_seconds:g}s  "
        f"runs={args.runs}  prompt={'long' if args.long else 'short'}"
    )
    print(f"{'call':>4}  {'ttft':>8}  {'duration':>10}  {'out_tok':>8}  {'tps':>8}  {'chunks':>7}  {'span':>8}")
    print("-" * 70)

    for i in range(1, args.runs + 1):
        try:
            ttft, duration, out_tok, chunks, span, text = run_once(
                client,
                args.model,
                user_prompt,
            )
        except Exception as e:
            print(f"{i:>4}  ERROR: {e}")
            continue

        tps = (out_tok / duration) if out_tok and duration else float("nan")
        print(
            f"{i:>4}  {ttft:>7.3f}s  {duration:>9.3f}s  {out_tok:>8}  {tps:>7.2f}  "
            f"{chunks:>7}  {span:>7.3f}s"
        )
        if args.show_text:
            print(f"      text: {text[:120]}...")


if __name__ == "__main__":
    main()
