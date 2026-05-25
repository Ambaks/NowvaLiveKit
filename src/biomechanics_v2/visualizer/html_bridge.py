"""Bridge V2 MuJoCo CaptureResult to V1 Three.js HTML viewer format."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from biomechanics_v2.model.skeleton_model import MujocoSkeleton, DOF_ORDER, N_DOF

if TYPE_CHECKING:
    from biomechanics.utils.types import JointAngles, PipelineFrame, RepData
    from biomechanics_v2.visualizer.capture import CaptureResult

# Ensure scripts/ is importable for V1 helper functions
_SCRIPTS_DIR = str(Path(__file__).resolve().parents[3] / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


def v2_q_to_19_coco_keypoints(
    skeleton: MujocoSkeleton,
    q_vector: np.ndarray,
) -> np.ndarray:
    """Convert q-vector to 19 COCO keypoints in vis-space.

    Returns (19, 3) array.

    MuJoCo (Z-up):  X=lateral, Y=forward, Z=up
    Vis-space (Y-up): X=lateral, Y=up, Z=forward
    So: vis_x = mj_x, vis_y = mj_z, vis_z = mj_y
    """
    skeleton.set_qpos(q_vector)
    skeleton.forward()
    positions = skeleton.get_body_positions()

    kpts_mj = np.zeros((19, 3))

    kpts_mj[0] = positions["head"]

    head_body_id = skeleton._body_ids["head"]
    head_rotation = skeleton.data.xmat[head_body_id].reshape(3, 3)
    head_pos = positions["head"]
    scale_factor = skeleton.height_m / 1.75

    eye_lateral = 0.03 * scale_factor
    eye_forward = 0.07 * scale_factor
    ear_lateral = 0.07 * scale_factor
    ear_backward = 0.02 * scale_factor

    local_left = head_rotation[:, 0]
    local_forward = head_rotation[:, 1]

    kpts_mj[1] = head_pos - local_left * eye_lateral + local_forward * eye_forward
    kpts_mj[2] = head_pos + local_left * eye_lateral + local_forward * eye_forward
    kpts_mj[3] = head_pos - local_left * ear_lateral - local_forward * ear_backward
    kpts_mj[4] = head_pos + local_left * ear_lateral - local_forward * ear_backward

    kpts_mj[5] = positions["L_shoulder"]
    kpts_mj[6] = positions["R_shoulder"]
    kpts_mj[7] = positions["L_elbow"]
    kpts_mj[8] = positions["R_elbow"]
    kpts_mj[9] = positions["L_wrist"]
    kpts_mj[10] = positions["R_wrist"]
    kpts_mj[11] = positions["L_hip"]
    kpts_mj[12] = positions["R_hip"]
    kpts_mj[13] = positions["L_knee"]
    kpts_mj[14] = positions["R_knee"]
    kpts_mj[15] = positions["L_ankle"]
    kpts_mj[16] = positions["R_ankle"]
    kpts_mj[17] = positions["L_toe"]
    kpts_mj[18] = positions["R_toe"]

    kpts_vis = np.zeros_like(kpts_mj)
    kpts_vis[:, 0] = kpts_mj[:, 0]  # vis_x = mj_x (lateral)
    kpts_vis[:, 1] = kpts_mj[:, 2]  # vis_y = mj_z (up)
    kpts_vis[:, 2] = kpts_mj[:, 1]  # vis_z = mj_y (forward)

    kpts_vis[17, 1] = kpts_vis[15, 1]
    kpts_vis[18, 1] = kpts_vis[16, 1]

    return kpts_vis


def v2_frame_to_v1_frame_data(
    skeleton: MujocoSkeleton,
    q_vector: np.ndarray,
    angles: JointAngles,
    frame_index: int,
) -> dict:
    """Convert one V2 frame into the V1 viewer's per-frame dict."""
    kpts_vis = v2_q_to_19_coco_keypoints(skeleton, q_vector)
    return {
        "kpts": kpts_vis.tolist(),
        "angles": {
            "knee_flex": angles.avg_knee_flexion,
            "knee_flex_l": angles.knee_flexion_l,
            "knee_flex_r": angles.knee_flexion_r,
            "trunk_flexion": angles.trunk_flexion,
            "knee_valgus_l": angles.knee_valgus_l,
            "knee_valgus_r": angles.knee_valgus_r,
            "dorsi_l": angles.ankle_dorsiflexion_l,
            "dorsi_r": angles.ankle_dorsiflexion_r,
            "hip_flex_l": angles.hip_flexion_l,
            "hip_flex_r": angles.hip_flexion_r,
            "shoulder_flex_l": angles.shoulder_flexion_l,
            "shoulder_flex_r": angles.shoulder_flexion_r,
            "elbow_flex_l": angles.elbow_flexion_l,
            "elbow_flex_r": angles.elbow_flexion_r,
        },
        "frame": frame_index,
    }


def _build_skeleton_def(skeleton: MujocoSkeleton) -> dict:
    """Build a skeleton_def dict compatible with V1's browser KinodynamicsSolver."""
    from biomechanics_v2.model.anthropometry import (
        BODY_OFFSETS,
        HINGE_JOINTS,
        SEGMENT_MASS_FRACTIONS,
        BODY_TO_SEGMENT,
    )

    scale_factor = skeleton.height_m / 1.75

    body_names_ordered = [
        "pelvis", "trunk", "head",
        "L_hip", "R_hip", "L_knee", "R_knee",
        "L_ankle", "R_ankle", "L_toe", "R_toe",
        "L_shoulder", "R_shoulder",
        "L_elbow", "R_elbow",
        "L_wrist", "R_wrist",
    ]

    joints_list = []
    for body_name in body_names_ordered:
        parent_name, offset_x, offset_y, offset_z = BODY_OFFSETS[body_name]
        scaled_offset = [
            offset_x * scale_factor,
            offset_y * scale_factor,
            offset_z * scale_factor,
        ]

        dof_axes = []
        limits = []
        if body_name == "pelvis":
            dof_axes = ["tx", "ty", "tz", "rx", "ry", "rz"]
            bounds = skeleton.get_bounds()
            for axis_name in dof_axes:
                dof_idx = skeleton.get_joint_index("pelvis", axis_name)
                low_bound, high_bound = bounds[dof_idx]
                limits.append([float(low_bound), float(high_bound)])
        elif body_name in HINGE_JOINTS:
            bounds = skeleton.get_bounds()
            for _joint_name, _axis_str, _low, _high in HINGE_JOINTS[body_name]:
                axis_letter = _axis_str.replace("-", "").replace(" ", "")
                if axis_letter == "100":
                    axis_key = "rx"
                elif axis_letter == "010":
                    axis_key = "ry"
                elif axis_letter == "001":
                    axis_key = "rz"
                else:
                    axis_key = "rx"
                dof_axes.append(axis_key)
                dof_idx = skeleton.get_joint_index(body_name, axis_key)
                low_bound, high_bound = bounds[dof_idx]
                limits.append([float(low_bound), float(high_bound)])

        joints_list.append({
            "name": body_name,
            "parent": parent_name,
            "offset": scaled_offset,
            "dof_axes": dof_axes,
            "limits": limits,
        })

    dof_map = {}
    for i, (body_name, axis) in enumerate(DOF_ORDER):
        dof_map[f"{body_name}.{axis}"] = i

    bounds = skeleton.get_bounds()
    bounds_list = [[float(low), float(high)] for low, high in bounds]

    joint_masses = []
    weight_kg = skeleton.weight_kg
    for body_name in body_names_ordered:
        segment_name = BODY_TO_SEGMENT.get(body_name)
        if segment_name and segment_name in SEGMENT_MASS_FRACTIONS:
            joint_masses.append(SEGMENT_MASS_FRACTIONS[segment_name] * weight_kg)
        else:
            joint_masses.append(0.5)

    return {
        "joints": joints_list,
        "n_dof": N_DOF,
        "n_joints": len(body_names_ordered),
        "dof_map": dof_map,
        "bounds": bounds_list,
        "joint_masses": joint_masses,
    }


def v2_capture_to_v1_html(
    capture_result: CaptureResult,
    skeleton: MujocoSkeleton,
) -> str:
    """Convert a V2 CaptureResult to a V1 HTML viewer string."""
    from visualize_video_squats import (
        build_html,
        compute_baseline,
        ground_and_center,
        add_phase_to_rep,
    )

    pipeline_frames: list[PipelineFrame] = capture_result.pipeline_frames
    reps: list[RepData] = capture_result.reps
    q_trajectory = capture_result.q_trajectory
    fps = capture_result.fps

    all_frame_dicts = []
    for frame_idx, pipeline_frame in enumerate(pipeline_frames):
        if pipeline_frame.joint_angles is None:
            all_frame_dicts.append(None)
            continue
        q_vec = q_trajectory[frame_idx] if frame_idx < len(q_trajectory) else None
        if q_vec is None:
            all_frame_dicts.append(None)
            continue
        frame_dict = v2_frame_to_v1_frame_data(
            skeleton, q_vec, pipeline_frame.joint_angles, frame_idx,
        )
        all_frame_dicts.append(frame_dict)

    replay_reps_data = []
    q_trajectory_per_rep = []

    for rep in reps:
        start_frame = rep.start_frame
        end_frame = rep.end_frame
        rep_frames = [
            all_frame_dicts[i]
            for i in range(start_frame, min(end_frame + 1, len(all_frame_dicts)))
        ]
        rep_frames = [f for f in rep_frames if f is not None]
        if not rep_frames:
            continue

        ground_and_center(rep_frames)
        add_phase_to_rep(rep_frames)
        replay_reps_data.append(rep_frames)

        rep_q = q_trajectory[start_frame:end_frame + 1]
        q_trajectory_per_rep.append(rep_q)

    if not replay_reps_data:
        raise ValueError("No valid reps found in capture result")

    baseline = compute_baseline(replay_reps_data[0])

    skeleton_def = _build_skeleton_def(skeleton)
    rep_boundaries = []
    for rep in reps:
        bottom_frame_offset = 0
        rep_start = rep.start_frame
        rep_end = rep.end_frame
        rep_length = rep_end - rep_start + 1
        if rep_length > 0:
            rep_q_slice = q_trajectory[rep_start:rep_end + 1]
            knee_idx = skeleton.get_joint_index("L_knee", "rx")
            if len(rep_q_slice) > 0:
                bottom_frame_offset = int(np.argmax(rep_q_slice[:, knee_idx]))
        rep_boundaries.append([0, rep_length - 1, bottom_frame_offset])

    kinodynamics_state = {
        "skeleton_def": skeleton_def,
        "reps": [
            {"q_trajectory": qt.tolist()}
            for qt in q_trajectory_per_rep
        ],
        "rep_boundaries": rep_boundaries,
    }

    return build_html(
        baseline,
        replay_reps_data,
        fps,
        athlete_params=None,
        kinodynamics_state=kinodynamics_state,
    )


def v2_synthetic_to_v1_html(
    skeleton: MujocoSkeleton,
    q_trajectory: np.ndarray,
    fps: float = 30.0,
    frames_per_rep: int = 60,
    standing_frames: int = 30,
    num_reps: int = 2,
) -> str:
    """Convert a synthetic V2 trajectory to V1 HTML (no CaptureResult needed)."""
    from visualize_video_squats import (
        build_html,
        compute_baseline,
        ground_and_center,
        add_phase_to_rep,
    )
    from biomechanics_v2.solver.angle_extract import q_to_joint_angles

    all_frame_dicts = []
    for frame_idx in range(len(q_trajectory)):
        angles = q_to_joint_angles(skeleton, q_trajectory[frame_idx],
                                   timestamp=frame_idx / fps,
                                   frame_index=frame_idx)
        frame_dict = v2_frame_to_v1_frame_data(
            skeleton, q_trajectory[frame_idx], angles, frame_idx,
        )
        all_frame_dicts.append(frame_dict)

    replay_reps_data = []
    q_trajectory_per_rep = []
    rep_boundaries = []

    for rep_idx in range(num_reps):
        start = standing_frames + rep_idx * frames_per_rep
        end = start + frames_per_rep
        rep_frames = all_frame_dicts[start:end]
        rep_q = q_trajectory[start:end]

        ground_and_center(rep_frames)
        add_phase_to_rep(rep_frames)
        replay_reps_data.append(rep_frames)
        q_trajectory_per_rep.append(rep_q)

        knee_idx = skeleton.get_joint_index("L_knee", "rx")
        bottom_offset = int(np.argmax(rep_q[:, knee_idx]))
        rep_boundaries.append([0, len(rep_frames) - 1, bottom_offset])

    baseline = compute_baseline(replay_reps_data[0])

    skeleton_def = _build_skeleton_def(skeleton)
    kinodynamics_state = {
        "skeleton_def": skeleton_def,
        "reps": [{"q_trajectory": qt.tolist()} for qt in q_trajectory_per_rep],
        "rep_boundaries": rep_boundaries,
    }

    return build_html(
        baseline,
        replay_reps_data,
        fps,
        athlete_params=None,
        kinodynamics_state=kinodynamics_state,
    )
