from __future__ import annotations

import uuid
from collections import Counter

from program_generator_v5.exercise_library import EXERCISE_LIBRARY
from program_generator_v5.layer5_validator import auto_fix_issue
from program_generator_v5.mutator import ProgramMutator

from .schemas import AssemblyTraceEntry, RepairOperation, ValidationIssue


EXERCISE_BY_ID = {exercise.id: exercise for exercise in EXERCISE_LIBRARY}


def repair_program(
    *,
    program,
    block_plan,
    issues: list[ValidationIssue],
    assembly_trace: list[AssemblyTraceEntry],
    max_iterations: int = 2,
):
    repair_log: list[RepairOperation] = []
    mutator = ProgramMutator(
        program=program,
        profile=block_plan.profile,
        strategy=block_plan.strategy,
        volume_allocation=block_plan.volume_allocation,
        exercise_library=EXERCISE_BY_ID,
    )

    for _ in range(max_iterations):
        fixes_applied = 0
        for issue in [issue for issue in issues if issue.severity in {"critical", "major"}]:
            result = None
            if issue.rule_id.startswith("V7_"):
                result = _apply_v7_fix(mutator, issue, assembly_trace)
            else:
                result = auto_fix_issue(mutator, issue.model_dump(), block_plan.profile)

            if result and getattr(result, "success", False):
                repair_log.append(RepairOperation(
                    op_id=str(uuid.uuid4()),
                    op_type=getattr(result, "mutation_type", issue.repair_ops[0] if issue.repair_ops else "repair"),
                    description=getattr(result, "description", issue.message),
                    week=issue.week,
                    session=issue.session,
                    source_exercise_id=issue.exercise_id,
                    target_exercise_id=_extract_target_id(result),
                    metadata={"rule_id": issue.rule_id},
                ))
                fixes_applied += 1
        if fixes_applied == 0:
            break
    return program, repair_log


def _apply_v7_fix(mutator: ProgramMutator, issue: ValidationIssue, assembly_trace: list[AssemblyTraceEntry]):
    if issue.rule_id == "V7_ANCHOR_001":
        return _restore_anchor_family(mutator, issue, assembly_trace)
    if issue.rule_id == "V7_FAT_001":
        return _reduce_session_fatigue(mutator, issue)
    if issue.rule_id == "V7_PAT_001":
        return _restore_pattern_quota(mutator, issue)
    if issue.rule_id == "V7_VAR_001":
        return _reduce_family_overuse(mutator, issue)
    if issue.rule_id == "V7_PROG_001":
        return _restore_anchor_from_issue(mutator, issue)
    return None


def _restore_anchor_family(
    mutator: ProgramMutator,
    issue: ValidationIssue,
    assembly_trace: list[AssemblyTraceEntry],
):
    target_family = issue.details.get("previous_family")
    if not target_family or not issue.week or not issue.session or not issue.exercise_id:
        return None

    replacement_id = _choose_family_member(
        mutator=mutator,
        family_id=target_family,
        week_num=issue.week,
        session_day=issue.session,
        exclude_ids=[issue.exercise_id],
    )
    if replacement_id is None:
        return None

    return mutator.swap_exercise(
        week_num=issue.week,
        session_day=issue.session,
        old_exercise_id=issue.exercise_id,
        new_exercise_id=replacement_id,
        source="v7_repair",
        reason="Restore previous anchor family",
    )


def _restore_anchor_from_issue(mutator: ProgramMutator, issue: ValidationIssue):
    families = issue.details.get("families", [])
    if not families or not issue.week or not issue.session or not issue.exercise_id:
        return None
    replacement_id = _choose_family_member(
        mutator=mutator,
        family_id=families[0],
        week_num=issue.week,
        session_day=issue.session,
        exclude_ids=[issue.exercise_id],
    )
    if replacement_id is None:
        return None
    return mutator.swap_exercise(
        week_num=issue.week,
        session_day=issue.session,
        old_exercise_id=issue.exercise_id,
        new_exercise_id=replacement_id,
        source="v7_repair",
        reason="Restore more stable family progression",
    )


def _reduce_session_fatigue(mutator: ProgramMutator, issue: ValidationIssue):
    if not issue.week or not issue.session:
        return None
    week = mutator._get_week(issue.week)
    if not week:
        return None
    workout = mutator._get_workout(week, issue.session)
    if not workout:
        return None

    fatigue_ranked = []
    for exercise in workout.exercises:
        library_exercise = EXERCISE_BY_ID.get(exercise.exercise_id)
        if not library_exercise:
            continue
        score = 0
        if library_exercise.systemic_fatigue == "high":
            score += 4
        if library_exercise.is_axial_loading:
            score += 3
        if library_exercise.grip_intensive:
            score += 1
        fatigue_ranked.append((score, exercise.exercise_id))
    if not fatigue_ranked:
        return None

    fatigue_ranked.sort(reverse=True)
    target_exercise_id = fatigue_ranked[0][1]
    alternative = mutator._find_non_axial_alternative(target_exercise_id, issue.week)
    if alternative:
        return mutator.swap_exercise(
            week_num=issue.week,
            session_day=issue.session,
            old_exercise_id=target_exercise_id,
            new_exercise_id=alternative.id,
            source="v7_repair",
            reason="Reduce fatigue clustering with a lower-fatigue sibling",
        )

    return mutator.remove_sets(
        week_num=issue.week,
        session_day=issue.session,
        exercise_id=target_exercise_id,
        sets_to_remove=1,
        source="v7_repair",
        reason="Trim fatigue when a lower-fatigue sibling is unavailable",
    )


def _restore_pattern_quota(mutator: ProgramMutator, issue: ValidationIssue):
    if not issue.week:
        return None
    pattern = issue.details.get("pattern")
    if not pattern:
        return None

    week = mutator._get_week(issue.week)
    if not week or not week.workouts:
        return None

    target_workout = min(week.workouts, key=lambda workout: len(workout.exercises))
    best = mutator._find_best_exercise_for_pattern(pattern, issue.week)
    if best is None:
        return None

    return mutator.add_exercise(
        week_num=issue.week,
        session_day=target_workout.day_number,
        exercise_id=best.id,
        sets=2,
        source="v7_repair",
        reason=f"Restore missing `{pattern}` pattern quota",
    )


def _reduce_family_overuse(mutator: ProgramMutator, issue: ValidationIssue):
    family_id = issue.details.get("family_id")
    if not family_id or not issue.week:
        return None
    week = mutator._get_week(issue.week)
    if not week:
        return None

    for workout in week.workouts:
        for exercise in workout.exercises:
            library_exercise = EXERCISE_BY_ID.get(exercise.exercise_id)
            if library_exercise and library_exercise.rotation_group == family_id:
                replacement_id = _choose_alternate_same_pattern(
                    mutator=mutator,
                    week_num=issue.week,
                    current_exercise_id=exercise.exercise_id,
                )
                if replacement_id:
                    return mutator.swap_exercise(
                        week_num=issue.week,
                        session_day=workout.day_number,
                        old_exercise_id=exercise.exercise_id,
                        new_exercise_id=replacement_id,
                        source="v7_repair",
                        reason="Reduce weekly overuse of one substitution chain",
                    )
    return None


def _choose_family_member(
    *,
    mutator: ProgramMutator,
    family_id: str,
    week_num: int,
    session_day: int,
    exclude_ids: list[str],
) -> str | None:
    week = mutator._get_week(week_num)
    if not week:
        return None
    workout = mutator._get_workout(week, session_day)
    in_session = {exercise.exercise_id for exercise in workout.exercises} if workout else set()

    candidates = []
    for exercise_id, exercise in EXERCISE_BY_ID.items():
        if exercise.rotation_group != family_id:
            continue
        if exercise_id in exclude_ids or exercise_id in in_session:
            continue
        if exercise.equipment_tier.value > mutator.profile.equipment_tier.value:
            continue
        if exercise_id in mutator.profile.exercises_to_avoid:
            continue
        candidates.append((exercise.sfr_rating, exercise_id))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _choose_alternate_same_pattern(
    *,
    mutator: ProgramMutator,
    week_num: int,
    current_exercise_id: str,
) -> str | None:
    current = EXERCISE_BY_ID.get(current_exercise_id)
    if current is None:
        return None

    week = mutator._get_week(week_num)
    week_ids = {
        exercise.exercise_id
        for workout in (week.workouts if week else [])
        for exercise in workout.exercises
    }
    candidates = []
    for exercise_id, exercise in EXERCISE_BY_ID.items():
        if exercise_id == current_exercise_id or exercise_id in week_ids:
            continue
        if exercise.movement_pattern != current.movement_pattern:
            continue
        if exercise.rotation_group == current.rotation_group:
            continue
        if exercise.equipment_tier.value > mutator.profile.equipment_tier.value:
            continue
        candidates.append((exercise.sfr_rating, exercise_id))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _extract_target_id(result) -> str | None:
    description = getattr(result, "description", "")
    if "→" in description:
        return description.split("→", 1)[-1].split(" ", 1)[0]
    return None
