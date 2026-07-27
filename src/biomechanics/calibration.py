"""
Biomechanical Calibration Module

Provides reusable calibration logic for personalizing fault detection thresholds
based on a user's own movement data (e.g., 5 bodyweight squats).

Extracted from test_calibrated_workout.py for production use.
"""

from typing import Dict, Optional

from biomechanics.faults.rules.knee_valgus import KneeValgusRule
from biomechanics.faults.rules.forward_lean import ForwardLeanRule
from biomechanics.faults.rules.symmetry import SymmetryRule
from biomechanics.faults.rules.heel_rise import HeelRiseRule
from biomechanics.faults.rules.depth import DepthRule


# ---------------------------------------------------------------------------
# Exercise -> Movement Pattern mapping
# ---------------------------------------------------------------------------

EXERCISE_TO_MOVEMENT_PATTERN: Dict[str, str] = {
    # Squat variants
    "Barbell Back Squat": "squat",
    "Barbell Front Squat": "squat",
    "Goblet Squat": "squat",
    # Hip hinge variants (future)
    "Barbell Deadlift": "hip_hinge",
    "Romanian Deadlift": "hip_hinge",
    "Sumo Deadlift": "hip_hinge",
    # Push variants (future)
    "Barbell Bench Press": "horizontal_push",
    "Barbell Overhead Press": "vertical_push",
}


def get_movement_pattern(exercise_name: str) -> Optional[str]:
    """Return the movement pattern for an exercise, or None if not mapped."""
    return EXERCISE_TO_MOVEMENT_PATTERN.get(exercise_name)


# ---------------------------------------------------------------------------
# Calibration profile building
# ---------------------------------------------------------------------------

def build_calibration_profile(peaks: dict, config=None) -> dict:
    """Build threshold profile from calibration peaks.

    Args:
        peaks: Dict with keys: trunk_flexion, hip_adduction, asymmetry, dorsiflexion_drop
        config: Optional pipeline config. If provided, defaults are included.

    Returns:
        Dict mapping fault_type -> threshold values.
    """
    profile = {
        "knee_valgus": {
            "mild": peaks["hip_adduction"] + 5.0,
            "moderate": peaks["hip_adduction"] + 10.0,
            "severe": peaks["hip_adduction"] + 15.0,
        },
        "forward_lean": {
            "mild": peaks["trunk_flexion"] - 10.0,
            "moderate": peaks["trunk_flexion"] - 15.0,
            "severe": peaks["trunk_flexion"] - 20.0,
        },
        "bilateral_asymmetry": {
            "mild": peaks["asymmetry"] + 5.0,
            "moderate": peaks["asymmetry"] + 10.0,
            "severe": peaks["asymmetry"] + 15.0,
        },
        "heel_rise": {
            "threshold_degrees": peaks["dorsiflexion_drop"] + 20.0,
        },
        "depth": {
            "parallel_threshold": peaks.get("avg_depth", 0.0) - 10.0,
            "half_threshold": peaks.get("avg_depth", 0.0) - 25.0,
            "quarter_threshold": peaks.get("avg_depth", 0.0) - 55.0,
        },
    }

    if config is not None:
        faults_cfg = config.faults
        profile["defaults"] = {
            "knee_valgus": {
                "mild": faults_cfg.knee_valgus.mild,
                "moderate": faults_cfg.knee_valgus.moderate,
                "severe": faults_cfg.knee_valgus.severe,
            },
            "forward_lean": {
                "mild": faults_cfg.forward_lean.mild,
                "moderate": faults_cfg.forward_lean.moderate,
                "severe": faults_cfg.forward_lean.severe,
            },
            "bilateral_asymmetry": {
                "mild": faults_cfg.bilateral_asymmetry.mild,
                "moderate": faults_cfg.bilateral_asymmetry.moderate,
                "severe": faults_cfg.bilateral_asymmetry.severe,
            },
            "heel_rise": {
                "threshold_degrees": faults_cfg.heel_rise.threshold_deg,
            },
            "depth": {
                "quarter_threshold": 60.0,
                "half_threshold": faults_cfg.depth.parallel,
                "parallel_threshold": faults_cfg.depth.below_parallel,
            },
        }

    return profile


def apply_calibration_to_rule_engine(rule_engine, profile: dict):
    """Directly set rule engine thresholds from a calibration profile.

    Also marks the rule engine as calibrated to prevent the built-in
    1-rep auto-calibration from overwriting these values.
    """
    for rule in rule_engine.rules:
        if isinstance(rule, KneeValgusRule):
            p = profile["knee_valgus"]
            rule.mild_threshold = p["mild"]
            rule.moderate_threshold = p["moderate"]
            rule.severe_threshold = p["severe"]
        elif isinstance(rule, ForwardLeanRule):
            p = profile["forward_lean"]
            rule.mild_threshold = p["mild"]
            rule.moderate_threshold = p["moderate"]
            rule.severe_threshold = p["severe"]
        elif isinstance(rule, SymmetryRule):
            p = profile["bilateral_asymmetry"]
            rule.mild_threshold = p["mild"]
            rule.moderate_threshold = p["moderate"]
            rule.severe_threshold = p["severe"]
        elif isinstance(rule, HeelRiseRule):
            rule.threshold_degrees = profile["heel_rise"]["threshold_degrees"]
        elif isinstance(rule, DepthRule):
            if "depth" in profile:
                p = profile["depth"]
                rule.quarter_threshold = p["quarter_threshold"]
                rule.half_threshold = p["half_threshold"]
                rule.parallel_threshold = p["parallel_threshold"]

    rule_engine._calibrated = True


def extract_thresholds_from_rule_engine(rule_engine) -> dict:
    """Read current thresholds from a rule engine for dashboard visualization."""
    thresholds = {}
    for rule in rule_engine.rules:
        if isinstance(rule, KneeValgusRule):
            thresholds["knee_valgus"] = {
                "mild": rule.mild_threshold,
                "moderate": rule.moderate_threshold,
                "severe": rule.severe_threshold,
            }
        elif isinstance(rule, ForwardLeanRule):
            thresholds["forward_lean"] = {
                "mild": rule.mild_threshold,
                "moderate": rule.moderate_threshold,
                "severe": rule.severe_threshold,
            }
        elif isinstance(rule, SymmetryRule):
            thresholds["bilateral_asymmetry"] = {
                "mild": rule.mild_threshold,
                "moderate": rule.moderate_threshold,
                "severe": rule.severe_threshold,
            }
        elif isinstance(rule, DepthRule):
            thresholds["depth"] = {
                "parallel_threshold": rule.parallel_threshold,
                "half_threshold": rule.half_threshold,
                "quarter_threshold": rule.quarter_threshold,
            }
    return thresholds


# ---------------------------------------------------------------------------
# CalibrationTracker — collects peak data during calibration reps
# ---------------------------------------------------------------------------

class CalibrationTracker:
    """Tracks peak angle values during calibration reps.

    Usage:
        tracker = CalibrationTracker(target_reps=5)
        while not tracker.is_complete:
            result = pipeline.process_frame()
            if result.joint_angles:
                tracker.record_frame(result.joint_angles)
            if result.rep_data:
                tracker.on_rep_complete(result.rep_data.max_depth_angle)
        peaks = tracker.get_peaks()
    """

    def __init__(self, target_reps: int = 5):
        self.target_reps = target_reps
        self.reps_completed = 0

        # Peak trackers (trunk uses 180-convention: track minimum = most lean)
        self.peak_trunk = 180.0
        self.rep_adduction_peaks: list = []
        self._current_rep_peak_adduction = 0.0
        self.peak_asymmetry = 0.0
        self.peak_dorsi_drop = 0.0
        self.rep_depth_peaks: list = []
        self._current_rep_peak_depth = 0.0

        # Dorsiflexion baseline (set on first frame)
        self._baseline_dorsi_l = 0.0
        self._baseline_dorsi_r = 0.0
        self._dorsi_baseline_set = False

        # Standing knee flexion (for gate widening after calibration)
        self.standing_knee_flexion = 0.0

    def record_frame(self, joint_angles, in_rep: bool = False) -> None:
        """Record a single frame's angles during calibration."""
        ja = joint_angles

        # Standing knee flexion: only track when NOT in a rep so the gate
        # threshold reflects actual standing posture, not squat depth.
        if not in_rep:
            standing_knee = max(ja.knee_flexion_l, ja.knee_flexion_r)
            self.standing_knee_flexion = max(self.standing_knee_flexion, standing_knee)

        # Peak trunk flexion (180-convention: track minimum = most lean)
        self.peak_trunk = min(self.peak_trunk, ja.trunk_flexion)

        # Per-rep peak abs(adduction)
        self._current_rep_peak_adduction = max(
            self._current_rep_peak_adduction,
            abs(ja.hip_adduction_l),
            abs(ja.hip_adduction_r),
        )

        # Per-rep peak knee flexion (depth)
        self._current_rep_peak_depth = max(
            self._current_rep_peak_depth,
            ja.avg_knee_flexion,
        )

        # Bilateral asymmetry
        self.peak_asymmetry = max(
            self.peak_asymmetry,
            ja.knee_asymmetry,
            ja.hip_asymmetry,
        )

        # Dorsiflexion drop
        if not self._dorsi_baseline_set:
            self._baseline_dorsi_l = ja.ankle_dorsiflexion_l
            self._baseline_dorsi_r = ja.ankle_dorsiflexion_r
            self._dorsi_baseline_set = True

        drop_l = self._baseline_dorsi_l - ja.ankle_dorsiflexion_l
        drop_r = self._baseline_dorsi_r - ja.ankle_dorsiflexion_r
        self.peak_dorsi_drop = max(self.peak_dorsi_drop, max(drop_l, drop_r))

    def on_rep_complete(self, depth_angle: float = 0.0) -> None:
        """Called when a rep completes during calibration."""
        self.reps_completed += 1
        self.rep_adduction_peaks.append(self._current_rep_peak_adduction)
        self._current_rep_peak_adduction = 0.0
        # Prefer self-tracked depth (from record_frame) over external depth_angle,
        # because when BiLSTM is enabled the rep counter may have already reset
        # its depth tracking by the time the BiLSTM rep event fires.
        depth = self._current_rep_peak_depth if self._current_rep_peak_depth > 0.0 else depth_angle
        if depth > 0.0:
            self.rep_depth_peaks.append(depth)
        self._current_rep_peak_depth = 0.0

    @property
    def is_complete(self) -> bool:
        return self.reps_completed >= self.target_reps

    def get_peaks(self) -> dict:
        """Build the peaks dict for profile generation."""
        avg_adduction = (
            sum(self.rep_adduction_peaks) / len(self.rep_adduction_peaks)
            if self.rep_adduction_peaks else 0.0
        )
        avg_depth = (
            sum(self.rep_depth_peaks) / len(self.rep_depth_peaks)
            if self.rep_depth_peaks else 0.0
        )
        return {
            "trunk_flexion": self.peak_trunk,
            "hip_adduction": avg_adduction,
            "hip_adduction_per_rep": self.rep_adduction_peaks,
            "asymmetry": self.peak_asymmetry,
            "dorsiflexion_drop": self.peak_dorsi_drop,
            "avg_depth": avg_depth,
            "depth_per_rep": self.rep_depth_peaks,
        }
