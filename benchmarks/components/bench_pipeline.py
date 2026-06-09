"""Benchmark: Full biomechanics pipeline E2E from video file or synthetic frames."""

from __future__ import annotations

import time

from biomechanics.config import BiomechanicsConfig
from biomechanics.pipeline import BiomechanicsPipeline
from biomechanics.utils.timing import PipelineProfiler

from benchmarks.config import BenchmarkResult, LatencyStats, evaluate_status, stats_from_profiler
from benchmarks.fixtures.data import load_video_frames
from benchmarks.profiler import ResourceProfiler


def run(iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    name = "biomechanics.pipeline_e2e"

    frames = load_video_frames(iterations + warmup)
    if not frames:
        return BenchmarkResult(
            component_name=name,
            latency=LatencyStats(),
            status="skipped",
            metadata={"reason": "No video frames available"},
        )

    config = BiomechanicsConfig()

    try:
        pipeline = BiomechanicsPipeline(config)
    except Exception as e:
        return BenchmarkResult(
            component_name=name,
            latency=LatencyStats(),
            status="skipped",
            metadata={"reason": f"Pipeline init failed: {e}"},
        )

    profiler = PipelineProfiler(window_size=iterations)

    # Warmup — feed frames through the pipeline
    for i in range(min(warmup, len(frames))):
        try:
            pipeline.process_frame(frames[i])
        except TypeError:
            pipeline.process_frame()
            break

    # Check if process_frame accepts a frame argument
    accepts_frame = True
    try:
        pipeline.process_frame(frames[0])
    except TypeError:
        accepts_frame = False

    layer_timings: dict[str, list[float]] = {}

    with ResourceProfiler() as rp:
        for i in range(iterations):
            frame = frames[i % len(frames)]
            with profiler.time_layer(name):
                if accepts_frame:
                    result = pipeline.process_frame(frame)
                else:
                    result = pipeline.process_frame()

            if result and hasattr(result, "latency_ms"):
                for layer, ms in result.latency_ms.items():
                    layer_timings.setdefault(layer, []).append(ms)

    try:
        pipeline.release()
    except Exception:
        pass

    stats = stats_from_profiler(profiler.get_stats(name))

    # Build layer breakdown
    breakdown = {}
    total_p50 = stats.p50 if stats.p50 > 0 else 1
    sub_results = []
    for layer, timings in layer_timings.items():
        import numpy as np
        arr = np.array(timings)
        layer_stats = LatencyStats(
            mean=float(np.mean(arr)),
            p50=float(np.percentile(arr, 50)),
            p95=float(np.percentile(arr, 95)),
            p99=float(np.percentile(arr, 99)),
            min=float(np.min(arr)),
            max=float(np.max(arr)),
            count=len(timings),
        )
        breakdown[layer] = round(layer_stats.p50 / total_p50 * 100, 1)
        sub_results.append(BenchmarkResult(
            component_name=f"biomechanics.pipeline.{layer}",
            latency=layer_stats,
            iterations=len(timings),
            status=evaluate_status(layer_stats.p95, f"biomechanics.pipeline.{layer}"),
        ))

    fps = 1000.0 / stats.p50 if stats.p50 > 0 else 0

    return BenchmarkResult(
        component_name=name,
        latency=stats,
        memory=rp.memory_stats,
        cpu_percent=rp.cpu_percent,
        gpu_vram_mb=rp.gpu_vram_delta,
        iterations=iterations,
        warmup=warmup,
        status=evaluate_status(stats.p95, name),
        threshold_ms=33.3,
        metadata={"fps": round(fps, 1), "breakdown_pct": breakdown},
        sub_results=sub_results,
    )
