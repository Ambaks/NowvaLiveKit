"""Per-rep quality scoring for squat biomechanics.

Scores each rep on 4 dimensions (depth, trunk control, knee tracking,
symmetry) and produces a weighted composite score.
All scores are in [0, 1] where 1.0 = perfect.
"""

from __future__ import annotations

from .graph.evidence_tests import _clamp, expected_trunk_lean_geometric
from .types import RepKinematicSummary, RepScore, SetScoreSummary

WEIGHT_DEPTH = 0.48
WEIGHT_TRUNK = 0.23
WEIGHT_KNEES = 0.18
WEIGHT_SYMMETRY = 0.11

TRUNK_TOLERANCE_DEGREES = 3.0
TRUNK_DECAY_RANGE_DEGREES = 20.0

KNEE_PERFECT_ZONE_DEGREES = 4.0
KNEE_DECAY_RANGE_DEGREES = 12.0

SYMMETRY_TOLERANCE_CM = 1.0
SYMMETRY_DECAY_RANGE_CM = 5.0


def score_depth(
    rep: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    hip_y_standing = (rep.hip_y_l_at_top + rep.hip_y_r_at_top) / 2.0
    hip_y_bottom = (rep.hip_y_l_at_bottom + rep.hip_y_r_at_bottom) / 2.0
    knee_y_bottom = (rep.knee_y_l_at_bottom + rep.knee_y_r_at_bottom) / 2.0

    denominator = hip_y_standing - knee_y_bottom
    if denominator <= 0.0:
        return 0.0

    return _clamp((hip_y_standing - hip_y_bottom) / denominator)


def score_trunk_control(
    rep: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    expected_lean = expected_trunk_lean_geometric(anthro)
    deviation = abs(rep.trunk_pitch_at_bottom - expected_lean)

    if deviation <= TRUNK_TOLERANCE_DEGREES:
        return 1.0
    return _clamp(
        1.0 - (deviation - TRUNK_TOLERANCE_DEGREES) / TRUNK_DECAY_RANGE_DEGREES
    )


def _score_single_knee(deviation_deg: float) -> float:
    abs_deviation = abs(deviation_deg)
    if abs_deviation <= KNEE_PERFECT_ZONE_DEGREES:
        return 1.0
    return _clamp(
        1.0 - (abs_deviation - KNEE_PERFECT_ZONE_DEGREES) / KNEE_DECAY_RANGE_DEGREES
    )


def score_knee_tracking(
    rep: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    return 0.5 * _score_single_knee(rep.knee_valgus_l) + 0.5 * _score_single_knee(rep.knee_valgus_r)


def score_symmetry(
    rep: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    asymmetry_cm = abs(rep.hip_y_l_at_bottom - rep.hip_y_r_at_bottom)

    if asymmetry_cm <= SYMMETRY_TOLERANCE_CM:
        return 1.0
    return _clamp(
        1.0 - (asymmetry_cm - SYMMETRY_TOLERANCE_CM) / SYMMETRY_DECAY_RANGE_CM
    )


def score_rep(
    rep: RepKinematicSummary, anthro: dict, rom: dict
) -> RepScore:
    depth = score_depth(rep, anthro, rom)
    trunk_control = score_trunk_control(rep, anthro, rom)
    knee_tracking = score_knee_tracking(rep, anthro, rom)
    symmetry = score_symmetry(rep, anthro, rom)

    composite = (
        depth * WEIGHT_DEPTH
        + trunk_control * WEIGHT_TRUNK
        + knee_tracking * WEIGHT_KNEES
        + symmetry * WEIGHT_SYMMETRY
    )

    return RepScore(
        rep_number=rep.rep_number,
        depth_score=round(depth, 3),
        trunk_control_score=round(trunk_control, 3),
        knee_tracking_score=round(knee_tracking, 3),
        symmetry_score=round(symmetry, 3),
        composite_score=round(composite, 3),
    )


def score_set(
    reps: list[RepKinematicSummary], anthro: dict, rom: dict
) -> SetScoreSummary:
    per_rep_scores = [score_rep(rep, anthro, rom) for rep in reps]
    composites = [score.composite_score for score in per_rep_scores]

    mean_score = sum(composites) / len(composites)
    best = max(per_rep_scores, key=lambda s: s.composite_score)
    worst = min(per_rep_scores, key=lambda s: s.composite_score)

    trend_slope = _compute_trend_slope(composites)

    return SetScoreSummary(
        mean_score=round(mean_score, 3),
        best_rep_number=best.rep_number,
        worst_rep_number=worst.rep_number,
        trend_slope=round(trend_slope, 4),
        per_rep_scores=per_rep_scores,
    )


def _compute_trend_slope(values: list[float]) -> float:
    num_values = len(values)
    if num_values < 2:
        return 0.0

    mean_x = (num_values - 1) / 2.0
    mean_y = sum(values) / num_values

    covariance = sum(
        (index - mean_x) * (value - mean_y)
        for index, value in enumerate(values)
    )
    variance_x = sum((index - mean_x) ** 2 for index in range(num_values))

    if variance_x == 0.0:
        return 0.0
    return covariance / variance_x
