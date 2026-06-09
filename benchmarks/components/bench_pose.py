"""Benchmark: MediaPipePoseEstimator + RTMPoseEstimator."""

from __future__ import annotations

import time

from biomechanics.utils.timing import PipelineProfiler

from benchmarks.config import BenchmarkResult, evaluate_status, stats_from_profiler
from benchmarks.fixtures.data import generate_synthetic_image
from benchmarks.profiler import ResourceProfiler


def _bench_backend(
    backend: str,
    component_name: str,
    iterations: int,
    warmup: int,
) -> BenchmarkResult:
    image = generate_synthetic_image()
    profiler = PipelineProfiler(window_size=iterations)

    if backend == "mediapipe":
        from biomechanics.pose.mediapipe_fallback import MediaPipePoseEstimator
        t0 = time.perf_counter()
        estimator = MediaPipePoseEstimator()
        model_load_ms = (time.perf_counter() - t0) * 1000
    else:
        from biomechanics.pose.rtmpose import RTMPoseEstimator
        t0 = time.perf_counter()
        estimator = RTMPoseEstimator()
        model_load_ms = (time.perf_counter() - t0) * 1000

    for _ in range(warmup):
        estimator.estimate(image)

    with ResourceProfiler() as rp:
        for _ in range(iterations):
            with profiler.time_layer(component_name):
                estimator.estimate(image)

    stats = stats_from_profiler(profiler.get_stats(component_name))
    return BenchmarkResult(
        component_name=component_name,
        latency=stats,
        memory=rp.memory_stats,
        cpu_percent=rp.cpu_percent,
        gpu_vram_mb=rp.gpu_vram_delta,
        iterations=iterations,
        warmup=warmup,
        status=evaluate_status(stats.p95, component_name),
        threshold_ms=15.0 if backend == "mediapipe" else 10.0,
        metadata={"model_load_ms": round(model_load_ms, 2), "backend": backend},
    )


def run(iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    mp_result = _bench_backend("mediapipe", "biomechanics.pose.mediapipe", iterations, warmup)

    sub = [mp_result]
    try:
        rtm_result = _bench_backend("rtmpose", "biomechanics.pose.rtmpose", iterations, warmup)
        sub.append(rtm_result)
    except Exception:
        pass

    return BenchmarkResult(
        component_name="biomechanics.pose.mediapipe",
        latency=mp_result.latency,
        memory=mp_result.memory,
        cpu_percent=mp_result.cpu_percent,
        gpu_vram_mb=mp_result.gpu_vram_mb,
        iterations=iterations,
        warmup=warmup,
        status=mp_result.status,
        threshold_ms=15.0,
        metadata=mp_result.metadata,
        sub_results=sub[1:],
    )
