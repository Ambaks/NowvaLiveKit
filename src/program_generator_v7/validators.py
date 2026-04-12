from __future__ import annotations

from collections import Counter, defaultdict

from program_generator_v5.exercise_library import EXERCISE_LIBRARY
from program_generator_v5.layer5_validator import run_all_validations

from .schemas import AssemblyTraceEntry, BlockPlanV7, ProgramArtifactV7, ValidationIssue


EXERCISE_BY_ID = {exercise.id: exercise for exercise in EXERCISE_LIBRARY}


def validate_program_artifact(
    *,
    program,
    block_plan: BlockPlanV7,
    assembly_trace: list[AssemblyTraceEntry],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    base_issues = run_all_validations(
        program=program,
        profile=block_plan.profile,
        strategy=block_plan.strategy,
        volume_allocation=block_plan.volume_allocation,
    )
    for issue in base_issues:
        issues.append(ValidationIssue(
            rule_id=issue["rule_id"],
            severity=issue["severity"],
            scope=_base_issue_scope(issue),
            message=issue["message"],
            week=issue.get("week"),
            session=issue.get("session"),
            exercise_id=issue.get("exercise_id"),
            details=dict(issue.get("details", {})),
            repair_ops=_default_repair_ops(issue["rule_id"]),
        ))

    issues.extend(_check_anchor_continuity(block_plan, assembly_trace))
    issues.extend(_check_family_progression(block_plan, assembly_trace))
    issues.extend(_check_fatigue_clustering(program))
    issues.extend(_check_substitution_chain_overuse(assembly_trace))
    issues.extend(_check_movement_quota_alignment(block_plan, program))
    return issues


def summarize_validation_issues(issues: list[ValidationIssue]) -> dict[str, int | bool]:
    critical = sum(1 for issue in issues if issue.severity == "critical")
    major = sum(1 for issue in issues if issue.severity == "major")
    warning = sum(1 for issue in issues if issue.severity == "warning")
    return {
        "critical_count": critical,
        "major_count": major,
        "warning_count": warning,
        "passed": critical == 0 and major == 0,
    }


def build_validation_payload(issues: list[ValidationIssue]) -> list[dict]:
    return [issue.model_dump() for issue in issues]


def _check_anchor_continuity(
    block_plan: BlockPlanV7,
    assembly_trace: list[AssemblyTraceEntry],
) -> list[ValidationIssue]:
    issues = []
    by_slot = defaultdict(list)
    deload_lookup = {week.week_number: week.deload for week in block_plan.weeks}

    for entry in assembly_trace:
        if entry.slot_kind == "legacy":
            continue
        if entry.slot_kind not in {"anchor", "power"}:
            continue
        slot_key = f"{entry.day_number}:{entry.session_role_id}:{entry.slot_kind}"
        by_slot[slot_key].append(entry)

    for traces in by_slot.values():
        traces.sort(key=lambda item: item.week_number)
        for previous, current in zip(traces, traces[1:]):
            if deload_lookup.get(previous.week_number) or deload_lookup.get(current.week_number):
                continue
            if previous.selected_family_id != current.selected_family_id:
                issues.append(ValidationIssue(
                    rule_id="V7_ANCHOR_001",
                    severity="major",
                    scope="block",
                    message=(
                        f"Anchor family changed from `{previous.selected_family_id}` to "
                        f"`{current.selected_family_id}` between weeks {previous.week_number} and {current.week_number}."
                    ),
                    week=current.week_number,
                    session=current.day_number,
                    exercise_id=current.selected_canonical_id,
                    details={
                        "previous_family": previous.selected_family_id,
                        "current_family": current.selected_family_id,
                    },
                    repair_ops=["swap_within_family", "restore_anchor_family"],
                ))
    return issues


def _check_family_progression(
    block_plan: BlockPlanV7,
    assembly_trace: list[AssemblyTraceEntry],
) -> list[ValidationIssue]:
    issues = []
    by_session = defaultdict(list)
    for entry in assembly_trace:
        if entry.slot_kind == "legacy":
            continue
        key = (entry.day_number, entry.session_role_id, entry.slot_kind)
        by_session[key].append(entry)

    for entries in by_session.values():
        entries.sort(key=lambda item: item.week_number)
        rolling_families = [entry.selected_family_id for entry in entries[:3]]
        if len(set(rolling_families)) == len(rolling_families) and len(rolling_families) >= 3:
            issue = ValidationIssue(
                rule_id="V7_PROG_001",
                severity="warning",
                scope="block",
                message="Progression family rotated every week before enough anchor exposure accumulated.",
                week=entries[-1].week_number,
                session=entries[-1].day_number,
                exercise_id=entries[-1].selected_canonical_id,
                details={"families": rolling_families},
                repair_ops=["restore_anchor_family"],
            )
            issues.append(issue)
    return issues


def _check_fatigue_clustering(program) -> list[ValidationIssue]:
    issues = []
    for week in program.weeks:
        for workout in week.workouts:
            high_systemic = 0
            axial = 0
            for exercise in workout.exercises:
                library_exercise = EXERCISE_BY_ID.get(exercise.exercise_id)
                if library_exercise is None:
                    continue
                if library_exercise.systemic_fatigue == "high":
                    high_systemic += 1
                if library_exercise.is_axial_loading:
                    axial += 1
            if high_systemic >= 3 or axial >= 3:
                issues.append(ValidationIssue(
                    rule_id="V7_FAT_001",
                    severity="major",
                    scope="session",
                    message=(
                        f"Week {week.week_number} {workout.day_label} clusters too many high-fatigue exercises "
                        f"(systemic={high_systemic}, axial={axial})."
                    ),
                    week=week.week_number,
                    session=workout.day_number,
                    details={"high_systemic_count": high_systemic, "axial_count": axial},
                    repair_ops=["swap_lower_fatigue_sibling", "trim_sets"],
                ))
    return issues


def _check_substitution_chain_overuse(assembly_trace: list[AssemblyTraceEntry]) -> list[ValidationIssue]:
    issues = []
    weekly_family_usage = defaultdict(Counter)
    for entry in assembly_trace:
        if entry.slot_kind == "legacy":
            continue
        weekly_family_usage[entry.week_number][entry.selected_family_id] += 1
    for week_number, usage in weekly_family_usage.items():
        for family_id, count in usage.items():
            if count > 3:
                issues.append(ValidationIssue(
                    rule_id="V7_VAR_001",
                    severity="warning",
                    scope="week",
                    message=f"Week {week_number} leans too heavily on family `{family_id}` ({count} slots).",
                    week=week_number,
                    details={"family_id": family_id, "count": count},
                    repair_ops=["swap_within_family", "rebalance_week"],
                ))
    return issues


def _check_movement_quota_alignment(block_plan: BlockPlanV7, program) -> list[ValidationIssue]:
    issues = []
    actual_lookup = {}
    for week in program.weeks:
        counter = Counter()
        for workout in week.workouts:
            for exercise in workout.exercises:
                counter[exercise.movement_pattern.value] += 1
        actual_lookup[week.week_number] = counter

    for week_plan in block_plan.weeks:
        actual = actual_lookup.get(week_plan.week_number, Counter())
        for pattern, target in week_plan.movement_quotas.items():
            if actual.get(pattern, 0) < target:
                issues.append(ValidationIssue(
                    rule_id="V7_PAT_001",
                    severity="warning",
                    scope="week",
                    message=(
                        f"Week {week_plan.week_number} under-fills movement pattern `{pattern}` "
                        f"({actual.get(pattern, 0)}/{target})."
                    ),
                    week=week_plan.week_number,
                    details={"pattern": pattern, "actual": actual.get(pattern, 0), "target": target},
                    repair_ops=["rebalance_week", "swap_within_family"],
                ))
    return issues


def _base_issue_scope(issue: dict) -> str:
    if issue.get("session") is not None:
        return "session"
    if issue.get("week") is not None:
        return "week"
    return "program"


def _default_repair_ops(rule_id: str) -> list[str]:
    if rule_id.startswith("VOL_"):
        return ["trim_sets", "add_sets", "rebalance_week"]
    if rule_id.startswith("SES_"):
        return ["reorder_session", "swap_lower_fatigue_sibling"]
    if rule_id.startswith("VAR_"):
        return ["swap_within_family", "rotate_family_member"]
    if rule_id.startswith("PER_"):
        return ["restore_anchor_family", "rebalance_week"]
    return ["rebalance_week"]
