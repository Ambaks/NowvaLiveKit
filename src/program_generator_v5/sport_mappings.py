"""
V5 Sport Mappings — Sport → base goal + sport-specific training adjustments.

Each entry captures how a given sport modifies the standard programming:
  base_goal            : "hypertrophy" | "strength" | "power"
  volume_modifier      : 0.6–1.0 (scale overall gym volume to preserve recovery for sport)
  emphasis_muscles     : muscles to push toward MAV/MRV
  deemphasis_muscles   : muscles to keep near MEV
  mandatory_movement_patterns : patterns that MUST appear every session
  forbidden_exercises  : exercise IDs that are contraindicated for this sport
  injury_prevention_additions : prehab/corrective exercise IDs to include

Sports are grouped by category per spec "Sport → Base Goal Mapping" table.
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# SPORT MAPPINGS DICTIONARY
# ─────────────────────────────────────────────────────────────────────────────

SPORT_MAPPINGS: dict[str, dict] = {

    # ── Basketball ────────────────────────────────────────────────────────────
    "basketball": {
        "base_goal": "power",
        "volume_modifier": 0.85,
        "emphasis_muscles": ["glutes", "hamstrings", "calves", "quads"],
        "deemphasis_muscles": ["chest", "triceps"],
        "mandatory_movement_patterns": ["power_lower", "lunge"],
        "forbidden_exercises": [],
        "injury_prevention_additions": [
            "nordic_curl",            # Hamstring injury prevention
            "single_leg_calf_raise",  # Ankle stability
        ],
    },

    # ── Football — skill positions (WR, DB, RB, QB) ─────────────────────────
    "football_skill": {
        "base_goal": "power",
        "volume_modifier": 0.85,
        "emphasis_muscles": ["glutes", "hamstrings", "quads", "calves"],
        "deemphasis_muscles": [],
        "mandatory_movement_patterns": ["power_lower", "power_upper", "lunge"],
        "forbidden_exercises": [],
        "injury_prevention_additions": [
            "nordic_curl",
            "copenhagen_plank",
        ],
    },

    # ── Football — linemen ────────────────────────────────────────────────────
    "football_linemen": {
        "base_goal": "strength",
        "volume_modifier": 1.0,
        "emphasis_muscles": ["traps", "upper_back", "glutes", "quads", "forearms"],
        "deemphasis_muscles": [],
        "mandatory_movement_patterns": ["horizontal_push", "squat", "hip_hinge"],
        "forbidden_exercises": [],
        "injury_prevention_additions": [
            "neck_harness_flexion",    # Neck strength for impact
            "farmers_carry",           # Grip and trap strength
        ],
    },

    # ── Rugby ─────────────────────────────────────────────────────────────────
    "rugby": {
        "base_goal": "strength",
        "volume_modifier": 0.9,
        "emphasis_muscles": ["traps", "upper_back", "glutes", "hamstrings", "forearms"],
        "deemphasis_muscles": [],
        "mandatory_movement_patterns": ["horizontal_push", "squat", "hip_hinge"],
        "forbidden_exercises": [],
        "injury_prevention_additions": [
            "nordic_curl",
            "copenhagen_plank",
        ],
    },

    # ── Wrestling ─────────────────────────────────────────────────────────────
    "wrestling": {
        "base_goal": "strength",
        "volume_modifier": 0.9,
        "emphasis_muscles": ["upper_back", "traps", "forearms", "glutes", "hamstrings"],
        "deemphasis_muscles": [],
        "mandatory_movement_patterns": ["horizontal_pull", "squat", "rotation"],
        "forbidden_exercises": [],
        "injury_prevention_additions": [
            "neck_harness_flexion",
            "barbell_shrug",
        ],
    },

    # ── Soccer ────────────────────────────────────────────────────────────────
    "soccer": {
        "base_goal": "power",
        "volume_modifier": 0.75,
        "emphasis_muscles": ["glutes", "hamstrings", "quads", "calves", "adductors"],
        "deemphasis_muscles": ["chest", "triceps"],
        "mandatory_movement_patterns": ["power_lower", "lunge"],
        "forbidden_exercises": [],
        "injury_prevention_additions": [
            "nordic_curl",
            "copenhagen_plank",     # Groin/adductor health
            "single_leg_rdl",       # Hip stability
        ],
    },

    # ── Volleyball ────────────────────────────────────────────────────────────
    "volleyball": {
        "base_goal": "power",
        "volume_modifier": 0.85,
        "emphasis_muscles": ["glutes", "quads", "calves", "side_delts", "rear_delts"],
        "deemphasis_muscles": [],
        "mandatory_movement_patterns": ["power_lower", "power_upper"],
        "forbidden_exercises": [],
        "injury_prevention_additions": [
            "band_external_rotation",  # Shoulder health
            "single_leg_calf_raise",
        ],
    },

    # ── Boxing ────────────────────────────────────────────────────────────────
    "boxing": {
        "base_goal": "power",
        "volume_modifier": 0.80,
        "emphasis_muscles": ["rear_delts", "upper_back", "obliques", "forearms", "glutes"],
        "deemphasis_muscles": ["quads", "calves"],
        "mandatory_movement_patterns": ["rotation", "power_upper", "horizontal_pull"],
        "forbidden_exercises": [],
        "injury_prevention_additions": [
            "band_external_rotation",
            "face_pull",             # Shoulder prehab
        ],
    },

    # ── MMA / Martial Arts ────────────────────────────────────────────────────
    "mma": {
        "base_goal": "power",
        "volume_modifier": 0.80,
        "emphasis_muscles": [
            "rear_delts", "upper_back", "obliques",
            "forearms", "glutes", "hamstrings",
        ],
        "deemphasis_muscles": [],
        "mandatory_movement_patterns": [
            "rotation", "power_upper", "power_lower",
            "horizontal_pull", "core",
        ],
        "forbidden_exercises": [],
        "injury_prevention_additions": [
            "band_external_rotation",
            "nordic_curl",
            "copenhagen_plank",
        ],
    },

    # ── Swimming ─────────────────────────────────────────────────────────────
    "swimming": {
        "base_goal": "strength",
        "volume_modifier": 0.80,
        "emphasis_muscles": ["lats", "upper_back", "rear_delts", "side_delts", "abs"],
        "deemphasis_muscles": ["quads", "calves"],
        "mandatory_movement_patterns": [
            "vertical_pull", "horizontal_pull", "core",
        ],
        "forbidden_exercises": [],
        "injury_prevention_additions": [
            "band_external_rotation",  # Shoulder health critical for swimmers
            "band_pull_apart",
            "face_pull",
        ],
    },

    # ── Running ───────────────────────────────────────────────────────────────
    "running": {
        "base_goal": "strength",
        "volume_modifier": 0.65,
        "emphasis_muscles": ["glutes", "hamstrings", "calves", "abs"],
        "deemphasis_muscles": ["chest", "triceps", "biceps"],
        "mandatory_movement_patterns": ["lunge", "hip_hinge"],
        "forbidden_exercises": [],           # No power movements — save CNS for sport
        "injury_prevention_additions": [
            "nordic_curl",               # #1 hamstring injury prevention tool
            "single_leg_rdl",            # Hip stability
            "copenhagen_plank",          # Adductor health
            "calf_raise",
        ],
    },

    # ── Cycling ───────────────────────────────────────────────────────────────
    "cycling": {
        "base_goal": "strength",
        "volume_modifier": 0.65,
        "emphasis_muscles": ["glutes", "quads", "hamstrings", "abs"],
        "deemphasis_muscles": ["chest", "triceps", "biceps"],
        "mandatory_movement_patterns": ["squat", "lunge"],
        "forbidden_exercises": [],
        "injury_prevention_additions": [
            "single_leg_rdl",
            "glute_bridge",
            "copenhagen_plank",
        ],
    },

    # ── Endurance (general) ───────────────────────────────────────────────────
    "endurance": {
        "base_goal": "strength",
        "volume_modifier": 0.60,
        "emphasis_muscles": ["glutes", "hamstrings", "calves", "abs"],
        "deemphasis_muscles": ["chest", "triceps", "biceps", "front_delts"],
        "mandatory_movement_patterns": ["hip_hinge", "lunge"],
        "forbidden_exercises": [],
        "injury_prevention_additions": [
            "nordic_curl",
            "single_leg_rdl",
            "calf_raise",
        ],
    },

    # ── Baseball ─────────────────────────────────────────────────────────────
    "baseball": {
        "base_goal": "power",
        "volume_modifier": 0.85,
        "emphasis_muscles": ["rear_delts", "upper_back", "obliques", "forearms", "glutes"],
        "deemphasis_muscles": [],
        "mandatory_movement_patterns": ["rotation", "power_upper", "hip_hinge"],
        "forbidden_exercises": [
            "barbell_behind_neck_press",  # Behind-neck press contraindicated for throwers
            "behind_neck_pulldown",
        ],
        "injury_prevention_additions": [
            "band_external_rotation",
            "band_pull_apart",
            "face_pull",
            "nordic_curl",
        ],
    },

    # ── Tennis ────────────────────────────────────────────────────────────────
    "tennis": {
        "base_goal": "power",
        "volume_modifier": 0.85,
        "emphasis_muscles": ["rear_delts", "upper_back", "obliques", "forearms", "glutes"],
        "deemphasis_muscles": [],
        "mandatory_movement_patterns": ["rotation", "lunge", "power_upper"],
        "forbidden_exercises": [
            "barbell_behind_neck_press",
        ],
        "injury_prevention_additions": [
            "band_external_rotation",
            "band_pull_apart",
            "face_pull",
        ],
    },

    # ── Golf ──────────────────────────────────────────────────────────────────
    "golf": {
        "base_goal": "power",
        "volume_modifier": 0.85,
        "emphasis_muscles": ["obliques", "glutes", "upper_back", "rear_delts", "forearms"],
        "deemphasis_muscles": [],
        "mandatory_movement_patterns": ["rotation", "hip_hinge", "core"],
        "forbidden_exercises": [],
        "injury_prevention_additions": [
            "band_external_rotation",
            "hip_flexor_stretch_exercise",
            "face_pull",
        ],
    },

    # ── General Athleticism ───────────────────────────────────────────────────
    "general_athleticism": {
        "base_goal": "power",
        "volume_modifier": 1.0,
        "emphasis_muscles": [],            # Balanced — no specific emphasis
        "deemphasis_muscles": [],
        "mandatory_movement_patterns": [
            "power_lower", "power_upper",
            "horizontal_push", "horizontal_pull",
            "squat", "hip_hinge",
        ],
        "forbidden_exercises": [],
        "injury_prevention_additions": [],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC HELPER
# ─────────────────────────────────────────────────────────────────────────────

def get_sport_adjustments(sport: str) -> dict | None:
    """
    Returns the sport adjustment dict for the given sport name, or None if not found.
    Lookup is case-insensitive and normalizes common variants.
    """
    if not sport:
        return None

    key = sport.lower().strip().replace(" ", "_").replace("-", "_")

    # Common aliases / variants
    _ALIASES: dict[str, str] = {
        "football":         "football_skill",
        "nfl":              "football_skill",
        "nfl_skill":        "football_skill",
        "lineman":          "football_linemen",
        "linemen":          "football_linemen",
        "american_football": "football_skill",
        "martial_arts":     "mma",
        "bjj":              "mma",
        "jiu_jitsu":        "mma",
        "kickboxing":       "boxing",
        "muay_thai":        "boxing",
        "track":            "running",
        "triathlon":        "endurance",
        "cross_country":    "running",
        "swim":             "swimming",
        "cycle":            "cycling",
        "biking":           "cycling",
        "baseball_softball": "baseball",
        "softball":         "baseball",
        "volleyball_beach": "volleyball",
        "general":          "general_athleticism",
        "sport":            "general_athleticism",
    }

    resolved_key = _ALIASES.get(key, key)
    return SPORT_MAPPINGS.get(resolved_key)
