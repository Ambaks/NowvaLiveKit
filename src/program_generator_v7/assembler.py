from __future__ import annotations

import math
from collections import Counter, defaultdict

from program_generator_v5.exercise_library import EXERCISE_LIBRARY
from program_generator_v5.schemas import (
    BuiltProgram,
    BuiltWeek,
    BuiltWorkout,
    ExerciseType,
    PrescribedExercise,
)
from program_generator_v5.utils import (
    build_supersets,
    estimate_session_duration,
    prescribe_exercise,
    sort_exercises_for_session,
)

from .candidate_index import CandidateIndex
from .scoring import score_candidate
from .schemas import AssemblyTraceEntry, BlockPlanV7


EXERCISE_LOOKUP = {exercise.id: exercise for exercise in EXERCISE_LIBRARY}


def assemble_program(
    block_plan: BlockPlanV7,
    snapshot,
) -> tuple[BuiltProgram, list[AssemblyTraceEntry]]:
    candidate_index = CandidateIndex(snapshot)
    built_weeks: list[BuiltWeek] = []
    assembly_trace: list[AssemblyTraceEntry] = []
    prior_week_family_by_slot: dict[str, str] = {}

    for week_plan, volume_week, week_profile in zip(
        block_plan.weeks,
        block_plan.volume_allocation.weeks,
        block_plan.strategy.week_profiles,
    ):
        weekly_remaining = dict(volume_week.weekly_totals)
        week_used_ids: set[str] = set()
        week_family_counts: Counter[str] = Counter()
        workouts: list[BuiltWorkout] = []
        current_week_family_by_slot: dict[str, str] = {}

        for session_skeleton, session_volume in zip(week_plan.sessions, volume_week.sessions):
            preferred_anchor_ids = block_plan.anchor_family_preferences.get(
                f"{week_plan.week_number}:{session_skeleton.session_type}",
                [],
            )
            workout, session_trace = _assemble_session(
                block_plan=block_plan,
                candidate_index=candidate_index,
                week_profile=week_profile,
                week_plan=week_plan,
                session_skeleton=session_skeleton,
                session_volume=session_volume,
                weekly_remaining=weekly_remaining,
                week_used_ids=week_used_ids,
                week_family_counts=week_family_counts,
                prior_week_family_by_slot=prior_week_family_by_slot,
                preferred_anchor_ids=preferred_anchor_ids,
            )
            workouts.append(workout)
            assembly_trace.extend(session_trace)
            for entry in session_trace:
                slot_key = _slot_key(session_skeleton.session_type, entry.slot_id)
                current_week_family_by_slot[slot_key] = entry.selected_family_id

            week_used_ids.update(exercise.exercise_id for exercise in workout.exercises)
            week_family_counts.update(EXERCISE_LOOKUP[exercise.exercise_id].rotation_group for exercise in workout.exercises)
            for muscle, delivered in workout.volume_delivered.items():
                weekly_remaining[muscle] = max(0.0, weekly_remaining.get(muscle, 0.0) - delivered)

        weekly_volume_actual = defaultdict(float)
        for workout in workouts:
            for muscle, delivered in workout.volume_delivered.items():
                weekly_volume_actual[muscle] += delivered

        volume_adherence = {}
        for muscle, target in volume_week.weekly_totals.items():
            actual = weekly_volume_actual.get(muscle, 0.0)
            if target > 0:
                volume_adherence[muscle] = actual / target
            else:
                volume_adherence[muscle] = 1.0

        built_weeks.append(BuiltWeek(
            week_number=week_plan.week_number,
            mesocycle=week_profile.mesocycle_number,
            phase=week_plan.phase_name,
            phase_name=week_plan.phase_name,
            workouts=workouts,
            weekly_volume_actual=dict(weekly_volume_actual),
            weekly_volume_target=dict(volume_week.weekly_totals),
            volume_adherence=volume_adherence,
            week_focus=week_plan.week_focus,
            recovery_notes="Respect the programmed fatigue budget and keep execution quality high.",
        ))
        prior_week_family_by_slot = current_week_family_by_slot

    total_sets = sum(workout.total_sets for week in built_weeks for workout in week.workouts)
    total_workouts = sum(len(week.workouts) for week in built_weeks)
    unique_exercises = len({
        exercise.exercise_id
        for week in built_weeks
        for workout in week.workouts
        for exercise in workout.exercises
    })

    program = BuiltProgram(
        profile=block_plan.profile,
        strategy=block_plan.strategy,
        volume_allocation=block_plan.volume_allocation,
        weeks=built_weeks,
        unique_exercises_used=unique_exercises,
        total_sets=total_sets,
        total_workouts=total_workouts,
        generation_time_seconds=0.0,
    )
    return program, assembly_trace


def trace_from_program(program: BuiltProgram) -> list[AssemblyTraceEntry]:
    trace = []
    for week in program.weeks:
        for workout in week.workouts:
            for order, exercise in enumerate(workout.exercises):
                library_exercise = EXERCISE_LOOKUP.get(exercise.exercise_id)
                family_id = library_exercise.rotation_group if library_exercise else exercise.exercise_id
                trace.append(AssemblyTraceEntry(
                    week_number=week.week_number,
                    day_number=workout.day_number,
                    slot_id=f"legacy_{workout.session_type}_{order}",
                    slot_kind="legacy",
                    session_role_id=workout.session_type,
                    selected_canonical_id=exercise.exercise_id,
                    selected_family_id=family_id,
                    selected_sets=exercise.total_sets,
                    score=0.0,
                    candidate_scores=[],
                    rationale=["legacy_builder_fallback"],
                ))
    return trace


def _assemble_session(
    *,
    block_plan: BlockPlanV7,
    candidate_index: CandidateIndex,
    week_profile,
    week_plan,
    session_skeleton,
    session_volume,
    weekly_remaining: dict[str, float],
    week_used_ids: set[str],
    week_family_counts: Counter[str],
    prior_week_family_by_slot: dict[str, str],
    preferred_anchor_ids: list[str],
) -> tuple[BuiltWorkout, list[AssemblyTraceEntry]]:
    beam = [{
        "selected": [],
        "trace": [],
        "score": 0.0,
        "session_axial_count": 0,
        "session_grip_count": 0,
        "used_ids": set(),
        "used_family_counts": Counter(),
        "remaining_minutes": session_skeleton.session_role.max_duration_minutes,
    }]

    for slot in session_skeleton.slots:
        next_beam = []
        slot_key = _slot_key(session_skeleton.session_type, slot.slot_id)
        prior_slot_family = prior_week_family_by_slot.get(slot_key)
        for beam_state in beam:
            state = {
                "weekly_deficits": weekly_remaining,
                "prior_slot_family": prior_slot_family,
                "used_family_counts": beam_state["used_family_counts"],
                "used_in_week": week_used_ids,
                "anchor_family_ids": preferred_anchor_ids,
                "remaining_minutes": beam_state["remaining_minutes"],
                "session_axial_count": beam_state["session_axial_count"],
                "session_grip_count": beam_state["session_grip_count"],
            }
            candidates = candidate_index.query_candidates(
                slot,
                block_plan.directive,
                used_in_session=beam_state["used_ids"],
                used_in_week=week_used_ids,
                preferred_anchor_ids=preferred_anchor_ids,
                top_k=8,
            )
            if not candidates:
                continue

            for candidate in candidates:
                v5_exercise = EXERCISE_LOOKUP.get(candidate.canonical_id)
                if v5_exercise is None:
                    continue
                total_sets = _determine_set_count(
                    block_plan=block_plan,
                    candidate_index=candidate_index,
                    week_profile=week_profile,
                    week_plan=week_plan,
                    session_role_id=session_skeleton.session_role.role_id,
                    slot=slot,
                    candidate=candidate,
                    weekly_remaining=weekly_remaining,
                )
                prescribed_sets = prescribe_exercise(
                    exercise=v5_exercise,
                    total_sets=total_sets,
                    week_profile=week_profile,
                    program_goal=block_plan.directive.derived_context.effective_goal,
                    vbt_enabled=block_plan.strategy.vbt_enabled,
                    vbt_protocol=block_plan.strategy.vbt_protocol,
                    training_level=block_plan.profile.training_level,
                    session_duration_limited=beam_state["remaining_minutes"] <= 15,
                )
                prescribed_exercise = PrescribedExercise(
                    exercise_id=v5_exercise.id,
                    exercise_name=v5_exercise.name,
                    exercise_type=v5_exercise.exercise_type,
                    movement_pattern=v5_exercise.movement_pattern,
                    sets=prescribed_sets,
                    total_sets=total_sets,
                    muscle_contributions=_muscle_contributions(v5_exercise, total_sets),
                    order_in_session=len(beam_state["selected"]) + 1,
                    rationale=slot.rationale,
                    vbt_eligible=v5_exercise.vbt_eligible,
                )
                estimated_minutes = estimate_session_duration(beam_state["selected"] + [prescribed_exercise])
                candidate_score = score_candidate(candidate, slot, block_plan.directive, state)
                duration_penalty = max(0.0, estimated_minutes - session_skeleton.session_role.max_duration_minutes) * 1.8
                new_score = beam_state["score"] + candidate_score.total - duration_penalty
                trace_entry = AssemblyTraceEntry(
                    week_number=week_plan.week_number,
                    day_number=session_skeleton.day_number,
                    slot_id=slot.slot_id,
                    slot_kind=slot.slot_kind,
                    session_role_id=session_skeleton.session_role.role_id,
                    selected_canonical_id=candidate.canonical_id,
                    selected_family_id=candidate.family_id,
                    selected_sets=total_sets,
                    score=candidate_score.total,
                    candidate_scores=[candidate_score],
                    rationale=candidate_score.rationale,
                )

                next_state = {
                    "selected": beam_state["selected"] + [prescribed_exercise],
                    "trace": beam_state["trace"] + [trace_entry],
                    "score": new_score,
                    "session_axial_count": beam_state["session_axial_count"] + int(v5_exercise.is_axial_loading),
                    "session_grip_count": beam_state["session_grip_count"] + int(v5_exercise.grip_intensive),
                    "used_ids": set(beam_state["used_ids"]) | {candidate.canonical_id},
                    "used_family_counts": beam_state["used_family_counts"] + Counter([candidate.family_id]),
                    "remaining_minutes": max(0, session_skeleton.session_role.max_duration_minutes - estimated_minutes),
                }
                next_beam.append(next_state)

        beam = sorted(next_beam, key=lambda item: item["score"], reverse=True)[:6]
        if not beam:
            break

    selected_state = beam[0] if beam else {
        "selected": [],
        "trace": [],
        "score": 0.0,
        "remaining_minutes": session_skeleton.session_role.max_duration_minutes,
    }

    exercises = selected_state["selected"]
    exercises = build_supersets(exercises, block_plan.directive.derived_context.effective_goal)
    exercises = sort_exercises_for_session(exercises, block_plan.directive.derived_context.effective_goal)
    exercises = _trim_or_expand_session(
        exercises=exercises,
        session_skeleton=session_skeleton,
        weekly_remaining=weekly_remaining,
    )
    estimated_duration = estimate_session_duration(exercises)
    volume_delivered = _workout_volume(exercises)

    workout = BuiltWorkout(
        day_number=session_skeleton.day_number,
        day_label=session_skeleton.day_label,
        session_type=session_skeleton.session_type,
        exercises=exercises,
        total_sets=sum(exercise.total_sets for exercise in exercises),
        estimated_duration_minutes=estimated_duration,
        volume_check=volume_delivered,
        volume_delivered=volume_delivered,
        warmup_notes="Ramp into the first compound, then keep transitions crisp.",
        warmup_protocol=None,
    )
    return workout, selected_state["trace"]


def _determine_set_count(
    *,
    block_plan: BlockPlanV7,
    candidate_index: CandidateIndex,
    week_profile,
    week_plan,
    session_role_id: str,
    slot,
    candidate,
    weekly_remaining: dict[str, float],
) -> int:
    progression_role = _progression_role_group(slot, candidate.exercise_type)
    template = candidate_index.get_progression_template(
        family_id=candidate.family_id,
        session_role_group=progression_role,
        goal_phase=week_plan.goal_phase,
        training_level=block_plan.profile.training_level,
    )
    week_index = max(0, week_profile.week_in_mesocycle - 1)
    if template and template.default_sets_by_week:
        template_sets = template.default_sets_by_week[min(week_index, len(template.default_sets_by_week) - 1)]
    else:
        template_sets = slot.target_sets

    deficit_bonus = 0
    for muscle in candidate.stimulus.get("primary_muscles", []):
        if weekly_remaining.get(muscle, 0.0) > slot.target_sets:
            deficit_bonus = max(deficit_bonus, 1)

    total_sets = template_sets + deficit_bonus
    return max(slot.min_sets, min(slot.max_sets, total_sets))


def _progression_role_group(slot, exercise_type: str) -> str:
    if slot.slot_kind == "power" or exercise_type in {"power", "plyometric"}:
        return "power_primer"
    if slot.slot_kind == "anchor" or exercise_type == "heavy_compound":
        return "primary_strength"
    if slot.slot_kind == "isolation" or exercise_type == "isolation":
        return "isolation_volume"
    if slot.slot_kind in {"core", "prehab"}:
        return "trunk_prehab"
    return "secondary_strength_hypertrophy"


def _muscle_contributions(exercise, total_sets: int) -> dict[str, float]:
    contributions = defaultdict(float)
    for activation in exercise.muscle_activations:
        contributions[activation.muscle.value] += activation.volume_credit * total_sets
    return dict(contributions)


def _workout_volume(exercises: list[PrescribedExercise]) -> dict[str, float]:
    delivered = defaultdict(float)
    for exercise in exercises:
        for muscle, contribution in exercise.muscle_contributions.items():
            delivered[muscle] += contribution
    return dict(delivered)


def _trim_or_expand_session(
    *,
    exercises: list[PrescribedExercise],
    session_skeleton,
    weekly_remaining: dict[str, float],
) -> list[PrescribedExercise]:
    if not exercises:
        return exercises

    max_minutes = session_skeleton.session_role.max_duration_minutes
    estimated = estimate_session_duration(exercises)
    mutable = list(exercises)

    while estimated > max_minutes and mutable:
        reduced = False
        for exercise in reversed(mutable):
            if exercise.total_sets <= 2:
                continue
            exercise.total_sets -= 1
            exercise.sets = exercise.sets[:-1]
            exercise.muscle_contributions = {
                muscle: contribution * (exercise.total_sets / max(1, exercise.total_sets + 1))
                for muscle, contribution in exercise.muscle_contributions.items()
            }
            estimated = estimate_session_duration(mutable)
            reduced = True
            if estimated <= max_minutes:
                break
        if not reduced:
            break

    if estimated < max_minutes - 10:
        best = max(
            mutable,
            key=lambda exercise: sum(weekly_remaining.get(muscle, 0.0) for muscle in exercise.muscle_contributions),
        )
        if best.total_sets < 5:
            best.total_sets += 1
            extra_set = best.sets[-1].model_copy(update={"set_number": len(best.sets) + 1})
            best.sets.append(extra_set)
            factor = best.total_sets / max(1, best.total_sets - 1)
            best.muscle_contributions = {
                muscle: contribution * factor
                for muscle, contribution in best.muscle_contributions.items()
            }

    for index, exercise in enumerate(mutable, start=1):
        exercise.order_in_session = index
    return mutable


def _slot_key(session_type: str, slot_id: str) -> str:
    return f"{session_type}:{slot_id.split('_', 2)[-1]}"
