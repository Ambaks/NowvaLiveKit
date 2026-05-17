"""Diagnose IK bugs: numerical Jacobian check + per-frame vs smoothed comparison."""

from __future__ import annotations
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from biomechanics.skeleton.anthropometry import scale_skeleton, calibrate_skeleton
from biomechanics.optimizer.ik import (
    fit_frame, fit_trajectory, _fk_jac, _build_descendants,
)
from biomechanics.optimizer.landmark_adapter import skeleton3d_to_landmarks


def numerical_jacobian(skel, q, desc, eps=1e-6):
    """Finite-difference Jacobian for comparison against analytical."""
    nj = skel.n_joints
    nd = skel.n_dof
    J_num = np.zeros((nj * 3, nd))
    for col in range(nd):
        q_plus = q.copy()
        q_minus = q.copy()
        q_plus[col] += eps
        q_minus[col] -= eps
        pos_plus, _ = _fk_jac(skel, q_plus, desc)
        pos_minus, _ = _fk_jac(skel, q_minus, desc)
        J_num[:, col] = (pos_plus - pos_minus).ravel() / (2 * eps)
    return J_num


def test_jacobian(skel, desc):
    """Compare analytical vs numerical Jacobian at several configurations."""
    print("=" * 60)
    print("TEST 1: Jacobian correctness (analytical vs numerical)")
    print("=" * 60)

    configs = {
        "neutral": skel.neutral_q(),
        "mid-squat": None,
        "random": None,
    }

    mid_squat = skel.neutral_q()
    mid_squat[skel.dof_index("L_hip", "rx")] = np.radians(80)
    mid_squat[skel.dof_index("R_hip", "rx")] = np.radians(80)
    mid_squat[skel.dof_index("L_knee", "rx")] = np.radians(90)
    mid_squat[skel.dof_index("R_knee", "rx")] = np.radians(90)
    mid_squat[skel.dof_index("L_ankle", "rx")] = np.radians(20)
    mid_squat[skel.dof_index("R_ankle", "rx")] = np.radians(20)
    mid_squat[skel.dof_index("trunk", "rx")] = np.radians(15)
    configs["mid-squat"] = mid_squat

    bounds = skel.bounds()
    rng = np.random.RandomState(42)
    random_q = np.array([
        rng.uniform(max(lo, -2), min(hi, 2)) for lo, hi in bounds
    ])
    configs["random"] = random_q

    all_pass = True
    for name, q in configs.items():
        pos_anal, J_anal = _fk_jac(skel, q, desc)
        J_num = numerical_jacobian(skel, q, desc)
        max_err = np.max(np.abs(J_anal - J_num))
        mean_err = np.mean(np.abs(J_anal - J_num))

        status = "PASS" if max_err < 1e-4 else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"\n  Config '{name}': max_err={max_err:.2e}, mean_err={mean_err:.2e} [{status}]")

        if max_err > 1e-4:
            row, col = np.unravel_index(
                np.argmax(np.abs(J_anal - J_num)), J_anal.shape
            )
            joint_idx = row // 3
            component = ["x", "y", "z"][row % 3]
            joint_name = skel.joints[joint_idx].name
            dof_info = _dof_name(skel, col)
            print(f"    Worst mismatch: J[{joint_name}.{component}, {dof_info}]")
            print(f"      analytical={J_anal[row, col]:.6f}, numerical={J_num[row, col]:.6f}")

    # Show which DOFs have zero Jacobian columns
    print(f"\n  Zero-Jacobian DOFs (at mid-squat config):")
    _, J_mid = _fk_jac(skel, mid_squat, desc)
    for col in range(skel.n_dof):
        col_norm = np.linalg.norm(J_mid[:, col])
        if col_norm < 1e-10:
            print(f"    DOF {col} ({_dof_name(skel, col)}): |J_col| = {col_norm:.2e} — ZERO GRADIENT")

    return all_pass


def test_single_frame_fit(skel, landmarks_single, desc):
    """Test fit_frame on a single frame with generous iterations."""
    print("\n" + "=" * 60)
    print("TEST 2: Single-frame fit quality (no smoothing)")
    print("=" * 60)

    ik_weights = np.array([0.5, 0.3, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.3, 0.8, 0.8])

    for max_iter_val in [50, 200, 500]:
        q_fit = fit_frame(
            skel, landmarks_single,
            weights=ik_weights,
            max_iter=max_iter_val,
            _desc=desc,
        )
        fk_pos, _ = _fk_jac(skel, q_fit, desc)
        errors_mm = np.linalg.norm(fk_pos - landmarks_single[:, :3], axis=1) * 1000

        print(f"\n  max_iter={max_iter_val}:")
        for joint_idx, jd in enumerate(skel.joints):
            vis = landmarks_single[joint_idx, 3]
            tag = "" if vis >= 0.5 else " (low vis)"
            print(f"    {jd.name:10s}: {errors_mm[joint_idx]:7.1f}mm{tag}")
        print(f"    Mean lower-body (hip/knee/ankle): "
              f"{np.mean(errors_mm[2:]):.1f}mm")


def test_smoothing_impact(skel, landmarks_traj, desc):
    """Compare per-frame fits vs smoothed trajectory."""
    print("\n" + "=" * 60)
    print("TEST 3: Smoothing impact (per-frame vs smoothed)")
    print("=" * 60)

    ik_weights = np.array([0.5, 0.3, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.3, 0.8, 0.8])
    n_frames = landmarks_traj.shape[0]

    q_no_smooth = fit_trajectory(
        skel, landmarks_traj, weights=ik_weights, smooth_sigma=0.0,
    )
    q_smoothed = fit_trajectory(
        skel, landmarks_traj, weights=ik_weights, smooth_sigma=1.5,
    )

    # Find bottom frame (min avg hip Y)
    hip_y_no_smooth = np.zeros(n_frames)
    hip_y_smoothed = np.zeros(n_frames)
    l_hip_idx = skel.joint_index("L_hip")
    r_hip_idx = skel.joint_index("R_hip")

    errors_no_smooth = np.zeros((n_frames, skel.n_joints))
    errors_smoothed = np.zeros((n_frames, skel.n_joints))

    for t in range(n_frames):
        fk_ns, _ = _fk_jac(skel, q_no_smooth[t], desc)
        fk_sm, _ = _fk_jac(skel, q_smoothed[t], desc)
        errors_no_smooth[t] = np.linalg.norm(fk_ns - landmarks_traj[t, :, :3], axis=1)
        errors_smoothed[t] = np.linalg.norm(fk_sm - landmarks_traj[t, :, :3], axis=1)
        hip_y_no_smooth[t] = (fk_ns[l_hip_idx, 1] + fk_ns[r_hip_idx, 1]) / 2
        hip_y_smoothed[t] = (fk_sm[l_hip_idx, 1] + fk_sm[r_hip_idx, 1]) / 2

    bottom_ns = int(np.argmin(hip_y_no_smooth))
    bottom_sm = int(np.argmin(hip_y_smoothed))

    print(f"\n  Trajectory: {n_frames} frames")
    print(f"\n  Mean error across ALL frames (mm):")
    print(f"    {'Joint':10s}  {'No smooth':>10s}  {'Smoothed':>10s}  {'Delta':>10s}")
    for joint_idx, jd in enumerate(skel.joints):
        mean_ns = np.mean(errors_no_smooth[:, joint_idx]) * 1000
        mean_sm = np.mean(errors_smoothed[:, joint_idx]) * 1000
        print(f"    {jd.name:10s}  {mean_ns:10.1f}  {mean_sm:10.1f}  {mean_sm - mean_ns:+10.1f}")

    print(f"\n  Error at BOTTOM frame (mm):")
    print(f"    Bottom frame index: no_smooth={bottom_ns}, smoothed={bottom_sm}")
    print(f"    {'Joint':10s}  {'No smooth':>10s}  {'Smoothed':>10s}")
    for joint_idx, jd in enumerate(skel.joints):
        err_ns = errors_no_smooth[bottom_ns, joint_idx] * 1000
        err_sm = errors_smoothed[bottom_sm, joint_idx] * 1000
        print(f"    {jd.name:10s}  {err_ns:10.1f}  {err_sm:10.1f}")

    # Show q values at bottom for both
    print(f"\n  Key DOFs at bottom frame:")
    print(f"    {'DOF':20s}  {'No smooth':>12s}  {'Smoothed':>12s}")
    for dof_name in ["L_hip.rx", "L_hip.rz", "L_knee.rx", "L_ankle.rx", "trunk.rx"]:
        joint, axis = dof_name.split(".")
        dof_idx = skel.dof_index(joint, axis)
        val_ns = np.degrees(q_no_smooth[bottom_ns, dof_idx])
        val_sm = np.degrees(q_smoothed[bottom_sm, dof_idx])
        print(f"    {dof_name:20s}  {val_ns:+12.1f}°  {val_sm:+12.1f}°")


def _dof_name(skel, dof_idx):
    for (joint_name, axis), idx in skel._dof_map.items():
        if idx == dof_idx:
            return f"{joint_name}.{axis}"
    return f"dof_{dof_idx}"


def load_landmarks(skel, html_path):
    """Load landmarks from a recording HTML file."""
    from biomechanics.utils.types import Point3D, Skeleton3D

    text = html_path.read_text()
    match = re.search(r'const DATA = ({.*?});\s*\n', text, re.DOTALL)
    if not match:
        print("ERROR: Could not find embedded DATA")
        sys.exit(1)
    data = json.loads(match.group(1))

    replay_reps = data["reps"]

    def vis_to_skeleton3d(kpts_vis):
        points = []
        for i in range(min(19, len(kpts_vis))):
            vis_x, vis_y, vis_z = kpts_vis[i]
            points.append(Point3D(x=-vis_z, y=-vis_y, z=vis_x, confidence=1.0))
        return Skeleton3D(keypoints=points)

    # Use the first rep that has valid frames
    for rep_frames in replay_reps:
        valid_frames = [
            f for f in rep_frames
            if f is not None and f.get("kpts")
        ]
        if len(valid_frames) < 5:
            continue

        n_valid = len(valid_frames)
        landmarks = np.zeros((n_valid, skel.n_joints, 4))
        for idx, frame in enumerate(valid_frames):
            skel3d = vis_to_skeleton3d(frame["kpts"])
            landmarks[idx] = skeleton3d_to_landmarks(skel3d)
        return landmarks

    print("ERROR: No valid rep found")
    sys.exit(1)


def check_bone_lengths(skel, landmarks):
    """Compare skeleton bone lengths to observed landmark segment lengths."""
    print("\n" + "=" * 60)
    print("TEST 0: Bone length vs observed segment length")
    print("=" * 60)

    segments = [
        ("L_thigh", "L_hip", "L_knee", 2, 4),
        ("R_thigh", "R_hip", "R_knee", 3, 5),
        ("L_shank", "L_knee", "L_ankle", 4, 6),
        ("R_shank", "R_knee", "R_ankle", 5, 7),
        ("pelvis_to_Lhip", "pelvis", "L_hip", 0, 2),
        ("pelvis_to_Rhip", "pelvis", "R_hip", 0, 3),
        ("pelvis_to_trunk", "pelvis", "trunk", 0, 1),
    ]

    print(f"\n  {'Segment':20s}  {'Skeleton':>10s}  {'Obs median':>10s}  {'Ratio':>8s}")
    for seg_name, parent_joint, child_joint, parent_lm_idx, child_lm_idx in segments:
        child_joint_idx = skel.joint_index(child_joint)
        skel_offset = np.linalg.norm(skel.offset(child_joint_idx))

        seg_lens = []
        for t in range(landmarks.shape[0]):
            if landmarks[t, parent_lm_idx, 3] > 0.5 and landmarks[t, child_lm_idx, 3] > 0.5:
                observed = np.linalg.norm(
                    landmarks[t, parent_lm_idx, :3] - landmarks[t, child_lm_idx, :3]
                )
                seg_lens.append(observed)

        if seg_lens:
            obs_median = np.median(seg_lens)
            ratio = obs_median / skel_offset if skel_offset > 0.001 else float("inf")
            flag = " ← MISMATCH" if abs(ratio - 1.0) > 0.15 else ""
            print(f"  {seg_name:20s}  {skel_offset:10.4f}m  {obs_median:10.4f}m  {ratio:8.2f}{flag}")
        else:
            print(f"  {seg_name:20s}  {skel_offset:10.4f}m  {'N/A':>10s}")


def main():
    # Load real data first so we can do data-driven scaling
    recordings_dir = Path("recordings")
    htmls = sorted(recordings_dir.glob("squat_*.html"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not htmls:
        print("No recordings found")
        return

    html_path = htmls[0]
    print(f"Using recording: {html_path}")

    # Load landmarks using a temp skeleton (just needs correct n_joints)
    temp_skel = scale_skeleton(1.75, 75.0)
    landmarks = load_landmarks(temp_skel, html_path)
    print(f"Loaded {landmarks.shape[0]} frames")

    # Per-segment calibration from observed landmarks
    skel = calibrate_skeleton(landmarks, 75.0)
    print(f"Calibrated skeleton: scale={skel._scale_factor:.3f}")
    desc = _build_descendants(skel)

    # Test 0: Bone length check
    check_bone_lengths(skel, landmarks)

    # Test 1: Jacobian correctness
    test_jacobian(skel, desc)

    # Find bottom frame
    hip_y = (landmarks[:, 2, 1] + landmarks[:, 3, 1]) / 2
    bottom_frame_idx = int(np.argmin(hip_y))
    print(f"\nBottom frame (by hip Y): index {bottom_frame_idx}")

    # Test 2: Single-frame fit
    test_single_frame_fit(skel, landmarks[bottom_frame_idx], desc)

    # Test 3: Smoothing impact
    test_smoothing_impact(skel, landmarks, desc)


if __name__ == "__main__":
    main()
