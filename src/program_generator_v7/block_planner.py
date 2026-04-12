from __future__ import annotations

import json
from collections import defaultdict

from program_generator_v5.layer1_profile_builder import build_profile_from_structured
from program_generator_v5.layer2_strategy_engine import build_strategy
from program_generator_v5.layer3_volume_engine import calculate_volume
from program_generator_v5.schemas import ExerciseType, MovementPattern

from .directive_compiler import build_v5_profile_seed
from .schemas import (
    BlockPlanV7,
    BlockWeekPlan,
    KGSnapshot,
    ProgramDirectiveV7,
    SessionRoleAssignment,
    SessionSlot,
    WeekSessionSkeleton,
)


async def build_block_plan(
    directive: ProgramDirectiveV7,
    snapshot: KGSnapshot,
    openai_client=None,
    use_llm: bool = True,
) -> BlockPlanV7:
    profile_seed = build_v5_profile_seed(directive.raw_request)
    profile_seed["exercises_to_avoid"] = directive.hard_constraints.forbidden_exercise_ids
    profile_seed["exercises_to_include"] = directive.soft_preferences.liked_exercise_ids
    profile = build_profile_from_structured(profile_seed)
    strategy = build_strategy(profile=profile, openai_client=None)
    volume_allocation = calculate_volume(profile, strategy)

    weeks: list[BlockWeekPlan] = []
    phase_sequence: list[str] = []
    anchor_family_preferences = defaultdict(list)
    planner_notes = []
    llm_used = False

    for week_profile, volume_week in zip(strategy.week_profiles, volume_allocation.weeks):
        goal_phase = _goal_phase_for_week(week_profile.phase_name, week_profile.block_phase)
        phase_sequence.append(goal_phase)

        sessions: list[WeekSessionSkeleton] = []
        week_roles: list[SessionRoleAssignment] = []
        week_movement_quotas = defaultdict(int)

        for day_number, (session_template, session_volume) in enumerate(
            zip(strategy.split.sessions_per_week, volume_week.sessions),
            start=1,
        ):
            role_id = f"{directive.derived_context.effective_goal}_{session_template.session_type}"
            session_role = snapshot.session_roles.get(role_id)
            if session_role is None:
                session_role = _fallback_session_role(directive.derived_context.effective_goal, session_template)

            role_assignment = SessionRoleAssignment(
                role_id=session_role.role_id,
                label=session_role.label,
                session_type=session_role.session_type,
                target_muscles=list(session_role.target_muscles),
                required_patterns=list(session_role.required_patterns),
                optional_patterns=list(session_role.optional_patterns),
                fatigue_budget=session_role.fatigue_budget,
                slot_budget=session_role.slot_budget,
                max_duration_minutes=session_role.max_duration_minutes,
                rationale=f"Derived from split template `{session_template.session_type}` and goal `{directive.derived_context.effective_goal}`.",
            )
            week_roles.append(role_assignment)

            slots = _build_session_slots(
                directive=directive,
                week_number=week_profile.week_number,
                day_number=day_number,
                goal_phase=goal_phase,
                role_assignment=role_assignment,
                session_template=session_template,
                session_volume=session_volume,
            )
            for slot in slots:
                if slot.required_pattern:
                    week_movement_quotas[slot.required_pattern] += 1
            sessions.append(WeekSessionSkeleton(
                week_number=week_profile.week_number,
                day_number=day_number,
                day_label=session_template.day_label,
                session_type=session_template.session_type,
                session_role=role_assignment,
                slots=slots,
            ))

            anchor_families = _preferred_anchor_families_for_session(
                snapshot=snapshot,
                directive=directive,
                session_type=session_template.session_type,
                required_patterns=role_assignment.required_patterns,
            )
            if anchor_families:
                anchor_family_preferences[f"{week_profile.week_number}:{session_template.session_type}"] = anchor_families

        weeks.append(BlockWeekPlan(
            week_number=week_profile.week_number,
            phase_name=week_profile.phase_name,
            goal_phase=goal_phase,
            week_focus=_week_focus_text(goal_phase, directive.derived_context.effective_goal, week_profile.is_deload),
            deload=week_profile.is_deload,
            fatigue_budget=_week_fatigue_budget(directive, week_profile.is_deload),
            anchor_family_ids=list(anchor_family_preferences.get(f"{week_profile.week_number}:{strategy.split.sessions_per_week[0].session_type}", [])),
            movement_quotas=dict(week_movement_quotas),
            session_roles=week_roles,
            sessions=sessions,
            rationale=f"Periodization phase `{week_profile.phase_name}` with {len(sessions)} session(s).",
        ))

    if directive.should_use_llm_planner and use_llm and openai_client:
        llm_result = await _llm_refine_plan(directive, weeks, openai_client)
        if llm_result:
            llm_used = True
            planner_notes.extend(llm_result.get("notes", []))
            for week in weeks:
                for session in week.sessions:
                    key = f"{week.week_number}:{session.session_type}"
                    if key in llm_result.get("anchor_family_preferences", {}):
                        anchor_family_preferences[key] = llm_result["anchor_family_preferences"][key]

    return BlockPlanV7(
        directive=directive,
        profile=profile,
        strategy=strategy,
        volume_allocation=volume_allocation,
        weeks=weeks,
        phase_sequence=phase_sequence,
        anchor_family_preferences=dict(anchor_family_preferences),
        planner_notes=planner_notes,
        llm_used=llm_used,
    )


def _fallback_session_role(goal: str, session_template) -> SessionRoleAssignment:
    return SessionRoleAssignment(
        role_id=f"{goal}_{session_template.session_type}",
        label=f"{goal.title()} {session_template.day_label}",
        session_type=session_template.session_type,
        target_muscles=[muscle.value for muscle in session_template.muscle_groups],
        required_patterns=[pattern.value for pattern in session_template.required_movement_patterns],
        optional_patterns=[pattern.value for pattern in session_template.optional_movement_patterns],
        fatigue_budget="moderate",
        slot_budget=session_template.max_exercises,
        max_duration_minutes=session_template.max_duration_minutes,
        rationale="Fallback role synthesized from split template.",
    )


def _build_session_slots(
    directive: ProgramDirectiveV7,
    week_number: int,
    day_number: int,
    goal_phase: str,
    role_assignment: SessionRoleAssignment,
    session_template,
    session_volume,
) -> list[SessionSlot]:
    slots: list[SessionSlot] = []
    required_patterns = list(role_assignment.required_patterns)
    slot_budget = max(len(required_patterns), min(role_assignment.slot_budget, session_template.max_exercises))

    for order_hint, pattern in enumerate(required_patterns):
        slots.append(SessionSlot(
            slot_id=f"w{week_number}_d{day_number}_{pattern}_{order_hint}",
            week_number=week_number,
            day_number=day_number,
            day_label=session_template.day_label,
            session_type=session_template.session_type,
            session_role_id=role_assignment.role_id,
            slot_kind=_slot_kind_for_pattern(pattern, directive.derived_context.effective_goal),
            required_pattern=pattern,
            target_muscles=[muscle.value for muscle in session_template.muscle_groups],
            preferred_family_ids=[],
            min_sets=2 if goal_phase != "realization" else 1,
            target_sets=_target_sets_for_slot(pattern, goal_phase),
            max_sets=5,
            intensity_bucket=_intensity_bucket(goal_phase, directive.derived_context.effective_goal),
            fatigue_budget=role_assignment.fatigue_budget,
            order_hint=order_hint,
            notes=[],
            rationale=f"Required pattern `{pattern}` for `{session_template.session_type}`.",
        ))

    if directive.derived_context.preferred_prehab_ids and len(slots) < slot_budget:
        slots.append(SessionSlot(
            slot_id=f"w{week_number}_d{day_number}_prehab",
            week_number=week_number,
            day_number=day_number,
            day_label=session_template.day_label,
            session_type=session_template.session_type,
            session_role_id=role_assignment.role_id,
            slot_kind="prehab",
            required_pattern=None,
            target_muscles=[muscle.value for muscle in session_template.muscle_groups[-2:]],
            preferred_family_ids=[],
            preferred_canonical_ids=list(directive.derived_context.preferred_prehab_ids),
            min_sets=2,
            target_sets=2,
            max_sets=3,
            intensity_bucket="light",
            fatigue_budget="low",
            order_hint=len(slots),
            notes=["sport_specific_prevention"],
            rationale="Prehab slot added from sport adjustments.",
        ))

    additional_patterns = _derive_additional_patterns(session_template, session_volume, slot_budget - len(slots))
    for index, pattern in enumerate(additional_patterns, start=len(slots)):
        slots.append(SessionSlot(
            slot_id=f"w{week_number}_d{day_number}_extra_{index}",
            week_number=week_number,
            day_number=day_number,
            day_label=session_template.day_label,
            session_type=session_template.session_type,
            session_role_id=role_assignment.role_id,
            slot_kind=_slot_kind_for_pattern(pattern, directive.derived_context.effective_goal),
            required_pattern=pattern,
            target_muscles=[muscle.value for muscle in session_template.muscle_groups],
            min_sets=2,
            target_sets=3,
            max_sets=4,
            intensity_bucket=_intensity_bucket(goal_phase, directive.derived_context.effective_goal),
            fatigue_budget=role_assignment.fatigue_budget,
            order_hint=index,
            notes=["volume_fill"],
            rationale=f"Additional slot to help cover volume targets for `{pattern}`.",
        ))
    return slots


def _goal_phase_for_week(phase_name: str, block_phase: str | None) -> str:
    if block_phase:
        return block_phase
    normalized = phase_name.lower()
    if "deload" in normalized:
        return "deload"
    if "overreach" in normalized or "heavy" in normalized:
        return "transmutation"
    if "intro" in normalized or "build" in normalized:
        return "accumulation"
    return "realization"


def _slot_kind_for_pattern(pattern: str, effective_goal: str) -> str:
    if pattern in {MovementPattern.POWER_LOWER.value, MovementPattern.POWER_UPPER.value}:
        return "power"
    if pattern in {MovementPattern.CORE.value, MovementPattern.CARRY.value, MovementPattern.ROTATION.value}:
        return "core"
    if effective_goal == "strength" and pattern in {MovementPattern.SQUAT.value, MovementPattern.HIP_HINGE.value, MovementPattern.HORIZONTAL_PUSH.value}:
        return "anchor"
    if pattern in {MovementPattern.ISOLATION_PULL.value, MovementPattern.ISOLATION_PUSH.value}:
        return "isolation"
    return "main"


def _target_sets_for_slot(pattern: str, goal_phase: str) -> int:
    if pattern in {MovementPattern.POWER_LOWER.value, MovementPattern.POWER_UPPER.value}:
        return 3
    if goal_phase == "deload":
        return 2
    if pattern in {MovementPattern.ISOLATION_PULL.value, MovementPattern.ISOLATION_PUSH.value}:
        return 3
    return 4 if goal_phase == "transmutation" else 3


def _intensity_bucket(goal_phase: str, effective_goal: str) -> str:
    if goal_phase == "deload":
        return "light"
    if effective_goal == "power":
        return "explosive"
    if goal_phase == "transmutation":
        return "heavy"
    if goal_phase == "realization":
        return "moderate_heavy"
    return "moderate"


def _derive_additional_patterns(session_template, session_volume, slots_remaining: int) -> list[str]:
    if slots_remaining <= 0:
        return []

    pattern_scores = []
    for pattern in session_template.optional_movement_patterns:
        pattern_scores.append((session_volume.movement_pattern_requirements.get(pattern.value, 1), pattern.value))

    for pattern_key, required_count in sorted(
        session_volume.movement_pattern_requirements.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        if pattern_key not in [pattern.value for pattern in session_template.required_movement_patterns]:
            pattern_scores.append((required_count, pattern_key))

    deduped = []
    seen = set()
    for _, pattern in sorted(pattern_scores, key=lambda item: (-item[0], item[1])):
        if pattern in seen:
            continue
        seen.add(pattern)
        deduped.append(pattern)
        if len(deduped) >= slots_remaining:
            break
    return deduped


def _preferred_anchor_families_for_session(
    snapshot: KGSnapshot,
    directive: ProgramDirectiveV7,
    session_type: str,
    required_patterns: list[str],
) -> list[str]:
    family_ids = []
    liked_ids = set(directive.soft_preferences.liked_exercise_ids)
    for canonical_id in liked_ids:
        exercise = snapshot.exercises.get(canonical_id)
        if not exercise:
            continue
        if exercise.movement_pattern in required_patterns:
            family_ids.append(exercise.family_id)
    if family_ids:
        return list(dict.fromkeys(family_ids))

    for exercise in snapshot.exercises.values():
        if exercise.movement_pattern in required_patterns:
            if "lower" in session_type and exercise.exercise_type == ExerciseType.HEAVY_COMPOUND.value:
                family_ids.append(exercise.family_id)
            elif "upper" in session_type and exercise.exercise_type in {
                ExerciseType.HEAVY_COMPOUND.value,
                ExerciseType.LIGHT_COMPOUND.value,
            }:
                family_ids.append(exercise.family_id)
    return list(dict.fromkeys(family_ids))[:3]


def _week_focus_text(goal_phase: str, effective_goal: str, is_deload: bool) -> str:
    if is_deload:
        return "Recovery-focused week with reduced fatigue and stable movement exposure."
    if effective_goal == "power":
        return f"{goal_phase.title()} week prioritizing explosive quality and freshness."
    if effective_goal == "strength":
        return f"{goal_phase.title()} week prioritizing anchor lift continuity and intensity."
    return f"{goal_phase.title()} week prioritizing coherent volume distribution and recoverable progression."


def _week_fatigue_budget(directive: ProgramDirectiveV7, is_deload: bool) -> str:
    if is_deload:
        return "low"
    if directive.derived_context.fatigue_sensitivity == "high":
        return "moderate"
    return "moderate_high"


async def _llm_refine_plan(directive: ProgramDirectiveV7, weeks: list[BlockWeekPlan], openai_client):
    summary = {
        "goal": directive.goal_stack.primary_goal,
        "effective_goal": directive.derived_context.effective_goal,
        "sport": directive.athlete.sport,
        "season": directive.athlete.training_season,
        "days_per_week": directive.program_request.days_per_week,
        "duration_weeks": directive.program_request.duration_weeks,
        "notes": directive.program_request.user_notes,
        "risk_flags": directive.derived_context.risk_flags,
        "weeks": [
            {
                "week_number": week.week_number,
                "phase_name": week.phase_name,
                "goal_phase": week.goal_phase,
                "session_types": [session.session_type for session in week.sessions],
            }
            for week in weeks
        ],
    }
    prompt = (
        "You are refining a deterministic strength-program block plan. "
        "Return only JSON with keys notes (string list) and anchor_family_preferences "
        "(object keyed by `week:session_type` with a list of family ids). "
        "Do not invent sessions. Keep suggestions sparse and bounded.\n\n"
        f"{json.dumps(summary)}"
    )
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-5-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        return json.loads(response.choices[0].message.content)
    except Exception:
        return None
