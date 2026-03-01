"""
V5 Layer 2: Strategy Engine

Rules engine for split + periodization selection, with LLM fallback for edge cases.

Determines:
- Split selection (based on days/week, level, goal)
- Periodization model (volume_ramp, linear_intensity, concurrent)
- Week profiles (volume_multiplier, intensity_modifier, RPE/RIR ranges)
- Mesocycle structure
- Sport-specific adjustments

90%+ of cases are handled deterministically; LLM only for conflicting constraints.
"""

from __future__ import annotations

import json
from typing import Optional

from .schemas import (
    AthleteProfile,
    ProgramStrategy,
    WeekProfile,
    MuscleGroup,
)
from .split_templates import SPLIT_TEMPLATES, get_split_for_config
from .sport_mappings import get_sport_adjustments
from .prompts import format_strategy_resolution_prompt


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────


def build_strategy(
    profile: AthleteProfile,
    openai_client=None,
) -> ProgramStrategy:
    """
    Build the program strategy from the athlete profile.

    Steps:
    1. Select split via get_split_for_config() — deterministic
    2. Select periodization model based on goal
    3. Calculate mesocycle structure
    4. Build WeekProfile for every week
    5. Apply sport adjustments if profile.sport is set
    6. If conflicting constraints: try rules, then LLM fallback

    Args:
        profile: AthleteProfile with all fields populated
        openai_client: Optional OpenAI client for edge case resolution

    Returns:
        ProgramStrategy with split, week_profiles, periodization model, etc.
    """
    # ── Step 1: Select split ────────────────────────────────────────────────
    effective_goal = profile.effective_goal or profile.training_goal
    split_id = get_split_for_config(
        days_per_week=profile.training_days_per_week,
        training_level=profile.training_level,
        goal=effective_goal,
    )
    split = SPLIT_TEMPLATES[split_id]

    # ── Step 2: Select periodization model ──────────────────────────────────
    periodization_model = _select_periodization_model(effective_goal)

    # ── Step 3: Calculate mesocycle structure ───────────────────────────────
    mesocycle_length = _get_mesocycle_length(profile.training_level)
    num_mesocycles = max(1, profile.program_duration_weeks // mesocycle_length)

    # Handle programs that don't divide evenly
    # If there are leftover weeks, they become a partial final mesocycle
    leftover_weeks = profile.program_duration_weeks % mesocycle_length
    if leftover_weeks > 0:
        num_mesocycles += 1  # Partial final mesocycle

    # ── Step 4: Build week profiles ─────────────────────────────────────────
    week_profiles = _build_week_profiles(
        total_weeks=profile.program_duration_weeks,
        mesocycle_length=mesocycle_length,
        periodization_model=periodization_model,
        training_goal=effective_goal,
    )

    # ── Step 5: Apply sport adjustments ─────────────────────────────────────
    volume_modifier = 1.0
    emphasis_muscles: list[MuscleGroup] = []
    deemphasis_muscles: list[MuscleGroup] = []

    if profile.sport_adjustments:
        adj = profile.sport_adjustments
        volume_modifier = adj.get("volume_modifier", 1.0)

        # Convert muscle names to MuscleGroup enums
        for muscle_name in adj.get("emphasis_muscles", []):
            try:
                emphasis_muscles.append(MuscleGroup(muscle_name))
            except ValueError:
                pass  # Skip invalid muscle names

        for muscle_name in adj.get("deemphasis_muscles", []):
            try:
                deemphasis_muscles.append(MuscleGroup(muscle_name))
            except ValueError:
                pass

    # ── Step 6: Check for conflicts ─────────────────────────────────────────
    conflicts = _detect_conflicts(profile, split, periodization_model)

    if conflicts and openai_client:
        # Try to resolve with LLM
        resolution = _resolve_conflicts_with_llm(
            profile=profile,
            conflicts=conflicts,
            current_split=split_id,
            current_periodization=periodization_model,
            openai_client=openai_client,
        )
        if resolution:
            # Apply resolution
            if resolution.get("resolution") == "override_split":
                new_split_id = resolution.get("value")
                if new_split_id in SPLIT_TEMPLATES:
                    split = SPLIT_TEMPLATES[new_split_id]
            elif resolution.get("resolution") == "override_periodization":
                new_periodization = resolution.get("value")
                if new_periodization in ("volume_ramp", "linear_intensity", "concurrent"):
                    periodization_model = new_periodization
                    # Rebuild week profiles with new model
                    week_profiles = _build_week_profiles(
                        total_weeks=profile.program_duration_weeks,
                        mesocycle_length=mesocycle_length,
                        periodization_model=periodization_model,
                        training_goal=effective_goal,
                    )

    return ProgramStrategy(
        split=split,
        week_profiles=week_profiles,
        periodization_model=periodization_model,
        volume_modifier=volume_modifier,
        emphasis_muscles=emphasis_muscles,
        deemphasis_muscles=deemphasis_muscles,
        mesocycle_count=num_mesocycles,
    )


# ─────────────────────────────────────────────────────────────────────────────
# PERIODIZATION MODEL SELECTION
# ─────────────────────────────────────────────────────────────────────────────


def _select_periodization_model(goal: str) -> str:
    """
    Select the appropriate periodization model for the goal.

    - hypertrophy → volume_ramp (volume increases across weeks, then deload)
    - strength → linear_intensity (intensity increases, volume moderate-to-lower)
    - power → concurrent (power + strength trained concurrently)
    """
    if goal == "hypertrophy":
        return "volume_ramp"
    elif goal == "strength":
        return "linear_intensity"
    elif goal == "power":
        return "concurrent"
    else:
        return "volume_ramp"  # Default


def _get_mesocycle_length(training_level: str) -> int:
    """
    Get mesocycle length in weeks based on training level.

    - Beginners: 3 weeks (recover faster, need frequent deloads)
    - Intermediate/Advanced: 4 weeks (standard mesocycle)
    """
    if training_level == "beginner":
        return 3
    return 4


# ─────────────────────────────────────────────────────────────────────────────
# WEEK PROFILE GENERATION
# ─────────────────────────────────────────────────────────────────────────────


def _build_week_profiles(
    total_weeks: int,
    mesocycle_length: int,
    periodization_model: str,
    training_goal: str,
) -> list[WeekProfile]:
    """
    Build WeekProfile for every week in the program.

    Each mesocycle follows the pattern appropriate for the periodization model.
    Last week of each mesocycle is deload (except possibly the final week).
    """
    week_profiles = []
    week_number = 1
    mesocycle_number = 1

    while week_number <= total_weeks:
        # Calculate weeks remaining
        remaining = total_weeks - week_number + 1

        # Determine actual mesocycle length for this meso
        # If remaining weeks < mesocycle_length, it's a partial final mesocycle
        actual_meso_length = min(mesocycle_length, remaining)

        # Build weeks for this mesocycle
        for week_in_meso in range(1, actual_meso_length + 1):
            # Determine if this should be a deload week
            is_last_week_of_meso = (week_in_meso == actual_meso_length)
            is_last_week_of_program = (week_number == total_weeks)

            # Deload on last week of meso, UNLESS:
            # - It's the last week of the program AND the meso is partial (< full length)
            # - In that case, we may skip deload to maximize training stimulus
            is_deload = False
            if is_last_week_of_meso:
                # Skip deload if partial meso at end AND short program
                if actual_meso_length < mesocycle_length and is_last_week_of_program:
                    if actual_meso_length <= 2:
                        is_deload = False  # Don't deload on 1-2 week final meso
                    else:
                        is_deload = True
                else:
                    is_deload = True

            # Build the week profile based on periodization model
            if periodization_model == "volume_ramp":
                wp = _build_volume_ramp_week(
                    week_number=week_number,
                    mesocycle_number=mesocycle_number,
                    week_in_meso=week_in_meso,
                    is_deload=is_deload,
                )
            elif periodization_model == "linear_intensity":
                wp = _build_linear_intensity_week(
                    week_number=week_number,
                    mesocycle_number=mesocycle_number,
                    week_in_meso=week_in_meso,
                    is_deload=is_deload,
                )
            elif periodization_model == "concurrent":
                wp = _build_concurrent_week(
                    week_number=week_number,
                    mesocycle_number=mesocycle_number,
                    week_in_meso=week_in_meso,
                    is_deload=is_deload,
                )
            else:
                # Fallback
                wp = _build_volume_ramp_week(
                    week_number=week_number,
                    mesocycle_number=mesocycle_number,
                    week_in_meso=week_in_meso,
                    is_deload=is_deload,
                )

            week_profiles.append(wp)
            week_number += 1

        mesocycle_number += 1

    return week_profiles


def _build_volume_ramp_week(
    week_number: int,
    mesocycle_number: int,
    week_in_meso: int,
    is_deload: bool,
) -> WeekProfile:
    """
    Build week profile for hypertrophy (volume_ramp) periodization.

    Pattern (4-week mesocycle):
    - Week 1 (Introduction): volume_multiplier=1.0, RPE 6.5-7.5, RIR 3-4
    - Week 2 (Building): volume_multiplier=1.15, RPE 7.0-8.0, RIR 2-3
    - Week 3 (Overreaching): volume_multiplier=1.25, RPE 8.0-9.0, RIR 1-2
    - Week 4 (Deload): volume_multiplier=0.5, RPE 5.0-6.0, RIR 4-6

    Each subsequent mesocycle starts with slightly higher baseline (+5%).
    """
    base_volume_bump = (mesocycle_number - 1) * 0.05

    if is_deload:
        return WeekProfile(
            week_number=week_number,
            mesocycle_number=mesocycle_number,
            week_in_mesocycle=week_in_meso,
            phase_name="Deload",
            volume_multiplier=0.5,
            intensity_modifier="deload",
            rpe_range=(5.0, 6.0),
            rir_range=(4, 6),
            is_deload=True,
            notes="Recovery week — reduce volume, maintain movement patterns",
        )

    # Non-deload weeks based on position in mesocycle
    if week_in_meso == 1:
        return WeekProfile(
            week_number=week_number,
            mesocycle_number=mesocycle_number,
            week_in_mesocycle=week_in_meso,
            phase_name="Introduction",
            volume_multiplier=1.0 + base_volume_bump,
            intensity_modifier="moderate",
            rpe_range=(6.5, 7.5),
            rir_range=(3, 4),
            is_deload=False,
            notes="Establish movement patterns, begin stimulus",
        )
    elif week_in_meso == 2:
        return WeekProfile(
            week_number=week_number,
            mesocycle_number=mesocycle_number,
            week_in_mesocycle=week_in_meso,
            phase_name="Building",
            volume_multiplier=1.15 + base_volume_bump,
            intensity_modifier="moderate",
            rpe_range=(7.0, 8.0),
            rir_range=(2, 3),
            is_deload=False,
            notes="Progressive overload — add sets/reps",
        )
    else:  # week_in_meso == 3 (or higher for partial mesos)
        return WeekProfile(
            week_number=week_number,
            mesocycle_number=mesocycle_number,
            week_in_mesocycle=week_in_meso,
            phase_name="Overreaching",
            volume_multiplier=1.25 + base_volume_bump,
            intensity_modifier="moderate_heavy",
            rpe_range=(8.0, 9.0),
            rir_range=(1, 2),
            is_deload=False,
            notes="Maximum stimulus before deload — push isolations to failure on last sets",
        )


def _build_linear_intensity_week(
    week_number: int,
    mesocycle_number: int,
    week_in_meso: int,
    is_deload: bool,
) -> WeekProfile:
    """
    Build week profile for strength (linear_intensity) periodization.

    Pattern (4-week mesocycle):
    - Week 1 (Accumulation): volume_multiplier=1.0, moderate-heavy, RPE 7.0-7.5
    - Week 2 (Intensification): volume_multiplier=0.95, heavy, RPE 7.5-8.0
    - Week 3 (Peak): volume_multiplier=0.85, very heavy, RPE 8.0-8.5
    - Week 4 (Deload): volume_multiplier=0.5, deload, RPE 5.0-6.0
    """
    if is_deload:
        return WeekProfile(
            week_number=week_number,
            mesocycle_number=mesocycle_number,
            week_in_mesocycle=week_in_meso,
            phase_name="Deload",
            volume_multiplier=0.5,
            intensity_modifier="deload",
            rpe_range=(5.0, 6.0),
            rir_range=(4, 6),
            is_deload=True,
            notes="Recovery week — maintain technique with lighter loads",
        )

    if week_in_meso == 1:
        return WeekProfile(
            week_number=week_number,
            mesocycle_number=mesocycle_number,
            week_in_mesocycle=week_in_meso,
            phase_name="Accumulation",
            volume_multiplier=1.0,
            intensity_modifier="moderate_heavy",
            rpe_range=(7.0, 7.5),
            rir_range=(2, 3),
            is_deload=False,
            notes="Build work capacity with moderate loads",
        )
    elif week_in_meso == 2:
        return WeekProfile(
            week_number=week_number,
            mesocycle_number=mesocycle_number,
            week_in_mesocycle=week_in_meso,
            phase_name="Intensification",
            volume_multiplier=0.95,
            intensity_modifier="heavy",
            rpe_range=(7.5, 8.0),
            rir_range=(2, 2),
            is_deload=False,
            notes="Increase intensity, slightly reduce volume",
        )
    else:  # week_in_meso == 3
        return WeekProfile(
            week_number=week_number,
            mesocycle_number=mesocycle_number,
            week_in_mesocycle=week_in_meso,
            phase_name="Peak",
            volume_multiplier=0.85,
            intensity_modifier="very_heavy",
            rpe_range=(8.0, 8.5),
            rir_range=(1, 2),
            is_deload=False,
            notes="Heaviest working week — peak strength expression",
        )


def _build_concurrent_week(
    week_number: int,
    mesocycle_number: int,
    week_in_meso: int,
    is_deload: bool,
) -> WeekProfile:
    """
    Build week profile for power (concurrent) periodization.

    Pattern (4-week mesocycle):
    - Weeks 1-2: Higher power volume, moderate strength
    - Week 3: Peak strength intensity, power maintained
    - Week 4: Deload all components
    """
    if is_deload:
        return WeekProfile(
            week_number=week_number,
            mesocycle_number=mesocycle_number,
            week_in_mesocycle=week_in_meso,
            phase_name="Deload",
            volume_multiplier=0.5,
            intensity_modifier="deload",
            rpe_range=(5.0, 6.0),
            rir_range=(4, 6),
            is_deload=True,
            notes="CNS recovery — maintain movement quality with reduced volume",
        )

    if week_in_meso in (1, 2):
        return WeekProfile(
            week_number=week_number,
            mesocycle_number=mesocycle_number,
            week_in_mesocycle=week_in_meso,
            phase_name="Power Development",
            volume_multiplier=1.0 if week_in_meso == 1 else 1.05,
            intensity_modifier="moderate",
            rpe_range=(7.0, 8.0),
            rir_range=(2, 3),
            is_deload=False,
            notes="Focus on explosive power — speed over load",
        )
    else:  # week_in_meso == 3
        return WeekProfile(
            week_number=week_number,
            mesocycle_number=mesocycle_number,
            week_in_mesocycle=week_in_meso,
            phase_name="Strength Integration",
            volume_multiplier=0.9,
            intensity_modifier="heavy",
            rpe_range=(8.0, 8.5),
            rir_range=(1, 2),
            is_deload=False,
            notes="Peak strength intensity — power work maintained",
        )


# ─────────────────────────────────────────────────────────────────────────────
# CONFLICT DETECTION
# ─────────────────────────────────────────────────────────────────────────────


def _detect_conflicts(
    profile: AthleteProfile,
    split,
    periodization_model: str,
) -> list[str]:
    """
    Detect conflicting constraints that may require LLM resolution.

    Conflict examples:
    - Beginner wanting 6 days/week (too much volume)
    - Multiple injuries eliminating most compounds
    - Conflicting goal statements (hypertrophy + peaking for meet)
    """
    conflicts = []

    # Beginner with very high frequency
    if profile.training_level == "beginner" and profile.training_days_per_week >= 6:
        conflicts.append(
            f"Beginner with {profile.training_days_per_week} days/week may be excessive. "
            "Consider reducing to 4 days or using full-body split."
        )

    # Too many injuries eliminating exercises
    if len(profile.exercises_to_avoid) > 20:
        conflicts.append(
            f"{len(profile.exercises_to_avoid)} exercises avoided due to injuries/preferences. "
            "May limit exercise variety."
        )

    # Sport-specific goal conflicts
    if profile.sport and profile.training_goal != profile.effective_goal:
        conflicts.append(
            f"User stated '{profile.training_goal}' goal but sport ({profile.sport}) "
            f"recommends '{profile.effective_goal}'. Using sport-specific approach."
        )

    # Advanced user with only 2 days/week
    if profile.training_level == "advanced" and profile.training_days_per_week <= 2:
        conflicts.append(
            f"Advanced trainee with only {profile.training_days_per_week} days/week. "
            "Frequency may be suboptimal for this training level."
        )

    # Very short program duration
    if profile.program_duration_weeks < 3:
        conflicts.append(
            f"Program duration ({profile.program_duration_weeks} weeks) is very short. "
            "May not see significant adaptations."
        )

    return conflicts


# ─────────────────────────────────────────────────────────────────────────────
# LLM CONFLICT RESOLUTION (EDGE CASES ONLY)
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_conflicts_with_llm(
    profile: AthleteProfile,
    conflicts: list[str],
    current_split: str,
    current_periodization: str,
    openai_client,
) -> Optional[dict]:
    """
    Use LLM to resolve conflicting constraints.

    This is called ONLY when deterministic rules can't resolve the conflict.
    """
    if not openai_client:
        return None

    # Build rules output for prompt
    rules_output = {
        "split": current_split,
        "periodization": current_periodization,
        "alternative_splits": [s for s in SPLIT_TEMPLATES.keys() if s != current_split],
        "alternative_periodizations": ["volume_ramp", "linear_intensity", "concurrent"],
        "possible_adjustments": "Reduce training frequency, modify volume targets, etc.",
    }

    conflict_description = "\n".join(f"- {c}" for c in conflicts)

    prompt = format_strategy_resolution_prompt(
        conflict_description=conflict_description,
        rules_output=rules_output,
        profile=profile,
    )

    try:
        # Note: This would be async in real usage
        # For now, we return None and let calling code handle
        # In the async main.py, this would be properly awaited
        return None  # Simplified for sync testing
    except Exception as e:
        print(f"⚠️  LLM conflict resolution failed: {e}")
        return None


async def resolve_conflicts_async(
    profile: AthleteProfile,
    conflicts: list[str],
    current_split: str,
    current_periodization: str,
    openai_client,
) -> Optional[dict]:
    """
    Async version of conflict resolution for use in async pipeline.
    """
    if not openai_client or not conflicts:
        return None

    rules_output = {
        "split": current_split,
        "periodization": current_periodization,
        "alternative_splits": [s for s in SPLIT_TEMPLATES.keys() if s != current_split],
        "alternative_periodizations": ["volume_ramp", "linear_intensity", "concurrent"],
        "possible_adjustments": "Reduce training frequency, modify volume targets, etc.",
    }

    conflict_description = "\n".join(f"- {c}" for c in conflicts)

    prompt = format_strategy_resolution_prompt(
        conflict_description=conflict_description,
        rules_output=rules_output,
        profile=profile,
    )

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-5-mini",  # Per spec: gpt-5-mini for strategy resolution
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.3,
        )

        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"⚠️  LLM conflict resolution failed: {e}")
        return None
