"""Geometric keypoint corrections for diagnosed squat faults.

Applies tier-1 (cue-correctable) fixes directly in 19-keypoint space,
replicating the same math as the viewer's bottomUpBuild, solveKnee,
and applyCounterbalance JS functions.

Joint indices (COCO 19-keypoint):
    0=nose, 1=L_eye, 2=R_eye, 3=L_ear, 4=R_ear,
    5=L_shoulder, 6=R_shoulder, 7=L_elbow, 8=R_elbow,
    9=L_wrist, 10=R_wrist, 11=L_hip, 12=R_hip,
    13=L_knee, 14=R_knee, 15=L_ankle, 16=R_ankle,
    17=L_foot_index, 18=R_foot_index
"""

from __future__ import annotations

import math

import numpy as np

from .types import DiagnosisResult

UPPER_BODY_INDICES = list(range(0, 11))
HIP_L, HIP_R = 11, 12
KNEE_L, KNEE_R = 13, 14
ANKLE_L, ANKLE_R = 15, 16
FOOT_L, FOOT_R = 17, 18


def solve_knee(
    hip: np.ndarray,
    ankle: np.ndarray,
    thigh_length: float,
    shin_length: float,
    ref_knee: np.ndarray,
) -> np.ndarray:
    """2-link IK: find knee position satisfying bone length constraints.

    Python port of the viewer's solveKnee JS function. Given fixed hip
    and ankle, returns the knee position where |hip-knee| == thigh_length
    and |knee-ankle| == shin_length. ref_knee disambiguates the bend plane.
    """
    ha_vec = ankle - hip
    distance = np.linalg.norm(ha_vec)
    if distance < 1e-9:
        distance = 1e-9
    unit_ha = ha_vec / distance

    distance_min = abs(thigh_length - shin_length) + 1e-4
    distance_max = thigh_length + shin_length - 1e-4
    distance_clamped = max(distance_min, min(distance_max, distance))

    cos_angle = (thigh_length**2 + distance_clamped**2 - shin_length**2) / (
        2.0 * thigh_length * distance_clamped
    )
    cos_angle = max(-1.0, min(1.0, cos_angle))
    sin_angle = math.sin(math.acos(cos_angle))

    pole = ref_knee - hip
    dot_proj = np.dot(pole, unit_ha)
    pole = pole - dot_proj * unit_ha
    pole_length = np.linalg.norm(pole)

    if pole_length < 1e-6:
        pole = np.array([-unit_ha[0] * unit_ha[1],
                         1.0 - unit_ha[1]**2,
                         -unit_ha[2] * unit_ha[1]])
        pole_length = np.linalg.norm(pole)
        if pole_length < 1e-9:
            pole_length = 1e-9
    pole = pole / pole_length

    return hip + thigh_length * cos_angle * unit_ha + thigh_length * sin_angle * pole


def rotate_y(vec: np.ndarray, angle_rad: float) -> np.ndarray:
    """Rotate a 3D vector about the Y axis."""
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    return np.array([
        cos_a * vec[0] + sin_a * vec[2],
        vec[1],
        -sin_a * vec[0] + cos_a * vec[2],
    ])


class KeypointCorrector:
    """Applies geometric corrections to 19 keypoints based on diagnosis."""

    def correct(
        self,
        observed_kpts: list[list[float]],
        diagnosis: DiagnosisResult,
    ) -> list[list[float]] | None:
        """Apply tier-1 corrections. Returns corrected kpts or None if no fixes needed."""
        tier1_causes = {
            cause.cause_id: cause
            for cause in diagnosis.immediate_causes
        }

        if not tier1_causes:
            return None

        kpts = np.array(observed_kpts, dtype=float)

        original_thigh_l = np.linalg.norm(kpts[KNEE_L] - kpts[HIP_L])
        original_shin_l = np.linalg.norm(kpts[ANKLE_L] - kpts[KNEE_L])
        original_thigh_r = np.linalg.norm(kpts[KNEE_R] - kpts[HIP_R])
        original_shin_r = np.linalg.norm(kpts[ANKLE_R] - kpts[KNEE_R])

        if "narrow_stance" in tier1_causes:
            self._widen_stance(kpts, tier1_causes["narrow_stance"])

        if "narrow_foot_angle" in tier1_causes:
            self._increase_toe_out(kpts, tier1_causes["narrow_foot_angle"])

        if "knee_track_cue" in tier1_causes:
            self._push_knees_out(kpts, tier1_causes["knee_track_cue"])

        if "weight_shift_cue" in tier1_causes:
            self._center_weight(kpts, tier1_causes["weight_shift_cue"])

        if "bracing_failure" in tier1_causes:
            self._reduce_trunk_lean(kpts, tier1_causes["bracing_failure"])

        self._enforce_bone_lengths(
            kpts, original_thigh_l, original_shin_l,
            original_thigh_r, original_shin_r,
        )
        self._reground(kpts)

        return kpts.tolist()

    def _widen_stance(self, kpts: np.ndarray, cause) -> None:
        """Scale ankle distance about ankle midpoint."""
        delta = cause.parameter_delta or {}
        foot_delta = delta.get("__foot_target_delta")
        if not foot_delta:
            return

        ankle_mid = (kpts[ANKLE_L] + kpts[ANKLE_R]) / 2.0

        shift_l = np.array([foot_delta[0], foot_delta[1], foot_delta[2]])
        shift_r = np.array([foot_delta[3], foot_delta[4], foot_delta[5]])

        kpts[ANKLE_L] += shift_l
        kpts[ANKLE_R] += shift_r
        kpts[FOOT_L] += shift_l
        kpts[FOOT_R] += shift_r

    def _increase_toe_out(self, kpts: np.ndarray, cause) -> None:
        """Rotate foot vectors about ankle Y-axis."""
        delta = cause.parameter_delta or {}
        delta_l_rad = delta.get("L_ankle.ry", 0.0)
        delta_r_rad = delta.get("R_ankle.ry", 0.0)

        if abs(delta_l_rad) > 1e-6:
            foot_vec = kpts[FOOT_L] - kpts[ANKLE_L]
            kpts[FOOT_L] = kpts[ANKLE_L] + rotate_y(foot_vec, delta_l_rad)

        if abs(delta_r_rad) > 1e-6:
            foot_vec = kpts[FOOT_R] - kpts[ANKLE_R]
            kpts[FOOT_R] = kpts[ANKLE_R] + rotate_y(foot_vec, delta_r_rad)

    def _push_knees_out(self, kpts: np.ndarray, cause) -> None:
        """Nudge knees laterally along the hip-lateral axis."""
        delta = cause.parameter_delta or {}
        delta_l_rad = abs(delta.get("L_hip.ry", 0.0))
        delta_r_rad = abs(delta.get("R_hip.ry", 0.0))

        hip_lateral = kpts[HIP_R] - kpts[HIP_L]
        hip_lateral[1] = 0.0
        hip_lat_norm = np.linalg.norm(hip_lateral)
        if hip_lat_norm < 1e-6:
            return
        hip_lateral_unit = hip_lateral / hip_lat_norm

        thigh_l = np.linalg.norm(kpts[KNEE_L] - kpts[HIP_L])
        nudge_l = thigh_l * math.sin(delta_l_rad)
        kpts[KNEE_L] -= hip_lateral_unit * nudge_l

        thigh_r = np.linalg.norm(kpts[KNEE_R] - kpts[HIP_R])
        nudge_r = thigh_r * math.sin(delta_r_rad)
        kpts[KNEE_R] += hip_lateral_unit * nudge_r

    def _center_weight(self, kpts: np.ndarray, cause) -> None:
        """Shift pelvis + upper body laterally."""
        delta = cause.parameter_delta or {}
        shift_x = delta.get("pelvis.tx", 0.0)
        if abs(shift_x) < 1e-6:
            return

        shift_vec = np.array([0.0, 0.0, shift_x])

        for idx in UPPER_BODY_INDICES + [HIP_L, HIP_R]:
            kpts[idx] += shift_vec

    def _reduce_trunk_lean(self, kpts: np.ndarray, cause) -> None:
        """Rotate upper body about hip midpoint in the sagittal plane.

        Same math as applyCounterbalance in the viewer JS.
        """
        delta = cause.parameter_delta or {}
        lean_delta_rad = delta.get("trunk.rx", 0.0)
        if abs(lean_delta_rad) < 1e-6:
            return

        hip_mid = (kpts[HIP_L] + kpts[HIP_R]) / 2.0
        shoulder_mid = (kpts[5] + kpts[6]) / 2.0

        trunk_dx = shoulder_mid[0] - hip_mid[0]
        trunk_dy = shoulder_mid[1] - hip_mid[1]
        torso_length = math.sqrt(trunk_dx**2 + trunk_dy**2)
        if torso_length < 1e-6:
            return

        current_lean = math.atan2(trunk_dx, trunk_dy)
        new_lean = current_lean + lean_delta_rad

        new_shoulder_mid_x = hip_mid[0] + torso_length * math.sin(new_lean)
        new_shoulder_mid_y = hip_mid[1] + torso_length * math.cos(new_lean)

        offset_x = new_shoulder_mid_x - shoulder_mid[0]
        offset_y = new_shoulder_mid_y - shoulder_mid[1]

        for idx in UPPER_BODY_INDICES:
            kpts[idx][0] += offset_x
            kpts[idx][1] += offset_y

    def _enforce_bone_lengths(
        self,
        kpts: np.ndarray,
        thigh_l: float,
        shin_l: float,
        thigh_r: float,
        shin_r: float,
    ) -> None:
        """Re-solve knees to maintain original bone lengths."""
        kpts[KNEE_L] = solve_knee(
            kpts[HIP_L], kpts[ANKLE_L], thigh_l, shin_l, kpts[KNEE_L],
        )
        kpts[KNEE_R] = solve_knee(
            kpts[HIP_R], kpts[ANKLE_R], thigh_r, shin_r, kpts[KNEE_R],
        )

    def _reground(self, kpts: np.ndarray) -> None:
        """Ensure ankles don't go below ground (Y=0 in viewer coords)."""
        min_ankle_y = min(kpts[ANKLE_L][1], kpts[ANKLE_R][1])
        if min_ankle_y < 0:
            for idx in range(HIP_L, FOOT_R + 1):
                kpts[idx][1] -= min_ankle_y


def build_morph_frames(
    observed_kpts: list[list[float]],
    corrected_kpts: list[list[float]],
    num_frames: int = 60,
) -> list[list[list[float]]]:
    """Generate morph frames using Gaussian-tapered interpolation.

    Frame 0 ≈ observed, midpoint ≈ corrected, frame N-1 ≈ observed.
    Creates a smooth breathing/pulsing animation.
    """
    observed = np.array(observed_kpts)
    corrected = np.array(corrected_kpts)

    sigma = num_frames / 5.0
    mid = num_frames / 2.0

    frames = []
    for frame_index in range(num_frames):
        weight = math.exp(-((frame_index - mid) ** 2) / (2.0 * sigma**2))
        interpolated = observed + weight * (corrected - observed)
        frames.append(interpolated.tolist())

    return frames
