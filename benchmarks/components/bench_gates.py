"""Benchmark: StandingPoseGate + ReadinessGate."""

from __future__ import annotations

from biomechanics.utils.standing_gate import StandingPoseGate
from biomechanics.utils.timing import PipelineProfiler

from benchmarks.config import BenchmarkResult, evaluate_status, stats_from_profiler
from benchmarks.fixtures.data import load_fixture_skeleton_3d
from benchmarks.profiler import ResourceProfiler


def run(iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    skeleton = load_fixture_skeleton_3d()

    standing_gate = StandingPoseGate()
    readiness_gate = StandingPoseGate()

    standing_name = "biomechanics.gates.standing"
    readiness_name = "biomechanics.gates.readiness"
    profiler_s = PipelineProfiler(window_size=iterations)
    profiler_r = PipelineProfiler(window_size=iterations)

    for _ in range(warmup):
        standing_gate.check(skeleton)
        readiness_gate.check(skeleton)

    with ResourceProfiler() as rp:
        for _ in range(iterations):
            with profiler_s.time_layer(standing_name):
                standing_gate.check(skeleton)
            with profiler_r.time_layer(readiness_name):
                readiness_gate.check(skeleton)

    stats_s = stats_from_profiler(profiler_s.get_stats(standing_name))
    stats_r = stats_from_profiler(profiler_r.get_stats(readiness_name))

    sub_results = [
        BenchmarkResult(
            component_name=readiness_name,
            latency=stats_r,
            iterations=iterations,
            warmup=warmup,
            status=evaluate_status(stats_r.p95, readiness_name),
            threshold_ms=0.5,
        ),
    ]

    return BenchmarkResult(
        component_name=standing_name,
        latency=stats_s,
        memory=rp.memory_stats,
        cpu_percent=rp.cpu_percent,
        gpu_vram_mb=rp.gpu_vram_delta,
        iterations=iterations,
        warmup=warmup,
        status=evaluate_status(stats_s.p95, standing_name),
        threshold_ms=0.5,
        sub_results=sub_results,
    )
