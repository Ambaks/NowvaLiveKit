"""Benchmark: Silero VAD model load + per-chunk inference."""

from __future__ import annotations

import time

import numpy as np

from biomechanics.utils.timing import PipelineProfiler

from benchmarks.config import BenchmarkResult, LatencyStats, evaluate_status, stats_from_profiler
from benchmarks.profiler import ResourceProfiler


def run(iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    load_name = "agent.vad.load"
    infer_name = "agent.vad.inference"

    try:
        from livekit.plugins import silero
    except ImportError:
        return BenchmarkResult(
            component_name=load_name,
            latency=LatencyStats(),
            status="skipped",
            metadata={"reason": "livekit.plugins.silero not importable"},
        )

    # Model load benchmark
    t0 = time.perf_counter()
    try:
        vad = silero.VAD.load()
    except Exception as e:
        return BenchmarkResult(
            component_name=load_name,
            latency=LatencyStats(),
            status="skipped",
            metadata={"reason": f"VAD load failed: {e}"},
        )
    load_ms = (time.perf_counter() - t0) * 1000

    # Synthetic 30ms audio chunk at 16kHz
    chunk = np.random.randint(-32768, 32767, size=480, dtype=np.int16)

    profiler = PipelineProfiler(window_size=iterations)

    for _ in range(warmup):
        try:
            vad.predict(chunk)
        except Exception:
            break

    with ResourceProfiler() as rp:
        for _ in range(iterations):
            with profiler.time_layer(infer_name):
                try:
                    vad.predict(chunk)
                except Exception:
                    pass

    stats_infer = stats_from_profiler(profiler.get_stats(infer_name))

    return BenchmarkResult(
        component_name=load_name,
        latency=LatencyStats(mean=load_ms, p50=load_ms, p95=load_ms, p99=load_ms, min=load_ms, max=load_ms, count=1),
        memory=rp.memory_stats,
        cpu_percent=rp.cpu_percent,
        gpu_vram_mb=rp.gpu_vram_delta,
        iterations=1,
        warmup=0,
        status=evaluate_status(load_ms, load_name),
        threshold_ms=500.0,
        metadata={"load_ms": round(load_ms, 2)},
        sub_results=[
            BenchmarkResult(
                component_name=infer_name,
                latency=stats_infer,
                iterations=iterations,
                warmup=warmup,
                status=evaluate_status(stats_infer.p95, infer_name),
                threshold_ms=5.0,
            ),
        ],
    )
