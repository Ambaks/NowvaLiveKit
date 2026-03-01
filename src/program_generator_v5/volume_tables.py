"""
V5 Volume Tables — MEV / MAV / MRV weekly set targets per muscle group per training level.

Intermediate values are sourced from the V5 spec with the following updates (Phase 1 Fix 1):
  - All muscles now have MEV >= 2 so the validator always has a nonzero floor to enforce.
  - front_delts, glutes, abs, obliques, forearms were raised from MEV=0 to their new values.

Beginner  = round(intermediate × 0.75), clamped so MEV >= 2
Advanced  = round(intermediate × 1.15), clamped so MEV >= 2
Invariant: MEV < MAV < MRV at every level for all 20 muscle groups.
"""

# ---------------------------------------------------------------------------
# Raw intermediate values (from spec)
# Format: muscle_key → {"mev": int, "mav": int, "mrv": int}
# ---------------------------------------------------------------------------

_INTERMEDIATE: dict[str, dict[str, int]] = {
    # ── Chest ────────────────────────────────────────────────────────────────
    "chest":        {"mev":  8, "mav": 14, "mrv": 20},
    "upper_chest":  {"mev":  4, "mav":  8, "mrv": 12},   # incline/upper angle emphasis
    "lower_chest":  {"mev":  0, "mav":  0, "mrv":  0},   # Tier 1: no separate lower chest targeting

    # ── Back ─────────────────────────────────────────────────────────────────
    "lats":         {"mev":  8, "mav": 14, "mrv": 20},
    "upper_back":   {"mev":  4, "mav":  8, "mrv": 14},   # rhomboids, mid traps
    "traps":        {"mev":  3, "mav":  6, "mrv": 10},   # upper traps; deadlifts contribute
    "erectors":     {"mev":  2, "mav":  5, "mrv":  8},   # RDLs/deadlifts cover most stimulus

    # ── Shoulders ────────────────────────────────────────────────────────────
    "front_delts":  {"mev":  4, "mav":  5, "mrv":  6},   # pressing contributes but needs floor
    "side_delts":   {"mev":  6, "mav": 12, "mrv": 20},
    "rear_delts":   {"mev":  6, "mav": 10, "mrv": 18},

    # ── Arms ─────────────────────────────────────────────────────────────────
    "biceps":       {"mev":  4, "mav": 10, "mrv": 16},
    "triceps":      {"mev":  4, "mav":  8, "mrv": 14},
    "forearms":     {"mev":  2, "mav":  4, "mrv":  8},   # gripping contributes; baseline floor

    # ── Lower Body ───────────────────────────────────────────────────────────
    "quads":        {"mev":  6, "mav": 12, "mrv": 20},
    "hamstrings":   {"mev":  4, "mav": 10, "mrv": 16},
    "glutes":       {"mev":  6, "mav":  9, "mrv": 12},   # squats/hinges contribute; direct still needed
    "calves":       {"mev":  4, "mav":  8, "mrv": 14},
    "adductors":    {"mev":  2, "mav":  4, "mrv":  8},   # sumo deadlifts/squats contribute

    # ── Core ─────────────────────────────────────────────────────────────────
    "abs":          {"mev":  4, "mav":  6, "mrv": 12},   # compounds contribute; direct floor needed
    "obliques":     {"mev":  2, "mav":  4, "mrv":  8},   # rotation work; minimal direct floor
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scale(vals: dict[str, int], multiplier: float) -> dict[str, int]:
    """Scale MEV/MAV/MRV by multiplier and round."""
    return {
        "mev": round(vals["mev"] * multiplier),
        "mav": round(vals["mav"] * multiplier),
        "mrv": round(vals["mrv"] * multiplier),
    }


def _clamp(vals: dict[str, int]) -> dict[str, int]:
    """
    Enforce invariants for all muscles:
      - MEV >= 0 (allow 0 for optional muscles like lower_chest)
      - If MEV > 0: MEV >= 2 and MEV < MAV < MRV (strict inequality)
      - If MEV = 0: all values stay 0 (muscle not tracked separately)
    """
    # If MEV is 0, this muscle is not tracked separately (e.g., lower_chest for Tier 1)
    if vals["mev"] == 0:
        return {"mev": 0, "mav": 0, "mrv": 0}

    mev = max(2, vals["mev"])
    mav = max(mev + 1, vals["mav"])
    mrv = max(mav + 1, vals["mrv"])
    return {"mev": mev, "mav": mav, "mrv": mrv}


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
    Returns {"mev": X, "mav": Y, "mrv": Z} for the given training level and muscle.

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
