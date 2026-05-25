"""Convert a q-vector to a JointAngles object using MuJoCo FK.

Sign conventions match V1 exactly — downstream fault rules and rep
segmentation work without changes.
"""

from __future__ import annotations

import mujoco
import numpy as np

from biomechanics_v2.model.skeleton_model import MujocoSkeleton
from biomechanics_v2.solver.mujoco_fk import joint_world_positions
from biomechanics.utils.types import JointAngles


def _angle_between(v1: np.ndarray, v2: np.ndarray) -> float:
    """Angle between two vectors in degrees (0-180)."""
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 < 1e-10 or n2 < 1e-10:
        return 0.0
    cos_angle = np.clip(np.dot(v1 / n1, v2 / n2), -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_angle)))


def q_to_joint_angles(
    skeleton: MujocoSkeleton,
    q: np.ndarray,
    timestamp: float = 0.0,
    frame_index: int = 0,
) -> JointAngles:
    """Convert q-vector (radians) to JointAngles (degrees)."""
    skeleton.set_qpos(q)
    skeleton.forward()

    model = skeleton.model
    data = skeleton.data
    positions = skeleton.get_body_positions()

    angles = JointAngles(timestamp=timestamp, frame_index=frame_index)

    _UP = np.array([0.0, 1.0, 0.0])

    # ------------------------------------------------------------------
    # Direct DOF -> degree mappings
    # ------------------------------------------------------------------
    angles.hip_flexion_l = np.degrees(q[skeleton.get_joint_index("L_hip", "rx")])
    angles.hip_flexion_r = np.degrees(q[skeleton.get_joint_index("R_hip", "rx")])

    angles.knee_flexion_l = np.degrees(q[skeleton.get_joint_index("L_knee", "rx")])
    angles.knee_flexion_r = np.degrees(q[skeleton.get_joint_index("R_knee", "rx")])

    angles.ankle_dorsiflexion_l = np.degrees(q[skeleton.get_joint_index("L_ankle", "rx")])
    angles.ankle_dorsiflexion_r = np.degrees(q[skeleton.get_joint_index("R_ankle", "rx")])

    angles.hip_rotation_l = np.degrees(q[skeleton.get_joint_index("L_hip", "rz")])
    angles.hip_rotation_r = np.degrees(q[skeleton.get_joint_index("R_hip", "rz")])

    # Trunk flexion from world-frame orientation (180° upright, decreases with lean)
    trunk_body_id = skeleton._body_ids["trunk"]
    trunk_rot_matrix = data.xmat[trunk_body_id].reshape(3, 3)
    trunk_world_up = trunk_rot_matrix @ _UP
    trunk_from_vertical = _angle_between(trunk_world_up, _UP)
    angles.trunk_flexion = 180.0 - trunk_from_vertical

    angles.trunk_lateral_flexion = np.degrees(q[skeleton.get_joint_index("trunk", "rz")])
    angles.trunk_rotation = np.degrees(q[skeleton.get_joint_index("pelvis", "ry")])

    angles.pelvis_tilt = np.degrees(q[skeleton.get_joint_index("pelvis", "rx")])
    angles.pelvis_list = np.degrees(q[skeleton.get_joint_index("pelvis", "rz")])
    angles.pelvis_rotation = np.degrees(q[skeleton.get_joint_index("pelvis", "ry")])

    # Toe-out angle from ankle ry DOF
    angles.toe_out_angle_l = np.degrees(q[skeleton.get_joint_index("L_ankle", "ry")])
    angles.toe_out_angle_r = np.degrees(q[skeleton.get_joint_index("R_ankle", "ry")])

    # ------------------------------------------------------------------
    # FK-derived geometric angles
    # ------------------------------------------------------------------
    for side, attr in (("L", "l"), ("R", "r")):
        hip = positions[f"{side}_hip"]
        knee = positions[f"{side}_knee"]
        ankle = positions[f"{side}_ankle"]

        # Hip adduction: frontal-plane deviation of thigh from sagittal (YZ) plane
        thigh = knee - hip
        thigh_sagittal = np.array([0.0, thigh[1], thigh[2]])
        if np.linalg.norm(thigh_sagittal) > 1e-6:
            adduction = _angle_between(thigh, thigh_sagittal)
            sign = (
                1.0
                if (side == "L" and thigh[0] > 0) or (side == "R" and thigh[0] < 0)
                else -1.0
            )
            setattr(angles, f"hip_adduction_{attr}", adduction * sign)

        # Knee valgus: frontal-plane deviation of knee from hip-ankle line
        hip_frontal = np.array([hip[0], hip[1]])
        knee_frontal = np.array([knee[0], knee[1]])
        ankle_frontal = np.array([ankle[0], ankle[1]])
        ref = ankle_frontal - hip_frontal
        knee_vec = knee_frontal - hip_frontal
        if np.linalg.norm(ref) > 1e-6:
            valgus = _angle_between(
                np.array([ref[0], ref[1], 0.0]),
                np.array([knee_vec[0], knee_vec[1], 0.0]),
            )
            cross_2d = ref[0] * knee_vec[1] - ref[1] * knee_vec[0]
            if side == "L":
                sign = 1.0 if cross_2d > 0 else -1.0
            else:
                sign = 1.0 if cross_2d < 0 else -1.0
            setattr(angles, f"knee_valgus_{attr}", valgus * sign)

    # Stance width ratio: ankle horizontal distance / hip width
    left_ankle = positions["L_ankle"]
    right_ankle = positions["R_ankle"]
    ankle_horizontal_dist = np.sqrt(
        (left_ankle[0] - right_ankle[0]) ** 2
        + (left_ankle[2] - right_ankle[2]) ** 2
    )
    left_hip = positions["L_hip"]
    right_hip = positions["R_hip"]
    hip_width = np.sqrt(
        (left_hip[0] - right_hip[0]) ** 2
        + (left_hip[2] - right_hip[2]) ** 2
    )
    if hip_width > 1e-6:
        angles.stance_width_ratio = ankle_horizontal_dist / hip_width

    # MuJoCo always has foot body positions, so high confidence
    angles.foot_confidence_l = 1.0
    angles.foot_confidence_r = 1.0

    # ------------------------------------------------------------------
    # Upper-body DOF -> degree mappings
    # ------------------------------------------------------------------
    angles.shoulder_flexion_l = np.degrees(q[skeleton.get_joint_index("L_shoulder", "rx")])
    angles.shoulder_flexion_r = np.degrees(q[skeleton.get_joint_index("R_shoulder", "rx")])
    angles.shoulder_abduction_l = np.degrees(q[skeleton.get_joint_index("L_shoulder", "rz")])
    angles.shoulder_abduction_r = np.degrees(q[skeleton.get_joint_index("R_shoulder", "rz")])
    angles.elbow_flexion_l = np.degrees(q[skeleton.get_joint_index("L_elbow", "rx")])
    angles.elbow_flexion_r = np.degrees(q[skeleton.get_joint_index("R_elbow", "rx")])

    if "L_wrist" in positions and "L_shoulder" in positions:
        wrist_to_shoulder_l = positions["L_wrist"] - positions["L_shoulder"]
        angles.wrist_y_l = wrist_to_shoulder_l[1] * 100.0
        angles.wrist_x_l = wrist_to_shoulder_l[2] * 100.0
    if "R_wrist" in positions and "R_shoulder" in positions:
        wrist_to_shoulder_r = positions["R_wrist"] - positions["R_shoulder"]
        angles.wrist_y_r = wrist_to_shoulder_r[1] * 100.0
        angles.wrist_x_r = wrist_to_shoulder_r[2] * 100.0

    return angles
