from __future__ import annotations

import re
from typing import Any

from program_generator_v5.exercise_library import EXERCISE_LIBRARY
from program_generator_v5.layer1_profile_builder import build_profile_from_structured
from program_generator_v5.schemas import MovementPattern, TrainingSeason
from program_generator_v5.sport_mappings import get_sport_adjustments

from .schemas import (
    DerivedContext,
    DirectiveAthlete,
    GoalStack,
    HardConstraints,
    ProgramDirectiveV7,
    ProgramRequest,
    SoftPreferences,
)


_MOVEMENT_PATTERN_ALIASES = {
    "bench": MovementPattern.HORIZONTAL_PUSH.value,
    "push": MovementPattern.HORIZONTAL_PUSH.value,
    "row": MovementPattern.HORIZONTAL_PULL.value,
    "pullup": MovementPattern.VERTICAL_PULL.value,
    "pull-up": MovementPattern.VERTICAL_PULL.value,
    "chinup": MovementPattern.VERTICAL_PULL.value,
    "chin-up": MovementPattern.VERTICAL_PULL.value,
    "press": MovementPattern.VERTICAL_PUSH.value,
    "overhead": MovementPattern.VERTICAL_PUSH.value,
    "squat": MovementPattern.SQUAT.value,
    "hinge": MovementPattern.HIP_HINGE.value,
    "deadlift": MovementPattern.HIP_HINGE.value,
    "lunge": MovementPattern.LUNGE.value,
    "core": MovementPattern.CORE.value,
    "carry": MovementPattern.CARRY.value,
    "rotation": MovementPattern.ROTATION.value,
    "jump": MovementPattern.POWER_LOWER.value,
    "throw": MovementPattern.POWER_UPPER.value,
}


def build_v5_profile_seed(input_data: dict[str, Any]) -> dict[str, Any]:
    goal_mapping = {
        "power": "power",
        "strength": "strength",
        "hypertrophy": "hypertrophy",
        "athletic_performance": "power",
    }
    training_goal = goal_mapping.get(input_data.get("goal_category"), "hypertrophy")

    injuries = []
    injury_history = (input_data.get("injury_history") or "").strip()
    if injury_history and injury_history.lower() not in ("none", "no", "n/a"):
        injuries.append({
            "area": "general",
            "description": injury_history,
            "avoid": [],
        })

    sport = (input_data.get("specific_sport") or "").strip().lower() or None
    if sport in {"none", "no", "n/a", "general"}:
        sport = None

    sex = input_data.get("sex")
    if isinstance(sex, str):
        sex = sex.upper()
        if sex in {"MALE", "M"}:
            sex = "M"
        elif sex in {"FEMALE", "F"}:
            sex = "F"

    return {
        "user_id": str(input_data.get("user_id", "unknown")),
        "name": input_data.get("name", "Athlete"),
        "age": input_data.get("age"),
        "sex": sex,
        "body_weight_kg": input_data.get("weight_kg"),
        "training_goal": training_goal,
        "training_level": input_data.get("fitness_level", "intermediate"),
        "program_duration_weeks": input_data.get("duration_weeks", 4),
        "training_days_per_week": input_data.get("days_per_week", 4),
        "session_duration_minutes": input_data.get("session_duration", 60) or 60,
        "equipment_tier": input_data.get("equipment_tier", 1) or 1,
        "injuries": injuries,
        "exercises_to_avoid": [],
        "exercises_to_include": [],
        "recovery_capacity": _infer_recovery_capacity(input_data),
        "weak_points": _extract_weak_points(input_data.get("user_notes")),
        "sport": sport,
        "vbt_capability": bool(input_data.get("has_vbt_capability", False)),
        "training_season": input_data.get("training_season"),
        "games_per_week": input_data.get("games_per_week", 0) or 0,
        "competition_date": input_data.get("competition_date"),
    }


def compile_program_directive(input_data: dict[str, Any]) -> ProgramDirectiveV7:
    profile_seed = build_v5_profile_seed(input_data)
    profile = build_profile_from_structured(profile_seed)

    note_preferences = _extract_note_preferences(input_data.get("user_notes"))
    sport_adjustments = get_sport_adjustments(profile.sport) if profile.sport else None

    forbidden_ids = sorted(
        set(note_preferences["avoid_exercise_ids"])
        | set(profile.exercises_to_avoid)
        | set(note_preferences["explicit_forbidden_ids"])
    )
    liked_ids = sorted(set(note_preferences["include_exercise_ids"]) | set(profile.exercises_to_include))

    derived_context = DerivedContext(
        effective_goal=profile.effective_goal or profile.training_goal,
        sport_interference=(sport_adjustments or {}).get("interference_level", "low"),
        fatigue_sensitivity=_infer_fatigue_sensitivity(profile_seed, sport_adjustments),
        max_difficulty=_infer_max_difficulty(profile_seed),
        movement_priorities=_derive_movement_priorities(profile, sport_adjustments),
        risk_flags=_derive_risk_flags(profile_seed, sport_adjustments),
        graph_coverage_warnings=list(profile.exercise_coverage_warnings),
        preferred_prehab_ids=list((sport_adjustments or {}).get("injury_prevention_additions", [])),
        excluded_canonical_ids=forbidden_ids,
        parsed_note_preferences=note_preferences,
    )

    directive = ProgramDirectiveV7(
        athlete=DirectiveAthlete(
            user_id=str(profile.user_id),
            name=profile.name,
            age=profile.age,
            sex=profile.sex,
            height_cm=input_data.get("height_cm"),
            weight_kg=input_data.get("weight_kg"),
            training_level=profile.training_level,
            training_age_years=profile.training_age_years,
            sport=profile.sport,
            training_season=profile.training_season.value if profile.training_season else None,
            games_per_week=profile.games_per_week,
            competition_date=profile.competition_date,
            recovery_capacity=profile.recovery_capacity,
            vbt_capability=profile.vbt_capability,
        ),
        goal_stack=GoalStack(
            primary_goal=profile.training_goal,
            secondary_goals=_derive_secondary_goals(profile, sport_adjustments),
            success_metrics=_derive_success_metrics(profile),
            time_horizon_weeks=profile.program_duration_weeks,
        ),
        hard_constraints=HardConstraints(
            equipment_tier=int(profile.equipment_tier.value),
            max_session_minutes=profile.session_duration_minutes,
            days_per_week=profile.training_days_per_week,
            injury_history=list(profile.injuries),
            forbidden_exercise_ids=forbidden_ids,
            forbidden_movement_patterns=note_preferences["forbidden_patterns"],
            fixed_schedule_notes=_extract_schedule_notes(input_data),
            exercise_blacklist_keywords=note_preferences["blacklist_keywords"],
        ),
        soft_preferences=SoftPreferences(
            liked_exercise_ids=liked_ids,
            disliked_exercise_ids=forbidden_ids,
            preferred_implements=note_preferences["preferred_implements"],
            preferred_movement_patterns=note_preferences["preferred_patterns"],
            preferred_split_bias=note_preferences.get("preferred_split_bias"),
            novelty_tolerance=note_preferences["novelty_tolerance"],
            aesthetic_emphasis=profile.weak_points,
            note_tags=note_preferences["tags"],
        ),
        program_request=ProgramRequest(
            duration_weeks=profile.program_duration_weeks,
            days_per_week=profile.training_days_per_week,
            goal_raw=input_data.get("goal_raw", profile.training_goal),
            session_duration_minutes=profile.session_duration_minutes,
            desired_split_bias=note_preferences.get("preferred_split_bias"),
            session_emphasis_requests=note_preferences["session_emphasis_requests"],
            phase_emphasis=note_preferences.get("phase_emphasis"),
            user_notes=input_data.get("user_notes"),
            send_email=bool(input_data.get("send_email", False)),
            generation_mode=_infer_generation_mode(input_data),
        ),
        derived_context=derived_context,
        raw_request=dict(input_data),
        should_use_llm_planner=_should_use_llm_planner(input_data, note_preferences, profile),
    )
    return directive


def _normalize_text(text: str | None) -> str:
    return re.sub(r"[^a-z0-9\s-]", " ", (text or "").lower())


def _extract_note_preferences(user_notes: str | None) -> dict[str, Any]:
    note_text = _normalize_text(user_notes)
    include_ids: list[str] = []
    avoid_ids: list[str] = []

    for exercise in EXERCISE_LIBRARY:
        exercise_name = _normalize_text(exercise.name)
        exercise_id_text = exercise.id.replace("_", " ")
        if not exercise_name.strip():
            continue
        if exercise_name in note_text or exercise_id_text in note_text:
            if any(token in note_text for token in (f"prefer {exercise_name}", f"include {exercise_name}", f"love {exercise_name}")):
                include_ids.append(exercise.id)
            if any(token in note_text for token in (f"avoid {exercise_name}", f"no {exercise_name}", f"skip {exercise_name}")):
                avoid_ids.append(exercise.id)

    preferred_patterns = sorted({
        pattern
        for token, pattern in _MOVEMENT_PATTERN_ALIASES.items()
        if token in note_text and any(trigger in note_text for trigger in ("prefer", "focus", "want", "emphas"))
    })
    forbidden_patterns = sorted({
        pattern
        for token, pattern in _MOVEMENT_PATTERN_ALIASES.items()
        if token in note_text and any(trigger in note_text for trigger in ("avoid", "no ", "skip", "cant ", "can't "))
    })

    preferred_implements = []
    for implement in ("barbell", "dumbbell", "cable", "machine", "bodyweight", "band", "kettlebell"):
        if implement in note_text:
            preferred_implements.append(implement)

    novelty_tolerance = "moderate"
    if any(token in note_text for token in ("keep it simple", "stable", "repeat", "consisten")):
        novelty_tolerance = "low"
    elif any(token in note_text for token in ("variety", "mix it up", "rotate", "novel")):
        novelty_tolerance = "high"

    tags = []
    if any(token in note_text for token in ("meet", "competition", "peak")):
        tags.append("peaking")
    if any(token in note_text for token in ("shoulder", "knee", "back", "hip")):
        tags.append("injury_context")

    session_emphasis_requests = []
    if "upper" in note_text:
        session_emphasis_requests.append("upper_bias")
    if "lower" in note_text or "legs" in note_text:
        session_emphasis_requests.append("lower_bias")

    preferred_split_bias = None
    if "full body" in note_text:
        preferred_split_bias = "full_body"
    elif "upper lower" in note_text:
        preferred_split_bias = "upper_lower"
    elif "push pull legs" in note_text or "ppl" in note_text:
        preferred_split_bias = "ppl"

    phase_emphasis = None
    if "build muscle" in note_text or "hypertrophy" in note_text:
        phase_emphasis = "accumulation"
    elif "peak" in note_text:
        phase_emphasis = "realization"

    return {
        "include_exercise_ids": sorted(set(include_ids)),
        "avoid_exercise_ids": sorted(set(avoid_ids)),
        "explicit_forbidden_ids": sorted(set(avoid_ids)),
        "preferred_patterns": preferred_patterns,
        "forbidden_patterns": forbidden_patterns,
        "preferred_implements": preferred_implements,
        "novelty_tolerance": novelty_tolerance,
        "tags": tags,
        "session_emphasis_requests": session_emphasis_requests,
        "preferred_split_bias": preferred_split_bias,
        "phase_emphasis": phase_emphasis,
        "blacklist_keywords": [
            keyword
            for keyword in ("pain", "impingement", "irritates", "aggravates")
            if keyword in note_text
        ],
    }


def _infer_recovery_capacity(input_data: dict[str, Any]) -> str:
    notes = _normalize_text(input_data.get("user_notes"))
    if any(token in notes for token in ("poor sleep", "stress", "busy", "recover slowly")):
        return "low"
    if any(token in notes for token in ("recover well", "sleep great", "high recovery")):
        return "high"
    return "normal"


def _infer_fatigue_sensitivity(profile_seed: dict[str, Any], sport_adjustments: dict[str, Any] | None) -> str:
    age = profile_seed.get("age") or 0
    games_per_week = profile_seed.get("games_per_week", 0) or 0
    season = profile_seed.get("training_season")
    if season == TrainingSeason.IN_SEASON.value or games_per_week >= 2:
        return "high"
    if age >= 55 or (sport_adjustments or {}).get("interference_level") == "high":
        return "high"
    if age >= 40:
        return "moderate_high"
    return "normal"


def _infer_max_difficulty(profile_seed: dict[str, Any]) -> int:
    age = profile_seed.get("age")
    if age is None:
        return 5
    if age >= 65:
        return 3
    if age >= 55:
        return 4
    if age <= 15:
        return 3
    if age <= 17:
        return 4
    return 5


def _derive_movement_priorities(profile, sport_adjustments: dict[str, Any] | None) -> list[str]:
    priorities = []
    priorities.extend((sport_adjustments or {}).get("mandatory_movement_patterns", []))
    for weak_point in profile.weak_points:
        if weak_point in _MOVEMENT_PATTERN_ALIASES:
            priorities.append(_MOVEMENT_PATTERN_ALIASES[weak_point])
    return list(dict.fromkeys(priorities))


def _derive_risk_flags(profile_seed: dict[str, Any], sport_adjustments: dict[str, Any] | None) -> list[str]:
    flags = []
    if profile_seed.get("training_season") == TrainingSeason.IN_SEASON.value:
        flags.append("in_season_recovery")
    if (profile_seed.get("games_per_week", 0) or 0) >= 2:
        flags.append("dense_competition_schedule")
    if profile_seed.get("injuries"):
        flags.append("injury_history")
    if (sport_adjustments or {}).get("interference_level") == "high":
        flags.append("high_sport_interference")
    if (profile_seed.get("age") or 0) >= 55:
        flags.append("masters_population")
    return flags


def _derive_secondary_goals(profile, sport_adjustments: dict[str, Any] | None) -> list[str]:
    secondary = []
    if profile.training_goal != profile.effective_goal:
        secondary.append(profile.effective_goal)
    if (sport_adjustments or {}).get("injury_prevention_additions"):
        secondary.append("injury_resilience")
    if profile.vbt_capability:
        secondary.append("auto_regulation")
    return list(dict.fromkeys(secondary))


def _derive_success_metrics(profile) -> list[str]:
    metrics = ["constraint_pass_rate", "weekly_coherence_score"]
    if profile.training_goal == "strength":
        metrics.append("anchor_lift_progression")
    elif profile.training_goal == "hypertrophy":
        metrics.append("target_volume_adherence")
    elif profile.training_goal == "power":
        metrics.append("power_slot_density")
    if profile.vbt_capability:
        metrics.append("velocity_quality")
    return metrics


def _extract_schedule_notes(input_data: dict[str, Any]) -> list[str]:
    notes = []
    if input_data.get("training_season") == TrainingSeason.IN_SEASON.value:
        notes.append("respect_competition_readiness")
    if (input_data.get("games_per_week") or 0) > 0:
        notes.append(f"{input_data.get('games_per_week')} game(s) per week")
    return notes


def _extract_weak_points(user_notes: str | None) -> list[str]:
    text = _normalize_text(user_notes)
    weak_points = []
    for weak_point in (
        "upper_chest",
        "chest",
        "lats",
        "upper_back",
        "side_delts",
        "rear_delts",
        "biceps",
        "triceps",
        "quads",
        "hamstrings",
        "glutes",
        "calves",
        "abs",
    ):
        pretty = weak_point.replace("_", " ")
        if pretty in text and any(token in text for token in ("bring up", "lagging", "weak", "focus")):
            weak_points.append(weak_point)
    return weak_points


def _infer_generation_mode(input_data: dict[str, Any]) -> str:
    notes = _normalize_text(input_data.get("user_notes"))
    if any(token in notes for token in ("audit", "explain every", "why each")):
        return "audit"
    if not input_data.get("user_notes"):
        return "cheap"
    return "standard"


def _should_use_llm_planner(
    input_data: dict[str, Any],
    note_preferences: dict[str, Any],
    profile,
) -> bool:
    if not input_data.get("user_notes"):
        return False
    if len(note_preferences["forbidden_patterns"]) >= 2:
        return True
    if profile.sport and profile.training_goal != profile.effective_goal:
        return True
    if len(profile.injuries) > 0 and len(note_preferences["preferred_patterns"]) > 0:
        return True
    return "?" in (input_data.get("goal_raw") or "")
