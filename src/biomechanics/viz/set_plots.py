"""
Post-session set visualization plots.

Generates hip position and hip velocity plots from collected pipeline data.
Plots are saved as PNGs and optionally shown interactively.
"""

import os
from datetime import datetime
from typing import Dict, List, Tuple

import numpy as np
import matplotlib.pyplot as plt


def make_output_dir(base: str = "output") -> str:
    """Create a timestamped output directory and return its path."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(base, f"set_{ts}")
    os.makedirs(out, exist_ok=True)
    return out


def plot_hip_position(
    data: dict,
    out_dir: str,
    show: bool = True,
) -> str:
    """Plot hip flexion angle over time.

    Args:
        data: Dict with keys ``timestamps``, ``hip_flexion_l``,
              ``hip_flexion_r``, ``rep_events``.
        out_dir: Directory to save the PNG.
        show: If True, call ``plt.show()`` for interactive viewing.

    Returns:
        Path to the saved PNG.
    """
    t = data["timestamps"] - data["timestamps"][0]
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(t, data["hip_flexion_l"], label="Left Hip Flexion", color="#2196F3", linewidth=1.5)
    ax.plot(t, data["hip_flexion_r"], label="Right Hip Flexion", color="#F44336", linewidth=1.5)
    ax.fill_between(
        t,
        data["hip_flexion_l"],
        data["hip_flexion_r"],
        alpha=0.15,
        color="gray",
        label="L-R Difference",
    )

    for ts_val, rep_num in data["rep_events"]:
        rel_t = ts_val - data["timestamps"][0]
        ax.axvline(x=rel_t, color="green", linestyle="--", alpha=0.5)
        ax.annotate(
            f"Rep {rep_num}",
            (rel_t, ax.get_ylim()[1]),
            textcoords="offset points",
            xytext=(5, -15),
            fontsize=8,
            color="green",
        )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Hip Flexion Angle (deg)")
    ax.set_title("Hip Joint Position Over Set")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    path = os.path.join(out_dir, "hip_position.png")
    fig.savefig(path, dpi=150)
    print(f"  Saved: {path}")
    if show:
        plt.show()
    else:
        plt.close(fig)
    return path


def plot_hip_velocity(
    data: dict,
    out_dir: str,
    show: bool = True,
) -> str:
    """Plot hip angular velocity over time.

    Args:
        data: Dict with keys ``timestamps``, ``hip_velocity_l``,
              ``hip_velocity_r``, ``rep_events``.
        out_dir: Directory to save the PNG.
        show: If True, call ``plt.show()`` for interactive viewing.

    Returns:
        Path to the saved PNG.
    """
    t = data["timestamps"] - data["timestamps"][0]
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(t, data["hip_velocity_l"], label="Left Hip Velocity", color="#2196F3", linewidth=1.0, alpha=0.8)
    ax.plot(t, data["hip_velocity_r"], label="Right Hip Velocity", color="#F44336", linewidth=1.0, alpha=0.8)
    ax.axhline(y=0, color="black", linewidth=0.5, linestyle="-")

    for ts_val, rep_num in data["rep_events"]:
        rel_t = ts_val - data["timestamps"][0]
        ax.axvline(x=rel_t, color="green", linestyle="--", alpha=0.5)

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Angular Velocity (deg/s)")
    ax.set_title("Hip Joint Velocity Over Set")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    path = os.path.join(out_dir, "hip_velocity.png")
    fig.savefig(path, dpi=150)
    print(f"  Saved: {path}")
    if show:
        plt.show()
    else:
        plt.close(fig)
    return path
