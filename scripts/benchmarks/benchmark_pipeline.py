#!/usr/bin/env python3
"""
Benchmark the biomechanics pipeline.

Runs the pipeline for N frames and reports per-layer latency statistics.
Supports comparing RTMPose vs MediaPipe backends.

Usage:
    python scripts/benchmark_pipeline.py                          # default mediapipe
    python scripts/benchmark_pipeline.py --backend rtmpose        # RTMPose only
    python scripts/benchmark_pipeline.py --backend both           # compare both
    python scripts/benchmark_pipeline.py --frames 100 --device 1
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from biomechanics.pipeline import BiomechanicsPipeline
from biomechanics.config import BiomechanicsConfig


def percentile(data, p):
    """Compute percentile of a list."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[f]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


def run_benchmark(backend: str, device_id: int, num_frames: int) -> dict:
    """
    Run benchmark for a single backend.

    Returns dict with timing results.
    """
    config = BiomechanicsConfig()
    config.capture.device_id = device_id
    config.pose.backend = backend

    print(f"\nInitializing pipeline with backend: {backend}...")
    pipeline = BiomechanicsPipeline(config)

    layer_timings: dict[str, list[float]] = {}
    total_timings: list[float] = []

    print(f"Running {num_frames} frames...")
    start_time = time.time()

    for i in range(num_frames):
        result = pipeline.process_frame()

        for layer, ms in result.latency_ms.items():
            layer_timings.setdefault(layer, []).append(ms)

        total_ms = sum(result.latency_ms.values())
        total_timings.append(total_ms)

        if (i + 1) % 50 == 0:
            elapsed = time.time() - start_time
            current_fps = (i + 1) / elapsed
            print(f"  Frame {i + 1}/{num_frames} — {current_fps:.1f} FPS")

    elapsed = time.time() - start_time
    pipeline.release()

    return {
        "backend": backend,
        "elapsed": elapsed,
        "fps": num_frames / elapsed,
        "layer_timings": layer_timings,
        "total_timings": total_timings,
    }


def print_results(results: dict, num_frames: int):
    """Print timing results for a single backend."""
    backend = results["backend"]
    elapsed = results["elapsed"]
    layer_timings = results["layer_timings"]
    total_timings = results["total_timings"]

    print(f"\n  Backend:     {backend}")
    print(f"  Total time:  {elapsed:.2f}s")
    print(f"  Overall FPS: {results['fps']:.1f}\n")

    header = f"  {'Layer':<12} {'Mean':>8} {'P50':>8} {'P95':>8} {'P99':>8}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for layer in ["capture", "pose", "bilstm", "ik", "faults"]:
        data = layer_timings.get(layer, [])
        if not data:
            continue
        mean = np.mean(data)
        p50 = percentile(data, 50)
        p95 = percentile(data, 95)
        p99 = percentile(data, 99)
        print(f"  {layer:<12} {mean:>7.2f}ms {p50:>7.2f}ms {p95:>7.2f}ms {p99:>7.2f}ms")

    mean = np.mean(total_timings)
    p50 = percentile(total_timings, 50)
    p95 = percentile(total_timings, 95)
    p99 = percentile(total_timings, 99)
    print("  " + "-" * (len(header) - 2))
    print(f"  {'TOTAL':<12} {mean:>7.2f}ms {p50:>7.2f}ms {p95:>7.2f}ms {p99:>7.2f}ms")


def print_comparison(results_a: dict, results_b: dict):
    """Print side-by-side comparison of two backends."""
    a_name = results_a["backend"]
    b_name = results_b["backend"]

    print(f"\n  {'':>12} {'--- ' + a_name + ' ---':>24} {'--- ' + b_name + ' ---':>24}")
    print(f"  {'Layer':<12} {'Mean':>8} {'P50':>8}   {'Mean':>8} {'P50':>8}   {'Diff':>8}")
    print("  " + "-" * 70)

    for layer in ["capture", "pose", "bilstm", "ik", "faults"]:
        data_a = results_a["layer_timings"].get(layer, [])
        data_b = results_b["layer_timings"].get(layer, [])
        if not data_a and not data_b:
            continue

        mean_a = np.mean(data_a) if data_a else 0.0
        p50_a = percentile(data_a, 50) if data_a else 0.0
        mean_b = np.mean(data_b) if data_b else 0.0
        p50_b = percentile(data_b, 50) if data_b else 0.0

        diff = mean_b - mean_a
        diff_str = f"{diff:>+7.2f}ms"

        a_str = f"{mean_a:>7.2f}ms {p50_a:>7.2f}ms" if data_a else f"{'N/A':>8} {'N/A':>8}"
        b_str = f"{mean_b:>7.2f}ms {p50_b:>7.2f}ms" if data_b else f"{'N/A':>8} {'N/A':>8}"

        print(f"  {layer:<12} {a_str}   {b_str}   {diff_str}")

    # Totals
    mean_a = np.mean(results_a["total_timings"])
    mean_b = np.mean(results_b["total_timings"])
    p50_a = percentile(results_a["total_timings"], 50)
    p50_b = percentile(results_b["total_timings"], 50)
    diff = mean_b - mean_a

    print("  " + "-" * 70)
    print(
        f"  {'TOTAL':<12} {mean_a:>7.2f}ms {p50_a:>7.2f}ms"
        f"   {mean_b:>7.2f}ms {p50_b:>7.2f}ms"
        f"   {diff:>+7.2f}ms"
    )

    print(f"\n  FPS: {results_a['backend']}={results_a['fps']:.1f}"
          f"  {results_b['backend']}={results_b['fps']:.1f}")


def main():
    parser = argparse.ArgumentParser(description="Benchmark biomechanics pipeline")
    parser.add_argument("--frames", type=int, default=300, help="Number of frames to process")
    parser.add_argument("--device", type=int, default=0, help="Camera device ID")
    parser.add_argument(
        "--backend",
        choices=["mediapipe", "rtmpose", "both"],
        default="mediapipe",
        help="Pose backend to benchmark (default: mediapipe)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  BIOMECHANICS PIPELINE BENCHMARK")
    print("=" * 60)
    print(f"\n  Frames:  {args.frames}")
    print(f"  Camera:  {args.device}")
    print(f"  Backend: {args.backend}")

    if args.backend == "both":
        results_mp = run_benchmark("mediapipe", args.device, args.frames)
        results_rtm = run_benchmark("rtmpose", args.device, args.frames)

        print("\n" + "=" * 60)
        print("  INDIVIDUAL RESULTS")
        print("=" * 60)
        print_results(results_mp, args.frames)
        print_results(results_rtm, args.frames)

        print("\n" + "=" * 60)
        print("  COMPARISON")
        print("=" * 60)
        print_comparison(results_mp, results_rtm)
    else:
        results = run_benchmark(args.backend, args.device, args.frames)
        print("\n" + "=" * 60)
        print("  RESULTS")
        print("=" * 60)
        print_results(results, args.frames)

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
