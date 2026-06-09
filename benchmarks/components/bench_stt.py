"""Benchmark: STT transcription latency — Deepgram Nova-3 + Whisper (requires --include-api)."""

from __future__ import annotations

import os
import time

import numpy as np

from biomechanics.utils.timing import PipelineProfiler

from benchmarks.config import BenchmarkResult, LatencyStats, evaluate_status, stats_from_profiler
from benchmarks.profiler import ResourceProfiler


def _generate_wav_bytes(duration_s: float = 2.0, sample_rate: int = 16000) -> bytes:
    """Generate a simple WAV file in memory for STT testing."""
    import struct
    import io

    n_samples = int(sample_rate * duration_s)
    # Simple sine wave at 440Hz
    t = np.linspace(0, duration_s, n_samples, dtype=np.float32)
    audio = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)

    buf = io.BytesIO()
    # WAV header
    data_size = n_samples * 2
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    buf.write(audio.tobytes())
    return buf.getvalue()


def _bench_deepgram(iterations: int, warmup: int) -> BenchmarkResult:
    name = "agent.stt.deepgram_nova3"
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        return BenchmarkResult(
            component_name=name, latency=LatencyStats(), status="skipped",
            metadata={"reason": "DEEPGRAM_API_KEY not set"},
        )

    try:
        from deepgram import DeepgramClient, PrerecordedOptions
        client = DeepgramClient(api_key)
    except Exception as e:
        return BenchmarkResult(
            component_name=name, latency=LatencyStats(), status="skipped",
            metadata={"reason": str(e)},
        )

    audio_bytes = _generate_wav_bytes()
    profiler = PipelineProfiler(window_size=iterations)
    options = PrerecordedOptions(model="nova-3", language="en")

    for _ in range(warmup):
        try:
            client.listen.rest.v("1").transcribe_file({"buffer": audio_bytes, "mimetype": "audio/wav"}, options)
        except Exception:
            pass

    with ResourceProfiler() as rp:
        for _ in range(iterations):
            with profiler.time_layer(name):
                client.listen.rest.v("1").transcribe_file({"buffer": audio_bytes, "mimetype": "audio/wav"}, options)

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


def _bench_whisper(iterations: int, warmup: int) -> BenchmarkResult:
    name = "agent.stt.whisper"
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return BenchmarkResult(
            component_name=name, latency=LatencyStats(), status="skipped",
            metadata={"reason": "OPENAI_API_KEY not set"},
        )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
    except Exception as e:
        return BenchmarkResult(
            component_name=name, latency=LatencyStats(), status="skipped",
            metadata={"reason": str(e)},
        )

    audio_bytes = _generate_wav_bytes()
    profiler = PipelineProfiler(window_size=iterations)

    import io

    for _ in range(warmup):
        try:
            buf = io.BytesIO(audio_bytes)
            buf.name = "audio.wav"
            client.audio.transcriptions.create(model="whisper-1", file=buf)
        except Exception:
            pass

    with ResourceProfiler() as rp:
        for _ in range(iterations):
            with profiler.time_layer(name):
                buf = io.BytesIO(audio_bytes)
                buf.name = "audio.wav"
                client.audio.transcriptions.create(model="whisper-1", file=buf)

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

    deepgram = _bench_deepgram(api_iters, api_warmup)
    whisper = _bench_whisper(api_iters, api_warmup)

    primary = deepgram if deepgram.status != "skipped" else whisper
    sub = [r for r in [deepgram, whisper] if r.component_name != primary.component_name]

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
