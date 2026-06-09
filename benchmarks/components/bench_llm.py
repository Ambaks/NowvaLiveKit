"""Benchmark: LLM TTFT — Gemini flash-lite + OpenAI GPT-5.4-mini (requires --include-api)."""

from __future__ import annotations

import os
import time

from biomechanics.utils.timing import PipelineProfiler

from benchmarks.config import BenchmarkResult, LatencyStats, evaluate_status, stats_from_profiler
from benchmarks.profiler import ResourceProfiler

_PROMPT = "You are a personal trainer. Give a short one-sentence form cue for barbell back squats."
_USER_MSG = "My knees keep caving in on the way up."


def _bench_gemini(iterations: int, warmup: int) -> BenchmarkResult:
    name = "agent.llm.gemini_flash_lite"
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return BenchmarkResult(
            component_name=name, latency=LatencyStats(), status="skipped",
            metadata={"reason": "GOOGLE_API_KEY / GEMINI_API_KEY not set"},
        )

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("LLM_MODEL", "gemini-3.1-flash-lite"))
    except Exception as e:
        return BenchmarkResult(
            component_name=name, latency=LatencyStats(), status="skipped",
            metadata={"reason": str(e)},
        )

    profiler = PipelineProfiler(window_size=iterations)

    for _ in range(warmup):
        try:
            resp = model.generate_content(_USER_MSG, stream=True)
            for _ in resp:
                break
        except Exception:
            pass

    with ResourceProfiler() as rp:
        for _ in range(iterations):
            with profiler.time_layer(name):
                resp = model.generate_content(_USER_MSG, stream=True)
                for _ in resp:
                    break

    stats = stats_from_profiler(profiler.get_stats(name))
    return BenchmarkResult(
        component_name=name,
        latency=stats,
        memory=rp.memory_stats,
        cpu_percent=rp.cpu_percent,
        gpu_vram_mb=rp.gpu_vram_delta,
        iterations=iterations,
        warmup=warmup,
        status=evaluate_status(stats.p95, name),
        threshold_ms=1500.0,
    )


def _bench_openai(iterations: int, warmup: int) -> BenchmarkResult:
    name = "agent.llm.openai_gpt54mini"
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return BenchmarkResult(
            component_name=name, latency=LatencyStats(), status="skipped",
            metadata={"reason": "OPENAI_API_KEY not set"},
        )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
    except Exception as e:
        return BenchmarkResult(
            component_name=name, latency=LatencyStats(), status="skipped",
            metadata={"reason": str(e)},
        )

    profiler = PipelineProfiler(window_size=iterations)
    messages = [
        {"role": "system", "content": _PROMPT},
        {"role": "user", "content": _USER_MSG},
    ]

    for _ in range(warmup):
        try:
            stream = client.chat.completions.create(model="gpt-5.4-mini", messages=messages, stream=True, max_tokens=50)
            for chunk in stream:
                break
        except Exception:
            pass

    with ResourceProfiler() as rp:
        for _ in range(iterations):
            with profiler.time_layer(name):
                stream = client.chat.completions.create(model="gpt-5.4-mini", messages=messages, stream=True, max_tokens=50)
                for chunk in stream:
                    break

    stats = stats_from_profiler(profiler.get_stats(name))
    return BenchmarkResult(
        component_name=name,
        latency=stats,
        memory=rp.memory_stats,
        cpu_percent=rp.cpu_percent,
        gpu_vram_mb=rp.gpu_vram_delta,
        iterations=iterations,
        warmup=warmup,
        status=evaluate_status(stats.p95, name),
        threshold_ms=1500.0,
    )


def run(iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    # Reduce iterations for API benchmarks (cost + rate limits)
    api_iters = min(iterations, 10)
    api_warmup = min(warmup, 2)

    gemini = _bench_gemini(api_iters, api_warmup)
    openai_result = _bench_openai(api_iters, api_warmup)

    primary = gemini if gemini.status != "skipped" else openai_result
    sub = [r for r in [gemini, openai_result] if r.component_name != primary.component_name]

    return BenchmarkResult(
        component_name=primary.component_name,
        latency=primary.latency,
        memory=primary.memory,
        cpu_percent=primary.cpu_percent,
        gpu_vram_mb=primary.gpu_vram_mb,
        iterations=primary.iterations,
        warmup=primary.warmup,
        status=primary.status,
        threshold_ms=1500.0,
        sub_results=sub,
    )
