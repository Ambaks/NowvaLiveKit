"""Benchmark: BarbellDetector (YOLO) + BarPathTracker (Kalman)."""

from __future__ import annotations

import time

from biomechanics.utils.timing import PipelineProfiler

from benchmarks.config import BenchmarkResult, LatencyStats, evaluate_status, stats_from_profiler
from benchmarks.fixtures.data import generate_synthetic_image
from benchmarks.profiler import ResourceProfiler


def run(iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    det_name = "biomechanics.barbell.detector"
    track_name = "biomechanics.barbell.tracker"

    try:
        from biomechanics.barbell_tracking.detector import BarbellDetector
        from biomechanics.barbell_tracking.tracker import BarPathTracker
    except ImportError:
        return BenchmarkResult(
            component_name=det_name,
            latency=LatencyStats(),
            status="skipped",
            metadata={"reason": "Barbell tracking not importable"},
        )

    image = generate_synthetic_image()

    try:
        t0 = time.perf_counter()
        detector = BarbellDetector()
        model_load_ms = (time.perf_counter() - t0) * 1000
    except Exception as e:
        return BenchmarkResult(
            component_name=det_name,
            latency=LatencyStats(),
            status="skipped",
            metadata={"reason": f"Detector init failed: {e}"},
        )

    tracker = BarPathTracker()
    p_det = PipelineProfiler(window_size=iterations)
    p_track = PipelineProfiler(window_size=iterations)

    for _ in range(warmup):
        det = detector.detect(image)
        tracker.update(det)

    with ResourceProfiler() as rp:
        for _ in range(iterations):
            with p_det.time_layer(det_name):
                det = detector.detect(image)
            with p_track.time_layer(track_name):
                tracker.update(det)

    stats_det = stats_from_profiler(p_det.get_stats(det_name))
    stats_track = stats_from_profiler(p_track.get_stats(track_name))

    return BenchmarkResult(
        component_name=det_name,
        latency=stats_det,
        memory=rp.memory_stats,
        cpu_percent=rp.cpu_percent,
        gpu_vram_mb=rp.gpu_vram_delta,
        iterations=iterations,
        warmup=warmup,
        status=evaluate_status(stats_det.p95, det_name),
        threshold_ms=10.0,
        metadata={"model_load_ms": round(model_load_ms, 2)},
        sub_results=[
            BenchmarkResult(
                component_name=track_name,
                latency=stats_track,
                iterations=iterations,
                warmup=warmup,
                status=evaluate_status(stats_track.p95, track_name),
                threshold_ms=1.0,
            ),
        ],
    )
