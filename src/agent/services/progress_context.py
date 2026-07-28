"""
Pure formatters that turn persisted biomechanics data into short text
the coaching LLM can relay verbatim: greeting context, recap comparisons,
and the main-menu progress report. No DB access here.
"""

from __future__ import annotations

MIN_DIMENSION_DELTA_POINTS = 3
TREND_MIN_SETS = 4
RECENT_WINDOW_SETS = 3

DIMENSION_LABELS = {
    "depth": "depth",
    "trunk_control": "trunk control",
    "knee_tracking": "knee tracking",
    "symmetry": "symmetry",
}

FAULT_LABELS = {
    "knee_valgus": "knees caving in",
    "butt_wink": "butt wink",
    "forward_lean": "leaning forward",
    "shallow_depth": "shallow depth",
    "asymmetric_loading": "uneven side loading",
}


def _days_ago_phrase(days_ago: int) -> str:
    if days_ago == 0:
        return "earlier today"
    if days_ago == 1:
        return "yesterday"
    return f"{days_ago} days ago"


def _fault_label(fault_type: str) -> str:
    return FAULT_LABELS.get(fault_type, fault_type.replace("_", " "))


def _weakest_dimension(per_dimension: dict) -> tuple[str, float] | None:
    if not per_dimension:
        return None
    key = min(per_dimension, key=per_dimension.get)
    return DIMENSION_LABELS.get(key, key), per_dimension[key]


def build_greeting_progress_line(baseline: dict | None) -> str | None:
    """One compact context block for the workout greeting."""
    if not baseline:
        return None
    parts = [
        f"PROGRESS CONTEXT: last squat session was {_days_ago_phrase(baseline.get('days_ago', 0))}"
    ]
    if baseline.get("mean_score") is not None:
        parts.append(f"form score {round(baseline['mean_score'] * 100)}/100")
    if baseline.get("total_reps"):
        parts.append(
            f"{baseline['total_reps']} reps across {baseline.get('total_sets', 0)} sets"
        )
    weakest = _weakest_dimension(baseline.get("per_dimension") or {})
    if weakest is not None:
        label, value = weakest
        parts.append(f"weakest area was {label} ({round(value * 100)}/100)")
    if baseline.get("avg_knee_valgus_deg") is not None:
        parts.append(
            f"knees caved about {baseline['avg_knee_valgus_deg']} degrees on average"
        )
    top_faults = baseline.get("top_faults") or []
    if top_faults:
        parts.append(f"most common fault: {_fault_label(top_faults[0]['fault_type'])}")
    return (
        ", ".join(parts) + ". "
        "Weave ONE brief reference to this into the greeting as today's goal "
        "(e.g. 'last time your knee tracking was the weak spot — today we clean that up')."
    )


def build_progress_comparison_lines(
    baseline: dict | None, scoring: dict | None
) -> list[str]:
    """Precomputed vs-last-session deltas for the set recap prompt."""
    if not baseline or not scoring:
        return []
    lines: list[str] = []

    # Deltas derive from the rounded endpoints so the spoken numbers
    # always agree ("72 -> 78" is always "+6")
    base_mean = baseline.get("mean_score")
    current_mean = scoring.get("mean_score")
    if base_mean is not None and current_mean is not None:
        base_points = round(base_mean * 100)
        current_points = round(current_mean * 100)
        lines.append(
            f"\nVS LAST SESSION ({_days_ago_phrase(baseline.get('days_ago', 0))}): "
            f"overall {base_points} -> {current_points} "
            f"({current_points - base_points:+d} points)"
        )

    base_dims = baseline.get("per_dimension") or {}
    current_dims = scoring.get("per_dimension") or {}
    dim_lines = []
    for key, label in DIMENSION_LABELS.items():
        base_value = base_dims.get(key)
        current_value = current_dims.get(key)
        if base_value is None or current_value is None:
            continue
        base_points = round(base_value * 100)
        current_points = round(current_value * 100)
        if abs(current_points - base_points) >= MIN_DIMENSION_DELTA_POINTS:
            dim_lines.append(
                f"{label}: {base_points} -> {current_points} "
                f"({current_points - base_points:+d})"
            )
    if dim_lines:
        lines.append("Changed vs last session: " + "; ".join(dim_lines) + ".")

    if lines:
        lines.append(
            "If something improved vs last session, call it out specifically — "
            "this is the payoff of their training."
        )
    return lines


def build_session_comparison_line(
    baseline: dict | None, session_mean_score: float | None
) -> str | None:
    """One-line whole-session comparison for the exercise recap."""
    if not baseline or session_mean_score is None:
        return None
    base_mean = baseline.get("mean_score")
    if base_mean is None:
        return None
    base_points = round(base_mean * 100)
    current_points = round(session_mean_score * 100)
    delta_points = current_points - base_points
    when = _days_ago_phrase(baseline.get("days_ago", 0))
    if delta_points > 0:
        return (
            f"Session-over-session: {delta_points} points better than last session "
            f"({when}: {base_points} -> today: {current_points})."
        )
    if delta_points < 0:
        return (
            f"Session-over-session: {abs(delta_points)} points below last session "
            f"({when}: {base_points} -> today: {current_points})."
        )
    return f"Session-over-session: matched last session's form score ({base_points}/100)."


def build_progress_report(
    score_rows: list[dict], baseline: dict | None
) -> str:
    """Text progress report for the main-menu view_progress tool."""
    if not score_rows:
        return (
            "No squat sessions recorded yet. Their progress tracking starts "
            "with their first workout."
        )
    lines = [f"{len(score_rows)} squat sets recorded."]

    if baseline:
        summary = f"Last session: {_days_ago_phrase(baseline.get('days_ago', 0))}"
        if baseline.get("mean_score") is not None:
            summary += f", form score {round(baseline['mean_score'] * 100)}/100"
        if baseline.get("total_reps"):
            summary += (
                f", {baseline['total_reps']} reps across "
                f"{baseline.get('total_sets', 0)} sets"
            )
        lines.append(summary + ".")

    def _window_mean(rows: list[dict], key: str) -> float | None:
        values = [row[key] for row in rows if row.get(key) is not None]
        if not values:
            return None
        return sum(values) / len(values)

    early_mean = _window_mean(score_rows[:RECENT_WINDOW_SETS], "mean_score")
    recent_mean = _window_mean(score_rows[-RECENT_WINDOW_SETS:], "mean_score")
    if (
        len(score_rows) >= TREND_MIN_SETS
        and early_mean is not None
        and recent_mean is not None
    ):
        early_points = round(early_mean * 100)
        recent_points = round(recent_mean * 100)
        lines.append(
            f"Form score trend: {early_points} -> {recent_points} "
            f"({recent_points - early_points:+d} points from their first sets to their recent ones)."
        )

    recent_rows = score_rows[-RECENT_WINDOW_SETS:]
    dimension_keys = (
        ("depth", "depth"),
        ("trunk control", "trunk_control"),
        ("knee tracking", "knee_tracking"),
        ("symmetry", "symmetry"),
    )
    current_dims = {}
    for label, key in dimension_keys:
        value = _window_mean(recent_rows, key)
        if value is not None:
            current_dims[label] = value
    if current_dims:
        profile = ", ".join(
            f"{label} {round(value * 100)}" for label, value in current_dims.items()
        )
        lines.append(f"Current form profile (out of 100): {profile}.")
        weakest_label = min(current_dims, key=current_dims.get)
        lines.append(f"Biggest opportunity: {weakest_label}.")

    if baseline and baseline.get("top_faults"):
        top = baseline["top_faults"][0]
        lines.append(
            f"Most common fault last session: {_fault_label(top['fault_type'])} "
            f"({top['count']} reps)."
        )
    return "\n".join(lines)
