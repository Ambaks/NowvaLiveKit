"""Post-hoc rep boundary segmentation from set plot data.

Given smoothed hip position and velocity time series, finds precise squat
bottoms and standing peaks, segments each rep with exact boundaries, and
computes per-rep metrics suitable for LLM-based coaching feedback.

Coordinate convention (from pipeline):
    hip_position_cm = (hip_mid_y - ankle_mid_y) * 100
    More negative  → standing (hip far above ankle)
    Less negative  → squat bottom (hip close to ankle)

So squat bottoms are LOCAL MAXIMA of hip_position_cm, and standing peaks
are LOCAL MINIMA.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.signal import find_peaks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def segment_set(
    data: dict | str | Path,
    *,
    min_depth_cm: float = 10.0,
    min_rep_distance_s: float = 1.0,
    active_velocity_threshold_cm_s: float = 3.0,
) -> dict:
    """Segment a set's plot data into precise rep boundaries.

    Args:
        data: Either a dict with keys ``timestamps``, ``hip_position_cm``,
            ``hip_velocity_cm_s``; or a path to the ``set*_plot_data.json``
            file.
        min_depth_cm: Minimum hip displacement (prominence) for a peak to
            count as a squat rep.  Filters small oscillations.
        min_rep_distance_s: Minimum elapsed time between consecutive squat
            bottoms.
        active_velocity_threshold_cm_s: Absolute velocity above which the
            athlete is considered "actively moving" (used for pause / phase
            detection).

    Returns:
        Dict with ``total_reps``, ``reps`` (list of per-rep metric dicts),
        and ``summary``.
    """
    if isinstance(data, (str, Path)):
        with open(data) as f:
            data = json.load(f)

    ts = np.asarray(data["timestamps"], dtype=np.float64)
    pos = np.asarray(data["hip_position_cm"], dtype=np.float64)
    vel = np.asarray(data["hip_velocity_cm_s"], dtype=np.float64)

    dt = float(np.median(np.diff(ts)))
    min_dist = max(1, int(min_rep_distance_s / dt))
    vel_thresh = active_velocity_threshold_cm_s

    # ------------------------------------------------------------------
    # 1. Find squat bottoms (local maxima of position — least negative)
    # ------------------------------------------------------------------
    bottom_idx, _ = find_peaks(pos, prominence=min_depth_cm, distance=min_dist)

    if len(bottom_idx) == 0:
        return {"total_reps": 0, "reps": [], "summary": {}}

    # ------------------------------------------------------------------
    # 2. Find standing boundaries between consecutive bottoms
    #    (the most-negative position point in each inter-bottom interval)
    # ------------------------------------------------------------------
    boundaries = _find_standing_boundaries(pos, bottom_idx)

    # ------------------------------------------------------------------
    # 3. Refine phase boundaries using velocity
    #    For each rep find:
    #      descent_onset  – velocity first exceeds +threshold (leaving standing)
    #      ascent_end     – velocity last exceeds -threshold (reaching standing)
    #    The gap between ascent_end[i] and descent_onset[i+1] is rest time.
    # ------------------------------------------------------------------
    reps: list[dict] = []
    for i, bi in enumerate(bottom_idx):
        start = boundaries[i]
        end = boundaries[i + 1]

        # --- descent onset: first index in [start, bi] where vel > +thresh
        descent_onset = start
        for j in range(start, bi):
            if vel[j] >= vel_thresh:
                descent_onset = j
                break

        # --- ascent end: last index in [bi, end] where vel < -thresh, then +1
        ascent_end = end
        for j in range(end, bi, -1):
            if vel[j] <= -vel_thresh:
                ascent_end = min(j + 1, end)
                break

        # --- average velocities (magnitude) for descent and ascent ---
        descent_vel = vel[descent_onset : bi + 1]
        ascent_vel = vel[bi : ascent_end + 1]
        avg_descent_vel = float(np.mean(descent_vel)) if len(descent_vel) > 0 else 0.0
        avg_ascent_vel = float(np.mean(np.abs(ascent_vel))) if len(ascent_vel) > 0 else 0.0

        # --- time at bottom: duration where |vel| < bottom_vel_thresh near bottom ---
        bottom_vel_thresh = 5.0  # cm/s
        bottom_lo = bi
        while bottom_lo > descent_onset and abs(vel[bottom_lo - 1]) < bottom_vel_thresh:
            bottom_lo -= 1
        bottom_hi = bi
        while bottom_hi < ascent_end and abs(vel[bottom_hi + 1]) < bottom_vel_thresh:
            bottom_hi += 1
        time_at_bottom = float(ts[bottom_hi] - ts[bottom_lo])

        rep = {
            "rep_number": i + 1,
            # boundary indices (standing-peak to standing-peak)
            "start_idx": int(start),
            "bottom_idx": int(bi),
            "end_idx": int(end),
            # phase indices (velocity-informed)
            "descent_onset_idx": int(descent_onset),
            "ascent_end_idx": int(ascent_end),
            # timestamps
            "start_time_s": _r(ts[start]),
            "descent_onset_time_s": _r(ts[descent_onset]),
            "bottom_time_s": _r(ts[bi]),
            "ascent_end_time_s": _r(ts[ascent_end]),
            "end_time_s": _r(ts[end]),
            # position
            "standing_position_cm": _r(pos[start]),
            "bottom_position_cm": _r(pos[bi]),
            "depth_cm": _r(abs(pos[start] - pos[bi])),
            # timing
            "total_duration_s": _r(ts[end] - ts[start]),
            "active_duration_s": _r(ts[ascent_end] - ts[descent_onset]),
            "descent_time_s": _r(ts[bi] - ts[descent_onset]),
            "ascent_time_s": _r(ts[ascent_end] - ts[bi]),
            "time_at_bottom_s": _r(time_at_bottom),
            # velocity
            "peak_descent_velocity_cm_s": _r(np.max(vel[start : bi + 1])),
            "peak_ascent_velocity_cm_s": _r(np.min(vel[bi : end + 1])),
            "avg_descent_velocity_cm_s": _r(avg_descent_vel),
            "avg_ascent_velocity_cm_s": _r(avg_ascent_vel),
        }
        reps.append(rep)

    # ------------------------------------------------------------------
    # 4. Compute rest at top / pause between reps
    # ------------------------------------------------------------------
    # First rep: rest at top = time from data start to descent onset
    reps[0]["rest_at_top_s"] = _r(max(0.0, reps[0]["descent_onset_time_s"] - ts[0]))
    for i in range(len(reps) - 1):
        rest = reps[i + 1]["descent_onset_time_s"] - reps[i]["ascent_end_time_s"]
        reps[i]["rest_after_s"] = _r(max(0.0, rest))
        reps[i + 1]["rest_at_top_s"] = _r(max(0.0, rest))

    # ------------------------------------------------------------------
    # 5. Build summary
    # ------------------------------------------------------------------
    depths = [r["depth_cm"] for r in reps]
    active_durs = [r["active_duration_s"] for r in reps]
    descent_ts = [r["descent_time_s"] for r in reps]
    ascent_ts = [r["ascent_time_s"] for r in reps]
    avg_descent_vels = [r["avg_descent_velocity_cm_s"] for r in reps]
    avg_ascent_vels = [r["avg_ascent_velocity_cm_s"] for r in reps]
    bottom_times = [r["time_at_bottom_s"] for r in reps]

    # Pause detection: rest > 1.8× median inter-rep rest
    rest_vals = [r.get("rest_after_s", 0) for r in reps[:-1]]
    pauses = []
    if len(rest_vals) >= 2:
        median_rest = float(np.median(rest_vals))
        for i, rv in enumerate(rest_vals):
            if rv > median_rest * 1.8:
                pauses.append({
                    "after_rep": i + 1,
                    "rest_s": _r(rv),
                    "typical_rest_s": _r(median_rest),
                })

    summary = {
        "avg_depth_cm": _r(np.mean(depths)),
        "std_depth_cm": _r(np.std(depths)),
        "min_depth_cm": _r(np.min(depths)),
        "max_depth_cm": _r(np.max(depths)),
        "shallowest_rep": int(np.argmin(depths)) + 1,
        "deepest_rep": int(np.argmax(depths)) + 1,
        "avg_descent_velocity_cm_s": _r(np.mean(avg_descent_vels)),
        "avg_ascent_velocity_cm_s": _r(np.mean(avg_ascent_vels)),
        "peak_descent_velocity_cm_s": _r(max(r["peak_descent_velocity_cm_s"] for r in reps)),
        "peak_ascent_velocity_cm_s": _r(max(abs(r["peak_ascent_velocity_cm_s"]) for r in reps)),
        "avg_time_at_bottom_s": _r(np.mean(bottom_times)),
        "avg_active_duration_s": _r(np.mean(active_durs)),
        "avg_descent_time_s": _r(np.mean(descent_ts)),
        "avg_ascent_time_s": _r(np.mean(ascent_ts)),
        "tempo_consistency": _r(1.0 - np.std(active_durs) / np.mean(active_durs))
            if np.mean(active_durs) > 0 else 0.0,
        "depth_consistency": _r(1.0 - np.std(depths) / np.mean(depths))
            if np.mean(depths) > 0 else 0.0,
    }
    if pauses:
        summary["pauses"] = pauses

    return {
        "total_reps": len(reps),
        "reps": reps,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_standing_boundaries(
    pos: np.ndarray, bottom_idx: np.ndarray
) -> list[int]:
    """Find the most-negative position (standing peak) between each pair of
    consecutive squat bottoms, plus before the first and after the last."""
    boundaries: list[int] = []

    # Before first bottom
    seg = pos[: bottom_idx[0]]
    boundaries.append(int(np.argmin(seg)))

    # Between consecutive bottoms
    for i in range(len(bottom_idx) - 1):
        lo, hi = int(bottom_idx[i]), int(bottom_idx[i + 1])
        seg = pos[lo : hi + 1]
        boundaries.append(int(np.argmin(seg)) + lo)

    # After last bottom
    seg = pos[int(bottom_idx[-1]) :]
    boundaries.append(int(np.argmin(seg)) + int(bottom_idx[-1]))

    return boundaries


def _r(val: float, ndigits: int = 3) -> float:
    """Round a float for clean JSON output."""
    return round(float(val), ndigits)


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_segmentation(
    data: dict | str | Path,
    result: dict | None = None,
    *,
    save_path: str | Path | None = None,
    show: bool = False,
) -> None:
    """Plot hip position + velocity with labelled squat bottoms, standing
    peaks, and rep boundaries.

    Args:
        data: Plot data dict or path to JSON file.
        result: Output from ``segment_set()``.  If *None*, ``segment_set``
            is called automatically.
        save_path: Where to save the figure.  If *None*, saves next to
            the input JSON (or ``segmentation_plot.png`` in cwd).
        show: If *True*, call ``plt.show()`` (blocks).
    """
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch

    json_path = None
    if isinstance(data, (str, Path)):
        json_path = Path(data)
        with open(data) as f:
            data = json.load(f)

    if result is None:
        result = segment_set(data)

    ts = np.asarray(data["timestamps"], dtype=np.float64)
    pos = np.asarray(data["hip_position_cm"], dtype=np.float64)
    vel = np.asarray(data["hip_velocity_cm_s"], dtype=np.float64)
    reps = result["reps"]

    fig, (ax_pos, ax_vel) = plt.subplots(
        2, 1, figsize=(14, 8), sharex=True,
        gridspec_kw={"height_ratios": [3, 2]},
    )

    # --- Position subplot ---
    ax_pos.plot(ts, pos, color="#2196F3", linewidth=1.5, label="Hip Position")
    ax_pos.set_ylabel("Hip Position (cm, rel. ankle)")
    ax_pos.set_title("Rep Segmentation — Hip Position & Velocity")
    ax_pos.invert_yaxis()
    ax_pos.grid(True, alpha=0.2)

    for rep in reps:
        bi = rep["bottom_idx"]
        si = rep["start_idx"]
        ei = rep["end_idx"]

        # Shade the active rep region
        ax_pos.axvspan(
            ts[rep["descent_onset_idx"]], ts[rep["ascent_end_idx"]],
            alpha=0.08, color="#4CAF50",
        )

        # Squat bottom marker (triangle pointing up since axis is inverted)
        ax_pos.plot(
            ts[bi], pos[bi], "v", color="#F44336", markersize=10, zorder=5,
        )
        ax_pos.annotate(
            f"Bottom {rep['rep_number']}\n{pos[bi]:.1f} cm",
            (ts[bi], pos[bi]),
            textcoords="offset points", xytext=(0, 18),
            fontsize=7, ha="center", color="#F44336", fontweight="bold",
        )

        # Standing peak marker
        ax_pos.plot(
            ts[si], pos[si], "^", color="#1565C0", markersize=8, zorder=5,
        )
        ax_pos.annotate(
            f"Stand\n{pos[si]:.1f}",
            (ts[si], pos[si]),
            textcoords="offset points", xytext=(0, -20),
            fontsize=6.5, ha="center", color="#1565C0",
        )

        # Depth annotation (arrow from standing to bottom)
        mid_t = (ts[si] + ts[bi]) / 2
        ax_pos.annotate(
            f"{rep['depth_cm']:.1f} cm",
            xy=(mid_t, (pos[si] + pos[bi]) / 2),
            fontsize=7, ha="center", color="#555",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#ccc", alpha=0.8),
        )

    # Mark end standing peak of last rep
    if reps:
        last = reps[-1]
        ei = last["end_idx"]
        ax_pos.plot(ts[ei], pos[ei], "^", color="#1565C0", markersize=8, zorder=5)

    # Mark original rep events from pipeline (if present)
    rep_events = data.get("rep_events", [])
    if rep_events:
        t0_abs = None
        if rep_events and "timestamp" in rep_events[0]:
            # Convert absolute timestamps to relative
            # Infer offset from data: first rep event should be near a bottom
            t0_abs = rep_events[0]["timestamp"] - ts[reps[0]["bottom_idx"]] if reps else 0
        for ev in rep_events:
            rt = ev["timestamp"] - t0_abs if t0_abs is not None else ev["timestamp"]
            if 0 <= rt <= ts[-1]:
                ax_pos.axvline(x=rt, color="green", linestyle="--", alpha=0.35, linewidth=0.8)

    ax_pos.legend(loc="upper right", fontsize=8)

    # --- Velocity subplot (negated so descent = negative, ascent = positive) ---
    vel_display = -vel
    ax_vel.plot(ts, vel_display, color="#FF9800", linewidth=1.0, alpha=0.9, label="Hip Velocity")
    ax_vel.axhline(y=0, color="black", linewidth=0.5)
    ax_vel.set_xlabel("Time (s)")
    ax_vel.set_ylabel("Velocity (cm/s)")
    ax_vel.grid(True, alpha=0.2)

    for rep in reps:
        bi = rep["bottom_idx"]
        # Mark velocity zero crossing at bottom
        ax_vel.plot(ts[bi], vel_display[bi], "o", color="#F44336", markersize=5, zorder=5)

        # Shade active region
        ax_vel.axvspan(
            ts[rep["descent_onset_idx"]], ts[rep["ascent_end_idx"]],
            alpha=0.08, color="#4CAF50",
        )

    # Annotate pauses
    summary = result.get("summary", {})
    for pause in summary.get("pauses", []):
        rep_i = pause["after_rep"] - 1
        if rep_i < len(reps) - 1:
            t_start = reps[rep_i]["ascent_end_time_s"]
            t_end = reps[rep_i + 1]["descent_onset_time_s"]
            mid = (t_start + t_end) / 2
            ax_vel.annotate(
                f"Pause\n{pause['rest_s']:.1f}s",
                (mid, 0), fontsize=8, ha="center", color="#9C27B0",
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", fc="#F3E5F5", ec="#9C27B0", alpha=0.9),
            )

    ax_vel.legend(loc="upper right", fontsize=8)

    plt.tight_layout()

    # Save
    if save_path is None:
        if json_path is not None:
            save_path = json_path.parent / f"set{data.get('set_number', '')}_segmentation.png"
        else:
            save_path = Path("segmentation_plot.png")
    fig.savefig(str(save_path), dpi=150, bbox_inches="tight")
    print(f"Saved: {save_path}")

    if show:
        plt.show()
    plt.close(fig)


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def write_set_report(
    result: dict,
    *,
    set_number: int = 1,
    save_path: str | Path | None = None,
) -> str:
    """Write a structured markdown report of the segmented set for LLM ingestion.

    Args:
        result: Output from ``segment_set()``.
        set_number: Set number for the report header.
        save_path: Where to save the ``.md`` file.  If *None*, returns the
            string without writing.

    Returns:
        The markdown string.
    """
    reps = result["reps"]
    s = result["summary"]
    lines: list[str] = []

    def _ln(text: str = "") -> None:
        lines.append(text)

    _ln(f"# Set {set_number} Analysis")
    _ln()
    _ln(f"Total reps: {result['total_reps']}")
    _ln()

    # --- Set-level summary ---
    _ln("## Set Summary")
    _ln()
    _ln(f"- Depth std: {s['std_depth_cm']} cm")
    _ln(f"- Shallowest rep: Rep {s['shallowest_rep']}")
    _ln(f"- Deepest rep: Rep {s['deepest_rep']}")
    _ln(f"- Peak downward velocity: {s['peak_descent_velocity_cm_s']} cm/s")
    _ln(f"- Peak upward velocity: {s['peak_ascent_velocity_cm_s']} cm/s")
    _ln(f"- Average time at bottom: {s['avg_time_at_bottom_s']} s")
    _ln(f"- Average active rep duration: {s['avg_active_duration_s']} s")
    _ln(f"- Average descent time: {s['avg_descent_time_s']} s")
    _ln(f"- Average ascent time: {s['avg_ascent_time_s']} s")
    _ln(f"- Tempo consistency: {s['tempo_consistency']} (1.0 = perfect)")
    _ln(f"- Depth consistency: {s['depth_consistency']} (1.0 = perfect)")

    for pause in s.get("pauses", []):
        _ln(f"- Pause detected after rep {pause['after_rep']}: "
            f"{pause['rest_s']}s rest (typical: {pause['typical_rest_s']}s)")
    _ln()

    # --- Per-rep table ---
    _ln("## Per-Rep Breakdown")
    _ln()
    _ln("| Rep | Depth (cm) | Avg Down (cm/s) | Avg Up (cm/s) | Descent (s) | Ascent (s) | Bottom (s) | Rest at Top (s) |")
    _ln("|-----|-----------|----------------|--------------|------------|-----------|-----------|----------------|")
    for r in reps:
        _ln(
            f"| {r['rep_number']} "
            f"| {r['depth_cm']} "
            f"| {r['avg_descent_velocity_cm_s']} "
            f"| {r['avg_ascent_velocity_cm_s']} "
            f"| {r['descent_time_s']} "
            f"| {r['ascent_time_s']} "
            f"| {r['time_at_bottom_s']} "
            f"| {r.get('rest_at_top_s', '-')} |"
        )
    _ln()

    # --- Per-rep details ---
    _ln("## Rep Details")
    _ln()
    avg_depth = s["avg_depth_cm"]
    for r in reps:
        _ln(f"### Rep {r['rep_number']}")
        pct_diff = ((r["depth_cm"] - avg_depth) / avg_depth) * 100 if avg_depth > 0 else 0
        depth_note = ""
        if r["rep_number"] == s["shallowest_rep"]:
            depth_note = f" (shallowest, {abs(pct_diff):.0f}% below avg)"
        elif r["rep_number"] == s["deepest_rep"]:
            depth_note = f" (deepest, {abs(pct_diff):.0f}% above avg)"
        _ln(f"- Depth: {r['depth_cm']} cm{depth_note}")
        _ln(f"- Downward velocity: avg {r['avg_descent_velocity_cm_s']} cm/s, peak {r['peak_descent_velocity_cm_s']} cm/s")
        _ln(f"- Upward velocity: avg {r['avg_ascent_velocity_cm_s']} cm/s, peak {abs(r['peak_ascent_velocity_cm_s'])} cm/s")
        _ln(f"- Descent: {r['descent_time_s']}s | Ascent: {r['ascent_time_s']}s | Active: {r['active_duration_s']}s")
        _ln(f"- Time at bottom: {r['time_at_bottom_s']}s")
        _ln(f"- Rest at top before this rep: {r.get('rest_at_top_s', 'N/A')}s")
        if "rest_after_s" in r:
            _ln(f"- Rest after: {r['rest_after_s']}s")
        _ln()

    md = "\n".join(lines)

    if save_path is not None:
        Path(save_path).write_text(md)
        print(f"Saved: {save_path}")

    return md
