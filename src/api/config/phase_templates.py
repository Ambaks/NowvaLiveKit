"""
Phase templates for program generation.

Defines structured phase blocks for different training goals and durations.
Each template specifies phases with detailed training parameters.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class PhaseBlock:
    """Represents a single phase within a training program."""
    name: str
    week_start: int  # 1-indexed
    week_end: int    # inclusive
    sets_x_reps: str
    intensity_range: str
    rest_period: str
    volume_adjustment: str
    exercise_selection: str
    notes: Optional[str] = None


@dataclass
class PhaseTemplate:
    """Complete phase structure for a specific goal and duration."""
    goal: str
    duration_weeks: int
    phases: List[PhaseBlock]


# ============================================================================
# HYPERTROPHY TEMPLATES
# ============================================================================

HYPERTROPHY_12W = PhaseTemplate(
    goal="hypertrophy",
    duration_weeks=12,
    phases=[
        PhaseBlock(
            name="Hypertrophy I",
            week_start=1,
            week_end=4,
            sets_x_reps="4x10-12",
            intensity_range="60-70%",
            rest_period="60-90s",
            volume_adjustment="Normal",
            exercise_selection="High variety, isolation work, machines",
            notes="Focus on metabolic stress and muscle damage. High variety in exercise selection."
        ),
        PhaseBlock(
            name="Deload",
            week_start=5,
            week_end=5,
            sets_x_reps="2x10",
            intensity_range="50-60%",
            rest_period="60s",
            volume_adjustment="Reduce volume by 40-50%",
            exercise_selection="Same movements, half volume",
            notes="Recovery week to dissipate fatigue before next phase."
        ),
        PhaseBlock(
            name="Hypertrophy II",
            week_start=6,
            week_end=9,
            sets_x_reps="4x8-10",
            intensity_range="67-75%",
            rest_period="90-120s",
            volume_adjustment="Normal",
            exercise_selection="Compound emphasis, progressive overload",
            notes="Increase mechanical tension. Progress load week to week."
        ),
        PhaseBlock(
            name="Deload",
            week_start=10,
            week_end=10,
            sets_x_reps="2x8",
            intensity_range="55-65%",
            rest_period="60s",
            volume_adjustment="Reduce volume by 40-50%",
            exercise_selection="Same movements, reduced volume",
            notes="Recovery week before realization phase."
        ),
        PhaseBlock(
            name="Strength/Realization",
            week_start=11,
            week_end=12,
            sets_x_reps="3x5-6",
            intensity_range="75-82%",
            rest_period="2-3min",
            volume_adjustment="Normal",
            exercise_selection="Test movements, express gains",
            notes="Express hypertrophy gains through strength testing."
        ),
    ]
)

HYPERTROPHY_8W = PhaseTemplate(
    goal="hypertrophy",
    duration_weeks=8,
    phases=[
        PhaseBlock(
            name="Hypertrophy I",
            week_start=1,
            week_end=3,
            sets_x_reps="4x10-12",
            intensity_range="63-72%",
            rest_period="60-90s",
            volume_adjustment="Normal",
            exercise_selection="High variety, isolation emphasis",
            notes="Accumulation phase focusing on volume and variety."
        ),
        PhaseBlock(
            name="Deload",
            week_start=4,
            week_end=4,
            sets_x_reps="2x10",
            intensity_range="55%",
            rest_period="60s",
            volume_adjustment="Reduce volume by 50%",
            exercise_selection="Same movements, half volume",
            notes="Mid-program deload for recovery."
        ),
        PhaseBlock(
            name="Hypertrophy II",
            week_start=5,
            week_end=7,
            sets_x_reps="4x8-10",
            intensity_range="68-77%",
            rest_period="90s",
            volume_adjustment="Normal",
            exercise_selection="Compound emphasis, progressive loads",
            notes="Intensification phase with heavier loads."
        ),
        PhaseBlock(
            name="Realization",
            week_start=8,
            week_end=8,
            sets_x_reps="3x6",
            intensity_range="77-82%",
            rest_period="2min",
            volume_adjustment="Normal",
            exercise_selection="Key test movements",
            notes="Peak week to express strength gains from hypertrophy."
        ),
    ]
)

HYPERTROPHY_4W = PhaseTemplate(
    goal="hypertrophy",
    duration_weeks=4,
    phases=[
        PhaseBlock(
            name="High Volume",
            week_start=1,
            week_end=1,
            sets_x_reps="4x12",
            intensity_range="65%",
            rest_period="60s",
            volume_adjustment="Normal",
            exercise_selection="High variety, metabolic stress",
            notes="Metabolic stress emphasis."
        ),
        PhaseBlock(
            name="Volume + Load",
            week_start=2,
            week_end=2,
            sets_x_reps="4x10",
            intensity_range="70%",
            rest_period="90s",
            volume_adjustment="Normal",
            exercise_selection="Balanced selection",
            notes="Progress load while maintaining volume."
        ),
        PhaseBlock(
            name="Moderate Volume",
            week_start=3,
            week_end=3,
            sets_x_reps="4x8",
            intensity_range="75%",
            rest_period="90s",
            volume_adjustment="Normal",
            exercise_selection="Mechanical tension focus",
            notes="Mechanical tension peak."
        ),
        PhaseBlock(
            name="Realization",
            week_start=4,
            week_end=4,
            sets_x_reps="3x6",
            intensity_range="78-80%",
            rest_period="2min",
            volume_adjustment="Normal",
            exercise_selection="Test rep maxes",
            notes="Test rep maxes (6RM, 8RM)."
        ),
    ]
)

# ============================================================================
# STRENGTH TEMPLATES
# ============================================================================

STRENGTH_12W = PhaseTemplate(
    goal="strength",
    duration_weeks=12,
    phases=[
        PhaseBlock(
            name="Hypertrophy",
            week_start=1,
            week_end=3,
            sets_x_reps="4x8-10",
            intensity_range="65-73%",
            rest_period="90s",
            volume_adjustment="Normal",
            exercise_selection="Compounds + accessories",
            notes="Build work capacity and muscle base."
        ),
        PhaseBlock(
            name="Deload",
            week_start=4,
            week_end=4,
            sets_x_reps="2x8",
            intensity_range="55-60%",
            rest_period="60s",
            volume_adjustment="Reduce volume by 50%",
            exercise_selection="Reduced volume",
            notes="Recovery week."
        ),
        PhaseBlock(
            name="Strength I",
            week_start=5,
            week_end=7,
            sets_x_reps="5x5",
            intensity_range="75-83%",
            rest_period="2-3min",
            volume_adjustment="Normal",
            exercise_selection="Competition lifts + variations",
            notes="Build strength foundation with moderate intensity."
        ),
        PhaseBlock(
            name="Deload",
            week_start=8,
            week_end=8,
            sets_x_reps="3x5",
            intensity_range="65-70%",
            rest_period="2min",
            volume_adjustment="Reduce volume by 40%",
            exercise_selection="Same movements",
            notes="Recovery before intensification."
        ),
        PhaseBlock(
            name="Strength II",
            week_start=9,
            week_end=10,
            sets_x_reps="5x3",
            intensity_range="83-90%",
            rest_period="3-4min",
            volume_adjustment="Normal",
            exercise_selection="Competition lifts dominant",
            notes="High intensity strength work."
        ),
        PhaseBlock(
            name="Peak",
            week_start=11,
            week_end=11,
            sets_x_reps="3x2, 2x1",
            intensity_range="90-97%",
            rest_period="4-5min",
            volume_adjustment="Normal",
            exercise_selection="Competition lifts only",
            notes="Peak performance preparation."
        ),
        PhaseBlock(
            name="Taper + Test",
            week_start=12,
            week_end=12,
            sets_x_reps="Openers",
            intensity_range="90-93%",
            rest_period="Full",
            volume_adjustment="Minimal volume",
            exercise_selection="Competition lifts",
            notes="Test week or competition simulation."
        ),
    ]
)

STRENGTH_8W = PhaseTemplate(
    goal="strength",
    duration_weeks=8,
    phases=[
        PhaseBlock(
            name="Volume/Hypertrophy",
            week_start=1,
            week_end=2,
            sets_x_reps="4x6-8",
            intensity_range="70-77%",
            rest_period="2min",
            volume_adjustment="Normal",
            exercise_selection="Compounds + accessories",
            notes="Build work capacity."
        ),
        PhaseBlock(
            name="Strength I",
            week_start=3,
            week_end=4,
            sets_x_reps="5x5",
            intensity_range="77-85%",
            rest_period="3min",
            volume_adjustment="Normal",
            exercise_selection="Competition lifts focus",
            notes="Strength foundation building."
        ),
        PhaseBlock(
            name="Deload",
            week_start=5,
            week_end=5,
            sets_x_reps="3x5",
            intensity_range="65-70%",
            rest_period="2min",
            volume_adjustment="Reduce volume by 40%",
            exercise_selection="Same movements",
            notes="Mid-program recovery."
        ),
        PhaseBlock(
            name="Peaking",
            week_start=6,
            week_end=7,
            sets_x_reps="4x3, 3x2",
            intensity_range="85-93%",
            rest_period="4min",
            volume_adjustment="Normal",
            exercise_selection="Competition lifts",
            notes="Peak strength expression."
        ),
        PhaseBlock(
            name="Taper + Test",
            week_start=8,
            week_end=8,
            sets_x_reps="Singles",
            intensity_range="93-100%",
            rest_period="Full",
            volume_adjustment="Minimal",
            exercise_selection="Competition lifts only",
            notes="Test maximal strength."
        ),
    ]
)

STRENGTH_4W = PhaseTemplate(
    goal="strength",
    duration_weeks=4,
    phases=[
        PhaseBlock(
            name="Volume Strength",
            week_start=1,
            week_end=1,
            sets_x_reps="5x5",
            intensity_range="78-82%",
            rest_period="3min",
            volume_adjustment="Normal",
            exercise_selection="Competition lifts + variations",
            notes="Build fatigue with volume."
        ),
        PhaseBlock(
            name="Intensity Strength",
            week_start=2,
            week_end=2,
            sets_x_reps="5x3",
            intensity_range="85-88%",
            rest_period="4min",
            volume_adjustment="Normal",
            exercise_selection="Competition lifts",
            notes="Shift to triples at higher intensity."
        ),
        PhaseBlock(
            name="Peaking",
            week_start=3,
            week_end=3,
            sets_x_reps="4x2, 2x1",
            intensity_range="90-95%",
            rest_period="4-5min",
            volume_adjustment="Normal",
            exercise_selection="Competition lifts only",
            notes="Heavy singles/doubles."
        ),
        PhaseBlock(
            name="Taper + Test",
            week_start=4,
            week_end=4,
            sets_x_reps="Openers, then max",
            intensity_range="92-100%",
            rest_period="Full",
            volume_adjustment="Minimal",
            exercise_selection="Competition lifts",
            notes="Compete/test maximal strength."
        ),
    ]
)

# ============================================================================
# POWER TEMPLATES
# ============================================================================

POWER_12W = PhaseTemplate(
    goal="power",
    duration_weeks=12,
    phases=[
        PhaseBlock(
            name="Strength Base",
            week_start=1,
            week_end=3,
            sets_x_reps="4x5-6",
            intensity_range="70-80%",
            rest_period="2-3min",
            volume_adjustment="Normal",
            exercise_selection="Squats, pulls, presses",
            notes="Build strength foundation for power development."
        ),
        PhaseBlock(
            name="Deload",
            week_start=4,
            week_end=4,
            sets_x_reps="2x5",
            intensity_range="60-65%",
            rest_period="2min",
            volume_adjustment="Reduce volume by 50%",
            exercise_selection="Reduced",
            notes="Recovery week."
        ),
        PhaseBlock(
            name="Power Development",
            week_start=5,
            week_end=7,
            sets_x_reps="5x3 @ 75-85% + 5x3 explosive",
            intensity_range="Mixed",
            rest_period="3-4min",
            volume_adjustment="Normal",
            exercise_selection="Olympic lifts, jumps, throws, ballistics",
            notes="Develop power output through explosive movements."
        ),
        PhaseBlock(
            name="Deload",
            week_start=8,
            week_end=8,
            sets_x_reps="3x3",
            intensity_range="65-70%",
            rest_period="2min",
            volume_adjustment="Reduce volume by 50%",
            exercise_selection="Reduced",
            notes="Mid-phase recovery."
        ),
        PhaseBlock(
            name="Power Realization",
            week_start=9,
            week_end=10,
            sets_x_reps="4x2",
            intensity_range="85-92%",
            rest_period="4min",
            volume_adjustment="Normal",
            exercise_selection="Competition lifts, contrast training",
            notes="Realize power gains at higher intensities."
        ),
        PhaseBlock(
            name="Peak",
            week_start=11,
            week_end=11,
            sets_x_reps="Singles/doubles",
            intensity_range="90-97%",
            rest_period="5min",
            volume_adjustment="Normal",
            exercise_selection="Sport-specific movements",
            notes="Peak power expression."
        ),
        PhaseBlock(
            name="Taper",
            week_start=12,
            week_end=12,
            sets_x_reps="Openers",
            intensity_range="90%",
            rest_period="Full",
            volume_adjustment="Minimal",
            exercise_selection="Competition",
            notes="Taper for competition."
        ),
    ]
)

POWER_8W = PhaseTemplate(
    goal="power",
    duration_weeks=8,
    phases=[
        PhaseBlock(
            name="Strength Base",
            week_start=1,
            week_end=2,
            sets_x_reps="4x5",
            intensity_range="75-82%",
            rest_period="3min",
            volume_adjustment="Normal",
            exercise_selection="Basic strength movements",
            notes="Establish strength foundation."
        ),
        PhaseBlock(
            name="Power Development",
            week_start=3,
            week_end=4,
            sets_x_reps="5x3 explosive",
            intensity_range="78-85%",
            rest_period="3-4min",
            volume_adjustment="Normal",
            exercise_selection="Olympic lifts, plyometrics, ballistics",
            notes="Develop explosive power. Add jumps/throws alongside barbell work."
        ),
        PhaseBlock(
            name="Deload",
            week_start=5,
            week_end=5,
            sets_x_reps="3x3",
            intensity_range="65%",
            rest_period="2min",
            volume_adjustment="Reduce volume by 50%",
            exercise_selection="Reduced",
            notes="Recovery week."
        ),
        PhaseBlock(
            name="Power Peaking",
            week_start=6,
            week_end=7,
            sets_x_reps="4x2",
            intensity_range="85-93%",
            rest_period="4min",
            volume_adjustment="Normal",
            exercise_selection="Competition movements, contrast training",
            notes="Peak power output."
        ),
        PhaseBlock(
            name="Taper + Test",
            week_start=8,
            week_end=8,
            sets_x_reps="Singles",
            intensity_range="93-100%",
            rest_period="Full",
            volume_adjustment="Minimal",
            exercise_selection="Competition",
            notes="Test/compete."
        ),
    ]
)

POWER_4W = PhaseTemplate(
    goal="power",
    duration_weeks=4,
    phases=[
        PhaseBlock(
            name="Potentiation",
            week_start=1,
            week_end=1,
            sets_x_reps="4x3 + plyos",
            intensity_range="80-85%",
            rest_period="3-4min",
            volume_adjustment="Normal",
            exercise_selection="Contrast method (heavy + explosive)",
            notes="Potentiate nervous system with contrast training."
        ),
        PhaseBlock(
            name="Power",
            week_start=2,
            week_end=2,
            sets_x_reps="5x2 explosive",
            intensity_range="85-90%",
            rest_period="4min",
            volume_adjustment="Normal",
            exercise_selection="Explosive lifts at load",
            notes="Speed emphasis at load."
        ),
        PhaseBlock(
            name="Peaking",
            week_start=3,
            week_end=3,
            sets_x_reps="3x1",
            intensity_range="92-97%",
            rest_period="5min",
            volume_adjustment="Normal",
            exercise_selection="Competition movements",
            notes="Near-max with explosive intent."
        ),
        PhaseBlock(
            name="Taper + Test",
            week_start=4,
            week_end=4,
            sets_x_reps="Openers",
            intensity_range="90-93%",
            rest_period="Full",
            volume_adjustment="Minimal",
            exercise_selection="Competition",
            notes="Compete."
        ),
    ]
)

# ============================================================================
# ATHLETIC PERFORMANCE TEMPLATES
# ============================================================================

ATHLETIC_PERFORMANCE_12W = PhaseTemplate(
    goal="athletic_performance",
    duration_weeks=12,
    phases=[
        PhaseBlock(
            name="Strength-Power Base",
            week_start=1,
            week_end=3,
            sets_x_reps="4x5 @ 75-82%",
            intensity_range="75-82%",
            rest_period="2-4min",
            volume_adjustment="Normal",
            exercise_selection="Concurrent training: strength compounds + jumps/throws (low volume plyos)",
            notes="Concurrent training foundation. Strength and power in same sessions."
        ),
        PhaseBlock(
            name="Deload",
            week_start=4,
            week_end=4,
            sets_x_reps="2x5 @ 60-65%",
            intensity_range="60-65%",
            rest_period="2min",
            volume_adjustment="Reduce volume by 50%",
            exercise_selection="Reduced plyos",
            notes="Recovery week with reduced volume."
        ),
        PhaseBlock(
            name="Power Emphasis",
            week_start=5,
            week_end=7,
            sets_x_reps="3x3 @ 80-85% maintenance + 5x3 explosive work",
            intensity_range="80-85%",
            rest_period="2-4min",
            volume_adjustment="Normal",
            exercise_selection="Strength maintenance + contrast training, explosive emphasis",
            notes="Shift emphasis to power while maintaining strength."
        ),
        PhaseBlock(
            name="Deload",
            week_start=8,
            week_end=8,
            sets_x_reps="2x3 @ 65%",
            intensity_range="65%",
            rest_period="2min",
            volume_adjustment="Reduce volume by 50%",
            exercise_selection="Reduced",
            notes="Mid-program recovery."
        ),
        PhaseBlock(
            name="Realization",
            week_start=9,
            week_end=10,
            sets_x_reps="3x2 @ 85-90%",
            intensity_range="85-90%",
            rest_period="3-4min",
            volume_adjustment="Normal",
            exercise_selection="Sport-specific power expression",
            notes="Express power gains in sport-specific contexts."
        ),
        PhaseBlock(
            name="Taper/Maintenance",
            week_start=11,
            week_end=12,
            sets_x_reps="2x3 @ 80%",
            intensity_range="80%",
            rest_period="3min",
            volume_adjustment="Low volume",
            exercise_selection="High intent, low volume",
            notes="Maintain qualities with minimal fatigue."
        ),
    ]
)

ATHLETIC_PERFORMANCE_8W = PhaseTemplate(
    goal="athletic_performance",
    duration_weeks=8,
    phases=[
        PhaseBlock(
            name="Strength-Power Base",
            week_start=1,
            week_end=2,
            sets_x_reps="4x5 @ 75-82%",
            intensity_range="75-82%",
            rest_period="2-4min",
            volume_adjustment="Normal",
            exercise_selection="Concurrent: strength + low volume plyos",
            notes="Establish concurrent training base."
        ),
        PhaseBlock(
            name="Power Emphasis",
            week_start=3,
            week_end=4,
            sets_x_reps="3x3 @ 80-85% + 5x3 explosive",
            intensity_range="80-85%",
            rest_period="2-4min",
            volume_adjustment="Normal",
            exercise_selection="Strength maintenance + power emphasis",
            notes="Shift to power development."
        ),
        PhaseBlock(
            name="Deload",
            week_start=5,
            week_end=5,
            sets_x_reps="2x3 @ 65%",
            intensity_range="65%",
            rest_period="2min",
            volume_adjustment="Reduce volume by 50%",
            exercise_selection="Reduced",
            notes="Recovery week."
        ),
        PhaseBlock(
            name="Realization",
            week_start=6,
            week_end=7,
            sets_x_reps="3x2 @ 85-90%",
            intensity_range="85-90%",
            rest_period="3-4min",
            volume_adjustment="Normal",
            exercise_selection="Sport-specific power",
            notes="Sport-specific power expression."
        ),
        PhaseBlock(
            name="Taper",
            week_start=8,
            week_end=8,
            sets_x_reps="2x3 @ 80%",
            intensity_range="80%",
            rest_period="3min",
            volume_adjustment="Minimal",
            exercise_selection="High intent, low volume",
            notes="Taper for competition."
        ),
    ]
)

ATHLETIC_PERFORMANCE_4W = PhaseTemplate(
    goal="athletic_performance",
    duration_weeks=4,
    phases=[
        PhaseBlock(
            name="Concurrent Base",
            week_start=1,
            week_end=1,
            sets_x_reps="4x5 @ 75-80%",
            intensity_range="75-80%",
            rest_period="2-3min",
            volume_adjustment="Normal",
            exercise_selection="Concurrent: strength + power",
            notes="Train both qualities simultaneously."
        ),
        PhaseBlock(
            name="Power Expression",
            week_start=2,
            week_end=2,
            sets_x_reps="3x3 explosive @ 80-85%",
            intensity_range="80-85%",
            rest_period="3-4min",
            volume_adjustment="Normal",
            exercise_selection="Explosive emphasis",
            notes="Emphasize power output."
        ),
        PhaseBlock(
            name="Realization",
            week_start=3,
            week_end=3,
            sets_x_reps="3x2 @ 85-90%",
            intensity_range="85-90%",
            rest_period="4min",
            volume_adjustment="Normal",
            exercise_selection="Sport-specific",
            notes="Sport-specific power expression."
        ),
        PhaseBlock(
            name="Taper",
            week_start=4,
            week_end=4,
            sets_x_reps="2x3 @ 80%",
            intensity_range="80%",
            rest_period="Full",
            volume_adjustment="Minimal",
            exercise_selection="High intent, low volume",
            notes="Taper for performance."
        ),
    ]
)

# ============================================================================
# TEMPLATE REGISTRY
# ============================================================================

TEMPLATES = {
    ("hypertrophy", 12): HYPERTROPHY_12W,
    ("hypertrophy", 8): HYPERTROPHY_8W,
    ("hypertrophy", 4): HYPERTROPHY_4W,
    ("strength", 12): STRENGTH_12W,
    ("strength", 8): STRENGTH_8W,
    ("strength", 4): STRENGTH_4W,
    ("power", 12): POWER_12W,
    ("power", 8): POWER_8W,
    ("power", 4): POWER_4W,
    ("athletic_performance", 12): ATHLETIC_PERFORMANCE_12W,
    ("athletic_performance", 8): ATHLETIC_PERFORMANCE_8W,
    ("athletic_performance", 4): ATHLETIC_PERFORMANCE_4W,
}


def get_template(goal: str, duration_weeks: int) -> PhaseTemplate:
    """
    Get the exact template for a goal and duration.

    Args:
        goal: Training goal (hypertrophy, strength, power, athletic_performance)
        duration_weeks: Program duration

    Returns:
        PhaseTemplate if exact match exists, None otherwise
    """
    return TEMPLATES.get((goal.lower(), duration_weeks))


def get_closest_template(goal: str, duration_weeks: int) -> PhaseTemplate:
    """
    Get the closest template for interpolation.

    Selects from 4-week, 8-week, or 12-week templates based on target duration.

    Args:
        goal: Training goal
        duration_weeks: Target program duration

    Returns:
        PhaseTemplate closest to target duration
    """
    goal = goal.lower()

    # For 1-2 weeks, use 4-week template
    if duration_weeks <= 2:
        return TEMPLATES[(goal, 4)]

    # For 3-6 weeks, use 4-week template
    elif duration_weeks <= 6:
        return TEMPLATES[(goal, 4)]

    # For 7-10 weeks, use 8-week template
    elif duration_weeks <= 10:
        return TEMPLATES[(goal, 8)]

    # For 11+ weeks, use 12-week template
    else:
        return TEMPLATES[(goal, 12)]
