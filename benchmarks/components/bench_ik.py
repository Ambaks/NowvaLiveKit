"""Benchmark: AnalyticalIKSolver.solve()"""

from __future__ import annotations

from biomechanics.kinematics.analytical_ik import AnalyticalIKSolver
from biomechanics.utils.timing import PipelineProfiler

from benchmarks.config import BenchmarkResult, evaluate_status, stats_from_profiler
from benchmarks.fixtures.data import load_fixture_skeleton_3d
from benchmarks.profiler import ResourceProfiler


def run(iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    name = "biomechanics.ik.analytical"
    profiler = PipelineProfiler(window_size=iterations)
    solver = AnalyticalIKSolver()
    skeleton = load_fixture_skeleton_3d()

    for _ in range(warmup):
        solver.solve(skeleton)

    with ResourceProfiler() as rp:
        for _ in range(iterations):
            with profiler.time_layer(name):
                solver.solve(skeleton)

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
        threshold_ms=2.0,
    )
