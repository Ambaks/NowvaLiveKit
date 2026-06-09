"""Benchmark: RepCounter.update() on a squat sequence."""

from __future__ import annotations

from biomechanics.faults.rep_counter import RepCounter
from biomechanics.kinematics.analytical_ik import AnalyticalIKSolver
from biomechanics.utils.timing import PipelineProfiler

from benchmarks.config import BenchmarkResult, evaluate_status, stats_from_profiler
from benchmarks.fixtures.data import generate_squat_sequence
from benchmarks.profiler import ResourceProfiler


def run(iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    name = "biomechanics.rep_counter"
    frames = generate_squat_sequence(max(iterations + warmup, 90))
    solver = AnalyticalIKSolver()
    profiler = PipelineProfiler(window_size=iterations)

    counter = RepCounter()
    for f in frames[:warmup]:
        a = solver.solve(f)
        counter.update(a)

    counter_bench = RepCounter()
    with ResourceProfiler() as rp:
        for i in range(iterations):
            frame = frames[i % len(frames)]
            a = solver.solve(frame)
            with profiler.time_layer(name):
                counter_bench.update(a)

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
