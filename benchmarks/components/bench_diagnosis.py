"""Benchmark: HypothesisEngine.diagnose() — per-set diagnosis."""

from __future__ import annotations

from biomechanics.diagnosis.engine import HypothesisEngine
from biomechanics.diagnosis.types import RepKinematicSummary, SetFeatures
from biomechanics.utils.timing import PipelineProfiler

from benchmarks.config import BenchmarkResult, evaluate_status, stats_from_profiler
from benchmarks.profiler import ResourceProfiler


def _make_set_features(n_reps: int = 5) -> SetFeatures:
    reps = []
    for i in range(n_reps):
        reps.append(RepKinematicSummary(
            rep_number=i + 1,
            trunk_pitch_at_bottom=35.0 + i * 2,
            knee_valgus_l=5.0,
            knee_valgus_r=4.0,
            ankle_df_l_max=28.0,
            ankle_df_r_max=27.0,
            hip_y_l_at_bottom=0.45,
            hip_y_r_at_bottom=0.44,
            knee_y_l_at_bottom=0.25,
            knee_y_r_at_bottom=0.24,
            stance_width_ratio=0.55,
            foot_direction_angle_l=15.0,
            foot_direction_angle_r=14.0,
            depth_class_int=3,
        ))

    return SetFeatures(
        user_id=1,
        set_id="bench_set_001",
        rep_count=n_reps,
        per_rep_kinematics=reps,
        anthropometry={"height_cm": 188.5, "femur_length_cm": 48.0, "tibia_length_cm": 42.0},
        rom={"ankle_df_max": 35.0, "hip_flexion_max": 120.0},
    )


def run(iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    name = "biomechanics.diagnosis"
    engine = HypothesisEngine()
    features = _make_set_features()
    profiler = PipelineProfiler(window_size=iterations)

    for _ in range(warmup):
        engine.diagnose(features)

    with ResourceProfiler() as rp:
        for _ in range(iterations):
            with profiler.time_layer(name):
                engine.diagnose(features)

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
        threshold_ms=50.0,
    )
