"""
Mode-aware knee valgus estimation.

Two estimators write the same JointAngles fields (knee_valgus in degrees,
positive = knee medial/valgus; a bilateral knee-to-ankle separation ratio) but
from different data depending on capture mode:

- SingleCameraValgusEstimator: frontal-plane projection angle (FPPA) from the
  image-plane 2D skeleton, plus an x-only knee-to-ankle separation ratio. Avoids
  the unreliable monocular depth axis entirely.
- TriangulatedValgusEstimator: true 3D knee abduction angle from a
  Grood-Suntay-style knee coordinate system (femoral medio-lateral axis vs tibial
  long axis), which is robust to hip axial rotation by construction, plus a metric
  3D separation ratio. Also exposes a hip internal-rotation estimate.
"""

from __future__ import annotations

from typing import NamedTuple, Protocol

import numpy as np

from biomechanics.utils.geometry import angle_between_vectors, normalize_vector
from biomechanics.utils.types import (
    CocoKeypoints as CK,
    Skeleton2D,
    Skeleton3D,
)

# Minimum limb-segment length (m) in 3D for a stable angle.
_MIN_SEGMENT_M = 0.05
# Minimum horizontal ankle separation (px) for a stable 2D ratio.
_MIN_ANKLE_SEP_PX = 1.0
# Minimum hip-to-ankle vertical span (px) for a stable FPPA. A near-zero span
# means a mistracked keypoint (ankle at hip height), and it sits in the
# arctan2 denominator — small values turn pixel noise into ~90 degree spikes.
_MIN_LEG_SPAN_PX = 10.0
# Minimum 3D ankle separation (m) for a stable ratio.
_MIN_ANKLE_SEP_M = 0.02
# Facing squareness (horizontal hip separation / torso length) at or above which
# single-camera valgus confidence saturates to full. Below it, confidence decays
# linearly toward zero as the subject rotates out of the frontal plane.
_FRONTAL_NOMINAL = 0.35
# Neutral separation ratio (knees exactly over ankles).
_NEUTRAL_KASR = 1.0
# Keypoint confidence floor for a usable measurement.
_MIN_CONFIDENCE = 0.1


class ValgusResult(NamedTuple):
    """Per-frame frontal/transverse knee kinematics from a valgus estimator."""
    valgus_l: float
    valgus_r: float
    foot_confidence_l: float
    foot_confidence_r: float
    kasr: float
    hip_rotation_l: float = 0.0
    hip_rotation_r: float = 0.0


class ValgusEstimator(Protocol):
    def estimate(
        self,
        skeleton_2d: Skeleton2D | None,
        skeleton_3d: Skeleton3D | None = None,
    ) -> ValgusResult:
        ...


_NEUTRAL_RESULT = ValgusResult(0.0, 0.0, 0.0, 0.0, _NEUTRAL_KASR, 0.0, 0.0)


def _xy(skeleton_2d: Skeleton2D, index: int) -> tuple[np.ndarray | None, float]:
    kp = skeleton_2d.get_keypoint(index)
    if kp is None:
        return None, 0.0
    if kp.confidence < _MIN_CONFIDENCE:
        return None, kp.confidence
    return np.array([kp.x, kp.y], dtype=np.float64), kp.confidence


def _xyz(skeleton_3d: Skeleton3D, index: int) -> tuple[np.ndarray | None, float]:
    if index >= len(skeleton_3d.keypoints):
        return None, 0.0
    pt = skeleton_3d.keypoints[index]
    if pt.confidence < _MIN_CONFIDENCE:
        return None, pt.confidence
    return np.array([pt.x, pt.y, pt.z], dtype=np.float64), pt.confidence


class SingleCameraValgusEstimator:
    """
    Frontal-plane projection angle (FPPA) from a single frontal camera.

    Works entirely in the image plane (x, y), never touching the monocular depth
    axis — the least reliable coordinate in a single-camera pose. Valgus is the
    horizontal deviation of the knee from the hip-ankle line, normalized by leg
    vertical extent (so it is robust to squat depth), signed positive when the
    knee moves medially (toward the midline between the feet).
    """

    def estimate(
        self,
        skeleton_2d: Skeleton2D | None,
        skeleton_3d: Skeleton3D | None = None,
    ) -> ValgusResult:
        if skeleton_2d is None:
            return _NEUTRAL_RESULT

        l_hip, c_lh = _xy(skeleton_2d, CK.LEFT_HIP)
        r_hip, c_rh = _xy(skeleton_2d, CK.RIGHT_HIP)
        l_knee, c_lk = _xy(skeleton_2d, CK.LEFT_KNEE)
        r_knee, c_rk = _xy(skeleton_2d, CK.RIGHT_KNEE)
        l_ankle, c_la = _xy(skeleton_2d, CK.LEFT_ANKLE)
        r_ankle, c_ra = _xy(skeleton_2d, CK.RIGHT_ANKLE)

        if l_ankle is None or r_ankle is None:
            return _NEUTRAL_RESULT
        midline_x = (l_ankle[0] + r_ankle[0]) / 2.0

        valgus_l = self._fppa(l_hip, l_knee, l_ankle, midline_x)
        valgus_r = self._fppa(r_hip, r_knee, r_ankle, midline_x)

        facing = self._facing_confidence(skeleton_2d, l_hip, r_hip)
        conf_l = min(c_lh, c_lk, c_la) * facing
        conf_r = min(c_rh, c_rk, c_ra) * facing

        kasr = self._kasr_2d(l_knee, r_knee, l_ankle, r_ankle)

        return ValgusResult(valgus_l, valgus_r, conf_l, conf_r, kasr)

    @staticmethod
    def _fppa(
        hip: np.ndarray | None,
        knee: np.ndarray | None,
        ankle: np.ndarray | None,
        midline_x: float,
    ) -> float:
        if hip is None or knee is None or ankle is None:
            return 0.0

        vertical_span = abs(ankle[1] - hip[1])
        if vertical_span < _MIN_LEG_SPAN_PX:
            return 0.0

        # Expected knee x if it tracked the hip-ankle line at the knee's height.
        # Clamp to the hip-ankle segment: a knee's y should fall between hip and
        # ankle, so a t far outside [0, 1] signals a mistracked keypoint rather
        # than real geometry — extrapolating from it would spike the angle.
        t = np.clip((knee[1] - hip[1]) / (ankle[1] - hip[1]), 0.0, 1.0)
        expected_x = hip[0] + t * (ankle[0] - hip[0])
        deviation_x = knee[0] - expected_x

        # Medial direction for this leg: toward the midline between the feet.
        medial_dir = 1.0 if midline_x >= ankle[0] else -1.0
        signed_deviation = deviation_x * medial_dir

        return float(np.degrees(np.arctan2(signed_deviation, vertical_span)))

    @staticmethod
    def _kasr_2d(
        l_knee: np.ndarray | None,
        r_knee: np.ndarray | None,
        l_ankle: np.ndarray | None,
        r_ankle: np.ndarray | None,
    ) -> float:
        if l_knee is None or r_knee is None or l_ankle is None or r_ankle is None:
            return _NEUTRAL_KASR
        knee_sep = abs(l_knee[0] - r_knee[0])
        ankle_sep = abs(l_ankle[0] - r_ankle[0])
        if ankle_sep < _MIN_ANKLE_SEP_PX:
            return _NEUTRAL_KASR
        return float(knee_sep / ankle_sep)

    @staticmethod
    def _facing_confidence(
        skeleton_2d: Skeleton2D,
        l_hip: np.ndarray | None,
        r_hip: np.ndarray | None,
    ) -> float:
        # Rotation out of the frontal plane collapses the horizontal hip
        # separation. Normalize it by torso length (rotation-stable) so the
        # measure is scale-invariant; saturate to 1.0 for any roughly frontal
        # stance, decay toward 0 only when clearly turned.
        l_sh, _ = _xy(skeleton_2d, CK.LEFT_SHOULDER)
        r_sh, _ = _xy(skeleton_2d, CK.RIGHT_SHOULDER)
        if l_hip is None or r_hip is None or l_sh is None or r_sh is None:
            return 1.0

        hip_sep_x = abs(l_hip[0] - r_hip[0])
        shoulder_mid = (l_sh + r_sh) / 2.0
        hip_mid = (l_hip + r_hip) / 2.0
        torso_len = float(np.linalg.norm(shoulder_mid - hip_mid))
        if torso_len < 1e-6:
            return 1.0

        ratio = hip_sep_x / torso_len
        return float(np.clip(ratio / _FRONTAL_NOMINAL, 0.0, 1.0))


class TriangulatedValgusEstimator:
    """
    True 3D knee abduction from triangulated (multi-camera) keypoints.

    Uses a Grood-Suntay-style knee coordinate system: the abduction/adduction
    angle is 90 degrees minus the angle between the femoral medio-lateral axis
    (pelvic ML axis made perpendicular to the femur) and the tibial long axis.
    Pure sagittal-plane knee flexion keeps the tibia perpendicular to the ML axis
    (abduction 0); knee cave tilts it, and the metric is robust to hip axial
    rotation because it is defined in the joint's own frame, not the world
    frontal plane. Positive = knee medial (valgus).
    """

    def estimate(
        self,
        skeleton_2d: Skeleton2D | None,
        skeleton_3d: Skeleton3D | None = None,
    ) -> ValgusResult:
        if skeleton_3d is None:
            return _NEUTRAL_RESULT

        l_hip, c_lh = _xyz(skeleton_3d, CK.LEFT_HIP)
        r_hip, c_rh = _xyz(skeleton_3d, CK.RIGHT_HIP)
        l_knee, c_lk = _xyz(skeleton_3d, CK.LEFT_KNEE)
        r_knee, c_rk = _xyz(skeleton_3d, CK.RIGHT_KNEE)
        l_ankle, c_la = _xyz(skeleton_3d, CK.LEFT_ANKLE)
        r_ankle, c_ra = _xyz(skeleton_3d, CK.RIGHT_ANKLE)
        l_foot, _ = _xyz(skeleton_3d, CK.LEFT_FOOT_INDEX)
        r_foot, _ = _xyz(skeleton_3d, CK.RIGHT_FOOT_INDEX)

        if l_hip is None or r_hip is None:
            return _NEUTRAL_RESULT
        ml_pelvis = normalize_vector(l_hip - r_hip)

        valgus_l = self._abduction(l_hip, l_knee, l_ankle, ml_pelvis, medial_sign=-1.0)
        valgus_r = self._abduction(r_hip, r_knee, r_ankle, ml_pelvis, medial_sign=1.0)

        hip_rot_l = self._hip_internal_rotation(l_hip, l_knee, l_ankle, l_foot, ml_pelvis)
        hip_rot_r = self._hip_internal_rotation(r_hip, r_knee, r_ankle, r_foot, ml_pelvis)

        # Valgus confidence tracks the leg keypoints (GS abduction needs no toe).
        conf_l = min(c_lh, c_lk, c_la)
        conf_r = min(c_rh, c_rk, c_ra)

        kasr = self._kasr_3d(l_knee, r_knee, l_ankle, r_ankle)

        return ValgusResult(valgus_l, valgus_r, conf_l, conf_r, kasr, hip_rot_l, hip_rot_r)

    @staticmethod
    def _abduction(
        hip: np.ndarray | None,
        knee: np.ndarray | None,
        ankle: np.ndarray | None,
        ml_pelvis: np.ndarray,
        medial_sign: float,
    ) -> float:
        if hip is None or knee is None or ankle is None:
            return 0.0

        femur = knee - hip
        tibia = ankle - knee
        if np.linalg.norm(femur) < _MIN_SEGMENT_M or np.linalg.norm(tibia) < _MIN_SEGMENT_M:
            return 0.0

        femur_axis = normalize_vector(femur)
        # Femoral medio-lateral axis: pelvic ML axis orthogonalized against the femur.
        e_ml = ml_pelvis - np.dot(ml_pelvis, femur_axis) * femur_axis
        if np.linalg.norm(e_ml) < 1e-6:
            return 0.0
        e_ml = normalize_vector(e_ml)
        e_tibia = normalize_vector(tibia)

        # Neutral flexion keeps the tibia perpendicular to the ML axis (angle 90).
        magnitude = abs(90.0 - angle_between_vectors(e_ml, e_tibia))

        # Sign: positive when the knee sits medial to the hip-ankle line.
        line = ankle - hip
        line_len_sq = float(np.dot(line, line))
        if line_len_sq < 1e-9:
            return 0.0
        proj = hip + (np.dot(knee - hip, line) / line_len_sq) * line
        deviation = knee - proj
        medial_axis = medial_sign * ml_pelvis
        sign = 1.0 if np.dot(deviation, medial_axis) >= 0 else -1.0

        return magnitude * sign

    @staticmethod
    def _hip_internal_rotation(
        hip: np.ndarray | None,
        knee: np.ndarray | None,
        ankle: np.ndarray | None,
        foot: np.ndarray | None,
        ml_pelvis: np.ndarray,
    ) -> float:
        # Transverse-plane yaw of the foot relative to the pelvis forward axis,
        # about the thigh long axis. Diagnostic only (needs real 3D depth, so it
        # is meaningful in triangulated mode). Positive = internal rotation.
        if hip is None or knee is None or ankle is None or foot is None:
            return 0.0

        thigh_axis = normalize_vector(knee - hip)
        if np.linalg.norm(thigh_axis) < 1e-6:
            return 0.0

        # Pelvis forward = ML axis crossed with the thigh (down) axis.
        forward = normalize_vector(np.cross(ml_pelvis, thigh_axis))
        foot_vec = foot - ankle
        # Project the foot and reference onto the transverse plane (normal = thigh).
        foot_t = foot_vec - np.dot(foot_vec, thigh_axis) * thigh_axis
        fwd_t = forward - np.dot(forward, thigh_axis) * thigh_axis
        if np.linalg.norm(foot_t) < 1e-6 or np.linalg.norm(fwd_t) < 1e-6:
            return 0.0
        return angle_between_vectors(fwd_t, foot_t)

    @staticmethod
    def _kasr_3d(
        l_knee: np.ndarray | None,
        r_knee: np.ndarray | None,
        l_ankle: np.ndarray | None,
        r_ankle: np.ndarray | None,
    ) -> float:
        if l_knee is None or r_knee is None or l_ankle is None or r_ankle is None:
            return _NEUTRAL_KASR
        knee_sep = float(np.linalg.norm(l_knee - r_knee))
        ankle_sep = float(np.linalg.norm(l_ankle - r_ankle))
        if ankle_sep < _MIN_ANKLE_SEP_M:
            return _NEUTRAL_KASR
        return knee_sep / ankle_sep


def build_valgus_estimator(multi_camera: bool) -> ValgusEstimator:
    """Select the valgus estimator for the active capture mode."""
    if multi_camera:
        return TriangulatedValgusEstimator()
    return SingleCameraValgusEstimator()
