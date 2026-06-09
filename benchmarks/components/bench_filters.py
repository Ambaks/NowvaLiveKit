"""Benchmark: Pre-IK filters (confidence, velocity, bone, position) + combined."""

from __future__ import annotations

from biomechanics.utils.confidence_blend import ConfidenceBlender
from biomechanics.utils.velocity_clamp import VelocityClamp
from biomechanics.utils.bone_constraints import BoneLengthConstraints
from biomechanics.utils.position_filter import KeypointPositionSmoother
from biomechanics.utils.timing import PipelineProfiler

from benchmarks.config import BenchmarkResult, LatencyStats, evaluate_status, stats_from_profiler
from benchmarks.fixtures.data import generate_squat_sequence
from benchmarks.profiler import ResourceProfiler


def _bench_single(
    filter_obj,
    method_name: str,
    component_name: str,
    frames: list,
    iterations: int,
    warmup: int,
) -> BenchmarkResult:
    fn = getattr(filter_obj, method_name)
    profiler = PipelineProfiler(window_size=iterations)

    for f in frames[:warmup]:
        fn(f)

    with ResourceProfiler() as rp:
        for i in range(iterations):
            frame = frames[i % len(frames)]
            with profiler.time_layer(component_name):
                fn(frame)

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
        threshold_ms=0.5,
    )


def run(iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    frames = generate_squat_sequence(max(iterations + warmup, 90))

    blender = ConfidenceBlender()
    clamper = VelocityClamp()
    bone = BoneLengthConstraints()
    smoother = KeypointPositionSmoother()

    # Calibrate bone constraints with standing frames
    for f in frames[:30]:
        bone.enforce(f)

    sub_results = [
        _bench_single(blender, "blend", "biomechanics.filters.confidence", frames, iterations, warmup),
        _bench_single(clamper, "clamp", "biomechanics.filters.velocity", frames, iterations, warmup),
        _bench_single(bone, "enforce", "biomechanics.filters.bone", frames, iterations, warmup),
        _bench_single(smoother, "smooth", "biomechanics.filters.position", frames, iterations, warmup),
    ]

    # Combined chain benchmark
    blender2 = ConfidenceBlender()
    clamper2 = VelocityClamp()
    bone2 = BoneLengthConstraints()
    smoother2 = KeypointPositionSmoother()
    for f in frames[:30]:
        bone2.enforce(f)

    combined_name = "biomechanics.filters.combined"
    profiler = PipelineProfiler(window_size=iterations)

    for f in frames[:warmup]:
        smoother2.smooth(bone2.enforce(clamper2.clamp(blender2.blend(f))))

    with ResourceProfiler() as rp:
        for i in range(iterations):
            frame = frames[i % len(frames)]
            with profiler.time_layer(combined_name):
                s = blender2.blend(frame)
                s = clamper2.clamp(s)
                s = bone2.enforce(s)
                s = smoother2.smooth(s)

    stats = stats_from_profiler(profiler.get_stats(combined_name))
    return BenchmarkResult(
        component_name=combined_name,
        latency=stats,
        memory=rp.memory_stats,
        cpu_percent=rp.cpu_percent,
        gpu_vram_mb=rp.gpu_vram_delta,
        iterations=iterations,
        warmup=warmup,
        status=evaluate_status(stats.p95, combined_name),
        threshold_ms=3.0,
        sub_results=sub_results,
    )
