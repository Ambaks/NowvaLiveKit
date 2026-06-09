"""Benchmark: estimate_text_tokens() speed + accuracy."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from agent.core.token_estimator import estimate_text_tokens
from biomechanics.utils.timing import PipelineProfiler

from benchmarks.config import BenchmarkResult, evaluate_status, stats_from_profiler
from benchmarks.profiler import ResourceProfiler

_SAMPLE_TEXTS = [
    "How many reps should I do?",
    "Let's start with barbell back squats. I want you to focus on keeping your chest up and pushing your knees out.",
    "Great set! You completed 8 reps. Your form looked solid on the first 5 reps, but I noticed some knee cave on reps 6-8. " * 3,
]


def run(iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    name = "agent.token_estimator"
    profiler = PipelineProfiler(window_size=iterations)

    for _ in range(warmup):
        for text in _SAMPLE_TEXTS:
            estimate_text_tokens(text)

    with ResourceProfiler() as rp:
        for i in range(iterations):
            text = _SAMPLE_TEXTS[i % len(_SAMPLE_TEXTS)]
            with profiler.time_layer(name):
                estimate_text_tokens(text)

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
        threshold_ms=1.0,
    )
