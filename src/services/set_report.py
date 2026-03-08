"""
Set Report Generator — Timeseries plot with labeled cue annotations.

Generates a per-set PNG report showing joint angle timeseries with
every coaching cue that fired annotated at its exact timestamp.
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def generate_set_report(
    set_number: int,
    angle_samples: List[Dict[str, Any]],
    cue_log: list,
    rep_events: List[Dict[str, Any]],
    set_start_time: float,
    output_dir: str = "recordings",
) -> Optional[str]:
    """
    Generate a timeseries plot for a completed set.

    Args:
        set_number: Which set (1-indexed).
        angle_samples: List of {wall_time, avg_knee, trunk_flexion}.
        cue_log: List of CueLogEntry objects (wall_time, label, category).
        rep_events: List of {wall_time, rep_number, is_clean, depth}.
        set_start_time: Wall-clock time when the set started.
        output_dir: Directory to save the PNG.

    Returns:
        Path to saved PNG, or None on error.
    """
    if len(angle_samples) < 3:
        logger.warning("[SET REPORT] Not enough angle data (%d samples) — skipping", len(angle_samples))
        return None

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
        import numpy as np
    except ImportError:
        logger.warning("[SET REPORT] matplotlib not installed — skipping plot")
        return None

    t0 = time.perf_counter()

    # --- Extract timeseries arrays ---
    start = set_start_time
    times = np.array([s["wall_time"] - start for s in angle_samples])
    knee_angles = np.array([s["avg_knee"] for s in angle_samples])
    trunk_angles = np.array([s["trunk_flexion"] for s in angle_samples])

    # --- Figure setup ---
    fig, (ax_knee, ax_trunk) = plt.subplots(
        2, 1, figsize=(14, 8), sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.12},
    )

    # --- Top subplot: Knee angle + cue labels ---
    ax_knee.plot(times, knee_angles, color="#1f77b4", linewidth=1.8, label="Avg knee flexion")
    ax_knee.axhline(y=95, color="red", linestyle="--", alpha=0.4, linewidth=1, label="Depth threshold (95°)")
    ax_knee.set_ylabel("Knee Flexion (°)", fontsize=11)
    ax_knee.set_title(f"Set {set_number} — Timeseries Report", fontsize=14, fontweight="bold")
    ax_knee.grid(True, alpha=0.2)

    # Set ylim before drawing rep labels so they land correctly
    ymax = max(max(knee_angles) * 1.15, 100) if len(knee_angles) > 0 else 120
    ax_knee.set_ylim(0, ymax)

    # Rep boundary vertical lines with labels at top
    for rep in rep_events:
        rt = rep["wall_time"] - start
        rep_num = rep["rep_number"]
        is_clean = rep.get("is_clean", False)
        color = "#2ca02c" if is_clean else "#d62728"
        ax_knee.axvline(x=rt, color=color, linestyle=":", alpha=0.5, linewidth=1)
        ax_knee.text(rt, ymax * 0.97, f"R{rep_num}", fontsize=8, color=color, va="top", ha="center")

    # Cue annotations
    category_styles = {
        "fault":      {"color": "#d62728", "marker": "v", "zorder": 10},
        "rep":        {"color": "#1f77b4", "marker": "s", "zorder": 8},
        "positive":   {"color": "#2ca02c", "marker": "D", "zorder": 9},
        "motivation": {"color": "#9467bd", "marker": "*", "zorder": 9},
    }

    # Stagger annotations to avoid overlap
    annotation_offsets = [30, -35, 45, -50, 60, -65]
    for idx, entry in enumerate(cue_log):
        ct = entry.wall_time - start
        category = entry.category
        label = entry.label
        style = category_styles.get(category, {"color": "gray", "marker": "o", "zorder": 7})

        # Find the nearest knee angle for y-position
        if len(times) > 0:
            nearest_idx = int(np.argmin(np.abs(times - ct)))
            y_val = knee_angles[nearest_idx]
        else:
            y_val = ymax * 0.5

        # Plot marker on the curve
        ax_knee.plot(ct, y_val, marker=style["marker"], color=style["color"],
                     markersize=8, zorder=style["zorder"])

        # Annotate with staggered offset
        offset_y = annotation_offsets[idx % len(annotation_offsets)]
        ax_knee.annotate(
            label, xy=(ct, y_val),
            xytext=(10, offset_y), textcoords="offset points",
            fontsize=7.5, fontweight="bold", color=style["color"],
            arrowprops=dict(arrowstyle="->", color=style["color"], lw=0.8),
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=style["color"], alpha=0.85),
            zorder=style["zorder"] + 1,
        )

    # Legend
    legend_elements = [
        Patch(facecolor="#d62728", label="Fault cue"),
        Patch(facecolor="#2ca02c", label="Positive cue"),
        Patch(facecolor="#9467bd", label="Motivation"),
    ]
    ax_knee.legend(handles=legend_elements, loc="upper left", fontsize=8, framealpha=0.8)

    # Summary text box
    total_reps = len(rep_events)
    clean_reps = sum(1 for r in rep_events if r.get("is_clean", False))
    depths = [r.get("depth", "") for r in rep_events]
    summary = f"{total_reps} reps ({clean_reps} clean)"
    if total_reps > 0:
        # Try to compute avg depth from angle samples at rep times
        rep_depths = []
        for rep in rep_events:
            rt = rep["wall_time"] - start
            if len(times) > 0:
                ni = int(np.argmin(np.abs(times - rt)))
                rep_depths.append(knee_angles[ni])
        if rep_depths:
            summary += f" | Avg peak: {np.mean(rep_depths):.0f}°"

    ax_knee.text(
        0.98, 0.97, summary, transform=ax_knee.transAxes,
        fontsize=9, va="top", ha="right",
        bbox=dict(boxstyle="round,pad=0.4", fc="#f0f0f0", ec="gray", alpha=0.9),
    )

    # --- Bottom subplot: Trunk flexion ---
    ax_trunk.plot(times, trunk_angles, color="#ff7f0e", linewidth=1.2, alpha=0.8)
    ax_trunk.set_ylabel("Trunk Flexion (°)", fontsize=10)
    ax_trunk.set_xlabel("Time (seconds)", fontsize=11)
    ax_trunk.grid(True, alpha=0.2)

    # Shared rep lines on bottom subplot
    for rep in rep_events:
        rt = rep["wall_time"] - start
        is_clean = rep.get("is_clean", False)
        color = "#2ca02c" if is_clean else "#d62728"
        ax_trunk.axvline(x=rt, color=color, linestyle=":", alpha=0.3, linewidth=1)

    # --- Save ---
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"set_{set_number}_report_{timestamp}.png"
    filepath = out_path / filename

    fig.subplots_adjust(hspace=0.12)
    plt.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)

    elapsed = (time.perf_counter() - t0) * 1000
    logger.info("[SET REPORT] Saved %s (%.0fms)", filepath, elapsed)
    print(f"[SET REPORT] Saved: {filepath}")

    return str(filepath)
