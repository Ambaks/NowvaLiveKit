"""Benchmark: CompactionService tier parsing (no API call)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from biomechanics.utils.timing import PipelineProfiler

from benchmarks.config import BenchmarkResult, LatencyStats, evaluate_status, stats_from_profiler
from benchmarks.profiler import ResourceProfiler

# Synthetic compaction output to parse
_SAMPLE_RESPONSE = """---HOT---
User asked about squat form. Agent explained knee tracking importance.
Agent provided 3 cues: knees out, chest up, brace core.
User completed set of 8 reps with 2 form faults.
---WARM---
Session started 5 minutes ago. User is intermediate lifter.
Working on barbell back squat, set 3 of 5.
Previous sets had minor knee valgus issues.
User responded positively to depth cue on set 2.
---COLD---
User profile: intermediate, 4 days/week, strength focus.
Program includes squat, deadlift, bench press.
Historical knee valgus tendency noted in onboarding.
"""


def run(iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    name = "agent.compaction.parse"
    profiler = PipelineProfiler(window_size=iterations)

    def _parse_tiers(text: str) -> dict:
        tiers = {"hot": "", "warm": "", "cold": ""}
        current = None
        for line in text.strip().split("\n"):
            stripped = line.strip()
            if stripped == "---HOT---":
                current = "hot"
            elif stripped == "---WARM---":
                current = "warm"
            elif stripped == "---COLD---":
                current = "cold"
            elif current:
                tiers[current] += line + "\n"
        return tiers

    for _ in range(warmup):
        _parse_tiers(_SAMPLE_RESPONSE)

    with ResourceProfiler() as rp:
        for _ in range(iterations):
            with profiler.time_layer(name):
                _parse_tiers(_SAMPLE_RESPONSE)

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
        threshold_ms=0.5,
    )
