"""
V5 Layer 1: Profile Builder

Two input paths:
A) Structured input (from API/form) → deterministic profile construction. No LLM.
B) Natural language input (from voice agent) → LLM extraction.

Computes derived fields:
- effective_goal (after sport mapping)
- sport_adjustments (volume_modifier, emphasis_muscles, etc.)
- available_exercises (filtered by tier, avoiding injuries)
- exercise_coverage_warnings (muscles with sparse options)
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .schemas import AthleteProfile, EquipmentTier, MuscleGroup
from .exercise_library import EXERCISE_LIBRARY
from .sport_mappings import get_sport_adjustments
from .prompts import format_profile_extraction_prompt


# ─────────────────────────────────────────────────────────────────────────────
# A) STRUCTURED INPUT PATH — NO LLM
# ─────────────────────────────────────────────────────────────────────────────


def build_profile_from_structured(data: dict) -> AthleteProfile:
    """
    Build an AthleteProfile from structured API/form input.

    Required fields:
      - user_id, name
      - training_goal: "hypertrophy" | "strength" | "power"
      - training_level: "beginner" | "intermediate" | "advanced"
      - program_duration_weeks: int
      - training_days_per_week: int (2-6)
      - equipment_tier: int (1, 2, or 3)

    Optional fields:
      - sport: str
      - age: int
      - sex: str
      - body_weight_kg: float
      - training_age_years: float
      - session_duration_minutes: int (default 60)
      - injuries: list[dict]
      - exercises_to_avoid: list[str]
      - exercises_to_include: list[str]
      - recovery_capacity: "low" | "normal" | "high"
      - weak_points: list[str]

    Returns fully populated AthleteProfile with derived fields computed.
    """
    # Extract and validate required fields
    user_id = data.get("user_id", "unknown")
    name = data.get("name", "Athlete")

    training_goal = data.get("training_goal", "hypertrophy").lower()
    if training_goal not in ("hypertrophy", "strength", "power"):
        training_goal = "hypertrophy"

    training_level = data.get("training_level", "intermediate").lower()
    if training_level not in ("beginner", "intermediate", "advanced"):
        training_level = "intermediate"

    program_duration_weeks = int(data.get("program_duration_weeks", 4))
    training_days_per_week = int(data.get("training_days_per_week", 4))
    training_days_per_week = max(2, min(6, training_days_per_week))  # Clamp 2-6

    # Equipment tier
    tier_value = data.get("equipment_tier", 1)
    if isinstance(tier_value, EquipmentTier):
        equipment_tier = tier_value
    else:
        tier_value = int(tier_value)
        equipment_tier = EquipmentTier(max(1, min(3, tier_value)))

    # Optional fields with defaults
    session_duration_minutes = int(data.get("session_duration_minutes", 60))
    age = data.get("age")
    sex = data.get("sex")
    body_weight_kg = data.get("body_weight_kg")
    training_age_years = data.get("training_age_years")

    injuries = data.get("injuries", [])
    exercises_to_avoid = data.get("exercises_to_avoid", [])
    exercises_to_include = data.get("exercises_to_include", [])

    recovery_capacity = data.get("recovery_capacity", "normal")
    if recovery_capacity not in ("low", "normal", "high"):
        recovery_capacity = "normal"

    weak_points = data.get("weak_points", [])
    sport = data.get("sport")
    vbt_capability = bool(data.get("vbt_capability", False))

    # ── Compute Derived Fields ──────────────────────────────────────────────

    # 1. Sport mapping → effective_goal and sport_adjustments
    effective_goal = training_goal
    sport_adjustments = None

    if sport:
        adj = get_sport_adjustments(sport)
        if adj:
            sport_adjustments = adj
            effective_goal = adj["base_goal"]
            # Merge forbidden exercises
            forbidden = adj.get("forbidden_exercises", [])
            exercises_to_avoid = list(set(exercises_to_avoid + forbidden))

    # 2. Filter available exercises
    available_exercises, coverage_warnings = _filter_exercises_for_profile(
        equipment_tier=equipment_tier,
        training_level=training_level,
        exercises_to_avoid=exercises_to_avoid,
        injuries=injuries,
    )

    return AthleteProfile(
        user_id=user_id,
        name=name,
        age=age,
        sex=sex,
        body_weight_kg=body_weight_kg,
        training_goal=training_goal,
        sport=sport,
        training_level=training_level,
        training_age_years=training_age_years,
        program_duration_weeks=program_duration_weeks,
        training_days_per_week=training_days_per_week,
        session_duration_minutes=session_duration_minutes,
        equipment_tier=equipment_tier,
        injuries=injuries,
        exercises_to_avoid=exercises_to_avoid,
        exercises_to_include=exercises_to_include,
        recovery_capacity=recovery_capacity,
        weak_points=weak_points,
        vbt_capability=vbt_capability,
        # Derived
        effective_goal=effective_goal,
        sport_adjustments=sport_adjustments,
        available_exercises=available_exercises,
        exercise_coverage_warnings=coverage_warnings,
    )


# ─────────────────────────────────────────────────────────────────────────────
# B) NATURAL LANGUAGE INPUT PATH — LLM EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────


async def build_profile_from_natural_language(
    text: str,
    openai_client,
    defaults: dict = None,
) -> AthleteProfile:
    """
    Extract structured profile from natural language input using LLM.

    Args:
        text: Raw text from voice agent transcript or free-form input
        openai_client: OpenAI async client
        defaults: Optional dict of default values for fields not extracted

    Returns:
        AthleteProfile with extracted and default values populated
    """
    defaults = defaults or {}

    # Build the extraction prompt
    prompt = format_profile_extraction_prompt(text)

    # Call LLM for extraction
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-5-mini",  # Per spec: gpt-5-mini for profile extraction
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,  # Low temp for consistent extraction
        )

        extracted = json.loads(response.choices[0].message.content)
    except Exception as e:
        # On extraction failure, use defaults only
        print(f"⚠️  LLM profile extraction failed: {e}")
        extracted = {}

    # Merge extracted values with defaults
    merged = {**defaults, **{k: v for k, v in extracted.items() if v is not None}}

    # Map extracted fields to structured input format
    structured_data = {
        "user_id": defaults.get("user_id", "voice_user"),
        "name": defaults.get("name", "Athlete"),
        "training_goal": merged.get("training_goal", "hypertrophy"),
        "sport": merged.get("sport"),
        "training_level": merged.get("training_level", "intermediate"),
        "training_days_per_week": merged.get("training_days_per_week", 4),
        "session_duration_minutes": merged.get("session_duration_minutes", 60),
        "program_duration_weeks": defaults.get("program_duration_weeks", 4),
        "equipment_tier": defaults.get("equipment_tier", 1),
        "injuries": merged.get("injuries", []),
        "exercises_to_avoid": merged.get("exercises_to_avoid", []),
        "exercises_to_include": merged.get("exercises_to_include", []),
        "weak_points": merged.get("weak_points", []),
        "recovery_capacity": _map_recovery_notes(merged.get("recovery_notes")),
    }

    # Use structured path to build the final profile
    return build_profile_from_structured(structured_data)


def _map_recovery_notes(notes: Optional[str]) -> str:
    """Map recovery notes from LLM extraction to recovery_capacity value."""
    if not notes:
        return "normal"

    notes_lower = notes.lower()

    # Check for low recovery indicators
    low_indicators = ["poor sleep", "stressed", "busy", "tired", "fatigued",
                      "recovery issues", "not sleeping", "overworked"]
    for indicator in low_indicators:
        if indicator in notes_lower:
            return "low"

    # Check for high recovery indicators
    high_indicators = ["great sleep", "well rested", "good recovery",
                       "sleeping well", "lots of rest", "athlete"]
    for indicator in high_indicators:
        if indicator in notes_lower:
            return "high"

    return "normal"


# ─────────────────────────────────────────────────────────────────────────────
# EXERCISE FILTERING
# ─────────────────────────────────────────────────────────────────────────────


def _filter_exercises_for_profile(
    equipment_tier: EquipmentTier,
    training_level: str,
    exercises_to_avoid: list[str],
    injuries: list[dict],
) -> tuple[list[str], list[str]]:
    """
    Filter exercises based on equipment tier, training level, and constraints.

    Returns:
        (available_exercise_ids, coverage_warnings)
    """
    available = []

    # Difficulty cap by level
    difficulty_cap = {"beginner": 3, "intermediate": 4, "advanced": 5}.get(training_level, 4)

    # Build set of exercises to avoid from injuries
    injury_avoids = set(exercises_to_avoid)
    for injury in injuries:
        avoid_list = injury.get("avoid", [])
        injury_avoids.update(avoid_list)

    for ex in EXERCISE_LIBRARY:
        # Check equipment tier
        if ex.equipment_tier.value > equipment_tier.value:
            continue

        # Check avoid list
        if ex.id in injury_avoids:
            continue

        # Check difficulty
        if ex.difficulty > difficulty_cap:
            continue

        # Check proficiency requirement
        if ex.requires_proficiency and training_level == "beginner":
            continue

        available.append(ex.id)

    # Check coverage: each muscle group should have at least 2 exercises
    coverage_warnings = _check_exercise_coverage(available)

    return available, coverage_warnings


def _check_exercise_coverage(available_ids: list[str]) -> list[str]:
    """
    Check that each muscle group has at least 2 available exercises.
    Returns list of muscle groups with insufficient coverage.
    """
    # Build a map: muscle → list of exercise IDs that hit it as primary
    muscle_coverage: dict[str, list[str]] = {m.value: [] for m in MuscleGroup}

    for ex in EXERCISE_LIBRARY:
        if ex.id not in available_ids:
            continue

        for ma in ex.muscle_activations:
            if ma.volume_credit >= 0.5:  # Primary or significant secondary
                muscle_coverage[ma.muscle.value].append(ex.id)

    warnings = []
    for muscle, exercises in muscle_coverage.items():
        if len(exercises) < 2:
            warnings.append(f"{muscle}: only {len(exercises)} exercise(s) available")

    return warnings


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────


def validate_profile(profile: AthleteProfile) -> list[str]:
    """
    Validate an AthleteProfile for completeness and consistency.
    Returns list of validation errors (empty if valid).
    """
    errors = []

    # Required field checks
    if not profile.user_id:
        errors.append("user_id is required")

    if profile.training_goal not in ("hypertrophy", "strength", "power"):
        errors.append(f"Invalid training_goal: {profile.training_goal}")

    if profile.training_level not in ("beginner", "intermediate", "advanced"):
        errors.append(f"Invalid training_level: {profile.training_level}")

    if not 2 <= profile.training_days_per_week <= 6:
        errors.append(f"training_days_per_week must be 2-6, got {profile.training_days_per_week}")

    if profile.program_duration_weeks < 1:
        errors.append(f"program_duration_weeks must be >= 1")

    # Coverage check
    if len(profile.available_exercises) < 20:
        errors.append(f"Only {len(profile.available_exercises)} exercises available - may not cover all muscle groups")

    return errors
