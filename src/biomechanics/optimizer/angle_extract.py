"""Convert a 20-DOF q vector to a JointAngles object.

Produces the same field names and sign conventions as AnalyticalIKSolver.solve()
so the entire post-IK chain (angle filtering, derivative tracking, fault rules)
works identically for both IK backends.

Primary joint angles (hip/knee/ankle flexion, trunk lean) are read directly
from the DOF values — this avoids the position-based pitfalls where terminal
joints (trunk, ankle) have no children and their orientation is invisible in
FK positions.  Hip adduction and knee valgus are derived from FK world
positions since they couple across multiple DOFs.
"""

from __future__ import annotations

import numpy as np

from biomechanics.skeleton.definition import SkeletonModel
from biomechanics.skeleton.forward_kin import forward_kinematics
from biomechanics.utils.geometry import angle_between_vectors
from biomechanics.utils.types import JointAngles


def q_to_joint_angles(
    skeleton: SkeletonModel,
    q: np.ndarray,
    timestamp: float = 0.0,
    frame_index: int = 0,
) -> JointAngles:
    """Convert a 20-DOF q vector into a JointAngles object.

    Uses DOF values for direct-mapped angles and FK world-frame
    orientations / positions for coupled geometric angles.
    """
    xforms = forward_kinematics(skeleton, q)
    pos = {name: T[:3, 3].copy() for name, T in xforms.items()}

    angles = JointAngles(timestamp=timestamp, frame_index=frame_index)

    _UP = np.array([0.0, 1.0, 0.0])

    # ------------------------------------------------------------------
    # Direct DOF → degree mappings
    # ------------------------------------------------------------------

    # Hip flexion (0° standing, positive = flexion)
    angles.hip_flexion_l = np.degrees(q[skeleton.dof_index("L_hip", "rx")])
    angles.hip_flexion_r = np.degrees(q[skeleton.dof_index("R_hip", "rx")])

    # Knee flexion (0° extended, positive = flexion)
    angles.knee_flexion_l = np.degrees(q[skeleton.dof_index("L_knee", "rx")])
    angles.knee_flexion_r = np.degrees(q[skeleton.dof_index("R_knee", "rx")])

    # Ankle dorsiflexion (0° neutral, positive = shin forward)
    angles.ankle_dorsiflexion_l = np.degrees(q[skeleton.dof_index("L_ankle", "rx")])
    angles.ankle_dorsiflexion_r = np.degrees(q[skeleton.dof_index("R_ankle", "rx")])

    # Trunk flexion from world-frame orientation (180° upright, decreases
    # with forward lean).  The trunk world rotation includes pelvis
    # rotation, so this matches the analytical solver's "total lean."
    trunk_world_up = xforms["trunk"][:3, :3] @ _UP
    trunk_from_vertical = angle_between_vectors(trunk_world_up, _UP)
    angles.trunk_flexion = 180.0 - trunk_from_vertical

    # Trunk lateral flexion: trunk rz DOF
    angles.trunk_lateral_flexion = np.degrees(q[skeleton.dof_index("trunk", "rz")])

    # Trunk rotation: pelvis ry (no shoulder joints in skeleton)
    angles.trunk_rotation = np.degrees(q[skeleton.dof_index("pelvis", "ry")])

    # Pelvis angles
    angles.pelvis_tilt = np.degrees(q[skeleton.dof_index("pelvis", "rx")])
    angles.pelvis_list = np.degrees(q[skeleton.dof_index("pelvis", "rz")])
    angles.pelvis_rotation = np.degrees(q[skeleton.dof_index("pelvis", "ry")])

    # ------------------------------------------------------------------
    # FK-derived geometric angles (couple across DOFs)
    # ------------------------------------------------------------------

    for side, attr in (("L", "l"), ("R", "r")):
        hip = pos[f"{side}_hip"]
        knee = pos[f"{side}_knee"]
        ankle = pos[f"{side}_ankle"]

        # Hip adduction: frontal-plane deviation of thigh from sagittal (YZ) plane
        thigh = knee - hip
        thigh_sagittal = np.array([0.0, thigh[1], thigh[2]])
        if np.linalg.norm(thigh_sagittal) > 1e-6:
            adduction = angle_between_vectors(thigh, thigh_sagittal)
            sign = (
                1.0
                if (side == "L" and thigh[0] > 0) or (side == "R" and thigh[0] < 0)
                else -1.0
            )
            setattr(angles, f"hip_adduction_{attr}", adduction * sign)

        # Knee valgus: frontal-plane deviation of knee from hip-ankle line
        hip_f = np.array([hip[0], hip[1]])
        knee_f = np.array([knee[0], knee[1]])
        ankle_f = np.array([ankle[0], ankle[1]])
        ref = ankle_f - hip_f
        knee_vec = knee_f - hip_f
        if np.linalg.norm(ref) > 1e-6:
            valgus = angle_between_vectors(
                np.array([ref[0], ref[1], 0.0]),
                np.array([knee_vec[0], knee_vec[1], 0.0]),
            )
            cross_2d = ref[0] * knee_vec[1] - ref[1] * knee_vec[0]
            if side == "L":
                sign = 1.0 if cross_2d > 0 else -1.0
            else:
                sign = 1.0 if cross_2d < 0 else -1.0
            setattr(angles, f"knee_valgus_{attr}", valgus * sign)

    # No foot landmarks → fallback to hip_adduction in KneeValgusRule
    angles.foot_confidence_l = 0.0
    angles.foot_confidence_r = 0.0

    return angles
