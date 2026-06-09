"""Background thread that samples CPU, memory, and GPU at regular intervals."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable


def _get_process_stats() -> dict[str, float]:
    stats: dict[str, float] = {}
    try:
        import psutil
        proc = psutil.Process()
        stats["cpu_percent"] = proc.cpu_percent(interval=None)
        mem = proc.memory_info()
        stats["memory_mb"] = mem.rss / (1024 * 1024)
    except Exception:
        stats["cpu_percent"] = 0.0
        stats["memory_mb"] = 0.0

    stats["gpu_vram_mb"] = _get_gpu_vram()
    return stats


def _get_gpu_vram() -> float | None:
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


class ResourceSampler:
    """Daemon thread that periodically samples system resource usage."""

    def __init__(self, callback: Callable[[dict[str, Any]], None], interval_s: float = 1.0):
        self._callback = callback
        self._interval = interval_s
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        try:
            import psutil
            psutil.Process().cpu_percent(interval=None)
        except Exception:
            pass

        self._thread = threading.Thread(target=self._run, daemon=True, name="profiler-resource-sampler")
        self._thread.start()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            stats = _get_process_stats()
            self._callback(stats)
            self._stop_event.wait(self._interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
