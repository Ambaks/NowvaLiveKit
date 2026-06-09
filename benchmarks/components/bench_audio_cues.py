"""Benchmark: AudioCueService disk indexing + cache lookup time."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from biomechanics.utils.timing import PipelineProfiler

from benchmarks.config import BenchmarkResult, LatencyStats, evaluate_status, stats_from_profiler
from benchmarks.profiler import ResourceProfiler

CUES_DIR = Path(__file__).parent.parent.parent / "src" / "agent" / "assets" / "cues" / "wav"

_CUE_KEYS = [
    "knees_out", "chest_up", "deeper", "heels_down", "brace",
    "good_rep", "great_depth", "strong", "clean", "perfect",
    "rep_1", "rep_2", "rep_3", "rep_4", "rep_5",
]


def run(iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    load_name = "agent.audio_cues.load"
    lookup_name = "agent.audio_cues.lookup"

    if not CUES_DIR.exists():
        return BenchmarkResult(
            component_name=load_name,
            latency=LatencyStats(),
            status="skipped",
            metadata={"reason": f"Cues directory not found: {CUES_DIR}"},
        )

    # Benchmark disk indexing
    t0 = time.perf_counter()
    cue_index = {}
    for wav_file in CUES_DIR.glob("*.wav"):
        key = wav_file.stem.rsplit("_", 1)[0]
        cue_index.setdefault(key, []).append(wav_file)
    index_ms = (time.perf_counter() - t0) * 1000

    # Benchmark cache lookup
    p_lookup = PipelineProfiler(window_size=iterations)

    for _ in range(warmup):
        for key in _CUE_KEYS:
            _ = key in cue_index

    with ResourceProfiler() as rp:
        for i in range(iterations):
            key = _CUE_KEYS[i % len(_CUE_KEYS)]
            with p_lookup.time_layer(lookup_name):
                _ = cue_index.get(key, [])

    stats_lookup = stats_from_profiler(p_lookup.get_stats(lookup_name))

    return BenchmarkResult(
        component_name=load_name,
        latency=LatencyStats(mean=index_ms, p50=index_ms, p95=index_ms, p99=index_ms, min=index_ms, max=index_ms, count=1),
        memory=rp.memory_stats,
        cpu_percent=rp.cpu_percent,
        gpu_vram_mb=rp.gpu_vram_delta,
        iterations=1,
        warmup=0,
        status=evaluate_status(index_ms, load_name),
        threshold_ms=500.0,
        metadata={"cue_count": sum(len(v) for v in cue_index.values()), "index_ms": round(index_ms, 2)},
        sub_results=[
            BenchmarkResult(
                component_name=lookup_name,
                latency=stats_lookup,
                iterations=iterations,
                warmup=warmup,
                status=evaluate_status(stats_lookup.p95, lookup_name),
                threshold_ms=0.1,
            ),
        ],
    )
