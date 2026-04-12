from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

from program_generator_v5.schemas import BuiltProgram

from .schemas import BlockPlanV7, CandidateScore, KGExercise, ProgramDirectiveV7, SessionSlot


def score_candidate(
    exercise: KGExercise,
    slot: SessionSlot,
    directive: ProgramDirectiveV7,
    state: dict[str, Any],
) -> CandidateScore:
    components: dict[str, float] = {}
    rationale: list[str] = []

    primary_muscles = list(exercise.stimulus.get("primary_muscles", []))
    weekly_deficits = state.get("weekly_deficits", {})
    prior_slot_family = state.get("prior_slot_family")
    used_family_counts = state.get("used_family_counts", {})
    used_in_week = set(state.get("used_in_week", set()))
    anchor_family_ids = set(state.get("anchor_family_ids", []))
    remaining_minutes = state.get("remaining_minutes", 60)

    slot_fit = 12.0
    if slot.required_pattern and exercise.movement_pattern == slot.required_pattern:
        slot_fit += 16.0
    if slot.slot_kind == "power" and exercise.exercise_type in {"power", "plyometric"}:
        slot_fit += 10.0
    if slot.slot_kind == "isolation" and exercise.exercise_type == "isolation":
        slot_fit += 7.0
    if slot.slot_kind == "anchor" and exercise.exercise_type == "heavy_compound":
        slot_fit += 12.0
    if slot.slot_kind == "prehab" and exercise.canonical_id in directive.derived_context.preferred_prehab_ids:
        slot_fit += 10.0
    components["slot_fit"] = slot_fit

    volume_fill = 0.0
    for muscle in primary_muscles:
        deficit = weekly_deficits.get(muscle, 0.0)
        volume_fill += min(deficit, float(slot.max_sets))
    if exercise.exercise_type == "isolation":
        volume_fill *= 0.9
    components["volume_fill"] = volume_fill
    if volume_fill > 0:
        rationale.append("fills_current_volume_deficit")

    progression_continuity = 0.0
    if prior_slot_family and prior_slot_family == exercise.family_id:
        progression_continuity += 9.0
        rationale.append("matches_prior_week_family")
    if exercise.family_id in anchor_family_ids:
        progression_continuity += 5.0
    if exercise.canonical_id in slot.preferred_canonical_ids:
        progression_continuity += 5.0
    if exercise.family_id in slot.preferred_family_ids:
        progression_continuity += 4.0
    components["progression_continuity"] = progression_continuity

    fatigue = 0.0
    systemic = exercise.fatigue.get("systemic_fatigue", "moderate")
    if systemic == "low":
        fatigue += 5.0
    elif systemic == "moderate":
        fatigue += 2.0
    else:
        fatigue -= 4.0
    if exercise.fatigue.get("axial_load") and state.get("session_axial_count", 0) >= 1:
        fatigue -= 4.0
    if exercise.fatigue.get("grip_load") == "high" and state.get("session_grip_count", 0) >= 1:
        fatigue -= 2.5
    if directive.derived_context.fatigue_sensitivity in {"high", "moderate_high"} and systemic == "high":
        fatigue -= 3.0
    components["fatigue_compatibility"] = fatigue

    preference = 0.0
    if exercise.canonical_id in directive.soft_preferences.liked_exercise_ids:
        preference += 8.0
        rationale.append("matches_user_preference")
    if exercise.canonical_id in directive.soft_preferences.disliked_exercise_ids:
        preference -= 8.0
    if exercise.movement_pattern in directive.soft_preferences.preferred_movement_patterns:
        preference += 3.0
    components["user_preference"] = preference

    novelty = 0.0
    if exercise.canonical_id in used_in_week:
        novelty -= 6.0
    else:
        novelty += 2.0
    if used_family_counts.get(exercise.family_id, 0) >= 2:
        novelty -= 3.0
    if directive.soft_preferences.novelty_tolerance == "low" and prior_slot_family == exercise.family_id:
        novelty += 2.0
    if directive.soft_preferences.novelty_tolerance == "high" and exercise.canonical_id not in used_in_week:
        novelty += 2.0
    components["novelty"] = novelty

    sport_specificity = 0.0
    if exercise.movement_pattern in directive.derived_context.movement_priorities:
        sport_specificity += 4.0
    if exercise.canonical_id in directive.derived_context.preferred_prehab_ids:
        sport_specificity += 5.0
    components["sport_specificity"] = sport_specificity

    time_efficiency = 0.0
    if remaining_minutes <= 20 and exercise.exercise_type == "isolation":
        time_efficiency -= 1.0
    elif remaining_minutes <= 20:
        time_efficiency += 2.0
    if not exercise.bilateral and remaining_minutes <= 20:
        time_efficiency -= 1.5
    components["time_efficiency"] = time_efficiency

    sfr_bonus = float(exercise.metadata.get("sfr_rating", 0.0))
    components["sfr_bonus"] = sfr_bonus

    total = sum(components.values())
    return CandidateScore(
        canonical_id=exercise.canonical_id,
        total=round(total, 3),
        components={key: round(value, 3) for key, value in components.items()},
        rationale=rationale,
    )


def score_workout_coherence(workout) -> float:
    total = 50.0
    patterns = [exercise.movement_pattern.value for exercise in workout.exercises]
    types = [exercise.exercise_type.value for exercise in workout.exercises]

    if len(patterns) != len(set(patterns)):
        duplicates = len(patterns) - len(set(patterns))
        total -= duplicates * 2.5
    if types and types[0] == "isolation":
        total -= 6.0
    if len(types) >= 2 and types[0] in {"power", "plyometric"}:
        total += 4.0
    if workout.estimated_duration_minutes > 70:
        total -= min(10.0, workout.estimated_duration_minutes - 70)
    return max(0.0, round(total, 2))


def compute_quality_metrics(
    program: BuiltProgram,
    block_plan: BlockPlanV7,
    assembly_trace: Iterable,
) -> dict[str, float]:
    trace_entries = list(assembly_trace)
    unique_exercise_count = len({
        exercise.exercise_id
        for week in program.weeks
        for workout in week.workouts
        for exercise in workout.exercises
    })

    weekly_adherence = []
    fatigue_balance_penalties = []
    workout_scores = []
    anchor_counter = Counter(entry.selected_family_id for entry in trace_entries if entry.slot_id.endswith("_0"))

    for week in program.weeks:
        for target_muscle, target in week.weekly_volume_target.items():
            if target <= 0:
                continue
            actual = week.weekly_volume_actual.get(target_muscle, 0.0)
            weekly_adherence.append(max(0.0, 1.0 - abs(actual - target) / max(target, 1.0)))

        heavy_days = 0
        for workout in week.workouts:
            workout_scores.append(score_workout_coherence(workout))
            if sum(1 for exercise in workout.exercises if exercise.exercise_type.value == "heavy_compound") >= 2:
                heavy_days += 1
        fatigue_balance_penalties.append(max(0, heavy_days - 2) / 2.0)

    pattern_counter = Counter(
        exercise.movement_pattern.value
        for week in program.weeks
        for workout in week.workouts
        for exercise in workout.exercises
    )
    pattern_coverage_score = min(1.0, len(pattern_counter) / 8.0)
    anchor_stability_score = 0.0
    if anchor_counter:
        dominant_anchor = anchor_counter.most_common(1)[0][1]
        anchor_stability_score = dominant_anchor / max(1, len(program.weeks))

    return {
        "unique_exercise_count": float(unique_exercise_count),
        "weekly_volume_alignment": round(sum(weekly_adherence) / max(1, len(weekly_adherence)), 4),
        "fatigue_balance_score": round(max(0.0, 1.0 - (sum(fatigue_balance_penalties) / max(1, len(fatigue_balance_penalties)))), 4),
        "pattern_coverage_score": round(pattern_coverage_score, 4),
        "anchor_stability_score": round(anchor_stability_score, 4),
        "avg_workout_coherence": round(sum(workout_scores) / max(1, len(workout_scores)), 4),
        "planned_week_count": float(len(block_plan.weeks)),
    }


def build_validation_score(metrics: dict[str, float], issues_count: int) -> float:
    base = (
        metrics.get("weekly_volume_alignment", 0.0) * 35.0
        + metrics.get("fatigue_balance_score", 0.0) * 25.0
        + metrics.get("pattern_coverage_score", 0.0) * 15.0
        + metrics.get("anchor_stability_score", 0.0) * 15.0
        + min(1.0, metrics.get("avg_workout_coherence", 0.0) / 60.0) * 10.0
    )
    return round(max(0.0, base - (issues_count * 1.75)), 2)
