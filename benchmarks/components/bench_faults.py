"""Benchmark: RuleEngine.evaluate() + per-rule breakdown."""

from __future__ import annotations

import logging

from biomechanics.config import BiomechanicsConfig
from biomechanics.faults.rule_engine import RuleEngine
from biomechanics.profiles.squat import SquatProfile
from biomechanics.utils.timing import PipelineProfiler

from benchmarks.config import BenchmarkResult, evaluate_status, stats_from_profiler
from benchmarks.fixtures.data import load_fixture_angles
from benchmarks.profiler import ResourceProfiler

logging.disable(logging.CRITICAL)


def run(iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    name = "biomechanics.faults.rule_engine"
    config = BiomechanicsConfig()
    profile = SquatProfile()
    rules = profile.create_fault_rules(config)
    engine = RuleEngine(config=config, rules=rules)
    angles = load_fixture_angles()
    profiler = PipelineProfiler(window_size=iterations)

    for _ in range(warmup):
        engine.evaluate(angles, in_rep=True, rep_number=1)

    # Per-rule profilers
    rule_profilers: dict[str, PipelineProfiler] = {}
    for rule in engine.rules:
        rule_name = f"biomechanics.faults.{rule.fault_type.value if hasattr(rule.fault_type, 'value') else rule.fault_type}"
        rule_profilers[rule_name] = PipelineProfiler(window_size=iterations)

    with ResourceProfiler() as rp:
        for _ in range(iterations):
            with profiler.time_layer(name):
                engine.evaluate(angles, in_rep=True, rep_number=1)

            # Individual rule timing
            for rule in engine.rules:
                rule_name = f"biomechanics.faults.{rule.fault_type.value if hasattr(rule.fault_type, 'value') else rule.fault_type}"
                rp_rule = rule_profilers[rule_name]
                with rp_rule.time_layer(rule_name):
                    rule.evaluate(angles, engine.history, in_rep=True, rep_number=1)

    stats = stats_from_profiler(profiler.get_stats(name))

    sub_results = []
    for rule_name, rp_rule in rule_profilers.items():
        rule_stats = stats_from_profiler(rp_rule.get_stats(rule_name))
        sub_results.append(BenchmarkResult(
            component_name=rule_name,
            latency=rule_stats,
            iterations=iterations,
            warmup=warmup,
            status=evaluate_status(rule_stats.p95, rule_name),
        ))

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
        metadata={"rule_count": len(engine.rules)},
        sub_results=sub_results,
    )
