"""Benchmark: TTS time-to-first-audio — Cartesia Sonic-2 + ElevenLabs (requires --include-api)."""

from __future__ import annotations

import os
import time

from biomechanics.utils.timing import PipelineProfiler

from benchmarks.config import BenchmarkResult, LatencyStats, evaluate_status, stats_from_profiler
from benchmarks.profiler import ResourceProfiler

_TEXT = "Push your knees out over your toes and keep your chest up."


def _bench_cartesia(iterations: int, warmup: int) -> BenchmarkResult:
    name = "agent.tts.cartesia_sonic2"
    api_key = os.getenv("CARTESIA_API_KEY")
    if not api_key:
        return BenchmarkResult(
            component_name=name, latency=LatencyStats(), status="skipped",
            metadata={"reason": "CARTESIA_API_KEY not set"},
        )

    try:
        from cartesia import Cartesia
        client = Cartesia(api_key=api_key)
    except Exception as e:
        return BenchmarkResult(
            component_name=name, latency=LatencyStats(), status="skipped",
            metadata={"reason": str(e)},
        )

    profiler = PipelineProfiler(window_size=iterations)
    voice_id = os.getenv("CARTESIA_VOICE_ID", "a0e99841-438c-4a64-b679-ae501e7d6091")

    for _ in range(warmup):
        try:
            output = client.tts.bytes(
                model_id="sonic-2",
                transcript=_TEXT,
                voice_id=voice_id,
                output_format={"container": "raw", "encoding": "pcm_s16le", "sample_rate": 24000},
            )
        except Exception:
            pass

    with ResourceProfiler() as rp:
        for _ in range(iterations):
            with profiler.time_layer(name):
                output = client.tts.bytes(
                    model_id="sonic-2",
                    transcript=_TEXT,
                    voice_id=voice_id,
                    output_format={"container": "raw", "encoding": "pcm_s16le", "sample_rate": 24000},
                )

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
        threshold_ms=500.0,
    )


def _bench_elevenlabs(iterations: int, warmup: int) -> BenchmarkResult:
    name = "agent.tts.elevenlabs"
    api_key = os.getenv("ELEVEN_API_KEY")
    if not api_key:
        return BenchmarkResult(
            component_name=name, latency=LatencyStats(), status="skipped",
            metadata={"reason": "ELEVEN_API_KEY not set"},
        )

    try:
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=api_key)
    except Exception as e:
        return BenchmarkResult(
            component_name=name, latency=LatencyStats(), status="skipped",
            metadata={"reason": str(e)},
        )

    profiler = PipelineProfiler(window_size=iterations)
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

    for _ in range(warmup):
        try:
            audio = client.generate(text=_TEXT, voice=voice_id, model="eleven_multilingual_v2")
            for _ in audio:
                break
        except Exception:
            pass

    with ResourceProfiler() as rp:
        for _ in range(iterations):
            with profiler.time_layer(name):
                audio = client.generate(text=_TEXT, voice=voice_id, model="eleven_multilingual_v2")
                for _ in audio:
                    break

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
        threshold_ms=500.0,
    )


def run(iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    api_iters = min(iterations, 10)
    api_warmup = min(warmup, 2)

    cartesia = _bench_cartesia(api_iters, api_warmup)
    elevenlabs = _bench_elevenlabs(api_iters, api_warmup)

    primary = cartesia if cartesia.status != "skipped" else elevenlabs
    sub = [r for r in [cartesia, elevenlabs] if r.component_name != primary.component_name]

    return BenchmarkResult(
        component_name=primary.component_name,
        latency=primary.latency,
        memory=primary.memory,
        cpu_percent=primary.cpu_percent,
        gpu_vram_mb=primary.gpu_vram_mb,
        iterations=primary.iterations,
        warmup=primary.warmup,
        status=primary.status,
        threshold_ms=500.0,
        sub_results=sub,
    )
