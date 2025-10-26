#!/usr/bin/env python3
"""
Test GPT-5-mini prompt caching behavior
"""
import asyncio
from openai import AsyncOpenAI
import os
from datetime import datetime

async def test_caching():
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = "gpt-5-mini"

    # System prompt > 1024 tokens (required for caching)
    system_prompt = """You are a fitness expert. """ + ("x" * 1100)  # Pad to > 1024 tokens

    print("="*80)
    print("Testing GPT-5-mini Prompt Caching")
    print("="*80)

    results = []

    for i in range(3):
        print(f"\n--- Request {i+1}/3 ---")
        start = datetime.now()

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Say 'Test {i+1}' and nothing else"}
            ],
            max_completion_tokens=10
        )

        elapsed = (datetime.now() - start).total_seconds()
        usage = response.usage

        # Extract cache info
        cached_tokens = 0
        if hasattr(usage, 'prompt_tokens_details'):
            if hasattr(usage.prompt_tokens_details, 'cached_tokens'):
                cached_tokens = usage.prompt_tokens_details.cached_tokens

        result = {
            "request": i+1,
            "prompt_tokens": usage.prompt_tokens,
            "cached_tokens": cached_tokens,
            "completion_tokens": usage.completion_tokens,
            "elapsed_seconds": elapsed,
            "cache_percentage": (cached_tokens / usage.prompt_tokens * 100) if usage.prompt_tokens > 0 else 0
        }

        results.append(result)

        print(f"  Prompt tokens: {usage.prompt_tokens}")
        print(f"  Cached tokens: {cached_tokens} ({result['cache_percentage']:.1f}%)")
        print(f"  Output tokens: {usage.completion_tokens}")
        print(f"  Time: {elapsed:.2f}s")

        # Wait 1 second between requests
        if i < 2:
            await asyncio.sleep(1)

    # Analysis
    print("\n" + "="*80)
    print("CACHE ANALYSIS:")
    print("="*80)

    if results[1]['cached_tokens'] > 0 or results[2]['cached_tokens'] > 0:
        print("✅ CACHING IS WORKING!")
        print(f"   Request 1: {results[0]['cached_tokens']} cached (baseline)")
        print(f"   Request 2: {results[1]['cached_tokens']} cached ({results[1]['cache_percentage']:.1f}%)")
        print(f"   Request 3: {results[2]['cached_tokens']} cached ({results[2]['cache_percentage']:.1f}%)")

        if results[2]['cached_tokens'] == results[1]['prompt_tokens']:
            print("\n🎉 Perfect caching! All prompt tokens cached on repeat requests.")
        else:
            print(f"\n⚠️  Partial caching. Expected ~{results[0]['prompt_tokens']} cached, got {results[2]['cached_tokens']}")
    else:
        print("❌ CACHING IS NOT WORKING!")
        print("   All requests showed 0 cached tokens.")
        print("   This is a known issue with GPT-5-mini.")
        print("\n   Recommendations:")
        print("   1. Try gpt-4o (better caching support)")
        print("   2. Wait for OpenAI to fix GPT-5 caching")
        print("   3. Accept the current performance")

    # Time savings calculation
    if results[1]['cached_tokens'] > 0:
        time_saved = results[0]['elapsed_seconds'] - results[2]['elapsed_seconds']
        print(f"\n⏱️  Time saved per request with cache: {time_saved:.2f}s ({time_saved/results[0]['elapsed_seconds']*100:.1f}%)")

    print("\n" + "="*80)

if __name__ == "__main__":
    asyncio.run(test_caching())
