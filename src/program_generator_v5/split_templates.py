"""
V6 Split Templates — All training split definitions and the selection decision tree.

Each SplitTemplate specifies how training days are structured across the week.
SessionTemplates define which muscle groups and movement patterns each day covers.

V6 additions:
- In-season 2x template (game-day-aware)
- Maintenance 2x template for in-season athletes
"""

from .schemas import (
    MuscleGroup, MovementPattern, SessionTemplate, SplitTemplate,
)

# Shorthand aliases for readability
MG = MuscleGroup
MP = MovementPattern

# All muscle groups (used for full-body sessions)
_ALL_MUSCLES: list[MuscleGroup] = list(MuscleGroup)

# ─────────────────────────────────────────────────────────────────────────────
# UPPER / LOWER 4x  (Primary for most users — 4 days/week)
# ─────────────────────────────────────────────────────────────────────────────

_UPPER_A = SessionTemplate(
    day_label="Upper A",
    session_type="upper_a",
    muscle_groups=[
        MG.CHEST, MG.UPPER_CHEST, MG.LOWER_CHEST,
        MG.LATS, MG.UPPER_BACK, MG.TRAPS,
        MG.REAR_DELTS, MG.SIDE_DELTS, MG.FRONT_DELTS,
        MG.BICEPS, MG.TRICEPS, MG.FOREARMS,
    ],
    required_movement_patterns=[
        MP.HORIZONTAL_PUSH, MP.HORIZONTAL_PULL, MP.VERTICAL_PULL,
        MP.ISOLATION_PUSH, MP.ISOLATION_PULL,
    ],
    optional_movement_patterns=[MP.VERTICAL_PUSH],
    max_exercises=7,
    max_duration_minutes=60,
    is_primary=True,
)

_LOWER_A = SessionTemplate(
    day_label="Lower A",
    session_type="lower_a",
    muscle_groups=[
        MG.QUADS, MG.HAMSTRINGS, MG.GLUTES, MG.CALVES,
        MG.ABS, MG.OBLIQUES, MG.ADDUCTORS, MG.ERECTORS,
    ],
    required_movement_patterns=[MP.SQUAT, MP.HIP_HINGE, MP.CORE],
    optional_movement_patterns=[MP.LUNGE],
    max_exercises=6,
    max_duration_minutes=60,
    is_primary=True,
)

_UPPER_B = SessionTemplate(
    day_label="Upper B",
    session_type="upper_b",
    muscle_groups=[
        MG.CHEST, MG.UPPER_CHEST, MG.LOWER_CHEST,
        MG.LATS, MG.UPPER_BACK, MG.TRAPS,
        MG.REAR_DELTS, MG.SIDE_DELTS, MG.FRONT_DELTS,
        MG.BICEPS, MG.TRICEPS, MG.FOREARMS,
    ],
    required_movement_patterns=[
        MP.HORIZONTAL_PUSH, MP.VERTICAL_PUSH, MP.HORIZONTAL_PULL, MP.VERTICAL_PULL,
        MP.ISOLATION_PUSH, MP.ISOLATION_PULL,
    ],
    optional_movement_patterns=[],
    max_exercises=7,
    max_duration_minutes=60,
    is_primary=True,
)

_LOWER_B = SessionTemplate(
    day_label="Lower B",
    session_type="lower_b",
    muscle_groups=[
        MG.QUADS, MG.HAMSTRINGS, MG.GLUTES, MG.CALVES,
        MG.ABS, MG.OBLIQUES, MG.ADDUCTORS, MG.ERECTORS,
    ],
    required_movement_patterns=[MP.HIP_HINGE, MP.SQUAT, MP.CORE],
    optional_movement_patterns=[MP.LUNGE],
    max_exercises=6,
    max_duration_minutes=60,
    is_primary=True,
)

UPPER_LOWER_4X = SplitTemplate(
    split_id="upper_lower_4x",
    name="Upper/Lower 4-Day Split",
    sessions_per_week=[_UPPER_A, _LOWER_A, _UPPER_B, _LOWER_B],
    suitable_levels=["beginner", "intermediate", "advanced"],
    suitable_goals=["hypertrophy", "strength", "power"],
)

# ─────────────────────────────────────────────────────────────────────────────
# PUSH / PULL / LEGS 3x
# ─────────────────────────────────────────────────────────────────────────────

_PUSH = SessionTemplate(
    day_label="Push",
    session_type="push",
    muscle_groups=[
        MG.CHEST, MG.UPPER_CHEST, MG.LOWER_CHEST,
        MG.FRONT_DELTS, MG.SIDE_DELTS,
        MG.TRICEPS,
    ],
    required_movement_patterns=[
        MP.HORIZONTAL_PUSH, MP.VERTICAL_PUSH, MP.ISOLATION_PUSH,
    ],
    optional_movement_patterns=[],
    max_exercises=6,
    max_duration_minutes=60,
    is_primary=True,
)

_PULL = SessionTemplate(
    day_label="Pull",
    session_type="pull",
    muscle_groups=[
        MG.LATS, MG.UPPER_BACK, MG.TRAPS,
        MG.REAR_DELTS,
        MG.BICEPS, MG.FOREARMS,
    ],
    required_movement_patterns=[
        MP.HORIZONTAL_PULL, MP.VERTICAL_PULL, MP.ISOLATION_PULL,
    ],
    optional_movement_patterns=[],
    max_exercises=6,
    max_duration_minutes=60,
    is_primary=True,
)

_LEGS = SessionTemplate(
    day_label="Legs",
    session_type="legs",
    muscle_groups=[
        MG.QUADS, MG.HAMSTRINGS, MG.GLUTES, MG.CALVES,
        MG.ABS, MG.OBLIQUES, MG.ADDUCTORS, MG.ERECTORS,
    ],
    required_movement_patterns=[MP.SQUAT, MP.HIP_HINGE],
    optional_movement_patterns=[MP.LUNGE, MP.CORE],
    max_exercises=6,
    max_duration_minutes=60,
    is_primary=True,
)

PPL_3X = SplitTemplate(
    split_id="ppl_3x",
    name="Push/Pull/Legs 3-Day Split",
    sessions_per_week=[_PUSH, _PULL, _LEGS],
    suitable_levels=["intermediate", "advanced"],
    suitable_goals=["hypertrophy", "strength"],
)

# ─────────────────────────────────────────────────────────────────────────────
# PUSH / PULL / LEGS 6x  (2× per week)
# ─────────────────────────────────────────────────────────────────────────────

_PUSH_A = SessionTemplate(
    day_label="Push A",
    session_type="push_a",
    muscle_groups=[
        MG.CHEST, MG.UPPER_CHEST,
        MG.FRONT_DELTS, MG.SIDE_DELTS,
        MG.TRICEPS,
    ],
    required_movement_patterns=[
        MP.HORIZONTAL_PUSH, MP.VERTICAL_PUSH, MP.ISOLATION_PUSH,
    ],
    optional_movement_patterns=[],
    max_exercises=6,
    max_duration_minutes=60,
    is_primary=True,
)

_PULL_A = SessionTemplate(
    day_label="Pull A",
    session_type="pull_a",
    muscle_groups=[
        MG.LATS, MG.UPPER_BACK,
        MG.REAR_DELTS,
        MG.BICEPS, MG.FOREARMS,
    ],
    required_movement_patterns=[
        MP.VERTICAL_PULL, MP.HORIZONTAL_PULL, MP.ISOLATION_PULL,
    ],
    optional_movement_patterns=[],
    max_exercises=6,
    max_duration_minutes=60,
    is_primary=True,
)

_LEGS_A = SessionTemplate(
    day_label="Legs A",
    session_type="legs_a",
    muscle_groups=[
        MG.QUADS, MG.GLUTES, MG.CALVES, MG.ABS, MG.OBLIQUES, MG.ERECTORS,
    ],
    required_movement_patterns=[MP.SQUAT, MP.LUNGE],
    optional_movement_patterns=[MP.HIP_HINGE, MP.CORE],
    max_exercises=6,
    max_duration_minutes=60,
    is_primary=True,
)

_PUSH_B = SessionTemplate(
    day_label="Push B",
    session_type="push_b",
    muscle_groups=[
        MG.CHEST, MG.LOWER_CHEST,
        MG.FRONT_DELTS, MG.SIDE_DELTS,
        MG.TRICEPS,
    ],
    required_movement_patterns=[
        MP.HORIZONTAL_PUSH, MP.VERTICAL_PUSH, MP.ISOLATION_PUSH,
    ],
    optional_movement_patterns=[],
    max_exercises=6,
    max_duration_minutes=60,
    is_primary=False,
)

_PULL_B = SessionTemplate(
    day_label="Pull B",
    session_type="pull_b",
    muscle_groups=[
        MG.LATS, MG.UPPER_BACK, MG.TRAPS,
        MG.REAR_DELTS,
        MG.BICEPS,
    ],
    required_movement_patterns=[
        MP.VERTICAL_PULL, MP.HORIZONTAL_PULL, MP.ISOLATION_PULL,
    ],
    optional_movement_patterns=[],
    max_exercises=6,
    max_duration_minutes=60,
    is_primary=False,
)

_LEGS_B = SessionTemplate(
    day_label="Legs B",
    session_type="legs_b",
    muscle_groups=[
        MG.HAMSTRINGS, MG.GLUTES, MG.CALVES, MG.ADDUCTORS,
        MG.ABS, MG.OBLIQUES, MG.ERECTORS,
    ],
    required_movement_patterns=[MP.HIP_HINGE, MP.SQUAT],
    optional_movement_patterns=[MP.LUNGE, MP.CORE],
    max_exercises=6,
    max_duration_minutes=60,
    is_primary=False,
)

PPL_6X = SplitTemplate(
    split_id="ppl_6x",
    name="Push/Pull/Legs 6-Day Split",
    sessions_per_week=[_PUSH_A, _PULL_A, _LEGS_A, _PUSH_B, _PULL_B, _LEGS_B],
    suitable_levels=["advanced"],
    suitable_goals=["hypertrophy"],
)

# ─────────────────────────────────────────────────────────────────────────────
# FULL BODY 2x
# ─────────────────────────────────────────────────────────────────────────────

_FULL_BODY_A = SessionTemplate(
    day_label="Full Body A",
    session_type="full_body_a",
    muscle_groups=_ALL_MUSCLES,
    required_movement_patterns=[
        MP.HORIZONTAL_PUSH, MP.HORIZONTAL_PULL, MP.SQUAT, MP.HIP_HINGE,
    ],
    optional_movement_patterns=[MP.ISOLATION_PUSH, MP.ISOLATION_PULL, MP.CORE],
    max_exercises=6,
    max_duration_minutes=60,
    is_primary=True,
)

_FULL_BODY_B = SessionTemplate(
    day_label="Full Body B",
    session_type="full_body_b",
    muscle_groups=_ALL_MUSCLES,
    required_movement_patterns=[
        MP.VERTICAL_PUSH, MP.VERTICAL_PULL, MP.LUNGE, MP.HIP_HINGE,
    ],
    optional_movement_patterns=[MP.ISOLATION_PUSH, MP.ISOLATION_PULL, MP.CORE],
    max_exercises=6,
    max_duration_minutes=60,
    is_primary=True,
)

FULL_BODY_2X = SplitTemplate(
    split_id="full_body_2x",
    name="Full Body 2-Day Split",
    sessions_per_week=[_FULL_BODY_A, _FULL_BODY_B],
    suitable_levels=["beginner", "intermediate", "advanced"],
    suitable_goals=["hypertrophy", "strength", "power"],
)

# ─────────────────────────────────────────────────────────────────────────────
# FULL BODY 3x
# ─────────────────────────────────────────────────────────────────────────────

_FULL_BODY_C = SessionTemplate(
    day_label="Full Body C",
    session_type="full_body_c",
    muscle_groups=_ALL_MUSCLES,
    required_movement_patterns=[
        MP.HORIZONTAL_PUSH, MP.HORIZONTAL_PULL, MP.SQUAT, MP.CORE,
    ],
    optional_movement_patterns=[MP.ISOLATION_PUSH, MP.ISOLATION_PULL],
    max_exercises=6,
    max_duration_minutes=60,
    is_primary=True,
)

FULL_BODY_3X = SplitTemplate(
    split_id="full_body_3x",
    name="Full Body 3-Day Split",
    sessions_per_week=[_FULL_BODY_A, _FULL_BODY_B, _FULL_BODY_C],
    suitable_levels=["beginner", "intermediate"],
    suitable_goals=["hypertrophy", "strength"],
)

# ─────────────────────────────────────────────────────────────────────────────
# CONCURRENT / POWER 4x  (for power goal)
# ─────────────────────────────────────────────────────────────────────────────

_POWER_UPPER = SessionTemplate(
    day_label="Power + Upper",
    session_type="power_upper",
    muscle_groups=[
        MG.CHEST, MG.UPPER_CHEST,
        MG.LATS, MG.UPPER_BACK,
        MG.SIDE_DELTS, MG.FRONT_DELTS,
        MG.BICEPS, MG.TRICEPS, MG.FOREARMS,
    ],
    required_movement_patterns=[
        MP.POWER_UPPER, MP.HORIZONTAL_PUSH, MP.HORIZONTAL_PULL,
    ],
    optional_movement_patterns=[
        MP.VERTICAL_PULL, MP.ISOLATION_PUSH, MP.ISOLATION_PULL,
    ],
    max_exercises=7,
    max_duration_minutes=75,
    is_primary=True,
)

_POWER_LOWER = SessionTemplate(
    day_label="Power + Lower",
    session_type="power_lower",
    muscle_groups=[
        MG.QUADS, MG.HAMSTRINGS, MG.GLUTES, MG.CALVES,
        MG.ABS, MG.OBLIQUES,
    ],
    required_movement_patterns=[
        MP.POWER_LOWER, MP.SQUAT, MP.HIP_HINGE,
    ],
    optional_movement_patterns=[MP.LUNGE, MP.CORE],
    max_exercises=6,
    max_duration_minutes=75,
    is_primary=True,
)

_STRENGTH_UPPER = SessionTemplate(
    day_label="Strength + Upper",
    session_type="strength_upper",
    muscle_groups=[
        MG.CHEST, MG.LATS, MG.UPPER_BACK,
        MG.FRONT_DELTS, MG.SIDE_DELTS, MG.REAR_DELTS,
        MG.BICEPS, MG.TRICEPS, MG.FOREARMS,
    ],
    required_movement_patterns=[
        MP.HORIZONTAL_PUSH, MP.HORIZONTAL_PULL, MP.VERTICAL_PULL,
    ],
    optional_movement_patterns=[
        MP.VERTICAL_PUSH,
        MP.ISOLATION_PUSH, MP.ISOLATION_PULL,
    ],
    max_exercises=6,
    max_duration_minutes=60,
    is_primary=False,
)

_STRENGTH_LOWER = SessionTemplate(
    day_label="Strength + Lower",
    session_type="strength_lower",
    muscle_groups=[
        MG.QUADS, MG.HAMSTRINGS, MG.GLUTES, MG.CALVES,
        MG.ABS, MG.OBLIQUES,
    ],
    required_movement_patterns=[MP.SQUAT, MP.HIP_HINGE],
    optional_movement_patterns=[MP.LUNGE, MP.CORE],
    max_exercises=6,
    max_duration_minutes=60,
    is_primary=False,
)

CONCURRENT_4X = SplitTemplate(
    split_id="concurrent_4x",
    name="Concurrent/Power 4-Day Split",
    sessions_per_week=[_POWER_UPPER, _POWER_LOWER, _STRENGTH_UPPER, _STRENGTH_LOWER],
    suitable_levels=["intermediate", "advanced"],
    suitable_goals=["power"],
)

# ─────────────────────────────────────────────────────────────────────────────
# CONCURRENT / POWER 5x  (for advanced power)
# ─────────────────────────────────────────────────────────────────────────────

_STRENGTH_FULL = SessionTemplate(
    day_label="Strength Full Body",
    session_type="strength_full",
    muscle_groups=_ALL_MUSCLES,
    required_movement_patterns=[
        MP.SQUAT, MP.HORIZONTAL_PUSH, MP.HORIZONTAL_PULL,
    ],
    optional_movement_patterns=[
        MP.HIP_HINGE, MP.CORE, MP.ISOLATION_PUSH, MP.ISOLATION_PULL,
    ],
    max_exercises=6,
    max_duration_minutes=75,
    is_primary=False,
)

CONCURRENT_5X = SplitTemplate(
    split_id="concurrent_5x",
    name="Concurrent/Power 5-Day Split",
    sessions_per_week=[
        _POWER_UPPER, _POWER_LOWER, _STRENGTH_UPPER, _STRENGTH_LOWER, _STRENGTH_FULL,
    ],
    suitable_levels=["advanced"],
    suitable_goals=["power"],
)

# ─────────────────────────────────────────────────────────────────────────────
# UPPER / LOWER 2x  (for non-beginner, 2 days/week)
# ─────────────────────────────────────────────────────────────────────────────

UPPER_LOWER_2X = SplitTemplate(
    split_id="upper_lower_2x",
    name="Upper/Lower 2-Day Split",
    sessions_per_week=[_UPPER_A, _LOWER_A],
    suitable_levels=["intermediate", "advanced"],
    suitable_goals=["hypertrophy", "strength", "power"],
)

# ─────────────────────────────────────────────────────────────────────────────
# V6: IN-SEASON MAINTENANCE 2x
# Heavy compounds + power maintenance. 2 sessions max, 30-45 min each.
# Session 1 (game+1 day): Heavy compounds, 85%+ 1RM, 3-5 reps
# Session 2 (game-3 day): Moderate/power emphasis, dynamic effort
# ─────────────────────────────────────────────────────────────────────────────

_MAINTENANCE_HEAVY = SessionTemplate(
    day_label="Heavy (Game+1)",
    session_type="maintenance_heavy",
    muscle_groups=[
        MG.QUADS, MG.HAMSTRINGS, MG.GLUTES,
        MG.CHEST, MG.LATS, MG.UPPER_BACK,
    ],
    required_movement_patterns=[
        MP.SQUAT, MP.HIP_HINGE, MP.HORIZONTAL_PUSH, MP.HORIZONTAL_PULL,
    ],
    optional_movement_patterns=[],
    max_exercises=5,
    max_duration_minutes=40,
    is_primary=True,
)

_MAINTENANCE_POWER = SessionTemplate(
    day_label="Power (Game-3)",
    session_type="maintenance_power",
    muscle_groups=[
        MG.QUADS, MG.HAMSTRINGS, MG.GLUTES,
        MG.CHEST, MG.LATS, MG.UPPER_BACK,
        MG.SIDE_DELTS, MG.BICEPS, MG.TRICEPS,
    ],
    required_movement_patterns=[
        MP.POWER_LOWER, MP.HORIZONTAL_PUSH, MP.HORIZONTAL_PULL,
    ],
    optional_movement_patterns=[MP.ISOLATION_PUSH, MP.ISOLATION_PULL],
    max_exercises=5,
    max_duration_minutes=40,
    is_primary=True,
)

MAINTENANCE_2X = SplitTemplate(
    split_id="maintenance_2x",
    name="In-Season Maintenance 2-Day Split",
    sessions_per_week=[_MAINTENANCE_HEAVY, _MAINTENANCE_POWER],
    suitable_levels=["beginner", "intermediate", "advanced"],
    suitable_goals=["power", "strength", "hypertrophy"],
)

# ─────────────────────────────────────────────────────────────────────────────
# REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

SPLIT_TEMPLATES: dict[str, SplitTemplate] = {
    "upper_lower_2x":  UPPER_LOWER_2X,
    "upper_lower_4x":  UPPER_LOWER_4X,
    "ppl_3x":          PPL_3X,
    "ppl_6x":          PPL_6X,
    "full_body_2x":    FULL_BODY_2X,
    "full_body_3x":    FULL_BODY_3X,
    "concurrent_4x":   CONCURRENT_4X,
    "concurrent_5x":   CONCURRENT_5X,
    "maintenance_2x":  MAINTENANCE_2X,
}


# ─────────────────────────────────────────────────────────────────────────────
# SPLIT SELECTION DECISION TREE
# ─────────────────────────────────────────────────────────────────────────────

def get_split_for_config(
    days_per_week: int,
    training_level: str,
    goal: str,
) -> str:
    """
    Returns the split_id appropriate for the given training configuration.

    Decision tree from the V5 spec:
        2 days → full_body_2x (ALL levels and goals — can't adequately hit all muscles
                 with only one upper + one lower session per week)
        3 days → full_body_3x (beginner/early-intermediate or strength goal)
                 ppl_3x (intermediate/advanced hypertrophy)
        4 days → concurrent_4x (power goal) or upper_lower_4x (default)
        5 days → concurrent_5x (advanced power) or upper_lower_4x + extra
        6 days → ppl_6x
    """
    level = training_level.lower()
    g = goal.lower()

    if days_per_week <= 2:
        return "full_body_2x"

    if days_per_week == 3:
        if level in ("beginner", "early_intermediate"):
            return "full_body_3x"
        if g == "strength":
            return "full_body_3x"
        return "ppl_3x"

    if days_per_week == 4:
        if g == "power":
            return "concurrent_4x"
        return "upper_lower_4x"

    if days_per_week == 5:
        if g == "power" and level == "advanced":
            return "concurrent_5x"
        # Default for 5-day hypertrophy/strength: use upper_lower_4x + rest day
        # (5th day can be an optional light accessory day handled at build time)
        return "upper_lower_4x"

    # 6+ days
    return "ppl_6x"
