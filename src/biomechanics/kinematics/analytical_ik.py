"""
Analytical Inverse Kinematics Solver.

Computes joint angles from 3D skeleton landmarks using geometric vector math.
This is a lightweight solver that doesn't require external dependencies like OpenSim.
"""

import logging
from typing import Optional
import numpy as np

from biomechanics.kinematics.base import IKSolver
from biomechanics.utils.types import Skeleton3D, JointAngles, CocoKeypoints, Point3D
from biomechanics.utils.geometry import (
    angle_between_vectors,
    midpoint,
    normalize_vector,
    project_to_plane,
    joint_angle_3_points,
    flexion_angle,
)

logger = logging.getLogger(__name__)


class AnalyticalIKSolver(IKSolver):
    """
    Analytical inverse kinematics solver using vector geometry.

    Computes joint angles directly from 3D keypoint positions without
    requiring a musculoskeletal model. This approach is fast and works
    well for common exercises like squats, lunges, and deadlifts.

    Coordinate system assumptions (MediaPipe world coordinates):
    - Y-axis points downward (gravity direction)
    - X-axis points to the subject's left
    - Z-axis points forward (toward camera)
    """

    # Minimum confidence threshold for keypoints
    MIN_CONFIDENCE = 0.1

    def __init__(self, min_confidence: float = 0.1):
        """
        Initialize analytical IK solver.

        Args:
            min_confidence: Minimum keypoint confidence to use in calculations
        """
        super().__init__()
        self.min_confidence = min_confidence
        self._initialized = True  # No initialization needed for analytical solver
        self._pelvis_tilt_coupling: float = 0.4  # Default; updated by body proportions

    def set_body_proportions(self, proportions) -> None:
        """Update pelvis tilt coupling from calibrated body proportions."""
        self._pelvis_tilt_coupling = proportions.pelvis_tilt_coupling

    def solve(self, skeleton: Skeleton3D) -> JointAngles:
        """
        Compute joint angles from a 3D skeleton.

        Args:
            skeleton: 3D skeleton with 17 COCO keypoints

        Returns:
            JointAngles with computed angles in degrees
        """
        # Extract keypoints as numpy arrays
        kpts = self._extract_keypoints(skeleton)

        # Compute all joint angles
        angles = JointAngles(
            timestamp=skeleton.timestamp,
            frame_index=skeleton.frame_index,
        )

        # Hip flexion (angle between trunk and thigh)
        angles.hip_flexion_l = self._compute_hip_flexion(kpts, side="left")
        angles.hip_flexion_r = self._compute_hip_flexion(kpts, side="right")

        # Hip adduction (medial/lateral deviation)
        angles.hip_adduction_l = self._compute_hip_adduction(kpts, side="left")
        angles.hip_adduction_r = self._compute_hip_adduction(kpts, side="right")

        # Knee valgus from toe (primary metric when foot landmarks available)
        valgus_l, foot_conf_l = self._compute_knee_valgus_from_toe(kpts, side="left")
        valgus_r, foot_conf_r = self._compute_knee_valgus_from_toe(kpts, side="right")
        angles.knee_valgus_l = valgus_l
        angles.knee_valgus_r = valgus_r
        angles.foot_confidence_l = foot_conf_l
        angles.foot_confidence_r = foot_conf_r

        # Hip rotation (internal/external)
        angles.hip_rotation_l = self._compute_hip_rotation(kpts, side="left")
        angles.hip_rotation_r = self._compute_hip_rotation(kpts, side="right")

        # Knee flexion
        angles.knee_flexion_l = self._compute_knee_flexion(kpts, side="left")
        angles.knee_flexion_r = self._compute_knee_flexion(kpts, side="right")

        # Ankle dorsiflexion
        angles.ankle_dorsiflexion_l = self._compute_ankle_dorsiflexion(kpts, side="left")
        angles.ankle_dorsiflexion_r = self._compute_ankle_dorsiflexion(kpts, side="right")

        # Trunk angles
        angles.trunk_flexion = self._compute_trunk_flexion(kpts)
        angles.trunk_lateral_flexion = self._compute_trunk_lateral_flexion(kpts)
        angles.trunk_rotation = self._compute_trunk_rotation(kpts)

        # Pelvis angles
        angles.pelvis_tilt = self._compute_pelvis_tilt(kpts)
        angles.pelvis_list = self._compute_pelvis_list(kpts)
        angles.pelvis_rotation = self._compute_pelvis_rotation(kpts)

        # Upper-body angles
        angles.elbow_flexion_l = self._compute_elbow_flexion(kpts, side="left")
        angles.elbow_flexion_r = self._compute_elbow_flexion(kpts, side="right")
        angles.shoulder_flexion_l = self._compute_shoulder_flexion(kpts, side="left")
        angles.shoulder_flexion_r = self._compute_shoulder_flexion(kpts, side="right")
        angles.shoulder_abduction_l = self._compute_shoulder_abduction(kpts, side="left")
        angles.shoulder_abduction_r = self._compute_shoulder_abduction(kpts, side="right")

        # Wrist positions relative to shoulder midpoint
        wrist_pos = self._compute_wrist_positions(kpts)
        angles.wrist_y_l = wrist_pos["wrist_y_l"]
        angles.wrist_y_r = wrist_pos["wrist_y_r"]
        angles.wrist_x_l = wrist_pos["wrist_x_l"]
        angles.wrist_x_r = wrist_pos["wrist_x_r"]

        # Stance geometry (squat setup)
        angles.stance_width_ratio = self._compute_stance_width_ratio(kpts)
        angles.toe_out_angle_l = self._compute_toe_out_angle(kpts, side="left")
        angles.toe_out_angle_r = self._compute_toe_out_angle(kpts, side="right")

        return angles

    def _extract_keypoints(self, skeleton: Skeleton3D) -> dict:
        """
        Extract keypoints as numpy arrays with confidence checking.

        Returns dict mapping keypoint name to (position, confidence) tuple.
        """
        names = [
            "nose", "left_eye", "right_eye", "left_ear", "right_ear",
            "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
            "left_wrist", "right_wrist", "left_hip", "right_hip",
            "left_knee", "right_knee", "left_ankle", "right_ankle",
            "left_foot_index", "right_foot_index",
        ]

        kpts = {}
        for i, name in enumerate(names):
            if i < len(skeleton.keypoints):
                kp = skeleton.keypoints[i]
                kpts[name] = (np.array([kp.x, kp.y, kp.z]), kp.confidence)
            else:
                kpts[name] = (np.zeros(3), 0.0)

        return kpts

    def _get_point(self, kpts: dict, name: str) -> Optional[np.ndarray]:
        """Get keypoint position if confidence is sufficient."""
        pos, conf = kpts.get(name, (np.zeros(3), 0.0))
        if conf >= self.min_confidence:
            return pos
        return None

    def _compute_hip_flexion(self, kpts: dict, side: str) -> float:
        """
        Compute hip flexion angle.

        Hip flexion is the angle between the trunk vector and the thigh vector
        projected onto the sagittal plane.

        0 degrees = standing upright (thigh aligned with trunk)
        Positive = flexion (thigh moving forward/up)
        """
        hip = self._get_point(kpts, f"{side}_hip")
        knee = self._get_point(kpts, f"{side}_knee")
        shoulder = self._get_point(kpts, f"{side}_shoulder")

        if hip is None or knee is None or shoulder is None:
            logger.debug(f"Missing keypoints for {side} hip flexion")
            return 0.0

        # Trunk vector (hip to shoulder)
        trunk_vec = shoulder - hip

        # Thigh vector (hip to knee)
        thigh_vec = knee - hip

        # In standing position, thigh points downward (negative Y in Y-up coords)
        # Measure how far the thigh deviates from the downward direction
        # 0 degrees when standing upright, increases with flexion

        # Downward reference (Y-up coordinate system)
        vertical = np.array([0, -1, 0])

        # Thigh angle from vertical (0 when standing)
        thigh_from_vertical = angle_between_vectors(thigh_vec, vertical)

        return thigh_from_vertical

    def _compute_hip_adduction(self, kpts: dict, side: str) -> float:
        """
        Compute hip adduction angle.

        Hip adduction is the medial/lateral deviation of the thigh from the
        sagittal plane.

        0 degrees = thigh in sagittal plane
        Positive = adduction (thigh moving toward midline)
        Negative = abduction (thigh moving away from midline)
        """
        hip = self._get_point(kpts, f"{side}_hip")
        knee = self._get_point(kpts, f"{side}_knee")

        if hip is None or knee is None:
            return 0.0

        # Vector from hip to knee
        thigh_vec = knee - hip

        # Get hip midpoint for reference
        left_hip = self._get_point(kpts, "left_hip")
        right_hip = self._get_point(kpts, "right_hip")

        if left_hip is None or right_hip is None:
            return 0.0

        # Sagittal plane normal (X-axis, pointing left)
        sagittal_normal = np.array([1, 0, 0])

        # Project thigh vector onto frontal plane (remove X component)
        thigh_frontal = np.array([0, thigh_vec[1], thigh_vec[2]])
        thigh_frontal_norm = np.linalg.norm(thigh_frontal)

        if thigh_frontal_norm < 1e-6:
            return 0.0

        # Angle between actual thigh and thigh projected to frontal plane
        angle = angle_between_vectors(thigh_vec, thigh_frontal)

        # Determine sign based on side
        if side == "left":
            # Left thigh moving left (negative X) is abduction
            sign = 1.0 if thigh_vec[0] > 0 else -1.0
        else:
            # Right thigh moving right (negative X) is abduction
            sign = -1.0 if thigh_vec[0] < 0 else 1.0

        return angle * sign

    def _compute_knee_valgus_from_toe(self, kpts: dict, side: str) -> tuple:
        """
        Compute knee valgus as the frontal-plane deviation of the knee
        from the hip-to-big-toe reference line.

        Returns:
            (valgus_angle_degrees, foot_confidence)

        Positive = valgus (knee medial to the hip-toe line)
        Negative = varus (knee lateral to the hip-toe line)
        """
        hip = self._get_point(kpts, f"{side}_hip")
        knee = self._get_point(kpts, f"{side}_knee")
        foot = self._get_point(kpts, f"{side}_foot_index")

        _, foot_conf = kpts.get(f"{side}_foot_index", (np.zeros(3), 0.0))

        if hip is None or knee is None or foot is None:
            return 0.0, foot_conf

        # Project onto frontal plane (XY in MediaPipe coords, removing Z/depth)
        hip_frontal = np.array([hip[0], hip[1]])
        knee_frontal = np.array([knee[0], knee[1]])
        foot_frontal = np.array([foot[0], foot[1]])

        # Reference line: hip to foot_index
        ref_vec = foot_frontal - hip_frontal
        ref_len = np.linalg.norm(ref_vec)
        if ref_len < 1e-6:
            return 0.0, foot_conf

        # Knee vector: hip to knee
        knee_vec = knee_frontal - hip_frontal

        # Angle magnitude via 3D helper (pad to 3D for angle_between_vectors)
        angle = angle_between_vectors(
            np.array([ref_vec[0], ref_vec[1], 0.0]),
            np.array([knee_vec[0], knee_vec[1], 0.0]),
        )

        # Sign via 2D cross product: positive cross = knee is to the left of ref line
        cross_2d = ref_vec[0] * knee_vec[1] - ref_vec[1] * knee_vec[0]

        if side == "left":
            # Left leg: knee medial (toward center/right) → cross > 0 = valgus
            sign = 1.0 if cross_2d > 0 else -1.0
        else:
            # Right leg: knee medial (toward center/left) → cross < 0 = valgus
            sign = 1.0 if cross_2d < 0 else -1.0

        return angle * sign, foot_conf

    def _compute_hip_rotation(self, kpts: dict, side: str) -> float:
        """
        Compute hip internal/external rotation.

        This is difficult to compute accurately without foot orientation.
        Returns 0 as a placeholder.
        """
        # Hip rotation requires knowing foot orientation
        # For now, return 0
        return 0.0

    def _compute_knee_flexion(self, kpts: dict, side: str) -> float:
        """
        Compute knee flexion angle.

        0 degrees = fully extended (straight leg)
        Positive = flexion (bending the knee)
        """
        hip = self._get_point(kpts, f"{side}_hip")
        knee = self._get_point(kpts, f"{side}_knee")
        ankle = self._get_point(kpts, f"{side}_ankle")

        if hip is None or knee is None or ankle is None:
            logger.debug(f"Missing keypoints for {side} knee flexion")
            return 0.0

        # Angle at the knee joint
        angle = joint_angle_3_points(hip, knee, ankle)

        # Convert from angle at joint to flexion angle
        # 180 degrees at joint = 0 degrees flexion (straight)
        # 90 degrees at joint = 90 degrees flexion (bent)
        return 180.0 - angle

    def _compute_ankle_dorsiflexion(self, kpts: dict, side: str) -> float:
        """
        Compute ankle dorsiflexion as shank tilt from vertical.

        0° = shank vertical (neutral), positive = shin tilted forward.
        Does not use foot keypoints — feet are assumed parallel to ground.
        """
        knee = self._get_point(kpts, f"{side}_knee")
        ankle = self._get_point(kpts, f"{side}_ankle")

        if knee is None or ankle is None:
            return 0.0

        shank = knee - ankle
        if np.linalg.norm(shank) < 1e-6:
            return 0.0

        # Upward direction (Y-down MediaPipe convention: -Y is up)
        up = np.array([0.0, -1.0, 0.0])
        return angle_between_vectors(shank, up)

    def _compute_trunk_flexion(self, kpts: dict) -> float:
        """
        Compute trunk forward flexion (sagittal plane).

        180 degrees = upright (fully extended)
        Decreases with forward lean (like knee/hip flexion convention)
        """
        left_shoulder = self._get_point(kpts, "left_shoulder")
        right_shoulder = self._get_point(kpts, "right_shoulder")
        left_hip = self._get_point(kpts, "left_hip")
        right_hip = self._get_point(kpts, "right_hip")

        if any(p is None for p in [left_shoulder, right_shoulder, left_hip, right_hip]):
            return 180.0

        # Midpoints
        shoulder_mid = midpoint(left_shoulder, right_shoulder)
        hip_mid = midpoint(left_hip, right_hip)

        # Trunk vector
        trunk_vec = shoulder_mid - hip_mid

        # Y-down reference (MediaPipe world coords are Y-down)
        vertical = np.array([0, -1, 0])

        # 180 - angle: 180° upright, decreases with lean
        angle = angle_between_vectors(trunk_vec, vertical)
        return 180.0 - angle

    def _compute_trunk_lateral_flexion(self, kpts: dict) -> float:
        """
        Compute trunk lateral flexion (frontal plane).

        0 degrees = upright
        Positive = lean to the left
        Negative = lean to the right
        """
        left_shoulder = self._get_point(kpts, "left_shoulder")
        right_shoulder = self._get_point(kpts, "right_shoulder")
        left_hip = self._get_point(kpts, "left_hip")
        right_hip = self._get_point(kpts, "right_hip")

        if any(p is None for p in [left_shoulder, right_shoulder, left_hip, right_hip]):
            return 0.0

        # Midpoints
        shoulder_mid = midpoint(left_shoulder, right_shoulder)
        hip_mid = midpoint(left_hip, right_hip)

        # Project trunk to frontal plane (YZ plane, remove X)
        trunk_vec = shoulder_mid - hip_mid
        trunk_frontal = np.array([trunk_vec[0], trunk_vec[1], 0])

        # Upward reference in frontal plane (Y-up coordinate system)
        vertical = np.array([0, 1, 0])

        angle = angle_between_vectors(trunk_frontal, vertical)

        # Determine sign (positive = lean left)
        if trunk_vec[0] > 0:
            angle = -angle

        return angle

    def _compute_trunk_rotation(self, kpts: dict) -> float:
        """
        Compute trunk axial rotation (transverse plane).

        0 degrees = facing forward
        Positive = rotated to the left
        Negative = rotated to the right
        """
        left_shoulder = self._get_point(kpts, "left_shoulder")
        right_shoulder = self._get_point(kpts, "right_shoulder")

        if left_shoulder is None or right_shoulder is None:
            return 0.0

        # Shoulder line vector
        shoulder_vec = left_shoulder - right_shoulder

        # Project to transverse (XZ) plane
        shoulder_xz = np.array([shoulder_vec[0], 0, shoulder_vec[2]])

        # Reference: facing forward (X-axis)
        reference = np.array([1, 0, 0])

        if np.linalg.norm(shoulder_xz) < 1e-6:
            return 0.0

        angle = angle_between_vectors(shoulder_xz, reference)

        # Determine sign based on Z component
        if shoulder_vec[2] > 0:
            angle = -angle

        return angle

    def _compute_pelvis_tilt(self, kpts: dict) -> float:
        """
        Compute pelvis anterior/posterior tilt.

        0 degrees = neutral pelvis
        Positive = anterior tilt (top of pelvis tilted forward)
        Negative = posterior tilt (top of pelvis tilted backward)
        """
        left_hip = self._get_point(kpts, "left_hip")
        right_hip = self._get_point(kpts, "right_hip")
        left_shoulder = self._get_point(kpts, "left_shoulder")
        right_shoulder = self._get_point(kpts, "right_shoulder")

        if any(p is None for p in [left_hip, right_hip, left_shoulder, right_shoulder]):
            return 0.0

        # Estimate pelvis tilt from trunk angle
        # This is an approximation - true pelvis tilt requires ASIS/PSIS markers
        hip_mid = midpoint(left_hip, right_hip)
        shoulder_mid = midpoint(left_shoulder, right_shoulder)

        trunk_vec = shoulder_mid - hip_mid

        # Project to sagittal plane (YZ)
        trunk_sagittal = np.array([0, trunk_vec[1], trunk_vec[2]])

        # Upward reference (Y-up coordinate system)
        vertical = np.array([0, 1, 0])

        if np.linalg.norm(trunk_sagittal) < 1e-6:
            return 0.0

        # Scale trunk flexion to estimate pelvis tilt
        # Pelvis tilt is typically 30-55% of trunk flexion in squats,
        # varying with hip width and torso proportions.
        trunk_angle = angle_between_vectors(trunk_sagittal, vertical)

        # Check direction (forward lean = positive Z component in trunk)
        if trunk_vec[2] < 0:
            trunk_angle = -trunk_angle

        return trunk_angle * self._pelvis_tilt_coupling

    def _compute_pelvis_list(self, kpts: dict) -> float:
        """
        Compute pelvis lateral list (hiking).

        0 degrees = level pelvis
        Positive = left hip higher
        Negative = right hip higher
        """
        left_hip = self._get_point(kpts, "left_hip")
        right_hip = self._get_point(kpts, "right_hip")

        if left_hip is None or right_hip is None:
            return 0.0

        # Height difference between hips
        height_diff = left_hip[1] - right_hip[1]

        # Convert to angle (approximate)
        # Hip width is roughly 0.25m, so tan(angle) = height_diff / 0.25
        hip_width = np.linalg.norm(left_hip - right_hip)

        if hip_width < 0.01:
            return 0.0

        angle_rad = np.arctan2(height_diff, hip_width)
        return np.degrees(angle_rad)

    def _compute_pelvis_rotation(self, kpts: dict) -> float:
        """
        Compute pelvis axial rotation.

        0 degrees = hips facing forward
        Positive = rotated to the left
        Negative = rotated to the right
        """
        left_hip = self._get_point(kpts, "left_hip")
        right_hip = self._get_point(kpts, "right_hip")

        if left_hip is None or right_hip is None:
            return 0.0

        # Hip line vector
        hip_vec = left_hip - right_hip

        # Project to transverse (XZ) plane
        hip_xz = np.array([hip_vec[0], 0, hip_vec[2]])

        # Reference: facing forward (X-axis)
        reference = np.array([1, 0, 0])

        if np.linalg.norm(hip_xz) < 1e-6:
            return 0.0

        angle = angle_between_vectors(hip_xz, reference)

        # Determine sign based on Z component
        if hip_vec[2] > 0:
            angle = -angle

        return angle

    # ------------------------------------------------------------------
    # Upper-body angle computations
    # ------------------------------------------------------------------

    def _compute_elbow_flexion(self, kpts: dict, side: str) -> float:
        """
        Compute elbow flexion angle.

        0 degrees = fully extended (straight arm)
        Positive = flexion (bending the elbow)
        Convention matches knee flexion: 180 - joint_angle.
        """
        shoulder = self._get_point(kpts, f"{side}_shoulder")
        elbow = self._get_point(kpts, f"{side}_elbow")
        wrist = self._get_point(kpts, f"{side}_wrist")

        if shoulder is None or elbow is None or wrist is None:
            return 0.0

        angle = joint_angle_3_points(shoulder, elbow, wrist)
        return 180.0 - angle

    def _compute_shoulder_flexion(self, kpts: dict, side: str) -> float:
        """
        Compute shoulder flexion angle (sagittal plane).

        Measures the angle between the upper arm and the trunk vector.
        0 degrees = arm hanging at side (aligned with trunk)
        90 degrees = arm horizontal in front
        180 degrees = arm fully overhead
        """
        shoulder = self._get_point(kpts, f"{side}_shoulder")
        elbow = self._get_point(kpts, f"{side}_elbow")
        hip = self._get_point(kpts, f"{side}_hip")

        if shoulder is None or elbow is None or hip is None:
            return 0.0

        # Trunk vector (hip to shoulder) — points upward along torso
        trunk_vec = shoulder - hip

        # Upper arm vector (shoulder to elbow) — points along the arm
        upper_arm_vec = elbow - shoulder

        # Angle between trunk and upper arm
        # When arm hangs down, upper_arm is roughly opposite to trunk → ~180°
        # We want 0° for hanging, so: flexion = 180 - raw_angle
        raw_angle = angle_between_vectors(trunk_vec, upper_arm_vec)
        return 180.0 - raw_angle

    def _compute_shoulder_abduction(self, kpts: dict, side: str) -> float:
        """
        Compute shoulder abduction angle (frontal plane).

        Measures how far the upper arm deviates laterally from the trunk.
        0 degrees = arm hanging at side
        90 degrees = arm horizontal out to the side
        """
        shoulder = self._get_point(kpts, f"{side}_shoulder")
        elbow = self._get_point(kpts, f"{side}_elbow")
        hip = self._get_point(kpts, f"{side}_hip")

        if shoulder is None or elbow is None or hip is None:
            return 0.0

        # Trunk vector (hip to shoulder)
        trunk_vec = shoulder - hip

        # Upper arm vector (shoulder to elbow)
        upper_arm_vec = elbow - shoulder

        # Project both vectors onto the frontal plane (XY, remove Z/depth)
        trunk_frontal = np.array([trunk_vec[0], trunk_vec[1], 0.0])
        arm_frontal = np.array([upper_arm_vec[0], upper_arm_vec[1], 0.0])

        trunk_norm = np.linalg.norm(trunk_frontal)
        arm_norm = np.linalg.norm(arm_frontal)

        if trunk_norm < 1e-6 or arm_norm < 1e-6:
            return 0.0

        # Angle between trunk and arm in frontal plane
        # When arm hangs down, arm_frontal is opposite to trunk_frontal → ~180°
        raw_angle = angle_between_vectors(trunk_frontal, arm_frontal)
        return 180.0 - raw_angle

    # ------------------------------------------------------------------
    # Stance geometry (squat setup)
    # ------------------------------------------------------------------

    def _compute_stance_width_ratio(self, kpts: dict) -> float:
        """Floor-plane distance between ankles divided by floor-plane
        distance between shoulders. 1.0 = feet directly under shoulders.

        Uses X (lateral) and Z (depth) only — Y is vertical in MediaPipe.
        Returns 0.0 if any keypoint is missing or shoulders are too close.
        """
        left_ankle = self._get_point(kpts, "left_ankle")
        right_ankle = self._get_point(kpts, "right_ankle")
        left_shoulder = self._get_point(kpts, "left_shoulder")
        right_shoulder = self._get_point(kpts, "right_shoulder")

        if any(p is None for p in (left_ankle, right_ankle, left_shoulder, right_shoulder)):
            return 0.0

        ankle_dist = float(np.linalg.norm(
            np.array([left_ankle[0] - right_ankle[0], left_ankle[2] - right_ankle[2]])
        ))
        shoulder_dist = float(np.linalg.norm(
            np.array([left_shoulder[0] - right_shoulder[0], left_shoulder[2] - right_shoulder[2]])
        ))

        if shoulder_dist < 1e-3:
            return 0.0
        return ankle_dist / shoulder_dist

    def _compute_toe_out_angle(self, kpts: dict, side: str) -> float:
        """Angle (degrees) between the foot vector (ankle → foot_index)
        and the sagittal plane, projected to the floor (XZ).

        Positive = toes pointed outward (lateral) for the given side.
        Returns 0.0 if landmarks are missing.
        """
        ankle = self._get_point(kpts, f"{side}_ankle")
        foot = self._get_point(kpts, f"{side}_foot_index")
        if ankle is None or foot is None:
            return 0.0

        foot_vec = np.array([foot[0] - ankle[0], foot[2] - ankle[2]])
        if np.linalg.norm(foot_vec) < 1e-6:
            return 0.0

        # Forward axis on the floor: +Z (toward camera in MediaPipe world).
        forward = np.array([0.0, 1.0])
        # 3D angle helper expects 3-vectors — pad with zero Y.
        angle = angle_between_vectors(
            np.array([foot_vec[0], 0.0, foot_vec[1]]),
            np.array([forward[0], 0.0, forward[1]]),
        )

        # Sign convention: outward = positive on each side.
        # Left foot pointed out = +X; right foot pointed out = -X.
        if side == "left":
            sign = 1.0 if foot_vec[0] >= 0 else -1.0
        else:
            sign = 1.0 if foot_vec[0] <= 0 else -1.0
        return angle * sign

    def _compute_wrist_positions(self, kpts: dict) -> dict:
        """
        Compute wrist positions relative to the shoulder midpoint.

        Returns dict with wrist_y_l, wrist_y_r (vertical, cm),
        wrist_x_l, wrist_x_r (forward-back, cm).

        Convention:
        - wrist_y: positive = above shoulder, negative = below
        - wrist_x: positive = forward of shoulder, negative = behind
        """
        left_shoulder = self._get_point(kpts, "left_shoulder")
        right_shoulder = self._get_point(kpts, "right_shoulder")
        left_wrist = self._get_point(kpts, "left_wrist")
        right_wrist = self._get_point(kpts, "right_wrist")

        result = {"wrist_y_l": 0.0, "wrist_y_r": 0.0,
                  "wrist_x_l": 0.0, "wrist_x_r": 0.0}

        if left_shoulder is None or right_shoulder is None:
            return result

        shoulder_mid = midpoint(left_shoulder, right_shoulder)

        # Y-axis is downward in MediaPipe, so shoulder_mid_y - wrist_y = above
        if left_wrist is not None:
            result["wrist_y_l"] = (shoulder_mid[1] - left_wrist[1]) * 100.0
            result["wrist_x_l"] = (left_wrist[2] - shoulder_mid[2]) * 100.0

        if right_wrist is not None:
            result["wrist_y_r"] = (shoulder_mid[1] - right_wrist[1]) * 100.0
            result["wrist_x_r"] = (right_wrist[2] - shoulder_mid[2]) * 100.0

        return result
