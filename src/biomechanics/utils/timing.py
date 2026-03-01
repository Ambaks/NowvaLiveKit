"""
Performance Profiling Utilities for Biomechanics Pipeline

Provides decorators and context managers for measuring execution time
of individual layers and the overall pipeline.
"""

import time
import functools
from typing import Dict, List, Optional, Callable, Any
from collections import defaultdict
import numpy as np


def timed(func: Callable) -> Callable:
    """
    Decorator that records execution time of a function.

    Usage:
        @timed
        def my_function():
            ...

        # After calling:
        print(my_function.last_execution_time_ms)  # Time in milliseconds
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        wrapper.last_execution_time_ms = elapsed * 1000.0
        return result

    wrapper.last_execution_time_ms = 0.0
    return wrapper


class LayerTimer:
    """
    Context manager for timing individual pipeline layers.

    Usage:
        with LayerTimer() as timer:
            # do work
        print(f"Elapsed: {timer.elapsed_ms:.2f}ms")
    """

    def __init__(self):
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "LayerTimer":
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.end_time = time.perf_counter()
        self.elapsed_ms = (self.end_time - self.start_time) * 1000.0


class PipelineProfiler:
    """
    Tracks latency statistics for each pipeline layer.

    Maintains running statistics (mean, p50, p95, p99) for each named layer,
    enabling performance monitoring and bottleneck identification.

    Usage:
        profiler = PipelineProfiler()

        # In processing loop:
        with profiler.time_layer("pose"):
            # pose estimation
        with profiler.time_layer("ik"):
            # inverse kinematics

        # Get stats:
        print(profiler.get_stats("pose"))
        # {'mean': 8.5, 'p50': 8.2, 'p95': 12.1, 'p99': 15.3, 'count': 100}

        # Get summary:
        profiler.print_summary()
    """

    def __init__(self, window_size: int = 100):
        """
        Initialize profiler.

        Args:
            window_size: Number of recent samples to keep for statistics.
        """
        self.window_size = window_size
        self._timings: Dict[str, List[float]] = defaultdict(list)
        self._current_layer: Optional[str] = None
        self._layer_start: float = 0.0

    def time_layer(self, layer_name: str) -> "LayerTimerContext":
        """
        Context manager for timing a specific layer.

        Args:
            layer_name: Name of the layer (e.g., "pose", "triangulation", "ik")

        Returns:
            Context manager that records timing on exit.
        """
        return LayerTimerContext(self, layer_name)

    def record(self, layer_name: str, elapsed_ms: float) -> None:
        """
        Record a timing measurement for a layer.

        Args:
            layer_name: Name of the layer
            elapsed_ms: Elapsed time in milliseconds
        """
        timings = self._timings[layer_name]
        timings.append(elapsed_ms)

        # Maintain window size
        if len(timings) > self.window_size:
            timings.pop(0)

    def get_stats(self, layer_name: str) -> Dict[str, float]:
        """
        Get statistics for a specific layer.

        Args:
            layer_name: Name of the layer

        Returns:
            Dict with mean, p50, p95, p99, min, max, count
        """
        timings = self._timings.get(layer_name, [])

        if not timings:
            return {
                "mean": 0.0,
                "p50": 0.0,
                "p95": 0.0,
                "p99": 0.0,
                "min": 0.0,
                "max": 0.0,
                "count": 0,
            }

        arr = np.array(timings)
        return {
            "mean": float(np.mean(arr)),
            "p50": float(np.percentile(arr, 50)),
            "p95": float(np.percentile(arr, 95)),
            "p99": float(np.percentile(arr, 99)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "count": len(timings),
        }

    def get_all_stats(self) -> Dict[str, Dict[str, float]]:
        """
        Get statistics for all layers.

        Returns:
            Dict mapping layer names to their stats.
        """
        return {name: self.get_stats(name) for name in self._timings}

    def get_last_timings(self) -> Dict[str, float]:
        """
        Get the most recent timing for each layer.

        Returns:
            Dict mapping layer names to their last recorded time in ms.
        """
        result = {}
        for name, timings in self._timings.items():
            if timings:
                result[name] = timings[-1]
        return result

    def get_total_latency(self) -> float:
        """
        Get total latency across all layers (sum of last timings).

        Returns:
            Total latency in milliseconds.
        """
        return sum(self.get_last_timings().values())

    def reset(self, layer_name: Optional[str] = None) -> None:
        """
        Reset timing data.

        Args:
            layer_name: If provided, reset only this layer. Otherwise reset all.
        """
        if layer_name:
            self._timings[layer_name] = []
        else:
            self._timings.clear()

    def print_summary(self) -> None:
        """Print a formatted summary of all layer statistics."""
        print("\n" + "=" * 60)
        print("Pipeline Profiler Summary")
        print("=" * 60)

        all_stats = self.get_all_stats()

        if not all_stats:
            print("No timing data recorded.")
            return

        # Header
        print(f"{'Layer':<20} {'Mean':>8} {'P50':>8} {'P95':>8} {'P99':>8} {'Count':>8}")
        print("-" * 60)

        total_mean = 0.0
        for name, stats in sorted(all_stats.items()):
            print(
                f"{name:<20} "
                f"{stats['mean']:>7.2f}ms "
                f"{stats['p50']:>7.2f}ms "
                f"{stats['p95']:>7.2f}ms "
                f"{stats['p99']:>7.2f}ms "
                f"{stats['count']:>8d}"
            )
            total_mean += stats["mean"]

        print("-" * 60)
        print(f"{'TOTAL':<20} {total_mean:>7.2f}ms")
        print(f"{'Target FPS':<20} {1000.0 / total_mean if total_mean > 0 else 0:>7.1f}")
        print("=" * 60 + "\n")


class LayerTimerContext:
    """Context manager for timing a layer within PipelineProfiler."""

    def __init__(self, profiler: PipelineProfiler, layer_name: str):
        self.profiler = profiler
        self.layer_name = layer_name
        self.start_time: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "LayerTimerContext":
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        elapsed = time.perf_counter() - self.start_time
        self.elapsed_ms = elapsed * 1000.0
        self.profiler.record(self.layer_name, self.elapsed_ms)


# Singleton profiler for global access
_global_profiler: Optional[PipelineProfiler] = None


def get_global_profiler() -> PipelineProfiler:
    """Get or create the global pipeline profiler."""
    global _global_profiler
    if _global_profiler is None:
        _global_profiler = PipelineProfiler()
    return _global_profiler


def reset_global_profiler() -> None:
    """Reset the global profiler."""
    global _global_profiler
    if _global_profiler:
        _global_profiler.reset()
