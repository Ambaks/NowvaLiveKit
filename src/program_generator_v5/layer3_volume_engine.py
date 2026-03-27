"""
V6 Layer 3: Volume Engine

100% deterministic. No LLM calls. Pure math.

Calculates weekly volume targets per muscle group based on:
- Training level (beginner/intermediate/advanced)
- Training goal (hypertrophy/strength/power)
- Week profile (volume_multiplier, is_deload)
- Sport adjustments, recovery capacity, weak points
- Distributes weekly volume across sessions

V6 additions:
- MV (Maintenance Volume) floor for in-season / deloads
- Age-tiered volume multipliers (youth safety, senior joint care)
- Sex-based volume modifier (females +10%)
- In-season volume reduction (40-60%)
- Training season awareness

Algorithm from spec § Layer 3.
"""

from __future__ import annotations

import math
from typing import Optional

from .schemas import (
    AthleteProfile,
    ProgramStrategy,
    VolumeAllocation,
    WeekVolumeAllocation,
    SessionVolumeTarget,
    MuscleGroup,
    MovementPattern,
    TrainingSeason,
)
from .volume_tables import get_volume_targets, get_age_multiplier, get_sex_modifier


def calculate_volume(
    profile: AthleteProfile,
    strategy: ProgramStrategy,
) -> VolumeAllocation:
    """
    Calculate volume allocation for the entire program.

    Returns VolumeAllocation with all weeks populated with:
    - Weekly volume targets per muscle
    - Session volume distribution
    - Movement pattern requirements per session

    Validates that all non-deload weeks meet MEV minimums and stay under MRV caps.
    """
    weeks = []

    for week_profile in strategy.week_profiles:
        week_allocation = _calculate_week_volume(
            profile=profile,
            strategy=strategy,
            week_profile=week_profile,
        )
        weeks.append(week_allocation)

    return VolumeAllocation(weeks=weeks)


def _calculate_week_volume(
    profile: AthleteProfile,
    strategy: ProgramStrategy,
    week_profile,
) -> WeekVolumeAllocation:
    """Calculate volume allocation for a single week."""

    # Step 1: Calculate prescribed weekly volume for each muscle group
    weekly_totals = {}
    below_mev = []
    above_mrv = []

    for muscle in MuscleGroup:
        muscle_key = muscle.value

        # Get base MV/MEV/MAV/MRV from volume tables
        targets = get_volume_targets(profile.training_level, muscle_key)
        mv = targets["mv"]
        mev = targets["mev"]
        mav = targets["mav"]
        mrv = targets["mrv"]

        # V6: Determine if in-season (MV floor instead of MEV floor)
        is_in_season = (
            profile.training_season == TrainingSeason.IN_SEASON
        )

        # Calculate prescribed volume based on goal and week profile
        if week_profile.is_deload:
            # V6: Deload uses MV as floor (maintenance volume)
            prescribed = max(mv, round(mev * 0.5))
        else:
            # Base calculation depends on goal
            if profile.training_goal == "hypertrophy":
                # BUG 4 FIX: Volume ramp formula from spec
                # multiplier 1.0 → MEV (Week 1 introduction)
                # multiplier 1.25 → MAV (Week 3 overreaching)
                # multiplier 1.5 → MRV (cap, would be overly aggressive)
                # Formula: base = MEV + (multiplier - 1.0) * (MAV - MEV) / 0.25
                # This means: mult=1.0 → MEV, mult=1.25 → MAV, mult=1.5 → MRV
                mav_mev_range = mav - mev
                prescribed = mev + (week_profile.volume_multiplier - 1.0) / 0.25 * mav_mev_range
                # Clamp to [MEV, MRV]
                prescribed = max(mev, min(mrv, prescribed))

            elif profile.training_goal == "strength":
                # Lower base volume than hypertrophy
                base = mev + 0.3 * (mav - mev)
                prescribed = base * week_profile.volume_multiplier

            elif profile.training_goal == "power":
                # Even lower volume - save recovery for explosive work
                base = mev + 0.2 * (mav - mev)
                prescribed = base * week_profile.volume_multiplier

            else:
                # Default fallback
                prescribed = mev * week_profile.volume_multiplier

        # Apply modifiers

        # Sport volume modifier (from strategy)
        prescribed *= strategy.volume_modifier

        # Recovery capacity
        if profile.recovery_capacity == "low":
            prescribed *= 0.85
        elif profile.recovery_capacity == "high":
            prescribed *= 1.10

        # V6: Age-tiered volume multiplier (replaces old age > 45 check)
        prescribed *= get_age_multiplier(profile.age)

        # V6: Sex-based volume modifier (females +10% volume tolerance)
        prescribed *= get_sex_modifier(profile.sex)

        # Weak points / emphasis
        if muscle in strategy.emphasis_muscles or muscle_key in profile.weak_points:
            prescribed *= 1.20

        # De-emphasis
        if muscle in strategy.deemphasis_muscles:
            prescribed *= 0.80

        # Round to integers
        prescribed = round(prescribed)

        # Clamp to valid range
        if not week_profile.is_deload:
            if is_in_season:
                # V6: In-season — MV is the floor (not MEV), allow lower volumes
                if prescribed < mv:
                    prescribed = mv
                    below_mev.append(muscle_key)
            else:
                # Standard: ensure >= MEV and <= MRV
                if prescribed < mev:
                    prescribed = mev
                    below_mev.append(muscle_key)
            if prescribed > mrv:
                prescribed = mrv
                above_mrv.append(muscle_key)
        else:
            # Deload weeks: MV floor, minimum 2 sets
            prescribed = max(2, max(mv, prescribed))

        weekly_totals[muscle_key] = float(prescribed)

    # Step 2: Distribute weekly volume across sessions
    sessions = []
    split = strategy.split

    for session_template in split.sessions_per_week:
        session_volumes = {}

        for muscle in session_template.muscle_groups:
            muscle_key = muscle.value
            weekly_total = weekly_totals.get(muscle_key, 0)

            # Find how many sessions target this muscle
            sessions_targeting = sum(
                1 for s in split.sessions_per_week
                if muscle in s.muscle_groups
            )

            # Divide evenly
            sets_per_session = weekly_total / sessions_targeting if sessions_targeting > 0 else 0

            # Cap at 10 sets per muscle per session
            sets_per_session = min(sets_per_session, 10)

            session_volumes[muscle_key] = round(sets_per_session)

        # Calculate total session sets
        total_sets = sum(session_volumes.values())

        # NOTE: Removed time budget scaling here - the program builder will handle
        # time constraints by selecting exercises intelligently. Layer 3 should
        # calculate ideal volume targets without artificial caps.
        # The builder will naturally limit exercises to hit targets within time.

        # Derive movement pattern requirements
        pattern_requirements = _derive_pattern_requirements(
            session_template,
            session_volumes,
            profile.training_goal,
        )

        sessions.append(SessionVolumeTarget(
            day_label=session_template.day_label,
            muscle_volumes=session_volumes,
            total_sets=int(total_sets),
            movement_pattern_requirements=pattern_requirements,
        ))

    # Recalculate actual weekly totals after distribution
    # (may differ slightly due to rounding and caps)
    actual_weekly_totals = {}
    for muscle in MuscleGroup:
        muscle_key = muscle.value
        total = sum(
            session.muscle_volumes.get(muscle_key, 0)
            for session in sessions
        )
        actual_weekly_totals[muscle_key] = float(total)

    return WeekVolumeAllocation(
        week_number=week_profile.week_number,
        is_deload=week_profile.is_deload,
        sessions=sessions,
        weekly_totals=actual_weekly_totals,
        below_mev=below_mev,
        above_mrv=above_mrv,
    )


def _derive_pattern_requirements(
    session_template,
    session_volumes: dict[str, int],
    training_goal: str,
) -> dict[str, int]:
    """
    Derive movement pattern requirements based on muscle volumes.

    Returns dict of {pattern: minimum_count}
    """
    requirements = {}

    # Start with required patterns from template
    for pattern in session_template.required_movement_patterns:
        requirements[pattern.value] = 1

    # Add patterns needed to fulfill muscle volumes

    # Chest volume → needs push patterns
    if session_volumes.get("chest", 0) > 0 or session_volumes.get("upper_chest", 0) > 0:
        if MovementPattern.HORIZONTAL_PUSH in session_template.required_movement_patterns:
            requirements[MovementPattern.HORIZONTAL_PUSH.value] = max(
                requirements.get(MovementPattern.HORIZONTAL_PUSH.value, 0), 1
            )
        if MovementPattern.VERTICAL_PUSH in session_template.required_movement_patterns:
            requirements[MovementPattern.VERTICAL_PUSH.value] = max(
                requirements.get(MovementPattern.VERTICAL_PUSH.value, 0), 1
            )

    # Lat volume → needs pull patterns
    if session_volumes.get("lats", 0) > 0:
        requirements[MovementPattern.VERTICAL_PULL.value] = max(
            requirements.get(MovementPattern.VERTICAL_PULL.value, 0), 1
        )

    # Upper back → horizontal pull
    if session_volumes.get("upper_back", 0) > 0:
        requirements[MovementPattern.HORIZONTAL_PULL.value] = max(
            requirements.get(MovementPattern.HORIZONTAL_PULL.value, 0), 1
        )

    # Quads → squat/lunge
    if session_volumes.get("quads", 0) > 0:
        if MovementPattern.SQUAT in session_template.required_movement_patterns:
            requirements[MovementPattern.SQUAT.value] = max(
                requirements.get(MovementPattern.SQUAT.value, 0), 1
            )

    # Hamstrings/glutes → hip hinge
    if session_volumes.get("hamstrings", 0) > 0 or session_volumes.get("glutes", 0) > 0:
        if MovementPattern.HIP_HINGE in session_template.required_movement_patterns:
            requirements[MovementPattern.HIP_HINGE.value] = max(
                requirements.get(MovementPattern.HIP_HINGE.value, 0), 1
            )

    # Side delts → isolation push
    if session_volumes.get("side_delts", 0) > 0:
        requirements[MovementPattern.ISOLATION_PUSH.value] = max(
            requirements.get(MovementPattern.ISOLATION_PUSH.value, 0), 1
        )

    # Biceps → isolation pull
    if session_volumes.get("biceps", 0) > 0:
        requirements[MovementPattern.ISOLATION_PULL.value] = max(
            requirements.get(MovementPattern.ISOLATION_PULL.value, 0), 1
        )

    # Triceps → isolation push
    if session_volumes.get("triceps", 0) > 0:
        if MovementPattern.ISOLATION_PUSH.value not in requirements:
            requirements[MovementPattern.ISOLATION_PUSH.value] = 1

    # Rear delts → isolation pull
    if session_volumes.get("rear_delts", 0) > 0:
        if MovementPattern.ISOLATION_PULL.value not in requirements:
            requirements[MovementPattern.ISOLATION_PULL.value] = 1

    return requirements
