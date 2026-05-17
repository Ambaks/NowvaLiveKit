"""Diagnostic: compare original captured keypoints vs FK-reconstructed keypoints.

Loads the latest recording via --refit, runs IK, then compares:
  1. Original captured vis-space keypoints (what replay renders)
  2. FK-reconstructed vis-space keypoints from the IK-fitted q vector

Prints per-joint errors so we can see exactly where the roundtrip breaks.

Usage:
    PYTHONPATH=src python scripts/debug_fk_roundtrip.py
    PYTHONPATH=src python scripts/debug_fk_roundtrip.py --html recordings/squat_XXXX.html
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description="Debug FK roundtrip")
    parser.add_argument("--html", type=str, default=None,
                        help="Path to recording HTML (default: latest in recordings/)")
    args = parser.parse_args()

    from biomechanics.skeleton.anthropometry import scale_skeleton
    from biomechanics.optimizer.ik import fit_trajectory, _fk_jac, _build_descendants
    from biomechanics.optimizer.landmark_adapter import skeleton3d_to_landmarks
    from biomechanics.viewer.keypoints import q_to_keypoints_19, _fk_pos_and_rotations

    # ── Find recording ──
    if args.html:
        html_path = Path(args.html)
    else:
        recordings_dir = Path("recordings")
        htmls = sorted(recordings_dir.glob("squat_*.html"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if not htmls:
            print("No recordings found in recordings/")
            sys.exit(1)
        html_path = htmls[0]

    print(f"Recording: {html_path}")

    # ── Extract embedded DATA ──
    text = html_path.read_text()
    match = re.search(r'const DATA = ({.*?});\s*\n', text, re.DOTALL)
    if not match:
        print("ERROR: Could not find embedded DATA in HTML file.")
        sys.exit(1)
    data = json.loads(match.group(1))

    replay_reps = data["reps"]
    athlete_params = data.get("athleteParams")
    weight_kg = (athlete_params or {}).get("weightKg", 75.0)

    # ── Reconstruct skeleton (same as _run_refit) ──
    from biomechanics.utils.types import Point3D, Skeleton3D

    def vis_to_skeleton3d(kpts_vis):
        points = []
        for i in range(min(19, len(kpts_vis))):
            vis_x, vis_y, vis_z = kpts_vis[i]
            points.append(Point3D(x=-vis_z, y=-vis_y, z=vis_x, confidence=1.0))
        return Skeleton3D(keypoints=points)

    all_rep_skels = []
    for rep_frames in replay_reps:
        skels = []
        for frame in rep_frames:
            if frame is not None and frame.get("kpts"):
                skels.append(vis_to_skeleton3d(frame["kpts"]))
            else:
                skels.append(None)
        all_rep_skels.append(skels)

    ref_thigh = 0.45
    ref_shank = 0.43
    seg_lens = []
    for rep_skels in all_rep_skels:
        for skeleton_3d in rep_skels:
            if skeleton_3d is None:
                continue
            lm = skeleton3d_to_landmarks(skeleton_3d)
            if lm[4, 3] > 0.5 and lm[2, 3] > 0.5:
                seg_lens.append(np.linalg.norm(lm[4, :3] - lm[2, :3]))
            if lm[5, 3] > 0.5 and lm[3, 3] > 0.5:
                seg_lens.append(np.linalg.norm(lm[5, :3] - lm[3, :3]))
            if lm[6, 3] > 0.5 and lm[4, 3] > 0.5:
                seg_lens.append(np.linalg.norm(lm[6, :3] - lm[4, :3]))
            if lm[7, 3] > 0.5 and lm[5, 3] > 0.5:
                seg_lens.append(np.linalg.norm(lm[7, :3] - lm[5, :3]))
            if len(seg_lens) > 200:
                break

    if seg_lens:
        median_seg = float(np.median(seg_lens))
        avg_ref_seg = (ref_thigh + ref_shank) / 2
        effective_height = 1.75 * (median_seg / avg_ref_seg)
    else:
        effective_height = (athlete_params or {}).get("heightM", 1.78)

    print(f"Effective height: {effective_height:.3f}m, Weight: {weight_kg}kg")
    skeleton_obj = scale_skeleton(effective_height, weight_kg)
    descendants = _build_descendants(skeleton_obj)

    # ── COCO keypoint names for display ──
    COCO_NAMES = [
        "nose", "L_eye", "R_eye", "L_ear", "R_ear",
        "L_shoulder", "R_shoulder", "L_elbow", "R_elbow",
        "L_wrist", "R_wrist", "L_hip", "R_hip",
        "L_knee", "R_knee", "L_ankle", "R_ankle",
        "L_foot", "R_foot",
    ]

    # Lower body indices (direct from FK, not synthesized)
    LOWER_BODY = [11, 12, 13, 14, 15, 16]

    # ── Process each rep ──
    for rep_index, rep_skels in enumerate(all_rep_skels):
        valid_skels = [s for s in rep_skels if s is not None]
        if not valid_skels:
            print(f"\nRep {rep_index + 2}: no valid frames, skipping")
            continue

        valid_frames = [
            (fi, rep_skels[fi])
            for fi in range(len(rep_skels))
            if rep_skels[fi] is not None
        ]
        n_valid = len(valid_frames)

        # Build landmarks array
        landmarks = np.zeros((n_valid, skeleton_obj.n_joints, 4))
        for idx, (fi, skel) in enumerate(valid_frames):
            landmarks[idx] = skeleton3d_to_landmarks(skel)

        # IK fit (same params as _run_refit)
        ik_weights = np.array([0.5, 0.3, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.3, 0.8, 0.8])
        q_init = skeleton_obj.neutral_q()
        q_init[0] = float(np.median(landmarks[:, 0, 0]))
        q_init[1] = float(np.median(landmarks[:, 0, 1]))
        q_init[2] = float(np.median(landmarks[:, 0, 2]))
        avg_hip_y = float(np.median(landmarks[:, 2, 1] + landmarks[:, 3, 1]) / 2)
        avg_ank_y = float(np.median(landmarks[:, 6, 1] + landmarks[:, 7, 1]) / 2)
        leg_len = 0.45 * skeleton_obj._scale_factor + 0.43 * skeleton_obj._scale_factor
        vert_ratio = max(0.0, min(1.0, (avg_hip_y - avg_ank_y) / leg_len))
        init_knee_rad = np.arccos(np.clip(vert_ratio, -1, 1))
        for dname in ("L_knee", "R_knee"):
            q_init[skeleton_obj.dof_index(dname, "rx")] = init_knee_rad
        for dname in ("L_hip", "R_hip"):
            q_init[skeleton_obj.dof_index(dname, "rx")] = init_knee_rad * 0.7

        reg_weights = np.zeros(skeleton_obj.n_dof)
        reg_weights[skeleton_obj.dof_index("pelvis", "ry")] = 5.0
        reg_weights[skeleton_obj.dof_index("pelvis", "rz")] = 3.0
        reg_weights[skeleton_obj.dof_index("pelvis", "rx")] = 0.5

        print(f"\nRep {rep_index + 2}: fitting IK ({n_valid} frames, "
              f"init knee={np.degrees(init_knee_rad):.0f}deg)...")
        q_traj = fit_trajectory(skeleton_obj, landmarks, q_init=q_init,
                                weights=ik_weights, reg_weights=reg_weights,
                                q_ref=q_init.copy())

        # Find bottom frame (min hip Y in FK space)
        hip_y_values = np.empty(n_valid)
        l_hip_idx = skeleton_obj.joint_index("L_hip")
        r_hip_idx = skeleton_obj.joint_index("R_hip")
        for idx in range(n_valid):
            fk_pos, _ = _fk_jac(skeleton_obj, q_traj[idx], descendants)
            hip_y_values[idx] = (fk_pos[l_hip_idx, 1] + fk_pos[r_hip_idx, 1]) / 2.0
        bottom_idx = int(np.argmin(hip_y_values))
        original_frame_idx = valid_frames[bottom_idx][0]

        print(f"  Bottom frame: valid_idx={bottom_idx}, "
              f"original_frame_idx={original_frame_idx}")

        # ── Data at bottom frame ──
        q_bottom = q_traj[bottom_idx]
        original_frame = replay_reps[rep_index][original_frame_idx]
        original_kpts = original_frame["kpts"]

        # FK positions (raw FK space)
        fk_pos, _ = _fk_jac(skeleton_obj, q_bottom, descendants)

        # Landmarks that IK was targeting
        target_landmarks = landmarks[bottom_idx]

        # Reconstructed vis-space keypoints
        reconstructed_kpts = q_to_keypoints_19(skeleton_obj, q_bottom)

        # ── Print q vector ──
        print(f"\n  q vector (20 DOFs):")
        for (joint_name, axis), dof_idx in sorted(
            skeleton_obj._dof_map.items(), key=lambda x: x[1]
        ):
            val = q_bottom[dof_idx]
            deg_str = f" ({np.degrees(val):+.1f}deg)" if axis.startswith("r") else ""
            print(f"    q[{dof_idx:2d}] {joint_name:8s}.{axis} = {val:+.4f}{deg_str}")

        # ── Print FK joint positions vs IK target landmarks ──
        joint_names = [jd.name for jd in skeleton_obj.joints]
        print(f"\n  FK positions vs IK target landmarks (FK space):")
        print(f"    {'Joint':10s}  {'FK_x':>8s} {'FK_y':>8s} {'FK_z':>8s}  "
              f"{'TGT_x':>8s} {'TGT_y':>8s} {'TGT_z':>8s}  {'err_mm':>7s}")
        for joint_idx, joint_name in enumerate(joint_names):
            fk_xyz = fk_pos[joint_idx]
            tgt_xyz = target_landmarks[joint_idx, :3]
            err_m = np.linalg.norm(fk_xyz - tgt_xyz)
            print(f"    {joint_name:10s}  {fk_xyz[0]:+8.4f} {fk_xyz[1]:+8.4f} {fk_xyz[2]:+8.4f}  "
                  f"{tgt_xyz[0]:+8.4f} {tgt_xyz[1]:+8.4f} {tgt_xyz[2]:+8.4f}  "
                  f"{err_m * 1000:7.1f}")

        # ── Print vis-space comparison (lower body only) ──
        print(f"\n  Vis-space keypoints: original (replay) vs reconstructed (FK):")
        print(f"    {'Keypoint':12s}  {'Orig_x':>8s} {'Orig_y':>8s} {'Orig_z':>8s}  "
              f"{'Reco_x':>8s} {'Reco_y':>8s} {'Reco_z':>8s}  {'err_mm':>7s}")

        for kpt_idx in LOWER_BODY:
            name = COCO_NAMES[kpt_idx]
            orig = original_kpts[kpt_idx] if kpt_idx < len(original_kpts) else [0, 0, 0]
            reco = reconstructed_kpts[kpt_idx]
            err_m = np.linalg.norm(np.array(orig) - np.array(reco))
            print(f"    {name:12s}  {orig[0]:+8.4f} {orig[1]:+8.4f} {orig[2]:+8.4f}  "
                  f"{reco[0]:+8.4f} {reco[1]:+8.4f} {reco[2]:+8.4f}  "
                  f"{err_m * 1000:7.1f}")

        # Also show original grounding info
        orig_ankle_l = original_kpts[15] if len(original_kpts) > 15 else [0, 0, 0]
        orig_ankle_r = original_kpts[16] if len(original_kpts) > 16 else [0, 0, 0]
        print(f"\n  Original ankle Y: L={orig_ankle_l[1]:.4f}, R={orig_ankle_r[1]:.4f}")
        print(f"  Reconstructed ankle Y: L={reconstructed_kpts[15][1]:.4f}, "
              f"R={reconstructed_kpts[16][1]:.4f}")

        # Dump to JSON for further analysis
        output = {
            "rep_number": rep_index + 2,
            "bottom_frame_index": original_frame_idx,
            "effective_height": effective_height,
            "q_bottom": q_bottom.tolist(),
            "original_kpts_vis": original_kpts,
            "reconstructed_kpts_vis": reconstructed_kpts,
            "fk_positions": fk_pos.tolist(),
            "ik_target_landmarks": target_landmarks.tolist(),
        }
        out_path = Path(f"recordings/debug_fk_roundtrip_rep{rep_index + 2}.json")
        out_path.write_text(json.dumps(output, indent=2))
        print(f"\n  Dumped to: {out_path}")


if __name__ == "__main__":
    main()
