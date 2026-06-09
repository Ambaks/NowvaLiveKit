"""Resource profiler: memory (tracemalloc), CPU (psutil), GPU (pynvml/torch.cuda)."""

from __future__ import annotations

import time
import tracemalloc

from benchmarks.config import MemoryStats


class ResourceProfiler:
    """Context manager that captures memory, CPU, and GPU metrics around a benchmark."""

    def __init__(self) -> None:
        self._process = None
        self._cpu_start = None
        self._wall_start: float = 0.0
        self._peak_mem: int = 0
        self._current_mem: int = 0
        self.cpu_percent: float = 0.0
        self._gpu_vram_start: float | None = None
        self._gpu_vram_end: float | None = None

    def __enter__(self) -> ResourceProfiler:
        tracemalloc.start()

        try:
            import psutil
            self._process = psutil.Process()
            self._cpu_start = self._process.cpu_times()
            self._wall_start = time.monotonic()
        except ImportError:
            self._process = None

        self._gpu_vram_start = _read_gpu_vram()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._current_mem, self._peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        if self._process and self._cpu_start:
            cpu_end = self._process.cpu_times()
            wall_elapsed = time.monotonic() - self._wall_start
            cpu_elapsed = (
                (cpu_end.user - self._cpu_start.user)
                + (cpu_end.system - self._cpu_start.system)
            )
            self.cpu_percent = (cpu_elapsed / wall_elapsed) * 100 if wall_elapsed > 0 else 0

        self._gpu_vram_end = _read_gpu_vram()

    @property
    def memory_stats(self) -> MemoryStats:
        return MemoryStats(
            peak_mb=self._peak_mem / (1024 * 1024),
            avg_mb=self._current_mem / (1024 * 1024),
            delta_mb=(self._peak_mem - self._current_mem) / (1024 * 1024),
        )

    @property
    def gpu_vram_delta(self) -> float | None:
        if self._gpu_vram_start is not None and self._gpu_vram_end is not None:
            return self._gpu_vram_end - self._gpu_vram_start
        return None


def _read_gpu_vram() -> float | None:
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        return info.used / (1024 * 1024)
    except Exception:
        pass
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.memory_allocated() / (1024 * 1024)
    except Exception:
        pass
    return None
