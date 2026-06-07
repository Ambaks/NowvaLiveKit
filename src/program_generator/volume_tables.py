"""
V6 Volume Tables — MV / MEV / MAV / MRV weekly set targets per muscle group per training level.

Volume landmarks (sets per week):
  MV  = Maintenance Volume — minimum to maintain current size (in-season / deloads)
  MEV = Minimum Effective Volume — minimum for growth stimulus
  MAV = Maximum Adaptive Volume — optimal growth zone
  MRV = Maximum Recoverable Volume — ceiling before overtraining

Intermediate values are aligned with RP Hypertrophy Hub (2024-2025) research.
Beginner  = round(intermediate × 0.75), clamped so MEV >= 2
Advanced  = round(intermediate × 1.15), clamped so MEV >= 2
Invariant: MV <= MEV < MAV < MRV at every level for all muscle groups.
"""

# ---------------------------------------------------------------------------
# Raw intermediate values (aligned with RP 2024-2025 research)
# Format: muscle_key → {"mv": int, "mev": int, "mav": int, "mrv": int}
# ---------------------------------------------------------------------------

_INTERMEDIATE: dict[str, dict[str, int]] = {
    # ── Chest ────────────────────────────────────────────────────────────────
    "chest":        {"mv": 8,  "mev": 10, "mav": 16, "mrv": 22},
    "upper_chest":  {"mv": 2,  "mev":  4, "mav":  8, "mrv": 12},   # incline/upper angle emphasis
    "lower_chest":  {"mv": 0,  "mev":  0, "mav":  0, "mrv":  0},   # no separate targeting in free-weight setup

    # ── Back ─────────────────────────────────────────────────────────────────
    "lats":         {"mv": 8,  "mev": 10, "mav": 18, "mrv": 25},
    "upper_back":   {"mv": 6,  "mev":  8, "mav": 14, "mrv": 20},   # rhomboids, mid traps
    "traps":        {"mv": 0,  "mev":  4, "mav": 12, "mrv": 20},   # upper traps; deadlifts contribute
    "erectors":     {"mv": 0,  "mev":  2, "mav":  5, "mrv":  8},   # RDLs/deadlifts cover most stimulus

    # ── Shoulders ────────────────────────────────────────────────────────────
    "front_delts":  {"mv": 0,  "mev":  0, "mav":  6, "mrv": 12},   # pressing covers; RP says 0 direct needed
    "side_delts":   {"mv": 6,  "mev":  8, "mav": 18, "mrv": 26},   # high tolerance, high frequency
    "rear_delts":   {"mv": 0,  "mev":  6, "mav": 14, "mrv": 22},

    # ── Arms ─────────────────────────────────────────────────────────────────
    "biceps":       {"mv": 4,  "mev":  6, "mav": 14, "mrv": 20},
    "triceps":      {"mv": 4,  "mev":  6, "mav": 12, "mrv": 18},
    "forearms":     {"mv": 0,  "mev":  2, "mav":  8, "mrv": 14},   # gripping contributes

    # ── Lower Body ───────────────────────────────────────────────────────────
    "quads":        {"mv": 6,  "mev":  8, "mav": 16, "mrv": 20},
    "hamstrings":   {"mv": 4,  "mev":  6, "mav": 14, "mrv": 20},
    "glutes":       {"mv": 0,  "mev":  4, "mav": 12, "mrv": 20},   # BIG change from V5 (was mrv=12)
    "calves":       {"mv": 4,  "mev":  6, "mav": 12, "mrv": 20},
    "adductors":    {"mv": 0,  "mev":  2, "mav":  6, "mrv": 10},   # sumo deadlifts/squats contribute

    # ── Core ─────────────────────────────────────────────────────────────────
    "abs":          {"mv": 0,  "mev":  4, "mav": 12, "mrv": 20},   # BIG change from V5 (was mav=6)
    "obliques":     {"mv": 0,  "mev":  2, "mav":  6, "mrv": 10},   # rotation work
}


# ---------------------------------------------------------------------------
# V6: Age-tiered volume multipliers (replace V5's single age>45 modifier)
# ---------------------------------------------------------------------------

AGE_MULTIPLIERS: dict[tuple[int, int], float] = {
    (10, 13): 0.60,   # Prepubescent: bodyweight focus, movement literacy
    (14, 15): 0.75,   # Early pubescent: light loads, technique emphasis
    (16, 17): 0.85,   # Late pubescent: full loading with proper technique
    (18, 39): 1.00,   # Standard adult programming
    (40, 54): 0.90,   # Masters: slightly reduced, maintain intensity
    (55, 64): 0.80,   # Older masters: joint-friendly alternatives
    (65, 100): 0.70,  # Seniors: power work critical for fall prevention
}


def get_age_multiplier(age: int | None) -> float:
    """Return the volume multiplier for a given age. Defaults to 1.0 if age is None."""
    if age is None:
        return 1.0
    for (lo, hi), mult in AGE_MULTIPLIERS.items():
        if lo <= age <= hi:
            return mult
    return 1.0


# ---------------------------------------------------------------------------
# V6: Sex-based volume modifier
# Women can handle ~20-30% more relative volume (greater Type I fiber area
# ratio, lower muscle damage, estrogen-mediated recovery). We apply a
# conservative +10% modifier.
# ---------------------------------------------------------------------------

SEX_VOLUME_MODIFIER: dict[str, float] = {
    "M": 1.00,
    "F": 1.10,  # +10% volume tolerance
}


def get_sex_modifier(sex: str | None) -> float:
    """Return volume modifier for biological sex. Defaults to 1.0."""
    if sex is None:
        return 1.0
    normalized = sex.upper()
    if normalized in ("F", "FEMALE"):
        return SEX_VOLUME_MODIFIER["F"]
    return SEX_VOLUME_MODIFIER["M"]


# ---------------------------------------------------------------------------
# V6: Muscle frequency tolerance (optimal training frequency range per week)
# Based on recovery rates and RP frequency recommendations.
# ---------------------------------------------------------------------------

MUSCLE_FREQUENCY_TOLERANCE: dict[str, tuple[int, int]] = {
    "side_delts":  (3, 6),   # Small muscle, rapid recovery
    "rear_delts":  (3, 6),
    "calves":      (2, 4),
    "abs":         (2, 4),
    "biceps":      (2, 4),
    "triceps":     (2, 4),
    "forearms":    (2, 4),
    "chest":       (2, 3),
    "upper_chest": (2, 3),
    "lats":        (2, 4),
    "upper_back":  (2, 4),
    "traps":       (2, 4),
    "quads":       (2, 3),   # Slow recovery (72-96h)
    "hamstrings":  (2, 3),
    "glutes":      (2, 3),   # Slow recovery (72-96h)
    "adductors":   (2, 3),
    "obliques":    (2, 4),
    "erectors":    (1, 3),
    "front_delts": (2, 3),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scale(vals: dict[str, int], multiplier: float) -> dict[str, int]:
    """Scale MV/MEV/MAV/MRV by multiplier and round."""
    return {
        "mv":  round(vals["mv"] * multiplier),
        "mev": round(vals["mev"] * multiplier),
        "mav": round(vals["mav"] * multiplier),
        "mrv": round(vals["mrv"] * multiplier),
    }


def _clamp(vals: dict[str, int]) -> dict[str, int]:
    """
    Enforce invariants for all muscles:
      - If MEV = 0: muscle not tracked separately, all values stay 0
      - If MEV > 0: MEV >= 2 and MV <= MEV < MAV < MRV (strict inequality)
    """
    # If MEV is 0, this muscle is not tracked separately
    if vals["mev"] == 0:
        return {"mv": 0, "mev": 0, "mav": 0, "mrv": 0}

    mev = max(2, vals["mev"])
    mv = min(vals["mv"], mev)  # MV can't exceed MEV
    mv = max(0, mv)
    mav = max(mev + 1, vals["mav"])
    mrv = max(mav + 1, vals["mrv"])
    return {"mv": mv, "mev": mev, "mav": mav, "mrv": mrv}


# ---------------------------------------------------------------------------
# Build the three-level table
# ---------------------------------------------------------------------------

VOLUME_TABLES: dict[str, dict[str, dict[str, int]]] = {
    "beginner": {},
    "intermediate": {},
    "advanced": {},
}

for _muscle, _vals in _INTERMEDIATE.items():
    VOLUME_TABLES["intermediate"][_muscle] = _clamp(dict(_vals))
    VOLUME_TABLES["beginner"][_muscle]     = _clamp(_scale(_vals, 0.75))
    VOLUME_TABLES["advanced"][_muscle]     = _clamp(_scale(_vals, 1.15))


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------

def get_volume_targets(training_level: str, muscle: str) -> dict[str, int]:
    """
    Returns {"mv": W, "mev": X, "mav": Y, "mrv": Z} for the given training
    level and muscle.

    training_level: "beginner" | "intermediate" | "advanced"
    muscle: MuscleGroup enum value string (e.g. "chest", "lats", "side_delts")
    """
    level = training_level.lower()
    if level not in VOLUME_TABLES:
        raise ValueError(
            f"Unknown training level '{training_level}'. "
            f"Valid options: {list(VOLUME_TABLES.keys())}"
        )
    muscle_key = muscle.lower()
    if muscle_key not in VOLUME_TABLES[level]:
        raise ValueError(
            f"Unknown muscle group '{muscle}'. "
            f"Valid options: {list(VOLUME_TABLES[level].keys())}"
        )
    return dict(VOLUME_TABLES[level][muscle_key])
