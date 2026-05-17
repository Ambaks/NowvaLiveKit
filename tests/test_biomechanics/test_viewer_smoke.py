"""Smoke test: launch the PyWebView kinodynamics viewer with synthetic data.

Run manually:
    python tests/test_biomechanics/test_viewer_smoke.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from biomechanics.skeleton.anthropometry import scale_skeleton
from biomechanics.optimizer.ik import _fk_jac, _build_descendants


def _synthetic_rep(skeleton, n_frames=60):
    """Create a synthetic squat trajectory (neutral → deep → neutral)."""
    nd = skeleton.n_dof
    q_traj = np.zeros((n_frames, nd))
    for t in range(n_frames):
        phase = np.sin(np.pi * t / (n_frames - 1))
        q = skeleton.neutral_q()
        q[skeleton.dof_index("L_hip", "rx")] = np.radians(100 * phase)
        q[skeleton.dof_index("R_hip", "rx")] = np.radians(100 * phase)
        q[skeleton.dof_index("L_knee", "rx")] = np.radians(120 * phase)
        q[skeleton.dof_index("R_knee", "rx")] = np.radians(120 * phase)
        q[skeleton.dof_index("L_ankle", "rx")] = np.radians(30 * phase)
        q[skeleton.dof_index("R_ankle", "rx")] = np.radians(30 * phase)
        q[skeleton.dof_index("trunk", "rx")] = np.radians(40 * phase)
        q[1] -= 0.35 * phase  # lower pelvis
        q_traj[t] = q
    return q_traj


def _q_to_keypoints_19(skeleton, q):
    """Convert skeleton q to 19-keypoint format for the HTML renderer."""
    desc = _build_descendants(skeleton)
    pos, _ = _fk_jac(skeleton, q, desc)
    kpts = {}
    joint_to_mp = {
        "L_hip": 11, "R_hip": 12,
        "L_knee": 13, "R_knee": 14,
        "L_ankle": 15, "R_ankle": 16,
    }
    for jname, mp_idx in joint_to_mp.items():
        ji = skeleton.joint_index(jname)
        kpts[mp_idx] = pos[ji].tolist()

    # Estimate upper body from trunk
    ti = skeleton.joint_index("trunk")
    trunk_pos = pos[ti]
    pelvis_pos = pos[0]
    hip_mid = (pos[skeleton.joint_index("L_hip")] + pos[skeleton.joint_index("R_hip")]) / 2

    shoulder_y = trunk_pos[1] + 0.22
    kpts[5] = [trunk_pos[0] - 0.18, shoulder_y, trunk_pos[2]]  # L shoulder
    kpts[6] = [trunk_pos[0] + 0.18, shoulder_y, trunk_pos[2]]  # R shoulder
    kpts[7] = [kpts[5][0] - 0.05, kpts[5][1] - 0.30, kpts[5][2]]  # L elbow
    kpts[8] = [kpts[6][0] + 0.05, kpts[6][1] - 0.30, kpts[6][2]]  # R elbow
    kpts[9] = [kpts[7][0], kpts[7][1] - 0.26, kpts[7][2]]  # L wrist
    kpts[10] = [kpts[8][0], kpts[8][1] - 0.26, kpts[8][2]]  # R wrist
    kpts[0] = [trunk_pos[0], shoulder_y + 0.22, trunk_pos[2]]  # nose
    kpts[1] = [kpts[0][0] - 0.03, kpts[0][1] + 0.02, kpts[0][2]]
    kpts[2] = [kpts[0][0] + 0.03, kpts[0][1] + 0.02, kpts[0][2]]
    kpts[3] = [kpts[0][0] - 0.06, kpts[0][1], kpts[0][2]]
    kpts[4] = [kpts[0][0] + 0.06, kpts[0][1], kpts[0][2]]
    # Foot tips
    kpts[17] = [kpts[15][0], kpts[15][1], kpts[15][2] - 0.26]
    kpts[18] = [kpts[16][0], kpts[16][1], kpts[16][2] - 0.26]
    return kpts


def _build_frame_data(skeleton, q, frame_idx):
    """Build a frame data dict matching the format expected by build_html."""
    kpts = _q_to_keypoints_19(skeleton, q)
    deg = np.degrees
    return {
        "frame_idx": frame_idx,
        "kpts": kpts,
        "phase": 0.0,
        "angles": {
            "knee_flex": deg(q[skeleton.dof_index("L_knee", "rx")]),
            "knee_flex_l": deg(q[skeleton.dof_index("L_knee", "rx")]),
            "knee_flex_r": deg(q[skeleton.dof_index("R_knee", "rx")]),
            "trunk_flexion": 180 - deg(q[skeleton.dof_index("trunk", "rx")]),
            "dorsi_l": deg(q[skeleton.dof_index("L_ankle", "rx")]),
            "dorsi_r": deg(q[skeleton.dof_index("R_ankle", "rx")]),
            "hip_flex_l": deg(q[skeleton.dof_index("L_hip", "rx")]),
            "hip_flex_r": deg(q[skeleton.dof_index("R_hip", "rx")]),
            "knee_valgus_l": 0.0,
            "knee_valgus_r": 0.0,
        },
    }


def main():
    skeleton = scale_skeleton(1.78, 80.0)
    q_traj = _synthetic_rep(skeleton, n_frames=60)
    bottom_frame = 30

    # Build frame data for HTML
    frames = [_build_frame_data(skeleton, q_traj[t], t) for t in range(len(q_traj))]
    for i, f in enumerate(frames):
        f["phase"] = np.sin(np.pi * i / 59)

    # Kinodynamics state
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
    from visualize_video_squats import build_html, serialize_kinodynamics_state, compute_baseline

    baseline = compute_baseline(frames)

    kino_state = serialize_kinodynamics_state(
        skeleton, [q_traj],
        rep_boundaries=[[0, len(q_traj) - 1, bottom_frame]],
    )

    html = build_html(baseline, [frames], 30.0, kinodynamics_state=kino_state)

    print(f"Generated HTML: {len(html)} chars")
    print(f"Skeleton: {skeleton.n_dof} DOF, {skeleton.n_joints} joints")
    print(f"Trajectory: {q_traj.shape} (frames x DOF)")
    print(f"Bottom frame: {bottom_frame}")
    print()
    print("Launching PyWebView viewer...")

    from biomechanics.viewer import launch_viewer
    launch_viewer(
        html, skeleton, [q_traj],
        rep_boundaries=[[0, len(q_traj) - 1, bottom_frame]],
    )


if __name__ == "__main__":
    main()
