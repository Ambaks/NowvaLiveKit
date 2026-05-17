"""
Anthropometry persistence and ROM accessor utilities.

Persists user body measurements (derived from bone-length calibration) to a
local JSON file at data/anthropometry.json. Provides accessors for ROM peaks
stored in UserCalibration.peaks JSONB.

Canonical ROM names (maps to UserCalibration.peaks keys):
    trunk_flexion       — peak trunk flexion angle (degrees, 180-convention)
    hip_adduction       — average peak hip adduction per rep (degrees)
    asymmetry           — peak bilateral asymmetry (degrees)
    dorsiflexion_drop   — peak dorsiflexion drop from baseline (degrees)
    avg_depth           — average peak knee flexion across reps (degrees)
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ANTHROPOMETRY_FILE = Path(__file__).parent.parent.parent / "data" / "anthropometry.json"

# Keys stored in UserCalibration.peaks (canonical ROM names)
ROM_KEYS = [
    "trunk_flexion",
    "hip_adduction",
    "asymmetry",
    "dorsiflexion_drop",
    "avg_depth",
]


def save_anthropometry_to_file(bone_constraints) -> Optional[Path]:
    """Persist anthropometry from a calibrated BoneLengthConstraints to JSON.

    Only writes if bone calibration completed. If a file already exists,
    overwrites only when the new calibration_quality_score is higher.

    Returns the file path on success, None otherwise.
    """
    from biomechanics.utils.types import CocoKeypoints as CK

    proportions = bone_constraints.body_proportions
    if proportions is None:
        logger.info("[ANTHROPOMETRY] Bone calibration not complete — skipping save")
        return None

    calibrated_lengths = bone_constraints._calibrated_lengths

    shoulder_width = calibrated_lengths.get(
        (CK.LEFT_SHOULDER, CK.RIGHT_SHOULDER), 0.0
    )
    femur_length_avg = proportions.femur_length_avg
    tibia_length_avg = proportions.tibia_length_avg
    torso_length = proportions.torso_length_avg
    hip_width = proportions.hip_width

    femur_tibia_ratio = femur_length_avg / max(tibia_length_avg, 0.01)
    femur_torso_ratio = femur_length_avg / max(torso_length, 0.01)

    calibration_quality_score = _compute_quality_score(bone_constraints)

    new_data = {
        "femur_length_avg": round(femur_length_avg, 4),
        "tibia_length_avg": round(tibia_length_avg, 4),
        "torso_length": round(torso_length, 4),
        "hip_width": round(hip_width, 4),
        "shoulder_width": round(shoulder_width, 4),
        "femur_tibia_ratio": round(femur_tibia_ratio, 4),
        "femur_torso_ratio": round(femur_torso_ratio, 4),
        "calibration_quality_score": round(calibration_quality_score, 4),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    # Only overwrite if new quality is higher
    if ANTHROPOMETRY_FILE.exists():
        try:
            existing = json.loads(ANTHROPOMETRY_FILE.read_text())
            existing_score = existing.get("calibration_quality_score", 0.0)
            if calibration_quality_score <= existing_score:
                logger.info(
                    "[ANTHROPOMETRY] Existing score %.3f >= new %.3f — keeping existing",
                    existing_score,
                    calibration_quality_score,
                )
                return ANTHROPOMETRY_FILE
        except (json.JSONDecodeError, KeyError):
            pass

    ANTHROPOMETRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    ANTHROPOMETRY_FILE.write_text(json.dumps(new_data, indent=2))
    logger.info("[ANTHROPOMETRY] Saved to %s (score=%.3f)", ANTHROPOMETRY_FILE, calibration_quality_score)
    print(f"  Anthropometry saved → {ANTHROPOMETRY_FILE} (quality={calibration_quality_score:.3f})")
    return ANTHROPOMETRY_FILE


def _compute_quality_score(bone_constraints) -> float:
    """Compute calibration quality from 0 to 1.

    Based on:
      - fraction of bone pairs that got observations (coverage)
      - low coefficient of variation across observations (consistency)
    """
    from biomechanics.utils.bone_constraints import BONE_PAIRS

    total_pairs = len(BONE_PAIRS)
    pairs_with_data = sum(
        1 for pair in BONE_PAIRS
        if bone_constraints._calibrated_lengths.get(pair, 0.0) > 0.0
    )
    coverage = pairs_with_data / max(total_pairs, 1)

    # Coverage alone gives a 0-1 score; full coverage = 1.0
    return float(min(coverage, 1.0))


def get_anthropometry() -> Optional[dict]:
    """Load anthropometry from local file. Returns None if not yet calibrated."""
    if not ANTHROPOMETRY_FILE.exists():
        return None
    try:
        return json.loads(ANTHROPOMETRY_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def get_user_rom(joint_name: str) -> Optional[float]:
    """Get a single ROM value by canonical name from the latest calibration.

    Canonical names: trunk_flexion, hip_adduction, asymmetry,
    dorsiflexion_drop, avg_depth.

    Returns None if no calibration exists or key not found.
    """
    peaks = _load_latest_peaks()
    if peaks is None:
        return None
    return peaks.get(joint_name)


def get_user_rom_full() -> dict[str, float]:
    """Get all ROM values from the latest calibration.

    Returns empty dict if no calibration exists.
    """
    peaks = _load_latest_peaks()
    if peaks is None:
        return {}
    return {key: peaks[key] for key in ROM_KEYS if key in peaks}


def _load_latest_peaks() -> Optional[dict]:
    """Load peaks from the most recent calibration profile JSON in recordings/."""
    recordings_dir = Path(__file__).parent.parent.parent / "recordings"
    if not recordings_dir.exists():
        return None

    calibration_files = sorted(
        recordings_dir.glob("**/calibration_profile.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not calibration_files:
        return None

    try:
        data = json.loads(calibration_files[0].read_text())
        return data.get("peaks")
    except (json.JSONDecodeError, OSError):
        return None
