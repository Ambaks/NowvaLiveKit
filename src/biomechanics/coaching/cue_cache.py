"""
Cue Cache for Real-Time Coaching

Manages exercise-specific audio cue lookups with rate-limiting to prevent
overwhelming the lifter. Cues are pre-cached per exercise so the voice agent
can pre-generate TTS and play them with minimal latency on fault detection.
"""

import random
from typing import Dict, Optional

from biomechanics.config import CoachingConfig


# =============================================================================
# CUE DICTIONARIES
# =============================================================================

def _build_cues(**named_cues: str) -> Dict[str, str]:
    """Build a cue dict with named cues + rep_1..rep_20."""
    cues = {k: k for k in named_cues}
    for i in range(1, 21):
        cues[f"rep_{i}"] = f"rep_{i}"
    return cues


SQUAT_CUES: Dict[str, str] = _build_cues(
    # Corrections
    knees_out="knees_out",
    chest_up="chest_up",
    deeper="deeper",
    heels_down="heels_down",
    even_it_out="even_it_out",
    slow_down="slow_down",
    brace="brace",
    # Positive reinforcement
    good_rep="good_rep",
    great_depth="great_depth",
    strong="strong",
    clean="clean",
    perfect="perfect",
)

DEADLIFT_CUES: Dict[str, str] = _build_cues(
    # Corrections
    hips_through="hips_through",
    flat_back="flat_back",
    chest_up="chest_up",
    lockout="lockout",
    slow_down="slow_down",
    # Positive reinforcement
    good_rep="good_rep",
    strong="strong",
)

DEFAULT_CUES: Dict[str, str] = _build_cues(
    good_rep="good_rep",
    chest_up="chest_up",
    brace="brace",
    slow_down="slow_down",
    strong="strong",
)

EXERCISE_CUE_MAP: Dict[str, Dict[str, str]] = {
    "squat": SQUAT_CUES,
    "back_squat": SQUAT_CUES,
    "front_squat": SQUAT_CUES,
    "goblet_squat": SQUAT_CUES,
    "deadlift": DEADLIFT_CUES,
    "romanian_deadlift": DEADLIFT_CUES,
    "sumo_deadlift": DEADLIFT_CUES,
}

FAULT_TO_CUE_MAP: Dict[str, str] = {
    "knee_valgus": "knees_out",
    "forward_lean": "chest_up",
    "depth": "deeper",
    "heel_rise": "heels_down",
    "bilateral_asymmetry": "even_it_out",
    "back_rounding": "chest_up",
}

POSITIVE_CUE_KEYS = frozenset({"good_rep", "great_depth", "strong", "clean", "perfect"})


# =============================================================================
# CUE CACHE
# =============================================================================

class CueCache:
    """
    Manages audio cue lookups with rate-limiting.

    Prepares exercise-specific cues and provides fault-to-cue mapping
    with a minimum gap between cues to avoid overwhelming the lifter.
    """

    def __init__(self, config: Optional[CoachingConfig] = None):
        config = config or CoachingConfig()
        self.current_exercise: Optional[str] = None
        self.cues: Dict[str, str] = {}
        self.last_cue_time: float = 0.0
        self.min_cue_gap: float = config.min_cue_gap_seconds

    def prepare_for_exercise(self, exercise_name: str) -> Dict[str, str]:
        """
        Load cues for an exercise. Returns the cue dict for IPC transmission.

        Args:
            exercise_name: Exercise name (e.g. "Barbell Back Squat")

        Returns:
            Dict mapping cue keys to cue identifiers
        """
        normalized = exercise_name.lower().replace(" ", "_")
        self.current_exercise = normalized
        self.cues = dict(EXERCISE_CUE_MAP.get(normalized, DEFAULT_CUES))
        self.last_cue_time = 0.0
        return dict(self.cues)

    def get_cue_for_fault(self, fault_type: str, timestamp: float) -> Optional[str]:
        """
        Get a cue key for a detected fault, respecting rate limiting.

        Args:
            fault_type: The fault type string (e.g. "knee_valgus")
            timestamp: Current time in seconds

        Returns:
            Cue key string if available and not rate-limited, else None
        """
        if timestamp - self.last_cue_time < self.min_cue_gap:
            return None

        cue_key = FAULT_TO_CUE_MAP.get(fault_type)
        if cue_key is None or cue_key not in self.cues:
            return None

        self.last_cue_time = timestamp
        return cue_key

    def get_rep_cue(self, rep_number: int) -> Optional[str]:
        """Get the cue key for a rep count callout."""
        key = f"rep_{rep_number}"
        return key if key in self.cues else None

    def get_positive_cue(self) -> Optional[str]:
        """Get a random positive reinforcement cue key."""
        available = [k for k in self.cues if k in POSITIVE_CUE_KEYS]
        return random.choice(available) if available else None
