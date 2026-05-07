"""Reusable tracemalloc memory profiler with matplotlib report generation."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


def _is_env_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("true", "1", "yes")


class MemoryProfiler:

    def __init__(self, enabled: bool | None = None):
        if enabled is None:
            enabled = _is_env_truthy(os.getenv("ENABLE_TRACEMALLOC"))
        self._enabled = enabled
        self._frame_snapshots: list[tuple[int, int, int]] = []
        self._start_snapshot = None
        self._end_snapshot = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start(self) -> None:
        if not self._enabled:
            return
        import tracemalloc
        tracemalloc.start(25)
        self._start_snapshot = tracemalloc.take_snapshot()
        self._frame_snapshots = []

    def snapshot(self, frame_idx: int) -> None:
        if not self._enabled:
            return
        import tracemalloc
        current, peak = tracemalloc.get_traced_memory()
        self._frame_snapshots.append((frame_idx, current, peak))

    def stop(self) -> None:
        if not self._enabled:
            return
        import tracemalloc
        if tracemalloc.is_tracing():
            self._end_snapshot = tracemalloc.take_snapshot()
            tracemalloc.stop()

    def generate_report(
        self,
        output_path: Path | str,
        title_prefix: str = "Memory Profile",
    ) -> Path | None:
        if not self._enabled or not self._frame_snapshots:
            return None

        output_path = Path(output_path)

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        frames = np.array([s[0] for s in self._frame_snapshots])
        current_bytes = np.array([s[1] for s in self._frame_snapshots], dtype=np.float64)
        peak_bytes = np.array([s[2] for s in self._frame_snapshots], dtype=np.float64)

        current_mib = current_bytes / (1024 * 1024)
        peak_mib = peak_bytes / (1024 * 1024)

        fig, axes = plt.subplots(3, 1, figsize=(14, 12), constrained_layout=True)

        # --- Chart 1: Memory usage over time ---
        ax = axes[0]
        ax.plot(frames, current_mib, color="#2196F3", linewidth=2, label="Current")
        ax.plot(frames, peak_mib, color="#FF5722", linewidth=1.5, linestyle="--", alpha=0.7, label="Peak")
        ax.fill_between(frames, 0, current_mib, color="#2196F3", alpha=0.15)

        max_idx = np.argmax(current_mib)
        ax.plot(frames[max_idx], current_mib[max_idx], "o", color="#F44336", markersize=8, zorder=5)
        ax.annotate(
            f"{current_mib[max_idx]:.1f} MiB",
            xy=(frames[max_idx], current_mib[max_idx]),
            xytext=(10, 10),
            textcoords="offset points",
            fontsize=9,
            fontweight="bold",
            color="#F44336",
            arrowprops=dict(arrowstyle="->", color="#F44336", lw=1.2),
        )

        ax.set_title(f"{title_prefix} — Memory Usage Over Time", fontsize=13, fontweight="bold")
        ax.set_xlabel("Frame")
        ax.set_ylabel("Memory (MiB)")
        ax.legend(loc="upper left")
        ax.grid(True, alpha=0.3)

        # --- Chart 2: Top 10 allocation hotspots ---
        ax = axes[1]
        if self._end_snapshot is not None:
            stats = self._end_snapshot.statistics("lineno")[:10]
            if stats:
                labels = []
                sizes_mib = []
                for stat in reversed(stats):
                    frame = stat.traceback[0]
                    path = frame.filename
                    if "NowvaLiveKit" in path:
                        path = path[path.index("NowvaLiveKit") + len("NowvaLiveKit/"):]
                    elif len(path) > 50:
                        path = "..." + path[-47:]
                    labels.append(f"{path}:{frame.lineno}")
                    sizes_mib.append(stat.size / (1024 * 1024))

                y_pos = np.arange(len(labels))
                bars = ax.barh(y_pos, sizes_mib, color="#4CAF50", edgecolor="#388E3C", linewidth=0.5)
                ax.set_yticks(y_pos)
                ax.set_yticklabels(labels, fontsize=8, fontfamily="monospace")
                for bar, size in zip(bars, sizes_mib):
                    ax.text(
                        bar.get_width() + max(sizes_mib) * 0.01,
                        bar.get_y() + bar.get_height() / 2,
                        f"{size:.2f} MiB",
                        va="center",
                        fontsize=8,
                        fontweight="bold",
                    )
                ax.set_xlim(0, max(sizes_mib) * 1.15)
            else:
                ax.text(0.5, 0.5, "No allocation data", transform=ax.transAxes, ha="center", va="center")
        else:
            ax.text(0.5, 0.5, "No end snapshot (profiler stopped early?)", transform=ax.transAxes, ha="center", va="center")

        ax.set_title(f"{title_prefix} — Top 10 Allocation Hotspots", fontsize=13, fontweight="bold")
        ax.set_xlabel("Size (MiB)")
        ax.grid(True, alpha=0.3, axis="x")

        # --- Chart 3: Per-frame memory delta ---
        ax = axes[2]
        if len(current_bytes) > 1:
            deltas_kib = np.diff(current_bytes) / 1024
            delta_frames = frames[1:]

            ax.fill_between(
                delta_frames, 0, deltas_kib,
                where=(deltas_kib >= 0), color="#F44336", alpha=0.4, label="Growth",
            )
            ax.fill_between(
                delta_frames, 0, deltas_kib,
                where=(deltas_kib < 0), color="#4CAF50", alpha=0.4, label="Freed",
            )
            ax.axhline(0, color="black", linewidth=0.8, alpha=0.3)

            window = min(10, len(deltas_kib))
            if window > 1:
                kernel = np.ones(window) / window
                rolling_avg = np.convolve(deltas_kib, kernel, mode="same")
                ax.plot(delta_frames, rolling_avg, color="#FF9800", linewidth=2, label=f"{window}-frame avg")

            ax.legend(loc="upper right", fontsize=9)
        else:
            ax.text(0.5, 0.5, "Not enough frames for delta", transform=ax.transAxes, ha="center", va="center")

        ax.set_title(f"{title_prefix} — Per-Frame Memory Delta", fontsize=13, fontweight="bold")
        ax.set_xlabel("Frame")
        ax.set_ylabel("Delta (KiB)")
        ax.grid(True, alpha=0.3)

        # --- Footer ---
        final_mib = current_mib[-1] if len(current_mib) > 0 else 0
        peak_total = peak_mib.max() if len(peak_mib) > 0 else 0
        fig.text(
            0.5, 0.005,
            f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
            f"{len(frames)} frames | Peak: {peak_total:.1f} MiB | Final: {final_mib:.1f} MiB",
            ha="center", fontsize=9, color="#666666",
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), dpi=150, facecolor="white", edgecolor="none")
        plt.close(fig)
        return output_path


@contextmanager
def memory_profiling(
    output_path: Path | str | None = None,
    title_prefix: str = "Memory Profile",
):
    profiler = MemoryProfiler()
    profiler.start()
    try:
        yield profiler
    finally:
        profiler.stop()
        if output_path:
            profiler.generate_report(output_path, title_prefix)
