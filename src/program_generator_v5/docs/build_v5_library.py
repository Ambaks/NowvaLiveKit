#!/usr/bin/env python3
"""
Convert existing exercise_library.json (V4 format) to V5 format,
add missing exercises to fill coverage gaps, and output as exercise_library_v5.py
"""
import json

# ──────────────────────────────────────────────
# V5 FIELD DERIVATION RULES
# ──────────────────────────────────────────────

def derive_equipment_tier(ex):
    m = ex["modality"]
    if m in ("barbell", "bodyweight", "plyometric"):
        return 1
    elif m == "dumbbell":
        return 2
    elif m == "band":
        return 3
    return 1

def derive_exercise_type_v5(ex):
    """Map V4 exercise_type + fatigue + cns + modality → V5 5-way type."""
    if ex["modality"] == "plyometric":
        return "plyometric"
    
    if ex["exercise_type"] == "isolation":
        return "isolation"
    
    if ex["exercise_type"] == "isometric":
        return "isolation"  # Planks, holds → treat as isolation for programming
    
    # Compound exercises: split into heavy_compound vs light_compound
    # Heavy compound = high fatigue OR high CNS AND primary barbell/BW compound lifts
    if ex["fatigue_profile"] == "high" and ex["cns_demand"] == "high":
        return "heavy_compound"
    
    # Specific overrides for known heavy compounds
    heavy_ids = {
        "barbell_back_squat", "barbell_front_squat", "barbell_conventional_deadlift",
        "barbell_sumo_deadlift", "barbell_bench_press", "barbell_incline_bench_press",
        "barbell_overhead_press", "barbell_push_press", "barbell_bent_over_row",
        "barbell_pendlay_row", "barbell_hip_thrust", "barbell_bulgarian_split_squat",
    }
    if ex["id"] in heavy_ids:
        return "heavy_compound"
    
    # Power movements
    power_ids = {
        "barbell_push_press", "barbell_hang_clean", "barbell_power_clean",
    }
    if ex["id"] in power_ids:
        return "power"
    
    return "light_compound"

def derive_movement_pattern_v5(ex):
    """Map V4 patterns to V5 more granular patterns."""
    p = ex["movement_pattern"]
    etype = ex["exercise_type"]
    modality = ex["modality"]
    primary = ex["primary_muscles"]
    
    if modality == "plyometric":
        # Plyometrics → power_lower or power_upper
        if any(m in primary for m in ["chest", "triceps", "front_delts"]):
            return "power_upper"
        return "power_lower"
    
    PATTERN_MAP = {
        "horizontal_push": "horizontal_push",
        "horizontal_pull": "horizontal_pull",
        "vertical_push": "vertical_push",
        "vertical_pull": "vertical_pull",
        "squat": "squat",
        "hinge": "hip_hinge",
        "lunge": "lunge",
        "carry": "carry",
        "rotation": "rotation",
        "anti_rotation": "core",
        "anti_extension": "core",
        "anti_lateral_flexion": "core",
        "hip_abduction": "isolation_pull",  # glute med work
        "full_body": "core",  # burpees, mountain climbers
    }
    
    if p in ("isolation_upper", "isolation_lower"):
        # Determine push vs pull isolation
        push_muscles = {"triceps", "chest", "front_delts", "side_delts", "calves"}
        pull_muscles = {"biceps", "rear_delts", "forearms", "hamstrings", "lats", "upper_back", "traps"}
        
        if any(m in push_muscles for m in primary):
            return "isolation_push"
        elif any(m in pull_muscles for m in primary):
            return "isolation_pull"
        else:
            return "core"  # abs, obliques, hip flexors, glute med
    
    return PATTERN_MAP.get(p, "core")

def derive_sfr_rating(ex):
    """
    Stimulus-to-Fatigue Ratio: 1-10.
    High SFR = lots of muscle stimulus for relatively little systemic fatigue.
    Low SFR = movement generates lots of fatigue relative to hypertrophy stimulus.
    """
    base = 5.0
    
    # Isolation exercises generally have high SFR
    if ex["exercise_type"] == "isolation":
        base = 7.5
    elif ex["exercise_type"] == "isometric":
        base = 6.0
    
    # Fatigue adjustments
    if ex["fatigue_profile"] == "high":
        base -= 2.0
    elif ex["fatigue_profile"] == "low":
        base += 1.5
    
    # CNS adjustments
    if ex["cns_demand"] == "high":
        base -= 1.0
    elif ex["cns_demand"] == "low":
        base += 0.5
    
    # Axial loading penalty (spinal compression = more systemic fatigue)
    if ex["loading_position"] == "axial":
        base -= 0.5
    
    # Specific exercise overrides based on known SFR characteristics
    HIGH_SFR = {
        "dumbbell_lateral_raise": 8.5, "band_lateral_raise": 9.0,
        "dumbbell_rear_delt_fly": 8.5, "band_pull_apart": 9.0,
        "band_face_pull": 8.5, "dumbbell_curl": 8.0, "band_bicep_curl": 8.5,
        "dumbbell_hammer_curl": 8.0, "barbell_curl": 7.5,
        "dumbbell_tricep_kickback": 8.0, "band_tricep_pushdown": 8.5,
        "dumbbell_skull_crusher": 7.5, "barbell_skull_crusher": 7.0,
        "dumbbell_chest_supported_row": 8.0,  # No spinal load
        "bodyweight_calf_raise": 8.0, "barbell_calf_raise": 7.0,
        "nordic_curl": 7.5, "dumbbell_incline_curl": 8.5,
        "band_external_rotation": 8.5,
        # Pull-ups/chin-ups: moderate SFR — good stimulus but grip + bodyweight fatigue
        "pull_up": 6.5, "chin_up": 7.0, "inverted_row": 7.5,
        # Bodyweight pushes
        "push_up": 7.0, "diamond_push_up": 7.0, "dip": 6.5,
        "pike_push_up": 6.0,
        # DB presses have good SFR (stable, less setup fatigue than barbell)
        "dumbbell_bench_press": 7.0, "dumbbell_incline_press": 7.0,
        "dumbbell_overhead_press": 7.0, "dumbbell_arnold_press": 7.0,
        # Band exercises: very high SFR (low systemic fatigue)
        "band_row": 8.0, "band_overhead_press": 7.0,
        "band_squat": 7.0, "band_good_morning": 7.5,
        "band_lateral_raise": 9.0, "band_pallof_press": 8.0,
    }
    LOW_SFR = {
        "barbell_conventional_deadlift": 3.0,  # Massive systemic fatigue
        "barbell_sumo_deadlift": 3.5,
        "barbell_back_squat": 4.0,
        "barbell_front_squat": 3.5,
        "barbell_bent_over_row": 4.5,  # Spinal load
        "barbell_pendlay_row": 4.5,
        "barbell_bench_press": 5.5,  # Good SFR for a heavy compound
        "barbell_incline_bench_press": 5.5,
        "barbell_overhead_press": 5.0,
        "barbell_push_press": 4.5,
        "barbell_floor_press": 5.5,
        "burpee": 3.0,
    }
    
    if ex["id"] in HIGH_SFR:
        return HIGH_SFR[ex["id"]]
    if ex["id"] in LOW_SFR:
        return LOW_SFR[ex["id"]]
    
    return round(max(1.0, min(10.0, base)), 1)

def derive_muscle_activations(ex):
    """
    Convert primary/secondary/stabilizer lists to MuscleActivation objects with volume_credit.
    
    Rules:
    - Primary: volume_credit = 1.0
    - Secondary: volume_credit = 0.5
    - Stabilizer: volume_credit = 0.0 (tracked but doesn't count)
    
    Also maps V4 muscle names to V5 MuscleGroup enum values.
    """
    MUSCLE_MAP = {
        "quads": "quads",
        "glutes": "glutes",
        "hamstrings": "hamstrings",
        "calves": "calves",
        "adductors": "adductors",
        "chest": "chest",
        "lats": "lats",
        "upper_back": "upper_back",
        "traps": "traps",
        "erectors": "erectors",
        "front_delts": "front_delts",
        "side_delts": "side_delts",
        "rear_delts": "rear_delts",
        "biceps": "biceps",
        "triceps": "triceps",
        "forearms": "forearms",
        "core": "abs",          # Map V4 'core' → V5 'abs'
        "obliques": "obliques",
        "hip_flexors": "abs",   # Group with abs for volume tracking
        "glute_medius": "glutes",  # Group with glutes
        "serratus": "chest",    # Minor, group with chest
    }
    
    activations = []
    seen = set()
    
    for m in ex["primary_muscles"]:
        mapped = MUSCLE_MAP.get(m, m)
        if mapped not in seen:
            activations.append({
                "muscle": mapped,
                "role": "primary",
                "volume_credit": 1.0
            })
            seen.add(mapped)
    
    for m in ex["secondary_muscles"]:
        mapped = MUSCLE_MAP.get(m, m)
        if mapped not in seen:
            activations.append({
                "muscle": mapped,
                "role": "secondary",
                "volume_credit": 0.5
            })
            seen.add(mapped)
    
    for m in ex["stabilizers"]:
        mapped = MUSCLE_MAP.get(m, m)
        if mapped not in seen:
            activations.append({
                "muscle": mapped,
                "role": "stabilizer",
                "volume_credit": 0.0
            })
            seen.add(mapped)
    
    return activations

def derive_rotation_group(ex, v5_type, v5_pattern):
    """
    Exercises in the same rotation group are interchangeable.
    Group by: movement_pattern + primary_muscle(s) + exercise_type
    """
    primary_sorted = "_".join(sorted(ex["primary_muscles"][:2]))  # Top 2 primary muscles
    return f"{v5_pattern}_{primary_sorted}_{v5_type}"

def derive_variation_tags(ex):
    """Extract variation-relevant tags."""
    tags = []
    name_lower = ex["name"].lower()
    
    if "incline" in name_lower: tags.append("incline")
    if "decline" in name_lower: tags.append("decline")
    if "close" in name_lower or "narrow" in name_lower: tags.append("close_grip")
    if "wide" in name_lower: tags.append("wide_grip")
    if "pause" in name_lower: tags.append("pause")
    if "deficit" in name_lower: tags.append("deficit")
    if "sumo" in name_lower: tags.append("sumo")
    if "front" in name_lower and "squat" in name_lower: tags.append("front_loaded")
    if "romanian" in name_lower or "stiff" in name_lower: tags.append("stretch")
    if "overhead" in name_lower: tags.append("overhead")
    if "hammer" in name_lower: tags.append("neutral_grip")
    if "reverse" in name_lower: tags.append("reverse_grip")
    if "single" in name_lower or ex["stance"] == "unilateral": tags.append("unilateral")
    if "supported" in name_lower: tags.append("supported")
    if "landmine" in name_lower: tags.append("landmine")
    if "arnold" in name_lower: tags.append("arnold")
    
    # Stretch-position exercises (high SFR for hypertrophy)
    stretch_ids = {
        "barbell_romanian_deadlift", "barbell_stiff_leg_deadlift",
        "dumbbell_romanian_deadlift", "dumbbell_single_leg_rdl",
        "barbell_skull_crusher", "dumbbell_skull_crusher",
        "dumbbell_incline_curl",  # stretch at bottom
        "barbell_incline_bench_press",  # stretch at bottom
        "dumbbell_fly", "dumbbell_incline_fly",
        "dumbbell_pullover",
        "nordic_curl",
    }
    if ex["id"] in stretch_ids:
        tags.append("stretch")
    
    return tags

def derive_min_max_reps(ex):
    """
    Get min/max reps from typical_rep_range.
    Use strength min and hypertrophy max to get the practical training range.
    Don't use endurance range (too wide) or power alone (too narrow).
    """
    rr = ex["typical_rep_range"]
    
    # Get the lowest from strength/power and highest from hypertrophy
    min_rep = 20
    max_rep = 1
    
    for goal in ["strength", "power"]:
        if goal in rr and rr[goal]:
            min_rep = min(min_rep, rr[goal][0])
    
    for goal in ["hypertrophy", "endurance"]:
        if goal in rr and rr[goal]:
            max_rep = max(max_rep, rr[goal][1])
    
    # Clamp to reasonable bounds
    min_rep = max(1, min(min_rep, 10))
    max_rep = min(30, max(max_rep, 5))
    
    # For isolations, don't go below 6 reps
    if ex["exercise_type"] == "isolation":
        min_rep = max(min_rep, 6)
    
    return min_rep, max_rep

def derive_bilateral(ex):
    """
    Determine if exercise works both sides simultaneously.
    False = need to do sets per side (unilateral).
    """
    # Staggered stance (lunges, split squats, single-arm rows) = unilateral
    # Unilateral = obvious
    if ex["stance"] in ("unilateral", "staggered"):
        return False
    return True

def derive_difficulty(ex):
    """Map skill_level to 1-5 difficulty."""
    return {"beginner": 1, "intermediate": 3, "advanced": 5}.get(ex["skill_level"], 3)

def derive_grip_intensive(ex):
    """True for exercises that heavily tax grip."""
    grip_ids = {
        "barbell_conventional_deadlift", "barbell_sumo_deadlift",
        "barbell_romanian_deadlift", "barbell_stiff_leg_deadlift",
        "barbell_bent_over_row", "barbell_pendlay_row", "barbell_landmine_row",
        "barbell_shrug", "barbell_curl", "barbell_upright_row",
        "pull_up", "chin_up", "inverted_row",
        "dumbbell_row", "dumbbell_renegade_row", "dumbbell_chest_supported_row",
        "dumbbell_shrug", "dumbbell_hammer_curl", "dumbbell_curl",
        "dumbbell_romanian_deadlift", "dumbbell_single_leg_rdl",
        "farmer_carry",
    }
    return ex["id"] in grip_ids

# ──────────────────────────────────────────────
# CONVERT ALL EXISTING EXERCISES
# ──────────────────────────────────────────────

def convert_exercise(ex):
    """Convert a V4 exercise to V5 format."""
    v5_type = derive_exercise_type_v5(ex)
    v5_pattern = derive_movement_pattern_v5(ex)
    min_reps, max_reps = derive_min_max_reps(ex)
    
    return {
        "id": ex["id"],
        "name": ex["name"],
        "equipment_tier": derive_equipment_tier(ex),
        "exercise_type": v5_type,
        "movement_pattern": v5_pattern,
        "muscle_activations": derive_muscle_activations(ex),
        
        "min_reps": min_reps,
        "max_reps": max_reps,
        "min_sets_per_session": 2,
        "max_sets_per_session": 5 if v5_type in ("heavy_compound", "light_compound") else 4,
        
        "is_axial_loading": ex["loading_position"] == "axial",
        "systemic_fatigue": ex["fatigue_profile"],
        "grip_intensive": derive_grip_intensive(ex),
        
        "difficulty": derive_difficulty(ex),
        "requires_proficiency": ex["skill_level"] == "advanced" and v5_type in ("heavy_compound", "power"),
        "bilateral": derive_bilateral(ex),
        
        "sfr_rating": derive_sfr_rating(ex),
        
        "cues": ex.get("coaching_cues", []),
        "common_mistakes": ex.get("common_mistakes", []),
        
        "rotation_group": derive_rotation_group(ex, v5_type, v5_pattern),
        "variation_tags": derive_variation_tags(ex),
        
        # Preserved V4 fields (useful for voice agent and other systems)
        "_v4_joint_stress": ex.get("joint_stress", {}),
        "_v4_contraindications": ex.get("contraindications", []),
        "_v4_substitutes": ex.get("substitutes", []),
        "_v4_supersets_well_with": ex.get("supersets_well_with", []),
        "_v4_progression_to": ex.get("progression_to"),
        "_v4_regression_of": ex.get("regression_of"),
        "_v4_tempo_sensitive": ex.get("tempo_sensitive", False),
        "_v4_eccentric_overload_suitable": ex.get("eccentric_overload_suitable", False),
        "_v4_warmup_suitable": ex.get("warmup_suitable", False),
        "_v4_finisher_suitable": ex.get("finisher_suitable", False),
        "_v4_mobility_prerequisites": ex.get("mobility_prerequisites", []),
        "_v4_tags": ex.get("tags", []),
    }

# ──────────────────────────────────────────────
# MANUAL OVERRIDES — Fix derivation errors
# ──────────────────────────────────────────────

OVERRIDES = {
    # Push press is a POWER movement, not heavy compound
    "barbell_push_press": {
        "exercise_type": "power",
        "movement_pattern": "power_upper",
    },
    # Upright row is vertical pull but for side delts/traps, not lats
    "barbell_upright_row": {
        "movement_pattern": "isolation_pull",  # Treat as pull isolation since it's not a lat vertical pull
    },
    # Dumbbell pullover targets lats (vertical pull-ish) and chest
    "dumbbell_pullover": {
        "movement_pattern": "vertical_pull",  # Best classification
    },
    # Plyometric push up is power_upper
    "plyometric_push_up": {
        "exercise_type": "plyometric",
        "movement_pattern": "power_upper",
    },
    # Burpee / mountain climber are full body conditioning, classify as power_lower
    "burpee": {
        "movement_pattern": "power_lower",
    },
    "mountain_climber": {
        "movement_pattern": "core",
        "exercise_type": "isolation",  # More of a core/conditioning exercise
    },
    # Jump rope is a calf/conditioning exercise
    "jump_rope": {
        "movement_pattern": "isolation_push",  # Calves
        "exercise_type": "isolation",
    },
    # Band external/internal rotation are isolation pull/push for rehab
    "band_external_rotation": {
        "movement_pattern": "isolation_pull",
    },
    "band_internal_rotation": {
        "movement_pattern": "isolation_push",
    },
    # Renegade row: keep as horizontal_pull but it's light compound
    "dumbbell_renegade_row": {
        "exercise_type": "light_compound",
        "sfr_rating": 5.0,  # High fatigue due to plank position
    },
    # Band pull apart: it's isolation_pull for rear delts, not horizontal_pull
    "band_pull_apart": {
        "movement_pattern": "isolation_pull",
    },
    # Band face pull: same — isolation_pull for rear delts
    "band_face_pull": {
        "movement_pattern": "isolation_pull",
    },
    # Diamond push-up: triceps-focused isolation, not light_compound
    "diamond_push_up": {
        "exercise_type": "isolation",
        "movement_pattern": "isolation_push",
        "muscle_activations_override": [
            {"muscle": "triceps", "role": "primary", "volume_credit": 1.0},
            {"muscle": "chest", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "front_delts", "role": "secondary", "volume_credit": 0.5},
        ],
        "sfr_rating": 7.0,
    },
    # Band good morning: light_compound hip hinge
    "band_good_morning": {
        "exercise_type": "light_compound",
        "movement_pattern": "hip_hinge",
        "muscle_activations_override": [
            {"muscle": "hamstrings", "role": "primary", "volume_credit": 1.0},
            {"muscle": "glutes", "role": "primary", "volume_credit": 1.0},
            {"muscle": "erectors", "role": "secondary", "volume_credit": 0.5},
        ],
    },
    # Barbell landmine press: add upper_chest to activations
    "barbell_landmine_press": {
        "muscle_activations_override": [
            {"muscle": "chest", "role": "primary", "volume_credit": 1.0},
            {"muscle": "upper_chest", "role": "primary", "volume_credit": 1.0},
            {"muscle": "front_delts", "role": "primary", "volume_credit": 1.0},
            {"muscle": "triceps", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "abs", "role": "stabilizer", "volume_credit": 0.0},
        ],
        "sfr_rating": 7.5,
    },
    # Barbell good morning: ensure correct classification
    "barbell_good_morning": {
        "exercise_type": "light_compound",
        "movement_pattern": "hip_hinge",
        "sfr_rating": 5.5,
    },
    # Band Pallof press: core anti-rotation isolation
    "band_pallof_press": {
        "exercise_type": "isolation",
        "movement_pattern": "core",
        "muscle_activations_override": [
            {"muscle": "abs", "role": "primary", "volume_credit": 1.0},
            {"muscle": "obliques", "role": "primary", "volume_credit": 1.0},
        ],
    },
    # Nordic curl: isolation_pull for hamstrings
    "nordic_curl": {
        "movement_pattern": "isolation_pull",
        "sfr_rating": 7.0,
    },
    # Cossack squat is more of a lunge/mobility
    "cossack_squat": {
        "movement_pattern": "lunge",
    },
    # Farmer carry
    "farmer_carry": {
        "movement_pattern": "carry",
    },
    # Side plank → core
    "side_plank": {
        "movement_pattern": "core",
    },
    # Dead bug → core
    "dead_bug": {
        "movement_pattern": "core",
    },
    # Hollow body hold → core
    "hollow_body_hold": {
        "movement_pattern": "core",
    },
    # Superman → core/hip_hinge hybrid, classify as core
    "superman": {
        "movement_pattern": "core",
    },
    # Hip thrust — heavy compound for glutes
    "barbell_hip_thrust": {
        "exercise_type": "heavy_compound",
        "sfr_rating": 6.5,  # Good SFR — no axial loading, targets glutes well
    },
    # Incline bench → add upper_chest as primary
    "barbell_incline_bench_press": {
        "muscle_activations_override": [
            {"muscle": "chest", "role": "primary", "volume_credit": 1.0},
            {"muscle": "upper_chest", "role": "primary", "volume_credit": 1.0},
            {"muscle": "front_delts", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "triceps", "role": "secondary", "volume_credit": 0.5},
        ]
    },
    "dumbbell_incline_bench_press": {
        "muscle_activations_override": [
            {"muscle": "chest", "role": "primary", "volume_credit": 1.0},
            {"muscle": "upper_chest", "role": "primary", "volume_credit": 1.0},
            {"muscle": "front_delts", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "triceps", "role": "secondary", "volume_credit": 0.5},
        ]
    },
    # Close grip bench → triceps is primary, chest secondary
    "barbell_close_grip_bench_press": {
        "muscle_activations_override": [
            {"muscle": "triceps", "role": "primary", "volume_credit": 1.0},
            {"muscle": "chest", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "front_delts", "role": "secondary", "volume_credit": 0.5},
        ],
        "exercise_type": "light_compound",
    },
    # Dip → triceps primary, chest secondary
    "dip": {
        "muscle_activations_override": [
            {"muscle": "triceps", "role": "primary", "volume_credit": 1.0},
            {"muscle": "chest", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "front_delts", "role": "secondary", "volume_credit": 0.5},
        ]
    },
    # Chin up → biceps AND lats both primary (it's excellent for both)
    "chin_up": {
        "muscle_activations_override": [
            {"muscle": "biceps", "role": "primary", "volume_credit": 1.0},
            {"muscle": "lats", "role": "primary", "volume_credit": 1.0},
            {"muscle": "upper_back", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "forearms", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "abs", "role": "stabilizer", "volume_credit": 0.0},
        ]
    },
    # Pull up → lats primary, biceps secondary (less biceps than chin-ups due to pronated grip)
    "pull_up": {
        "muscle_activations_override": [
            {"muscle": "lats", "role": "primary", "volume_credit": 1.0},
            {"muscle": "upper_back", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "biceps", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "forearms", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "abs", "role": "stabilizer", "volume_credit": 0.0},
        ]
    },
}

# ──────────────────────────────────────────────
# NEW EXERCISES TO ADD (filling coverage gaps)
# ──────────────────────────────────────────────

NEW_EXERCISES = [
    # ─── TIER 1: Rear Delt (CRITICAL GAP) ───
    {
        "id": "barbell_face_pull",
        "name": "Barbell Face Pull",
        "equipment_tier": 1,
        "exercise_type": "isolation",
        "movement_pattern": "isolation_pull",
        "muscle_activations": [
            {"muscle": "rear_delts", "role": "primary", "volume_credit": 1.0},
            {"muscle": "upper_back", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "traps", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 10, "max_reps": 20,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": True,
        "difficulty": 2, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 7.0,
        "cues": ["Pull the bar to your forehead", "Flare elbows high", "Squeeze rear delts at top", "Use lighter weight, control the movement"],
        "common_mistakes": ["Using too much weight", "Turning it into a row", "Not flaring elbows high enough"],
        "rotation_group": "isolation_pull_rear_delts_isolation",
        "variation_tags": ["face_pull"],
    },
    {
        "id": "wide_grip_inverted_row",
        "name": "Wide-Grip Inverted Row (Elbows Flared)",
        "equipment_tier": 1,
        "exercise_type": "light_compound",
        "movement_pattern": "horizontal_pull",
        "muscle_activations": [
            {"muscle": "rear_delts", "role": "primary", "volume_credit": 1.0},
            {"muscle": "upper_back", "role": "primary", "volume_credit": 1.0},
            {"muscle": "lats", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "biceps", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 6, "max_reps": 20,
        "min_sets_per_session": 2, "max_sets_per_session": 5,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": True,
        "difficulty": 2, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 7.5,
        "cues": ["Grip wider than shoulder width", "Flare elbows out at 45-60 degrees", "Pull chest to bar", "Squeeze shoulder blades together"],
        "common_mistakes": ["Tucking elbows (turns into lat row)", "Sagging hips", "Not getting full range"],
        "rotation_group": "horizontal_pull_rear_delts_upper_back_light_compound",
        "variation_tags": ["wide_grip", "bodyweight"],
    },
    {
        "id": "prone_y_raise_plate",
        "name": "Prone Y-Raise (Plate/Light Bar)",
        "equipment_tier": 1,
        "exercise_type": "isolation",
        "movement_pattern": "isolation_pull",
        "muscle_activations": [
            {"muscle": "rear_delts", "role": "primary", "volume_credit": 1.0},
            {"muscle": "upper_back", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "traps", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 12, "max_reps": 25,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": False,
        "difficulty": 1, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 8.0,
        "cues": ["Lie face down on incline bench", "Raise arms in Y-shape", "Thumbs pointing up", "Light weight, focus on squeeze"],
        "common_mistakes": ["Using too much weight", "Shrugging traps instead of rear delts", "Not reaching full extension"],
        "rotation_group": "isolation_pull_rear_delts_isolation",
        "variation_tags": ["prone", "y_raise"],
    },

    # ─── TIER 1: Side Delt Isolation (CRITICAL GAP) ───
    {
        "id": "plate_lateral_raise",
        "name": "Plate Lateral Raise",
        "equipment_tier": 1,
        "exercise_type": "isolation",
        "movement_pattern": "isolation_push",
        "muscle_activations": [
            {"muscle": "side_delts", "role": "primary", "volume_credit": 1.0},
            {"muscle": "traps", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 10, "max_reps": 25,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": False,
        "difficulty": 1, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 8.0,
        "cues": ["Hold plate by edges", "Raise to shoulder height", "Slight lean forward", "Control the descent"],
        "common_mistakes": ["Swinging", "Raising above shoulder height", "Using momentum"],
        "rotation_group": "isolation_push_side_delts_isolation",
        "variation_tags": ["plate", "lateral_raise"],
    },
    {
        "id": "barbell_lateral_raise",
        "name": "Barbell Lateral Raise",
        "equipment_tier": 1,
        "exercise_type": "isolation",
        "movement_pattern": "isolation_push",
        "muscle_activations": [
            {"muscle": "side_delts", "role": "primary", "volume_credit": 1.0},
            {"muscle": "front_delts", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "traps", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 10, "max_reps": 20,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": True,
        "difficulty": 2, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 6.5,
        "cues": ["Grab barbell at center with both hands", "Raise in front then to sides", "Keep arms slightly bent", "Lighter weight is better"],
        "common_mistakes": ["Using too much weight", "Turning it into a front raise"],
        "rotation_group": "isolation_push_side_delts_isolation",
        "variation_tags": ["barbell", "lateral_raise"],
    },

    # ─── TIER 1: Bicep Isolation Variety ───
    {
        "id": "barbell_drag_curl",
        "name": "Barbell Drag Curl",
        "equipment_tier": 1,
        "exercise_type": "isolation",
        "movement_pattern": "isolation_pull",
        "muscle_activations": [
            {"muscle": "biceps", "role": "primary", "volume_credit": 1.0},
            {"muscle": "forearms", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 8, "max_reps": 15,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": True,
        "difficulty": 2, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 8.0,
        "cues": ["Drag the bar up your torso", "Elbows go back, not forward", "Squeeze biceps at top", "Slow eccentric"],
        "common_mistakes": ["Elbows drifting forward (turns into regular curl)", "Using momentum"],
        "rotation_group": "isolation_pull_biceps_isolation",
        "variation_tags": ["drag_curl", "stretch"],
    },
    {
        "id": "barbell_reverse_curl",
        "name": "Barbell Reverse Curl",
        "equipment_tier": 1,
        "exercise_type": "isolation",
        "movement_pattern": "isolation_pull",
        "muscle_activations": [
            {"muscle": "forearms", "role": "primary", "volume_credit": 1.0},
            {"muscle": "biceps", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 8, "max_reps": 15,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": True,
        "difficulty": 2, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 7.5,
        "cues": ["Overhand/pronated grip", "Keep wrists straight", "Controlled tempo", "Squeeze at top"],
        "common_mistakes": ["Wrists bending", "Too much body english"],
        "rotation_group": "isolation_pull_forearms_isolation",
        "variation_tags": ["reverse_grip"],
    },

    # ─── TIER 1: Tricep Isolation Variety ───
    {
        "id": "barbell_overhead_tricep_extension",
        "name": "Barbell Overhead Tricep Extension",
        "equipment_tier": 1,
        "exercise_type": "isolation",
        "movement_pattern": "isolation_push",
        "muscle_activations": [
            {"muscle": "triceps", "role": "primary", "volume_credit": 1.0},
        ],
        "min_reps": 8, "max_reps": 15,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": False,
        "difficulty": 2, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 7.5,
        "cues": ["Keep elbows pointed forward", "Lower bar behind head", "Full stretch at bottom", "Lock out at top"],
        "common_mistakes": ["Elbows flaring out", "Not going deep enough", "Using too much weight"],
        "rotation_group": "isolation_push_triceps_isolation",
        "variation_tags": ["overhead", "stretch"],
    },
    {
        "id": "diamond_push_up",
        "name": "Diamond Push-Up",
        "equipment_tier": 1,
        "exercise_type": "isolation",
        "movement_pattern": "isolation_push",
        "muscle_activations": [
            {"muscle": "triceps", "role": "primary", "volume_credit": 1.0},
            {"muscle": "chest", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "front_delts", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 6, "max_reps": 25,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": False,
        "difficulty": 2, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 7.0,
        "cues": ["Hands together forming a diamond", "Keep elbows close to body", "Full range of motion", "Squeeze triceps at top"],
        "common_mistakes": ["Elbows flaring wide", "Sagging hips", "Partial reps"],
        "rotation_group": "isolation_push_triceps_isolation",
        "variation_tags": ["close_grip", "bodyweight"],
    },
    {
        "id": "bodyweight_dip",
        "name": "Dip (Bodyweight)",
        "equipment_tier": 1,
        "exercise_type": "light_compound",
        "movement_pattern": "horizontal_push",
        "muscle_activations": [
            {"muscle": "triceps", "role": "primary", "volume_credit": 1.0},
            {"muscle": "chest", "role": "primary", "volume_credit": 1.0},
            {"muscle": "front_delts", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 5, "max_reps": 20,
        "min_sets_per_session": 2, "max_sets_per_session": 5,
        "is_axial_loading": False, "systemic_fatigue": "moderate", "grip_intensive": False,
        "difficulty": 3, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 7.0,
        "cues": ["Lean forward for chest, upright for triceps", "Lower until upper arms parallel to floor", "Lock out at top", "Control the descent"],
        "common_mistakes": ["Going too deep (shoulder impingement)", "Swinging", "Not locking out"],
        "rotation_group": "horizontal_push_chest_triceps_light_compound",
        "variation_tags": ["bodyweight", "dip"],
    },

    # ─── TIER 1: Vertical Pull Variety (CRITICAL GAP) ───
    {
        "id": "wide_grip_pull_up",
        "name": "Wide-Grip Pull-Up",
        "equipment_tier": 1,
        "exercise_type": "light_compound",
        "movement_pattern": "vertical_pull",
        "muscle_activations": [
            {"muscle": "lats", "role": "primary", "volume_credit": 1.0},
            {"muscle": "upper_back", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "biceps", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "forearms", "role": "stabilizer", "volume_credit": 0.0},
        ],
        "min_reps": 3, "max_reps": 15,
        "min_sets_per_session": 2, "max_sets_per_session": 5,
        "is_axial_loading": False, "systemic_fatigue": "moderate", "grip_intensive": True,
        "difficulty": 4, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 6.5,
        "cues": ["Grip wider than shoulder width", "Pull elbows down and back", "Chest to bar", "Full dead hang at bottom"],
        "common_mistakes": ["Half reps", "Kipping", "Not going to full extension"],
        "rotation_group": "vertical_pull_lats_light_compound",
        "variation_tags": ["wide_grip"],
    },
    {
        "id": "commando_pull_up",
        "name": "Commando Pull-Up",
        "equipment_tier": 1,
        "exercise_type": "light_compound",
        "movement_pattern": "vertical_pull",
        "muscle_activations": [
            {"muscle": "lats", "role": "primary", "volume_credit": 1.0},
            {"muscle": "biceps", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "upper_back", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "obliques", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "forearms", "role": "stabilizer", "volume_credit": 0.0},
        ],
        "min_reps": 4, "max_reps": 12,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "moderate", "grip_intensive": True,
        "difficulty": 4, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 6.0,
        "cues": ["Hands staggered on bar (one in front of other)", "Alternate head side each rep", "Control the movement", "Full hang at bottom"],
        "common_mistakes": ["Kipping", "Only going to one side", "Partial range of motion"],
        "rotation_group": "vertical_pull_lats_light_compound",
        "variation_tags": ["neutral_grip", "alternating"],
    },
    {
        "id": "neutral_grip_pull_up",
        "name": "Neutral-Grip Pull-Up",
        "equipment_tier": 1,
        "exercise_type": "light_compound",
        "movement_pattern": "vertical_pull",
        "muscle_activations": [
            {"muscle": "lats", "role": "primary", "volume_credit": 1.0},
            {"muscle": "biceps", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "upper_back", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "forearms", "role": "stabilizer", "volume_credit": 0.0},
        ],
        "min_reps": 4, "max_reps": 15,
        "min_sets_per_session": 2, "max_sets_per_session": 5,
        "is_axial_loading": False, "systemic_fatigue": "moderate", "grip_intensive": True,
        "difficulty": 3, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 7.0,
        "cues": ["Palms facing each other", "Pull chest to bar", "Squeeze lats at top", "Full extension at bottom"],
        "common_mistakes": ["Half reps", "Kipping"],
        "rotation_group": "vertical_pull_lats_light_compound",
        "variation_tags": ["neutral_grip"],
    },
    {
        "id": "towel_pull_up",
        "name": "Towel Pull-Up",
        "equipment_tier": 1,
        "exercise_type": "light_compound",
        "movement_pattern": "vertical_pull",
        "muscle_activations": [
            {"muscle": "lats", "role": "primary", "volume_credit": 1.0},
            {"muscle": "forearms", "role": "primary", "volume_credit": 1.0},
            {"muscle": "biceps", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "upper_back", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 3, "max_reps": 10,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "moderate", "grip_intensive": True,
        "difficulty": 5, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 5.5,
        "cues": ["Drape towel over bar, grip both ends", "Massive grip challenge", "Full range of motion", "Builds grip and forearm strength"],
        "common_mistakes": ["Letting go (grip failure)", "Partial reps"],
        "rotation_group": "vertical_pull_lats_forearms_light_compound",
        "variation_tags": ["towel", "grip_strength"],
    },

    # ─── TIER 1: Oblique Exercises (CRITICAL GAP) ───
    {
        "id": "barbell_landmine_rotation",
        "name": "Barbell Landmine Rotation",
        "equipment_tier": 1,
        "exercise_type": "isolation",
        "movement_pattern": "rotation",
        "muscle_activations": [
            {"muscle": "obliques", "role": "primary", "volume_credit": 1.0},
            {"muscle": "abs", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "front_delts", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 8, "max_reps": 15,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": False,
        "difficulty": 2, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 7.5,
        "cues": ["Wedge one end of barbell in corner or landmine", "Arms extended, rotate side to side", "Power from the hips", "Control the weight at end range"],
        "common_mistakes": ["All arm movement, no rotation", "Rounding the back", "Going too fast"],
        "rotation_group": "rotation_obliques_isolation",
        "variation_tags": ["landmine", "rotation"],
    },
    {
        "id": "hanging_oblique_knee_raise",
        "name": "Hanging Oblique Knee Raise",
        "equipment_tier": 1,
        "exercise_type": "isolation",
        "movement_pattern": "core",
        "muscle_activations": [
            {"muscle": "obliques", "role": "primary", "volume_credit": 1.0},
            {"muscle": "abs", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 8, "max_reps": 20,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": True,
        "difficulty": 3, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 7.5,
        "cues": ["Hang from pull-up bar", "Raise knees to the side", "Alternate sides or do one side at a time", "Control the swing"],
        "common_mistakes": ["Too much swinging", "Not targeting obliques (going straight up)"],
        "rotation_group": "core_obliques_isolation",
        "variation_tags": ["hanging", "oblique"],
    },
    {
        "id": "suitcase_carry",
        "name": "Barbell Suitcase Carry",
        "equipment_tier": 1,
        "exercise_type": "isolation",
        "movement_pattern": "carry",
        "muscle_activations": [
            {"muscle": "obliques", "role": "primary", "volume_credit": 1.0},
            {"muscle": "abs", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "forearms", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "traps", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 1, "max_reps": 1,  # Measured in distance/time, program as 1 "rep" per set
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "moderate", "grip_intensive": True,
        "difficulty": 2, "requires_proficiency": False, "bilateral": False,
        "sfr_rating": 7.0,
        "cues": ["Hold barbell at one side only", "Walk tall, don't lean", "Brace core hard", "Switch sides each set"],
        "common_mistakes": ["Leaning to one side", "Holding breath"],
        "rotation_group": "carry_obliques_isolation",
        "variation_tags": ["carry", "unilateral", "anti_lateral_flexion"],
    },

    # ─── TIER 1: Core Variety ───
    {
        "id": "hanging_leg_raise",
        "name": "Hanging Leg Raise",
        "equipment_tier": 1,
        "exercise_type": "isolation",
        "movement_pattern": "core",
        "muscle_activations": [
            {"muscle": "abs", "role": "primary", "volume_credit": 1.0},
            {"muscle": "obliques", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 6, "max_reps": 20,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": True,
        "difficulty": 3, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 8.0,
        "cues": ["Hang from pull-up bar", "Raise legs to parallel or higher", "Posterior pelvic tilt at top", "Control the descent"],
        "common_mistakes": ["Swinging", "Using hip flexors only", "Not reaching full range"],
        "rotation_group": "core_abs_isolation",
        "variation_tags": ["hanging"],
    },
    {
        "id": "barbell_ab_rollout",
        "name": "Barbell Ab Rollout",
        "equipment_tier": 1,
        "exercise_type": "isolation",
        "movement_pattern": "core",
        "muscle_activations": [
            {"muscle": "abs", "role": "primary", "volume_credit": 1.0},
            {"muscle": "obliques", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "lats", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 5, "max_reps": 15,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": False,
        "difficulty": 3, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 8.0,
        "cues": ["Load small plates on barbell", "Roll out from knees", "Brace core entire time", "Don't let hips sag"],
        "common_mistakes": ["Hips sagging", "Not going far enough", "Using hip flexors to pull back"],
        "rotation_group": "core_abs_isolation",
        "variation_tags": ["rollout", "anti_extension"],
    },

    # ─── TIER 2: Bicep Variety ───
    {
        "id": "dumbbell_incline_curl",
        "name": "Dumbbell Incline Curl",
        "equipment_tier": 2,
        "exercise_type": "isolation",
        "movement_pattern": "isolation_pull",
        "muscle_activations": [
            {"muscle": "biceps", "role": "primary", "volume_credit": 1.0},
            {"muscle": "forearms", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 8, "max_reps": 15,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": True,
        "difficulty": 1, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 8.5,
        "cues": ["Set bench to 30-45 degrees", "Let arms hang straight down", "Curl without moving upper arm", "Maximum stretch at bottom"],
        "common_mistakes": ["Bench angle too steep", "Swinging upper arms forward"],
        "rotation_group": "isolation_pull_biceps_isolation",
        "variation_tags": ["incline", "stretch"],
    },
    {
        "id": "dumbbell_concentration_curl",
        "name": "Dumbbell Concentration Curl",
        "equipment_tier": 2,
        "exercise_type": "isolation",
        "movement_pattern": "isolation_pull",
        "muscle_activations": [
            {"muscle": "biceps", "role": "primary", "volume_credit": 1.0},
        ],
        "min_reps": 8, "max_reps": 15,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": True,
        "difficulty": 1, "requires_proficiency": False, "bilateral": False,
        "sfr_rating": 8.5,
        "cues": ["Brace elbow against inner thigh", "Curl with full range", "Squeeze at top", "Slow negative"],
        "common_mistakes": ["Using body english", "Not bracing elbow properly"],
        "rotation_group": "isolation_pull_biceps_isolation",
        "variation_tags": ["concentration", "unilateral"],
    },

    # ─── TIER 2: Tricep Variety ───
    {
        "id": "dumbbell_overhead_extension",
        "name": "Dumbbell Overhead Tricep Extension",
        "equipment_tier": 2,
        "exercise_type": "isolation",
        "movement_pattern": "isolation_push",
        "muscle_activations": [
            {"muscle": "triceps", "role": "primary", "volume_credit": 1.0},
        ],
        "min_reps": 8, "max_reps": 15,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": False,
        "difficulty": 1, "requires_proficiency": False, "bilateral": False,
        "sfr_rating": 8.5,
        "cues": ["Hold one DB overhead", "Lower behind head", "Keep elbow pointed up", "Full stretch at bottom"],
        "common_mistakes": ["Elbow flaring", "Not going deep enough", "Arching lower back"],
        "rotation_group": "isolation_push_triceps_isolation",
        "variation_tags": ["overhead", "stretch", "unilateral"],
    },

    # ─── TIER 2: Rear Delt Variety ───
    {
        "id": "dumbbell_prone_y_raise",
        "name": "Dumbbell Prone Y-Raise",
        "equipment_tier": 2,
        "exercise_type": "isolation",
        "movement_pattern": "isolation_pull",
        "muscle_activations": [
            {"muscle": "rear_delts", "role": "primary", "volume_credit": 1.0},
            {"muscle": "upper_back", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "traps", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 12, "max_reps": 20,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": False,
        "difficulty": 1, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 8.5,
        "cues": ["Lie face down on incline bench", "Light DBs, thumbs up", "Raise arms in Y shape", "Squeeze at top for 1 second"],
        "common_mistakes": ["Too heavy", "Shrugging up instead of pulling back"],
        "rotation_group": "isolation_pull_rear_delts_isolation",
        "variation_tags": ["prone", "y_raise", "dumbbell"],
    },

    # ─── TIER 3: Hamstring Variety ───
    {
        "id": "band_leg_curl",
        "name": "Band Leg Curl",
        "equipment_tier": 3,
        "exercise_type": "isolation",
        "movement_pattern": "isolation_pull",
        "muscle_activations": [
            {"muscle": "hamstrings", "role": "primary", "volume_credit": 1.0},
        ],
        "min_reps": 10, "max_reps": 20,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": False,
        "difficulty": 1, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 8.0,
        "cues": ["Anchor band to rack low", "Lie face down, band around ankles", "Curl heels to glutes", "Squeeze hamstrings at top"],
        "common_mistakes": ["Using momentum", "Not anchoring band securely"],
        "rotation_group": "isolation_pull_hamstrings_isolation",
        "variation_tags": ["band", "knee_flexion"],
    },
    {
        "id": "band_good_morning",
        "name": "Band Good Morning",
        "equipment_tier": 3,
        "exercise_type": "light_compound",
        "movement_pattern": "hip_hinge",
        "muscle_activations": [
            {"muscle": "hamstrings", "role": "primary", "volume_credit": 1.0},
            {"muscle": "glutes", "role": "primary", "volume_credit": 1.0},
            {"muscle": "erectors", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 10, "max_reps": 20,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": False,
        "difficulty": 1, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 7.5,
        "cues": ["Step on band, loop around neck/shoulders", "Hinge at hips", "Feel stretch in hamstrings", "Drive hips forward to stand"],
        "common_mistakes": ["Rounding lower back", "Bending knees too much"],
        "rotation_group": "hip_hinge_glutes_hamstrings_light_compound",
        "variation_tags": ["band", "good_morning"],
    },

    # ─── TIER 3: Glute Variety ───
    {
        "id": "band_hip_abduction",
        "name": "Band Hip Abduction",
        "equipment_tier": 3,
        "exercise_type": "isolation",
        "movement_pattern": "isolation_push",
        "muscle_activations": [
            {"muscle": "glutes", "role": "primary", "volume_credit": 1.0},
        ],
        "min_reps": 12, "max_reps": 25,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": False,
        "difficulty": 1, "requires_proficiency": False, "bilateral": False,
        "sfr_rating": 8.5,
        "cues": ["Band above knees", "Stand or lie on side", "Push knees apart against band", "Squeeze glutes at end range"],
        "common_mistakes": ["Moving too fast", "Not enough tension in band"],
        "rotation_group": "isolation_push_glutes_isolation",
        "variation_tags": ["band", "abduction"],
    },

    # ─── TIER 3: Pallof Press (Anti-Rotation Core) ───
    {
        "id": "band_pallof_press",
        "name": "Band Pallof Press",
        "equipment_tier": 3,
        "exercise_type": "isolation",
        "movement_pattern": "core",
        "muscle_activations": [
            {"muscle": "abs", "role": "primary", "volume_credit": 1.0},
            {"muscle": "obliques", "role": "primary", "volume_credit": 1.0},
        ],
        "min_reps": 8, "max_reps": 15,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": False,
        "difficulty": 1, "requires_proficiency": False, "bilateral": False,
        "sfr_rating": 8.0,
        "cues": ["Anchor band at chest height", "Hold at chest, press out", "Resist rotation", "Hold extended position for 1-2 seconds"],
        "common_mistakes": ["Rotating toward anchor", "Not bracing core"],
        "rotation_group": "core_abs_obliques_isolation",
        "variation_tags": ["band", "anti_rotation", "pallof"],
    },

    # ─── TIER 1: Upper Chest (CRITICAL GAP — only 1 at T1) ───
    {
        "id": "incline_push_up_feet_elevated",
        "name": "Decline Push-Up (Feet Elevated)",
        "equipment_tier": 1,
        "exercise_type": "light_compound",
        "movement_pattern": "horizontal_push",
        "muscle_activations": [
            {"muscle": "chest", "role": "primary", "volume_credit": 1.0},
            {"muscle": "upper_chest", "role": "primary", "volume_credit": 1.0},
            {"muscle": "front_delts", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "triceps", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 5, "max_reps": 25,
        "min_sets_per_session": 2, "max_sets_per_session": 5,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": False,
        "difficulty": 2, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 7.5,
        "cues": ["Feet on bench, hands on floor", "Targets upper chest due to angle", "Full range — chest to floor", "Keep core tight"],
        "common_mistakes": ["Sagging hips", "Not going deep enough", "Elbows flaring too wide"],
        "rotation_group": "horizontal_push_chest_upper_chest_light_compound",
        "variation_tags": ["decline_push", "bodyweight", "upper_chest"],
    },
    # ─── TIER 1: Barbell Good Morning handled via OVERRIDES (exists in V4) ───

    # ─── TIER 1: Barbell Wrist Curl (Forearm Isolation) ───
    {
        "id": "barbell_wrist_curl",
        "name": "Barbell Wrist Curl",
        "equipment_tier": 1,
        "exercise_type": "isolation",
        "movement_pattern": "isolation_pull",
        "muscle_activations": [
            {"muscle": "forearms", "role": "primary", "volume_credit": 1.0},
        ],
        "min_reps": 12, "max_reps": 25,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": True,
        "difficulty": 1, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 8.0,
        "cues": ["Rest forearms on bench, wrists over edge", "Curl wrists up", "Full range of motion", "Controlled reps"],
        "common_mistakes": ["Lifting forearms off bench", "Going too fast"],
        "rotation_group": "isolation_pull_forearms_isolation",
        "variation_tags": ["wrist_curl"],
    },

    # ─── POWER: Barbell Hang Clean (Tier 1) ───
    {
        "id": "barbell_hang_clean",
        "name": "Barbell Hang Clean",
        "equipment_tier": 1,
        "exercise_type": "power",
        "movement_pattern": "power_lower",
        "muscle_activations": [
            {"muscle": "glutes", "role": "primary", "volume_credit": 1.0},
            {"muscle": "hamstrings", "role": "primary", "volume_credit": 1.0},
            {"muscle": "quads", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "traps", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "upper_back", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "forearms", "role": "stabilizer", "volume_credit": 0.0},
            {"muscle": "abs", "role": "stabilizer", "volume_credit": 0.0},
        ],
        "min_reps": 1, "max_reps": 5,
        "min_sets_per_session": 3, "max_sets_per_session": 5,
        "is_axial_loading": True, "systemic_fatigue": "high", "grip_intensive": True,
        "difficulty": 5, "requires_proficiency": True, "bilateral": True,
        "sfr_rating": 4.0,
        "cues": ["Start at hang position (mid-thigh)", "Explosive hip extension", "Pull under the bar", "Catch in front rack position"],
        "common_mistakes": ["Pulling with arms instead of hips", "Not getting under the bar", "Landing on toes"],
        "rotation_group": "power_lower_glutes_hamstrings_power",
        "variation_tags": ["olympic", "explosive", "hang"],
    },
    {
        "id": "barbell_power_clean",
        "name": "Barbell Power Clean",
        "equipment_tier": 1,
        "exercise_type": "power",
        "movement_pattern": "power_lower",
        "muscle_activations": [
            {"muscle": "glutes", "role": "primary", "volume_credit": 1.0},
            {"muscle": "hamstrings", "role": "primary", "volume_credit": 1.0},
            {"muscle": "quads", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "traps", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "upper_back", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "erectors", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "forearms", "role": "stabilizer", "volume_credit": 0.0},
            {"muscle": "abs", "role": "stabilizer", "volume_credit": 0.0},
        ],
        "min_reps": 1, "max_reps": 5,
        "min_sets_per_session": 3, "max_sets_per_session": 5,
        "is_axial_loading": True, "systemic_fatigue": "high", "grip_intensive": True,
        "difficulty": 5, "requires_proficiency": True, "bilateral": True,
        "sfr_rating": 3.5,
        "cues": ["Start from the floor", "First pull: push floor away", "Second pull: explosive hip extension", "Catch in quarter squat front rack"],
        "common_mistakes": ["Pulling early with arms", "Rounding back off floor", "Not catching properly"],
        "rotation_group": "power_lower_glutes_hamstrings_power",
        "variation_tags": ["olympic", "explosive", "from_floor"],
    },

    # ─── POWER: Dumbbell Snatch (Tier 2) ───
    {
        "id": "dumbbell_snatch",
        "name": "Dumbbell Snatch",
        "equipment_tier": 2,
        "exercise_type": "power",
        "movement_pattern": "power_lower",
        "muscle_activations": [
            {"muscle": "glutes", "role": "primary", "volume_credit": 1.0},
            {"muscle": "hamstrings", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "quads", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "traps", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "front_delts", "role": "secondary", "volume_credit": 0.5},
            {"muscle": "abs", "role": "stabilizer", "volume_credit": 0.0},
        ],
        "min_reps": 1, "max_reps": 5,
        "min_sets_per_session": 3, "max_sets_per_session": 5,
        "is_axial_loading": False, "systemic_fatigue": "high", "grip_intensive": True,
        "difficulty": 4, "requires_proficiency": True, "bilateral": False,
        "sfr_rating": 5.0,
        "cues": ["DB between legs, hinge position", "Explosive hip drive", "Pull DB overhead in one motion", "Lock out overhead"],
        "common_mistakes": ["Pressing instead of pulling", "Not using hips"],
        "rotation_group": "power_lower_glutes_power",
        "variation_tags": ["dumbbell", "unilateral", "explosive"],
    },

    # ─── TIER 2: Dumbbell Fly (Chest Isolation Stretch) ───
    {
        "id": "dumbbell_fly",
        "name": "Dumbbell Fly (Flat)",
        "equipment_tier": 2,
        "exercise_type": "isolation",
        "movement_pattern": "isolation_push",
        "muscle_activations": [
            {"muscle": "chest", "role": "primary", "volume_credit": 1.0},
            {"muscle": "front_delts", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 8, "max_reps": 15,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": False,
        "difficulty": 2, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 8.0,
        "cues": ["Slight bend in elbows throughout", "Lower in an arc, feel the stretch", "Squeeze chest at top", "Don't go too deep (shoulder safety)"],
        "common_mistakes": ["Straightening arms (turns into press)", "Going too deep", "Losing control"],
        "rotation_group": "isolation_push_chest_isolation",
        "variation_tags": ["fly", "stretch"],
    },
    {
        "id": "dumbbell_incline_fly",
        "name": "Dumbbell Incline Fly",
        "equipment_tier": 2,
        "exercise_type": "isolation",
        "movement_pattern": "isolation_push",
        "muscle_activations": [
            {"muscle": "chest", "role": "primary", "volume_credit": 1.0},
            {"muscle": "upper_chest", "role": "primary", "volume_credit": 1.0},
            {"muscle": "front_delts", "role": "secondary", "volume_credit": 0.5},
        ],
        "min_reps": 8, "max_reps": 15,
        "min_sets_per_session": 2, "max_sets_per_session": 4,
        "is_axial_loading": False, "systemic_fatigue": "low", "grip_intensive": False,
        "difficulty": 2, "requires_proficiency": False, "bilateral": True,
        "sfr_rating": 8.0,
        "cues": ["Set bench to 30-45 degrees", "Arc pattern, slight elbow bend", "Great upper chest stretch", "Control the weight"],
        "common_mistakes": ["Bench too steep", "Pressing instead of flying"],
        "rotation_group": "isolation_push_chest_isolation",
        "variation_tags": ["fly", "incline", "stretch"],
    },
]


# ──────────────────────────────────────────────
# MAIN: BUILD THE COMPLETE V5 LIBRARY
# ──────────────────────────────────────────────

def main():
    with open("/mnt/user-data/uploads/exercise_library.json") as f:
        v4_data = json.load(f)
    
    print(f"Loaded {len(v4_data)} V4 exercises")
    
    # Convert all V4 exercises
    v5_exercises = []
    for ex in v4_data:
        v5 = convert_exercise(ex)
        
        # Apply overrides
        if ex["id"] in OVERRIDES:
            for key, value in OVERRIDES[ex["id"]].items():
                if key == "muscle_activations_override":
                    v5["muscle_activations"] = value
                else:
                    v5[key] = value
                    # Recalculate rotation_group if type or pattern changed
                    if key in ("exercise_type", "movement_pattern"):
                        v5["rotation_group"] = derive_rotation_group(
                            ex, v5["exercise_type"], v5["movement_pattern"]
                        )
        
        v5_exercises.append(v5)
    
    print(f"Converted {len(v5_exercises)} exercises to V5 format")
    
    # Add new exercises
    for new_ex in NEW_EXERCISES:
        # Check for ID collisions
        existing_ids = {e["id"] for e in v5_exercises}
        if new_ex["id"] in existing_ids:
            print(f"  WARNING: Skipping duplicate ID: {new_ex['id']}")
            continue
        v5_exercises.append(new_ex)
    
    print(f"Added {len(NEW_EXERCISES)} new exercises")
    print(f"Total V5 library: {len(v5_exercises)} exercises")
    
    # Output as JSON
    with open("/home/claude/exercise_library_v5.json", "w") as f:
        json.dump(v5_exercises, f, indent=2)
    
    print("\nSaved to exercise_library_v5.json")
    
    return v5_exercises

exercises = main()
