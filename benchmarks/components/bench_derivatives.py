"""Benchmark: DerivativeTracker, JointAngleFilter, SquatProfile.get_rep_signal."""

from __future__ import annotations

from biomechanics.utils.derivatives import DerivativeTracker
from biomechanics.utils.filters import JointAngleFilter
from biomechanics.kinematics.analytical_ik import AnalyticalIKSolver
from biomechanics.profiles.squat import SquatProfile
from biomechanics.utils.timing import PipelineProfiler

from benchmarks.config import BenchmarkResult, evaluate_status, stats_from_profiler
from benchmarks.fixtures.data import generate_squat_sequence, load_fixture_angles
from benchmarks.profiler import ResourceProfiler


def run(iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    angles = load_fixture_angles()
    frames = generate_squat_sequence(max(iterations + warmup, 90))
    solver = AnalyticalIKSolver()
    profile = SquatProfile()

    tracker = DerivativeTracker()
    angle_filter = JointAngleFilter()

    tracker_name = "biomechanics.derivatives.tracker"
    filter_name = "biomechanics.derivatives.angle_filter"
    signal_name = "biomechanics.derivatives.rep_signal"

    p_tracker = PipelineProfiler(window_size=iterations)
    p_filter = PipelineProfiler(window_size=iterations)
    p_signal = PipelineProfiler(window_size=iterations)

    for _ in range(warmup):
        tracker.update(angles)
        angle_filter.filter_angles(angles)

    with ResourceProfiler() as rp:
        for i in range(iterations):
            frame = frames[i % len(frames)]
            a = solver.solve(frame)

            with p_tracker.time_layer(tracker_name):
                tracker.update(a)

            with p_filter.time_layer(filter_name):
                angle_filter.filter_angles(a)

            with p_signal.time_layer(signal_name):
                profile.get_rep_signal(frame, a)

    stats_t = stats_from_profiler(p_tracker.get_stats(tracker_name))
    stats_f = stats_from_profiler(p_filter.get_stats(filter_name))
    stats_s = stats_from_profiler(p_signal.get_stats(signal_name))

    return BenchmarkResult(
        component_name=tracker_name,
        latency=stats_t,
        memory=rp.memory_stats,
        cpu_percent=rp.cpu_percent,
        gpu_vram_mb=rp.gpu_vram_delta,
        iterations=iterations,
        warmup=warmup,
        status=evaluate_status(stats_t.p95, tracker_name),
        threshold_ms=0.5,
        sub_results=[
            BenchmarkResult(
                component_name=filter_name,
                latency=stats_f,
                iterations=iterations,
                warmup=warmup,
                status=evaluate_status(stats_f.p95, filter_name),
                threshold_ms=0.5,
            ),
            BenchmarkResult(
                component_name=signal_name,
                latency=stats_s,
                iterations=iterations,
                warmup=warmup,
                status=evaluate_status(stats_s.p95, signal_name),
                threshold_ms=0.5,
            ),
        ],
    )
