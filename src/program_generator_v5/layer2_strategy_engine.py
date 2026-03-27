"""
V6 Layer 2: Strategy Engine

Rules engine for split + periodization selection, with LLM fallback for edge cases.

Determines:
- Split selection (based on days/week, level, goal, training season)
- Periodization model (volume_ramp, linear_intensity, concurrent, dup, block, maintenance)
- Week profiles (volume_multiplier, intensity_modifier, RPE/RIR ranges)
- Mesocycle structure (with variable deload frequency by age/level)
- Sport-specific adjustments

V6 additions:
- DUP (Daily Undulating Periodization) for intermediate+ lifters
- Block periodization for peaking (pre-season, competition prep)
- Maintenance periodization for in-season athletes
- Age-tiered deload frequency
- Season-aware strategy selection
- DUP session emphasis patterns

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
    TrainingSeason,
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

    # V6: In-season forces maintenance split
    if profile.training_season == TrainingSeason.IN_SEASON:
        split_id = "maintenance_2x"
    else:
        split_id = get_split_for_config(
            days_per_week=profile.training_days_per_week,
            training_level=profile.training_level,
            goal=effective_goal,
        )
    split = SPLIT_TEMPLATES[split_id]

    # ── Step 2: Select periodization model ──────────────────────────────────
    periodization_model = _select_periodization_model(
        goal=effective_goal,
        training_level=profile.training_level,
        training_season=profile.training_season,
        days_per_week=profile.training_days_per_week,
    )

    # ── Step 3: Calculate mesocycle structure ───────────────────────────────
    mesocycle_length = _get_mesocycle_length(
        training_level=profile.training_level,
        age=profile.age,
        training_season=profile.training_season,
    )
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
        days_per_week=profile.training_days_per_week,
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
                valid_models = ("volume_ramp", "linear_intensity", "concurrent", "dup", "block", "maintenance")
                if new_periodization in valid_models:
                    periodization_model = new_periodization
                    # Rebuild week profiles with new model
                    week_profiles = _build_week_profiles(
                        total_weeks=profile.program_duration_weeks,
                        mesocycle_length=mesocycle_length,
                        periodization_model=periodization_model,
                        training_goal=effective_goal,
                        days_per_week=profile.training_days_per_week,
                    )

    # ── Step 7: VBT protocol selection ───────────────────────────────────────
    vbt_enabled = profile.vbt_capability
    vbt_protocol = ""
    if vbt_enabled:
        if effective_goal == "power":
            vbt_protocol = "velocity_based"     # Primary metric = bar speed
        elif effective_goal == "strength":
            vbt_protocol = "load_velocity"      # Primary = load, velocity for autoregulation
        else:  # hypertrophy
            vbt_protocol = "load_velocity"      # Velocity for fatigue monitoring

    return ProgramStrategy(
        split=split,
        week_profiles=week_profiles,
        periodization_model=periodization_model,
        volume_modifier=volume_modifier,
        emphasis_muscles=emphasis_muscles,
        deemphasis_muscles=deemphasis_muscles,
        mesocycle_count=num_mesocycles,
        vbt_enabled=vbt_enabled,
        vbt_protocol=vbt_protocol,
    )


# ─────────────────────────────────────────────────────────────────────────────
# PERIODIZATION MODEL SELECTION
# ─────────────────────────────────────────────────────────────────────────────


def _select_periodization_model(
    goal: str,
    training_level: str = "intermediate",
    training_season: TrainingSeason | None = None,
    days_per_week: int = 4,
) -> str:
    """
    V6: Smart periodization selection based on goal, level, season, and frequency.

    Decision tree:
    - in_season → "maintenance" (preserve strength, minimize fatigue)
    - pre_season → "block" (accumulation → transmutation → realization)
    - hypertrophy + beginner → "volume_ramp" (linear progression)
    - hypertrophy + intermediate/advanced + 3+ days → "dup" (daily undulating)
    - strength + beginner → "linear_intensity"
    - strength + intermediate/advanced → "dup"
    - power → "concurrent"
    """
    # Season overrides
    if training_season == TrainingSeason.IN_SEASON:
        return "maintenance"
    if training_season == TrainingSeason.PRE_SEASON:
        return "block"

    # Goal + level based selection
    if goal == "hypertrophy":
        if training_level == "beginner":
            return "volume_ramp"
        if training_level in ("intermediate", "advanced") and days_per_week >= 3:
            return "dup"
        return "volume_ramp"
    elif goal == "strength":
        if training_level == "beginner":
            return "linear_intensity"
        if training_level in ("intermediate", "advanced"):
            return "dup"
        return "linear_intensity"
    elif goal == "power":
        return "concurrent"
    else:
        return "volume_ramp"  # Default


def _get_mesocycle_length(
    training_level: str,
    age: int | None = None,
    training_season: TrainingSeason | None = None,
) -> int:
    """
    V6: Variable mesocycle length based on training level, age, and season.

    - Beginners: 3 weeks (3:1 load:deload)
    - Intermediate: 4 weeks (4:1)
    - Advanced: 4 weeks (can extend to 5-6 with reactive deloads)
    - Age 55+: 3 weeks (more frequent recovery needed)
    - In-season: 3 weeks (minimize fatigue accumulation)
    """
    # In-season: shorter mesocycles
    if training_season == TrainingSeason.IN_SEASON:
        return 3

    # Age overrides
    if age is not None and age >= 55:
        return 3

    # Level-based
    if training_level == "beginner":
        return 3

    # Age 40+ gets shorter mesocycles
    if age is not None and age >= 40:
        return 3

    return 4  # Intermediate/advanced default


# ─────────────────────────────────────────────────────────────────────────────
# WEEK PROFILE GENERATION
# ─────────────────────────────────────────────────────────────────────────────


def _build_week_profiles(
    total_weeks: int,
    mesocycle_length: int,
    periodization_model: str,
    training_goal: str,
    days_per_week: int = 4,
) -> list[WeekProfile]:
    """
    Build WeekProfile for every week in the program.

    Each mesocycle follows the pattern appropriate for the periodization model.
    Last week of each mesocycle is deload (except possibly the final week).

    V6: Supports DUP, block, and maintenance models.
    """
    # V6: Block periodization builds all weeks at once (not per-mesocycle)
    if periodization_model == "block":
        return _build_block_periodization_weeks(total_weeks)

    # V6: Maintenance has no deloads — flat structure
    if periodization_model == "maintenance":
        return _build_maintenance_weeks(total_weeks)

    week_profiles = []
    week_number = 1
    mesocycle_number = 1

    while week_number <= total_weeks:
        # Calculate weeks remaining
        remaining = total_weeks - week_number + 1

        # Determine actual mesocycle length for this meso
        actual_meso_length = min(mesocycle_length, remaining)

        # Build weeks for this mesocycle
        for week_in_meso in range(1, actual_meso_length + 1):
            is_last_week_of_meso = (week_in_meso == actual_meso_length)
            is_last_week_of_program = (week_number == total_weeks)

            is_deload = False
            if is_last_week_of_meso:
                if actual_meso_length < mesocycle_length and is_last_week_of_program:
                    if actual_meso_length <= 2:
                        is_deload = False
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
            elif periodization_model == "dup":
                wp = _build_dup_week(
                    week_number=week_number,
                    mesocycle_number=mesocycle_number,
                    week_in_meso=week_in_meso,
                    is_deload=is_deload,
                    days_per_week=days_per_week,
                )
            else:
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
# V6: DUP (DAILY UNDULATING PERIODIZATION)
# ─────────────────────────────────────────────────────────────────────────────


def _build_dup_week(
    week_number: int,
    mesocycle_number: int,
    week_in_meso: int,
    is_deload: bool,
    days_per_week: int = 4,
) -> WeekProfile:
    """
    Build week profile for DUP periodization.

    Within each week, sessions alternate emphasis:
    - Heavy (85%+ 1RM, 3-5 reps)
    - Moderate (70-80%, 6-8 reps)
    - Light/Power (60-70%, 8-12 or explosive)

    Volume ramps across weeks within mesocycle (like volume_ramp),
    but each session within a week has different intensity.
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
            notes="Recovery week — light movement quality work",
            session_emphases=["light"] * days_per_week,
            deload_type="volume",
        )

    # Build session emphasis pattern based on days per week
    if days_per_week >= 4:
        emphases = ["heavy", "moderate", "light", "moderate"][:days_per_week]
    elif days_per_week == 3:
        emphases = ["heavy", "moderate", "light"]
    else:
        emphases = ["heavy", "moderate"]

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
            notes="DUP Week 1 — establish patterns across intensity zones",
            session_emphases=emphases,
        )
    elif week_in_meso == 2:
        return WeekProfile(
            week_number=week_number,
            mesocycle_number=mesocycle_number,
            week_in_mesocycle=week_in_meso,
            phase_name="Building",
            volume_multiplier=1.10 + base_volume_bump,
            intensity_modifier="moderate_heavy",
            rpe_range=(7.0, 8.0),
            rir_range=(2, 3),
            is_deload=False,
            notes="DUP Week 2 — increase load on heavy days, add reps on light days",
            session_emphases=emphases,
        )
    else:
        return WeekProfile(
            week_number=week_number,
            mesocycle_number=mesocycle_number,
            week_in_mesocycle=week_in_meso,
            phase_name="Overreaching",
            volume_multiplier=1.20 + base_volume_bump,
            intensity_modifier="heavy",
            rpe_range=(8.0, 9.0),
            rir_range=(1, 2),
            is_deload=False,
            notes="DUP Week 3 — push all zones, heavy day near max effort",
            session_emphases=emphases,
        )


# ─────────────────────────────────────────────────────────────────────────────
# V6: BLOCK PERIODIZATION (for peaking / pre-season)
# ─────────────────────────────────────────────────────────────────────────────


def _build_block_periodization_weeks(total_weeks: int) -> list[WeekProfile]:
    """
    Build block periodization weeks.

    Phases:
    - Accumulation (40% of weeks): High volume, moderate intensity, hypertrophy focus
    - Transmutation (35% of weeks): Moderate volume, high intensity, strength focus
    - Realization (25% of weeks): Low volume, very high intensity, peaking
    """
    accum_weeks = max(2, round(total_weeks * 0.40))
    trans_weeks = max(2, round(total_weeks * 0.35))
    real_weeks = max(1, total_weeks - accum_weeks - trans_weeks)

    weeks = []
    week_num = 1

    # Accumulation block
    for i in range(accum_weeks):
        ramp = i / max(1, accum_weeks - 1)  # 0.0 → 1.0
        weeks.append(WeekProfile(
            week_number=week_num,
            mesocycle_number=1,
            week_in_mesocycle=i + 1,
            phase_name="Accumulation",
            volume_multiplier=1.0 + ramp * 0.25,  # 1.0 → 1.25
            intensity_modifier="moderate",
            rpe_range=(6.5 + ramp, 7.5 + ramp),
            rir_range=(max(1, 3 - int(ramp * 2)), 4 - int(ramp * 2)),
            is_deload=False,
            notes=f"Accumulation block — high volume, hypertrophy focus",
            block_phase="accumulation",
        ))
        week_num += 1

    # Transmutation block
    for i in range(trans_weeks):
        ramp = i / max(1, trans_weeks - 1)
        weeks.append(WeekProfile(
            week_number=week_num,
            mesocycle_number=2,
            week_in_mesocycle=i + 1,
            phase_name="Transmutation",
            volume_multiplier=0.85 - ramp * 0.10,  # 0.85 → 0.75
            intensity_modifier="heavy",
            rpe_range=(7.5 + ramp * 0.5, 8.5 + ramp * 0.5),
            rir_range=(max(1, 2 - int(ramp)), 2),
            is_deload=False,
            notes=f"Transmutation block — moderate volume, high intensity, strength focus",
            block_phase="transmutation",
        ))
        week_num += 1

    # Realization block
    for i in range(real_weeks):
        ramp = i / max(1, real_weeks - 1)
        weeks.append(WeekProfile(
            week_number=week_num,
            mesocycle_number=3,
            week_in_mesocycle=i + 1,
            phase_name="Realization",
            volume_multiplier=0.6 - ramp * 0.15,  # 0.6 → 0.45
            intensity_modifier="very_heavy",
            rpe_range=(8.5 + ramp * 0.5, 9.0 + ramp * 0.5),
            rir_range=(0, 1),
            is_deload=False,
            notes=f"Realization block — low volume, peak intensity, competition prep",
            block_phase="realization",
        ))
        week_num += 1

    return weeks


# ─────────────────────────────────────────────────────────────────────────────
# V6: MAINTENANCE PERIODIZATION (for in-season)
# ─────────────────────────────────────────────────────────────────────────────


def _build_maintenance_weeks(total_weeks: int) -> list[WeekProfile]:
    """
    Build maintenance periodization for in-season athletes.

    Key principles:
    - Intensity maintained at 85%+ (critical for strength maintenance)
    - Volume at 40-60% of off-season
    - No traditional deloads (competition schedule provides natural recovery)
    - 2 sessions/week max
    """
    weeks = []
    for i in range(total_weeks):
        weeks.append(WeekProfile(
            week_number=i + 1,
            mesocycle_number=1,
            week_in_mesocycle=i + 1,
            phase_name="Maintenance",
            volume_multiplier=0.50,  # 50% of off-season volume
            intensity_modifier="heavy",
            rpe_range=(7.5, 8.5),
            rir_range=(1, 3),
            is_deload=False,
            notes="In-season maintenance — preserve strength, minimize DOMS. "
                  "Intensity is the critical variable for maintaining strength.",
        ))
    return weeks


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
        "alternative_periodizations": ["volume_ramp", "linear_intensity", "concurrent", "dup", "block", "maintenance"],
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
        "alternative_periodizations": ["volume_ramp", "linear_intensity", "concurrent", "dup", "block", "maintenance"],
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
