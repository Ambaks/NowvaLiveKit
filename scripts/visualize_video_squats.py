#!/usr/bin/env python3
"""
Live-capture squat visualizer.

Flow:
  1. Open webcam with live skeleton preview
  2. Calibration: wait for stable keypoint detection (low jitter)
  3. Press SPACE to start recording
  4. Record until 5 reps are detected (rep counter runs live)
  5. Save video, generate 3D replay HTML, open in browser

Usage:
    python scripts/visualize_video_squats.py
    python scripts/visualize_video_squats.py --output my_session.mp4 --camera 0
"""

import argparse
import json
import re
import sys
import time
import webbrowser
from collections import deque
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import cv2
import numpy as np

from biomechanics.pose.mediapipe_fallback import MediaPipePoseEstimator
from biomechanics.kinematics.analytical_ik import AnalyticalIKSolver
from biomechanics.faults.rep_counter import RepCounter, RepCounterConfig
from biomechanics.utils.filters import JointAngleFilter
from biomechanics.utils.derivatives import DerivativeTracker
from biomechanics.utils.confidence_blend import ConfidenceBlender
from biomechanics.utils.velocity_clamp import VelocityClamp
from biomechanics.utils.bone_constraints import BoneLengthConstraints
from biomechanics.utils.position_filter import KeypointPositionSmoother
from biomechanics.utils.predictive_state import PredictiveStateEstimator
from biomechanics.utils.standing_gate import StandingPoseGate
from utils.memory_profiler import MemoryProfiler


COCO_CONNECTIONS = [
    (0, 1), (0, 2), (1, 3), (2, 4),
    (0, 5), (0, 6),
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
    (15, 17), (16, 18),
]

TARGET_REPS = 5
CALIBRATION_FRAMES = 30  # frames of stable detection before ready
JITTER_THRESHOLD = 8.0   # max pixel stddev across calibration window


def draw_skeleton(frame, skeleton_2d, color=(0, 255, 0)):
    if skeleton_2d is None:
        return
    for i, j in COCO_CONNECTIONS:
        kp1, kp2 = skeleton_2d.keypoints[i], skeleton_2d.keypoints[j]
        if kp1.confidence > 0.3 and kp2.confidence > 0.3:
            cv2.line(frame, (int(kp1.x), int(kp1.y)),
                     (int(kp2.x), int(kp2.y)), color, 2)
    for kp in skeleton_2d.keypoints[:19]:
        if kp.confidence > 0.3:
            cv2.circle(frame, (int(kp.x), int(kp.y)), 5, color, -1)


def draw_banner(frame, text, color=(40, 40, 40), text_color=(255, 255, 255)):
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 60), color, -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
    cv2.putText(frame, text, (20, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.0, text_color, 2)


def draw_status(frame, lines, y_start=80):
    for i, (text, color) in enumerate(lines):
        cv2.putText(frame, text, (20, y_start + i * 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1)


def check_stability(history):
    """Check if recent keypoint positions are stable (low jitter)."""
    if len(history) < CALIBRATION_FRAMES:
        return False, 999.0
    arr = np.array(history)  # (N, 17, 2)
    stddev = arr.std(axis=0).mean()
    return stddev < JITTER_THRESHOLD, stddev


def extract_frame_data(skeleton_3d, angles, frame_idx):
    """Convert a single frame's 3D skeleton + angles to viewer format."""
    kpts_mp = skeleton_3d.to_numpy()[:19]
    kpts_vis = np.zeros_like(kpts_mp)
    kpts_vis[:, 0] = kpts_mp[:, 2]   # vis_x = mp_z
    kpts_vis[:, 1] = -kpts_mp[:, 1]  # vis_y = -mp_y
    kpts_vis[:, 2] = -kpts_mp[:, 0]  # vis_z = -mp_x
    # Feet parallel to ground: project foot_index Y to ankle Y
    kpts_vis[17][1] = kpts_vis[15][1]
    kpts_vis[18][1] = kpts_vis[16][1]
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
        "frame": frame_idx,
    }


def ground_and_center(rep_frames):
    for frame in rep_frames:
        if frame is None:
            continue
        kpts = np.array(frame["kpts"])
        ankle_y = min(kpts[15][1], kpts[16][1])
        kpts[:, 1] -= ankle_y
        hip_mid_x = (kpts[11][0] + kpts[12][0]) / 2
        hip_mid_z = (kpts[11][2] + kpts[12][2]) / 2
        kpts[:, 0] -= hip_mid_x
        kpts[:, 2] -= hip_mid_z
        frame["kpts"] = kpts.tolist()


def add_phase_to_rep(rep_frames):
    """Add normalized phase (0=standing, ~1=max depth) to each frame."""
    max_kf = max(
        (f["angles"]["knee_flex"] for f in rep_frames if f is not None),
        default=1.0,
    )
    for f in rep_frames:
        if f is None:
            continue
        f["phase"] = f["angles"]["knee_flex"] / max(max_kf, 1.0)


def compute_baseline(rep_frames):
    peak_trunk_offset = 0.0
    peak_valgus = 0.0
    peak_knee_flex = 0.0
    peak_dorsi = 0.0
    for f in rep_frames:
        if f is None:
            continue
        a = f["angles"]
        peak_trunk_offset = max(peak_trunk_offset, 180 - a["trunk_flexion"])
        peak_valgus = max(peak_valgus, abs(a["knee_valgus_l"]), abs(a["knee_valgus_r"]))
        peak_knee_flex = max(peak_knee_flex, a["knee_flex"])
        peak_dorsi = max(peak_dorsi, a["dorsi_l"], a["dorsi_r"])
    return {
        "peakTrunkOffset": round(peak_trunk_offset, 2),
        "peakValgus": round(peak_valgus, 2),
        "peakKneeFlex": round(peak_knee_flex, 2),
        "peakDorsi": round(peak_dorsi, 2),
        "leanThresholds": {
            "mild": round(peak_trunk_offset + 10, 1),
            "moderate": round(peak_trunk_offset + 15, 1),
            "severe": round(peak_trunk_offset + 20, 1),
        },
        "valgusThresholds": {
            "mild": round(peak_valgus + 5, 1),
            "moderate": round(peak_valgus + 10, 1),
            "severe": round(peak_valgus + 15, 1),
        },
    }


def compute_athlete_params(frames_data, rep_boundaries, bone_constraints):
    """Reverse-compute athlete parameters for the synthetic visualizer."""
    from biomechanics.utils.types import CocoKeypoints as CK

    props = bone_constraints.body_proportions
    if props is None:
        return None

    cal = bone_constraints._calibrated_lengths

    REF_HIP_WIDTH = 0.22
    REF_TORSO = 0.50
    REF_THIGH = 0.42
    REF_SHIN = 0.40
    REF_UPPER_ARM = 0.30
    REF_FOREARM = 0.26
    REF_SHOULDER_W = 0.36

    raw_torso = props.torso_length_avg / REF_TORSO
    raw_thigh = props.femur_length_avg / REF_THIGH
    raw_shin = props.tibia_length_avg / REF_SHIN
    body_scale = (raw_torso + raw_thigh + raw_shin) / 3.0
    torso_ratio = raw_torso / body_scale
    thigh_ratio = raw_thigh / body_scale
    shin_ratio = raw_shin / body_scale

    # Arm ratios from calibrated bone lengths (split upper arm / forearm)
    upper_arm_l = cal.get((CK.LEFT_SHOULDER, CK.LEFT_ELBOW), REF_UPPER_ARM)
    upper_arm_r = cal.get((CK.RIGHT_SHOULDER, CK.RIGHT_ELBOW), REF_UPPER_ARM)
    forearm_l = cal.get((CK.LEFT_ELBOW, CK.LEFT_WRIST), REF_FOREARM)
    forearm_r = cal.get((CK.RIGHT_ELBOW, CK.RIGHT_WRIST), REF_FOREARM)
    upper_arm_avg = (upper_arm_l + upper_arm_r) / 2.0
    forearm_avg = (forearm_l + forearm_r) / 2.0
    upper_arm_ratio = (upper_arm_avg / REF_UPPER_ARM) / body_scale
    forearm_ratio = (forearm_avg / REF_FOREARM) / body_scale
    arm_ratio = (upper_arm_ratio + forearm_ratio) / 2.0

    shoulder_width = cal.get((CK.LEFT_SHOULDER, CK.RIGHT_SHOULDER), REF_SHOULDER_W)
    shoulder_width_ratio = (shoulder_width / REF_SHOULDER_W) / body_scale

    REF_FOOT = 0.26
    foot_l = cal.get((CK.LEFT_ANKLE, CK.LEFT_FOOT_INDEX), REF_FOOT)
    foot_r = cal.get((CK.RIGHT_ANKLE, CK.RIGHT_FOOT_INDEX), REF_FOOT)
    foot_avg = (foot_l + foot_r) / 2.0
    foot_ratio = (foot_avg / REF_FOOT) / body_scale

    # Stance width & toe-out from standing frames (before first rep)
    first_rep_start = rep_boundaries[0][0] if rep_boundaries else len(frames_data)
    standing_frames = [f for f in frames_data[:first_rep_start] if f is not None]
    sample = standing_frames[-10:] if len(standing_frames) >= 10 else standing_frames

    stance_widths = []
    toe_outs = []

    for f in sample:
        kpts = np.array(f["kpts"])
        if len(kpts) < 19:
            continue

        l_ankle, r_ankle = kpts[15], kpts[16]
        ankle_z_dist = abs(r_ankle[2] - l_ankle[2])
        fk_hip_width = REF_HIP_WIDTH * body_scale
        stance_widths.append(ankle_z_dist / fk_hip_width)

        # Toe-out: ankle→foot_index projected onto ground plane vs forward
        # vis_x = mp_z which points backward (away from person), so forward = -x
        forward = np.array([-1.0, 0.0])
        for ankle_idx, foot_idx in [(15, 17), (16, 18)]:
            vec = kpts[foot_idx] - kpts[ankle_idx]
            vec_xz = np.array([vec[0], vec[2]])
            norm = np.linalg.norm(vec_xz)
            if norm > 1e-6:
                cos_a = np.clip(np.dot(vec_xz, forward) / norm, -1, 1)
                toe_outs.append(np.degrees(np.arccos(cos_a)))

    stance_width = float(np.median(stance_widths)) if stance_widths else 1.2
    toe_out = float(np.median(toe_outs)) if toe_outs else 15.0

    # Find peak depth frame and extract angles at that point
    peak_dorsi_ratio = 0.15
    max_knee = 0.0
    peak_trunk_offset = 0.0
    peak_valgus = 0.0
    peak_shoulder_flex = 0.0
    peak_elbow_flex = 0.0
    for f in frames_data:
        if f is None:
            continue
        a = f["angles"]
        if a["knee_flex"] > max_knee:
            max_knee = a["knee_flex"]
            avg_dorsi = (a["dorsi_l"] + a["dorsi_r"]) / 2.0
            if max_knee > 5:
                peak_dorsi_ratio = avg_dorsi / max_knee
            peak_trunk_offset = 180 - a["trunk_flexion"]
            peak_valgus = max(abs(a["knee_valgus_l"]), abs(a["knee_valgus_r"]))
            peak_shoulder_flex = (a["shoulder_flex_l"] + a["shoulder_flex_r"]) / 2.0
            peak_elbow_flex = (a["elbow_flex_l"] + a["elbow_flex_r"]) / 2.0

    return {
        "bodyScale": round(body_scale, 3),
        "torsoRatio": round(torso_ratio, 3),
        "thighRatio": round(thigh_ratio, 3),
        "shinRatio": round(shin_ratio, 3),
        "armRatio": round(arm_ratio, 3),
        "upperArmRatio": round(upper_arm_ratio, 3),
        "forearmRatio": round(forearm_ratio, 3),
        "shoulderWidthRatio": round(shoulder_width_ratio, 3),
        "footRatio": round(foot_ratio, 3),
        "stanceWidth": round(stance_width, 2),
        "toeOut": round(toe_out, 1),
        "dorsiRatio": round(peak_dorsi_ratio, 3),
        "maxKneeFlex": round(max_knee, 1),
        "forwardLean": round(peak_trunk_offset, 1),
        "kneeValgus": round(peak_valgus, 1),
        "shoulderFlex": round(peak_shoulder_flex, 1),
        "elbowFlex": round(peak_elbow_flex, 1),
        "hip_width_m": round(props.hip_width, 4),
        "femur_avg_m": round(props.femur_length_avg, 4),
        "tibia_avg_m": round(props.tibia_length_avg, 4),
        "torso_avg_m": round(props.torso_length_avg, 4),
        "upper_arm_avg_m": round(upper_arm_avg, 4),
        "forearm_avg_m": round(forearm_avg, 4),
        "shoulder_width_m": round(shoulder_width, 4),
        "foot_avg_m": round(foot_avg, 4),
    }


def run_capture(camera_id, video_output_path, profiler=None):
    """Run the full capture session: calibrate → record → return data."""
    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        print(f"ERROR: Could not open camera {camera_id}")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    print(f"Camera {camera_id}: {w}x{h} @ {fps:.0f}fps")
    print("Stand back so your full body is visible.")
    print("Recording starts automatically after calibration. Q=quit\n")

    pose = MediaPipePoseEstimator(model_complexity=1)
    ik = AnalyticalIKSolver()
    angle_filter = JointAngleFilter(min_cutoff=1.0, beta=0.007)
    deriv_tracker = DerivativeTracker(smoothing_alpha=0.3)
    rep_counter = RepCounter(RepCounterConfig(
        entry_knee_angle=30.0,
        exit_knee_angle=25.0,
        min_depth_knee_angle=95.0,
        min_rep_duration_frames=15,
    ))

    # Pre-IK filters (matches production pipeline)
    standing_gate = StandingPoseGate(
        min_confidence=0.5,
        max_knee_flexion_deg=20.0,
        max_trunk_flexion_deg=25.0,
        min_torso_length_m=0.25,
        max_torso_length_m=0.80,
        required_consecutive_frames=5,
    )
    confidence_blender = ConfidenceBlender(min_confidence=0.1, max_confidence=0.9)
    velocity_clamp = VelocityClamp(max_velocity_m_per_s=2.5, target_fps=int(fps))
    bone_constraints = BoneLengthConstraints(
        calibration_frames=30, tolerance=0.15, standing_gate=standing_gate,
    )
    position_smoother = KeypointPositionSmoother(min_cutoff=0.8, beta=4.0, d_cutoff=1.0)
    predictive_estimator = PredictiveStateEstimator(
        horizon_seconds=0.2, max_extrapolation_deg=15.0,
    )
    proportions_applied = False

    # State
    state = "calibrating"  # calibrating → recording → done
    kpt_history = deque(maxlen=CALIBRATION_FRAMES)
    stable = False
    jitter = 999.0

    video_writer = None
    frames_data = []
    skeletons_3d = []
    reps = []
    rep_boundaries = []
    current_rep_start = None
    prev_in_rep = False
    rec_frame_idx = 0
    rec_start_time = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        display = frame.copy()
        skeleton_2d, skeleton_3d = pose.estimate_both(frame)
        angles = None

        if skeleton_3d is not None:
            # Standing gate (feeds bone constraint calibration)
            standing_gate.check(skeleton_3d)

            # Pre-IK filtering chain (matches production pipeline)
            skeleton_3d = confidence_blender.blend(skeleton_3d)
            skeleton_3d = velocity_clamp.clamp(skeleton_3d)
            skeleton_3d = bone_constraints.enforce(skeleton_3d)
            skeleton_3d = position_smoother.smooth(skeleton_3d)

            # Apply body proportions once after bone calibration
            if (
                not proportions_applied
                and bone_constraints.is_calibrated
                and bone_constraints.body_proportions is not None
            ):
                ik.set_body_proportions(bone_constraints.body_proportions)
                proportions_applied = True

            # IK solve on filtered skeleton
            raw_angles = ik.solve(skeleton_3d)
            raw_angles.timestamp = time.time()
            angles = angle_filter.filter_angles(raw_angles)
            angles.timestamp = raw_angles.timestamp

        # --- CALIBRATING ---
        if state == "calibrating":
            if skeleton_2d is not None:
                pts = [(kp.x, kp.y) for kp in skeleton_2d.keypoints[:17]
                       if kp.confidence > 0.3]
                if len(pts) >= 12:
                    kpt_history.append(pts[:12])  # use first 12 visible
                else:
                    kpt_history.clear()

                # Need uniform length for stability check
                if len(kpt_history) == CALIBRATION_FRAMES:
                    min_len = min(len(p) for p in kpt_history)
                    trimmed = [p[:min_len] for p in kpt_history]
                    stable, jitter = check_stability(trimmed)
                    if stable:
                        state = "recording"
                        rec_start_time = time.time()
                        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                        video_writer = cv2.VideoWriter(str(video_output_path), fourcc, fps, (w, h))
                        angle_filter = JointAngleFilter(min_cutoff=1.0, beta=0.007)
                        deriv_tracker = DerivativeTracker(smoothing_alpha=0.3)
                        print("Calibration complete — recording started automatically.")
                        print(f"Recording → {video_output_path}")

            draw_skeleton(display, skeleton_2d, (100, 200, 255))
            pct = min(100, int(len(kpt_history) / CALIBRATION_FRAMES * 100))
            bone_cal = "done" if bone_constraints.is_calibrated else "calibrating"
            draw_banner(display, f"CALIBRATING... {pct}%  (jitter: {jitter:.1f}px)",
                        (40, 60, 80), (200, 220, 255))
            status = [
                (f"Visible keypoints: {sum(1 for kp in (skeleton_2d.keypoints[:17] if skeleton_2d else []) if kp.confidence > 0.3)}/17",
                 (180, 180, 200)),
                (f"Bone calibration: {bone_cal} | Standing gate: {'ready' if standing_gate.is_ready else 'waiting'}",
                 (180, 180, 200)),
                ("Stand still with full body visible", (150, 150, 170)),
            ]
            draw_status(display, status)

        # --- RECORDING ---
        elif state == "recording":
            elapsed = time.time() - rec_start_time
            if video_writer is not None:
                video_writer.write(frame)

            if skeleton_3d is not None and angles is not None:
                derivs = deriv_tracker.update(angles)

                # Predictive estimation for fault evaluation (200ms lookahead)
                eval_angles = predictive_estimator.predict(angles, derivs)

                rep_data, _ = rep_counter.update(angles, derivs)

                # Phase-aware smoothing (heavier during idle, lighter during movement)
                angle_filter.update_phase(rep_counter.phase)

                in_rep = rep_counter.in_rep
                if in_rep and not prev_in_rep:
                    current_rep_start = rec_frame_idx
                if not in_rep and prev_in_rep and current_rep_start is not None:
                    rep_boundaries.append((current_rep_start, rec_frame_idx))
                    current_rep_start = None
                prev_in_rep = in_rep

                if rep_data is not None:
                    reps.append(rep_data)
                    print(f"  Rep {rep_data.rep_number}: depth={rep_data.max_depth_angle:.1f}°")

                fd = extract_frame_data(skeleton_3d, angles, rec_frame_idx)
                frames_data.append(fd)
                skeletons_3d.append(skeleton_3d)
            else:
                frames_data.append(None)
                skeletons_3d.append(None)

            rec_frame_idx += 1
            if profiler:
                profiler.snapshot(rec_frame_idx)

            # Check if we have enough reps
            if len(reps) >= TARGET_REPS:
                state = "done"
                print(f"\n{TARGET_REPS} reps captured!")

            skel_color = (0, 200, 255) if rep_counter.in_rep else (0, 255, 0)
            draw_skeleton(display, skeleton_2d, skel_color)

            phase_name = rep_counter.phase.upper() if hasattr(rep_counter, 'phase') else ""
            draw_banner(display,
                        f"RECORDING  Rep {len(reps)}/{TARGET_REPS}  "
                        f"[{phase_name}]  {elapsed:.1f}s",
                        (80, 20, 20), (255, 100, 100))
            if angles:
                status = [
                    (f"Knee: {angles.avg_knee_flexion:.1f}°  "
                     f"Trunk: {angles.trunk_flexion:.1f}°  "
                     f"Depth: {rep_counter._max_depth_angle:.0f}°",
                     (200, 200, 220)),
                ]
                draw_status(display, status)

        # --- DONE ---
        elif state == "done":
            draw_banner(display, f"DONE — {len(reps)} reps captured. Processing...",
                        (20, 60, 20), (100, 255, 100))
            cv2.imshow("Squat Capture", display)
            cv2.waitKey(500)
            break

        cv2.imshow("Squat Capture", display)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            print("Quit.")
            cap.release()
            if video_writer:
                video_writer.release()
            cv2.destroyAllWindows()
            pose.release()
            sys.exit(0)


    cap.release()
    if video_writer:
        video_writer.release()
    cv2.destroyAllWindows()
    pose.release()

    return frames_data, reps, rep_boundaries, fps, bone_constraints, skeletons_3d


def serialize_kinodynamics_state(skeleton, q_trajectory_per_rep, foot_targets_per_rep=None,
                                  faults_per_rep=None, rep_boundaries=None,
                                  joint_angles_per_rep=None):
    """Serialize pipeline state for the browser-side KinodynamicsSolver.

    Parameters
    ----------
    skeleton : SkeletonModel (must have joint_masses set via scale_skeleton)
    q_trajectory_per_rep : list of (T_i, n_dof) ndarrays, one per rep
    foot_targets_per_rep : list of (T_i, 2, 3) ndarrays (L/R ankle world pos)
    faults_per_rep : list of fault dicts per rep
    rep_boundaries : list of [start_frame, end_frame, bottom_frame] per rep
    joint_angles_per_rep : list of per-frame JointAngles dicts per rep
    """
    joints_ser = []
    for jd in skeleton.joints:
        joints_ser.append({
            "name": jd.name,
            "parent": jd.parent,
            "offset": [float(x) for x in jd.offset],
            "dof_axes": list(jd.dof_axes),
            "limits": [[float(lo), float(hi)] for lo, hi in jd.limits],
        })

    dof_map = {}
    for (joint, axis), idx in skeleton._dof_map.items():
        dof_map[f"{joint}.{axis}"] = idx

    bounds = skeleton.bounds()

    skel_def = {
        "joints": joints_ser,
        "n_dof": skeleton.n_dof,
        "n_joints": skeleton.n_joints,
        "dof_map": dof_map,
        "bounds": [[float(lo), float(hi)] for lo, hi in bounds],
        "joint_masses": (
            [float(x) for x in skeleton.joint_masses]
            if skeleton.joint_masses is not None
            else None
        ),
    }

    reps_ser = []
    for i, qt in enumerate(q_trajectory_per_rep):
        rep = {"q_trajectory": qt.tolist()}
        if foot_targets_per_rep and i < len(foot_targets_per_rep):
            ft = foot_targets_per_rep[i]
            rep["foot_targets"] = ft.tolist() if hasattr(ft, "tolist") else ft
        if faults_per_rep and i < len(faults_per_rep):
            rep["faults"] = faults_per_rep[i]
        if joint_angles_per_rep and i < len(joint_angles_per_rep):
            rep["joint_angles"] = joint_angles_per_rep[i]
        reps_ser.append(rep)

    result = {"skeleton_def": skel_def, "reps": reps_ser}
    if rep_boundaries is not None:
        result["rep_boundaries"] = (
            rep_boundaries.tolist()
            if hasattr(rep_boundaries, "tolist")
            else rep_boundaries
        )
    return result


def build_html(baseline, replay_reps_data, fps, athlete_params=None, kinodynamics_state=None):
    data_json = json.dumps({
        "baseline": baseline,
        "reps": replay_reps_data,
        "fps": fps,
        "athleteParams": athlete_params,
    })
    kino_json = json.dumps(kinodynamics_state) if kinodynamics_state else "null"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Squat Video Replay</title>
<script type="importmap">
{{
    "imports": {{
        "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
        "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
    }}
}}
</script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: #0a0a1a; color: #e0e0e0;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    overflow: hidden; height: 100vh; display: flex;
}}
#scene-container {{ flex: 1; position: relative; }}
#controls {{
    width: 380px; background: #12122a; border-left: 1px solid #2a2a4a;
    overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 14px;
}}
h1 {{ font-size: 18px; font-weight: 600; color: #a0a0ff; margin-bottom: 4px; }}
.section {{
    background: #1a1a35; border: 1px solid #2a2a4a; border-radius: 8px; padding: 14px;
    transition: opacity 0.3s;
}}
.section-title {{
    font-size: 13px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 1px; margin-bottom: 10px; display: flex; align-items: center; gap: 8px;
}}
.section-title .dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}
.baseline .section-title {{ color: #2ecc71; }}  .baseline .dot {{ background: #2ecc71; }}
.angles .section-title {{ color: #a0a0ff; }}    .angles .dot {{ background: #a0a0ff; }}
.faults .section-title {{ color: #ff6b6b; }}    .faults .dot {{ background: #ff6b6b; }}
.playback .section-title {{ color: #ffd93d; }}  .playback .dot {{ background: #ffd93d; }}
.mono {{ font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; line-height: 1.8; }}
.lbl {{ color: #888; }} .val {{ color: #a0a0ff; }}
.val-green {{ color: #2ecc71; font-weight: 600; }}
.severity-indicator {{
    font-size: 11px; padding: 2px 8px; border-radius: 10px; margin-left: 4px; font-weight: 600;
}}
.sev-none {{ background: #1a3a2a; color: #2ecc71; }}
.sev-mild {{ background: #3a3a1a; color: #f1c40f; }}
.sev-moderate {{ background: #3a2a1a; color: #e67e22; }}
.sev-severe {{ background: #3a1a1a; color: #e74c3c; }}
.anim-controls {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
.anim-controls button {{
    width: 32px; height: 32px; border-radius: 50%; border: 1px solid #3a3a5a;
    background: #2a2a4a; color: #e0e0e0; font-size: 14px; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
}}
.anim-controls button:hover {{ background: #3a3a5a; }}
.slider-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
.slider-row label {{ font-size: 12px; color: #b0b0cc; min-width: 90px; flex-shrink: 0; }}
.slider-row input[type="range"] {{
    flex: 1; -webkit-appearance: none; height: 4px; background: #2a2a4a;
    border-radius: 2px; outline: none;
}}
.slider-row input[type="range"]::-webkit-slider-thumb {{
    -webkit-appearance: none; width: 14px; height: 14px; border-radius: 50%;
    background: #6060ff; cursor: pointer;
}}
.slider-row .value {{
    font-size: 12px; color: #8080cc; min-width: 42px; text-align: right;
    font-family: 'SF Mono', 'Fira Code', monospace;
}}
#info-overlay {{
    position: absolute; top: 12px; left: 12px;
    background: rgba(18, 18, 42, 0.85); border: 1px solid #2a2a4a;
    border-radius: 8px; padding: 10px 14px; font-size: 12px;
    font-family: 'SF Mono', 'Fira Code', monospace; line-height: 1.6;
    pointer-events: none;
}}
#info-overlay .lbl {{ color: #888; }} #info-overlay .val {{ color: #a0a0ff; }}
#ground-label {{
    position: absolute; bottom: 12px; left: 12px; font-size: 11px;
    color: #555; pointer-events: none;
}}
.rep-btn {{
    padding: 6px 14px; border: 1px solid #3a3a5a; border-radius: 6px;
    background: #2a2a4a; color: #b0b0cc; font-size: 12px; font-weight: 600;
    cursor: pointer; transition: all 0.2s;
}}
.rep-btn:hover {{ background: #3a3a5a; }}
.rep-btn.active {{ background: #4040cc; color: white; border-color: #6060ff; }}
.athlete .section-title {{ color: #c090ff; }} .athlete .dot {{ background: #c090ff; }}
.sandbox .section-title {{ color: #4ecdc4; }} .sandbox .dot {{ background: #4ecdc4; }}
.barbell-s .section-title {{ color: #f0a040; }} .barbell-s .dot {{ background: #f0a040; }}
.mode-tab {{
    padding: 5px 14px; border: 1px solid #3a3a5a; border-radius: 6px;
    background: #2a2a4a; color: #b0b0cc; font-size: 12px; font-weight: 600;
    cursor: pointer; transition: all 0.2s;
}}
.mode-tab:hover {{ background: #3a3a5a; }}
.mode-tab.active {{ background: #4040cc; color: white; border-color: #6060ff; }}
.threshold-bar {{ display: flex; height: 8px; border-radius: 4px; overflow: hidden; margin: 8px 0; }}
.threshold-bar .band {{ height: 100%; }}
.threshold-legend {{ display: flex; gap: 8px; font-size: 10px; margin-bottom: 4px; }}
.threshold-legend span {{ padding: 1px 6px; border-radius: 3px; }}
.legend-ok {{ background: #1a3a2a; color: #2ecc71; }}
.legend-mild {{ background: #3a3a1a; color: #f1c40f; }}
.legend-moderate {{ background: #3a2a1a; color: #e67e22; }}
.legend-severe {{ background: #3a1a1a; color: #e74c3c; }}
.balance-ok {{ color: #2ecc71; font-weight: 600; }}
.balance-bad {{ color: #ff4444; font-weight: 600; }}
#sb-kino-controls input[type="checkbox"] {{ accent-color: #4ecdc4; }}
.kino-fault-item {{ padding: 2px 0; }}
.kino-fault-item .sev {{ font-size: 10px; padding: 1px 6px; border-radius: 8px; font-weight: 600; }}
.kino-fault-item .sev-mild {{ background: #3a3a1a; color: #f1c40f; }}
.kino-fault-item .sev-moderate {{ background: #3a2a1a; color: #e67e22; }}
.kino-fault-item .sev-severe {{ background: #3a1a1a; color: #e74c3c; }}
</style>
</head>
<body>
<div id="scene-container">
    <canvas id="three-canvas"></canvas>
    <div id="info-overlay"></div>
    <div id="ground-label">Drag to orbit | Scroll to zoom</div>
</div>
<div id="controls">
    <div>
        <h1>Squat Replay</h1>
        <div style="display:flex; gap:8px; margin-top:8px;">
            <button class="mode-tab active" id="tab-replay">Replay</button>
            <button class="mode-tab" id="tab-sandbox">Sandbox</button>
        </div>
    </div>

    <!-- ======== REPLAY PANEL ======== -->
    <div id="replay-panel">
        <div class="section baseline">
            <div class="section-title"><span class="dot"></span> Baseline (Rep 1)</div>
            <div class="mono" id="baseline-info"></div>
        </div>
        <div class="section athlete">
            <div class="section-title"><span class="dot"></span> Athlete Stats</div>
            <div class="mono" id="athlete-info"></div>
        </div>
        <div class="section playback">
            <div class="section-title"><span class="dot"></span> Playback</div>
            <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:10px;" id="rep-buttons"></div>
            <div class="anim-controls">
                <button id="play-btn" title="Play/Pause">&#9646;&#9646;</button>
                <input type="range" id="frame-scrubber" min="0" max="100" value="0" step="1">
                <span class="value" id="frame-val" style="min-width:50px;">0/0</span>
            </div>
            <div class="slider-row">
                <label>Speed</label>
                <input type="range" id="speed-slider" min="0.1" max="3.0" value="1.0" step="0.1">
                <span class="value" id="speed-val">1.0x</span>
            </div>
        </div>
        <div class="section angles">
            <div class="section-title"><span class="dot"></span> Live Angles</div>
            <div class="mono" id="angles-info"></div>
        </div>
        <div class="section faults">
            <div class="section-title"><span class="dot"></span> Fault Classification</div>
            <div class="mono" id="faults-info"></div>
        </div>
    </div>

    <!-- ======== SANDBOX PANEL ======== -->
    <div id="sandbox-panel" style="display:none">
        <div class="section sandbox">
            <div class="section-title"><span class="dot"></span> Body Proportions</div>
            <div class="slider-row"><label>Body scale</label><input type="range" id="sb-body-scale" min="0.7" max="1.3" value="1.0" step="0.01"><span class="value" id="sb-body-scale-val">1.00</span></div>
            <div class="slider-row"><label>Torso ratio</label><input type="range" id="sb-torso-ratio" min="0.8" max="1.2" value="1.0" step="0.01"><span class="value" id="sb-torso-ratio-val">1.00</span></div>
            <div class="slider-row"><label>Thigh ratio</label><input type="range" id="sb-thigh-ratio" min="0.8" max="1.2" value="1.0" step="0.01"><span class="value" id="sb-thigh-ratio-val">1.00</span></div>
            <div class="slider-row"><label>Shin ratio</label><input type="range" id="sb-shin-ratio" min="0.8" max="1.2" value="1.0" step="0.01"><span class="value" id="sb-shin-ratio-val">1.00</span></div>
            <div class="slider-row"><label>Shoulder width</label><input type="range" id="sb-shoulder-width-ratio" min="0.8" max="1.2" value="1.0" step="0.01"><span class="value" id="sb-shoulder-width-ratio-val">1.00</span></div>
            <div class="slider-row"><label>Foot ratio</label><input type="range" id="sb-foot-ratio" min="0.5" max="1.5" value="1.0" step="0.01"><span class="value" id="sb-foot-ratio-val">1.00</span></div>
        </div>
        <div class="section sandbox">
            <div class="section-title"><span class="dot"></span> Stance</div>
            <div class="slider-row"><label>Stance width</label><input type="range" id="sb-stance-width" min="0.8" max="2.5" value="1.2" step="0.05"><span class="value" id="sb-stance-width-val">1.20x</span></div>
            <div class="slider-row"><label>Toe-out angle</label><input type="range" id="sb-toe-out" min="0" max="45" value="15" step="1"><span class="value" id="sb-toe-out-val">15°</span></div>
        </div>
        <div class="section barbell-s">
            <div class="section-title"><span class="dot"></span> Barbell</div>
            <div class="slider-row"><label>Weight</label><input type="range" id="sb-barbell-weight" min="0" max="200" value="0" step="5"><span class="value" id="sb-barbell-weight-val">0 kg</span></div>
            <div class="slider-row"><label>Body mass</label><input type="range" id="sb-body-mass" min="40" max="150" value="75" step="1"><span class="value" id="sb-body-mass-val">75 kg</span></div>
        </div>
        <div class="section sandbox">
            <div class="section-title"><span class="dot"></span> Knee Flexion (delta)</div>
            <div class="slider-row"><label>Knee flex &Delta;</label><input type="range" id="sb-d-knee-flex" min="-30" max="30" value="0" step="1"><span class="value" id="sb-d-knee-flex-val">0°</span></div>
        </div>
        <div class="section sandbox">
            <div class="section-title"><span class="dot"></span> Dorsiflexion (delta)</div>
            <div class="slider-row"><label>Both ankles &Delta;</label><input type="range" id="sb-d-dorsi" min="-20" max="20" value="0" step="0.5"><span class="value" id="sb-d-dorsi-val">0°</span></div>
            <div class="slider-row"><label>Left ankle &Delta;</label><input type="range" id="sb-d-dorsi-l" min="-20" max="20" value="0" step="0.5"><span class="value" id="sb-d-dorsi-l-val">0°</span></div>
            <div class="slider-row"><label>Right ankle &Delta;</label><input type="range" id="sb-d-dorsi-r" min="-20" max="20" value="0" step="0.5"><span class="value" id="sb-d-dorsi-r-val">0°</span></div>
        </div>
        <div class="section sandbox">
            <div class="section-title"><span class="dot"></span> Trunk Lean (delta)</div>
            <div class="slider-row"><label>Forward lean &Delta;</label><input type="range" id="sb-d-forward-lean" min="-30" max="30" value="0" step="1"><span class="value" id="sb-d-forward-lean-val">0°</span></div>
        </div>
        <div class="section faults">
            <div class="section-title"><span class="dot"></span> Forward Lean (thresholds)</div>
            <div class="threshold-legend"><span class="legend-ok">OK</span><span class="legend-mild">Mild</span><span class="legend-moderate">Moderate</span><span class="legend-severe">Severe</span></div>
            <div class="threshold-bar" id="sb-lean-threshold-bar"></div>
        </div>
        <div class="section faults">
            <div class="section-title"><span class="dot"></span> Knee Valgus (delta)</div>
            <div class="slider-row"><label>Both knees &Delta;</label><input type="range" id="sb-d-valgus" min="-15" max="15" value="0" step="0.5"><span class="value" id="sb-d-valgus-val">0°</span></div>
            <div class="slider-row"><label>Left knee &Delta;</label><input type="range" id="sb-d-valgus-l" min="-15" max="15" value="0" step="0.5"><span class="value" id="sb-d-valgus-l-val">0°</span></div>
            <div class="slider-row"><label>Right knee &Delta;</label><input type="range" id="sb-d-valgus-r" min="-15" max="15" value="0" step="0.5"><span class="value" id="sb-d-valgus-r-val">0°</span></div>
            <div class="threshold-legend"><span class="legend-ok">OK</span><span class="legend-mild">Mild</span><span class="legend-moderate">Moderate</span><span class="legend-severe">Severe</span></div>
            <div class="threshold-bar" id="sb-valgus-threshold-bar"></div>
        </div>
        <div class="section sandbox">
            <div class="section-title"><span class="dot"></span> Knee Tracking</div>
            <div class="slider-row"><label>Track over toes</label><input type="range" id="sb-d-knee-tracking" min="0" max="1" value="0" step="0.05"><span class="value" id="sb-d-knee-tracking-val">0.00</span></div>
        </div>
        <div class="section sandbox">
            <div class="section-title"><span class="dot"></span> Chain Solver</div>
            <div class="slider-row" style="gap:12px">
                <label style="display:flex; align-items:center; gap:4px; cursor:pointer">
                    <input type="radio" name="sb-solver-mode" value="independent" checked> Independent
                </label>
                <label style="display:flex; align-items:center; gap:4px; cursor:pointer">
                    <input type="radio" name="sb-solver-mode" value="compensated"> Compensated
                </label>
                <label id="sb-kino-radio-label" style="display:none; align-items:center; gap:4px; cursor:pointer">
                    <input type="radio" name="sb-solver-mode" value="kinodynamics"> Kinodynamics
                </label>
            </div>
            <div id="sb-compensated-controls" style="display:none">
                <div class="slider-row"><label>Ankle dorsi override</label><input type="range" id="sb-ankle-override" min="0" max="45" value="15" step="0.5"><span class="value" id="sb-ankle-override-val">15°</span></div>
                <div class="mono" id="sb-solved-angles" style="margin-top:6px; font-size:11px"></div>
            </div>
            <div id="sb-kino-controls" style="display:none">
                <div class="mono" id="sb-kino-info" style="margin-top:6px; font-size:11px; color:#4ecdc4">
                    20-DOF soft-cost optimizer &bull; 5 cost terms &bull; temporal taper
                </div>
                <div style="margin-top:10px">
                    <div class="slider-row"><label>Dorsiflexion &Delta;</label><input type="range" id="kino-dorsi" min="-20" max="20" value="0" step="0.5"><span class="value" id="kino-dorsi-val">0°</span></div>
                    <div class="slider-row"><label>Stance Width &Delta;</label><input type="range" id="kino-stance" min="-10" max="10" value="0" step="0.5"><span class="value" id="kino-stance-val">0 cm</span></div>
                    <div class="slider-row"><label>Toe Angle &Delta;</label><input type="range" id="kino-toe" min="-15" max="15" value="0" step="0.5"><span class="value" id="kino-toe-val">0°</span></div>
                    <div class="slider-row"><label>Knee Tracking</label><input type="range" id="kino-kneetrack" min="0" max="5" value="1" step="0.1"><span class="value" id="kino-kneetrack-val">1.0&times;</span></div>
                </div>
                <div style="margin-top:8px; display:flex; align-items:center; gap:10px">
                    <label style="display:flex; align-items:center; gap:4px; cursor:pointer; font-size:12px; color:#b0b0cc">
                        <input type="checkbox" id="kino-show-original"> Show original
                    </label>
                    <span class="mono" id="kino-solve-time" style="font-size:11px; color:#666"></span>
                </div>
            </div>
            <div id="sb-kino-faults" style="display:none; margin-top:10px">
                <div class="section faults" style="margin:0; padding:10px">
                    <div class="section-title"><span class="dot"></span> IK Faults</div>
                    <div class="mono" id="kino-faults-info"></div>
                </div>
            </div>
        </div>
        <div class="section baseline">
            <div class="section-title"><span class="dot"></span> Baseline</div>
            <div class="mono" id="sb-baseline-results"></div>
        </div>
        <div class="section playback">
            <div class="section-title"><span class="dot"></span> Playback</div>
            <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:10px;" id="sb-rep-buttons"></div>
            <div class="anim-controls">
                <button id="sb-play-btn" title="Play/Pause">&#9646;&#9646;</button>
                <input type="range" id="sb-frame-scrubber" min="0" max="100" value="0" step="1">
                <span class="value" id="sb-frame-val" style="min-width:50px;">0/0</span>
            </div>
            <div class="slider-row">
                <label>Speed</label>
                <input type="range" id="sb-speed-slider" min="0.1" max="3.0" value="1.0" step="0.1">
                <span class="value" id="sb-speed-val">1.0x</span>
            </div>
        </div>
        <div class="section angles">
            <div class="section-title"><span class="dot"></span> Live Angles</div>
            <div class="mono" id="sb-angles-info"></div>
        </div>
    </div>
</div>
<script type="module">
import * as THREE from 'three';
import {{ OrbitControls }} from 'three/addons/controls/OrbitControls.js';

const DATA = {data_json};
const KINO_DATA = {kino_json};
const BONE_CONNECTIONS = [
    [0,1],[0,2],[1,3],[2,4],
    [0,5],[0,6],
    [5,6],[5,7],[7,9],[6,8],[8,10],
    [5,11],[6,12],[11,12],[11,13],[13,15],[12,14],[14,16],
    [15,17],[16,18],
];
const baselineData = DATA.baseline;
let LEAN_T = baselineData.leanThresholds;
let VALG_T = baselineData.valgusThresholds;

// FK reference body dimensions
const REF = {{
    hip_width: 0.22, thigh_len: 0.42, shin_len: 0.40,
    torso_len: 0.50, shoulder_width: 0.36, upper_arm: 0.30,
    forearm: 0.26, head_offset: 0.22, neck_len: 0.10, foot_len: 0.26,
}};
const SEGMENT_MASS = {{
    head: {{ joints: null, frac: 0.081 }},
    trunk: {{ joints: null, frac: 0.497 }},
    upper_arm_l: {{ joints: [5,7], frac: 0.028 }}, upper_arm_r: {{ joints: [6,8], frac: 0.028 }},
    forearm_l: {{ joints: [7,9], frac: 0.022 }}, forearm_r: {{ joints: [8,10], frac: 0.022 }},
    thigh_l: {{ joints: [11,13], frac: 0.100 }}, thigh_r: {{ joints: [12,14], frac: 0.100 }},
    shank_l: {{ joints: [13,15], frac: 0.047 }}, shank_r: {{ joints: [14,16], frac: 0.047 }},
    foot_l: {{ joints: [15,null], frac: 0.014 }}, foot_r: {{ joints: [16,null], frac: 0.014 }},
}};

// ======== Populate baseline info ========
document.getElementById('baseline-info').innerHTML = `
    <span class="lbl">Peak trunk offset:</span> <span class="val-green">${{baselineData.peakTrunkOffset.toFixed(1)}}°</span><br>
    <span class="lbl">Peak knee flex:</span> <span class="val-green">${{baselineData.peakKneeFlex.toFixed(1)}}°</span><br>
    <span class="lbl">Peak dorsiflexion:</span> <span class="val-green">${{baselineData.peakDorsi.toFixed(1)}}°</span><br>
    <span class="lbl">Baseline valgus:</span> <span class="val-green">${{baselineData.peakValgus.toFixed(1)}}°</span><br>
    <hr style="border-color:#2a2a4a; margin:6px 0">
    <span class="lbl">Lean thresholds:</span> <span class="val">${{LEAN_T.mild}}° / ${{LEAN_T.moderate}}° / ${{LEAN_T.severe}}°</span><br>
    <span class="lbl">Valgus thresholds:</span> <span class="val">${{VALG_T.mild}}° / ${{VALG_T.moderate}}° / ${{VALG_T.severe}}°</span>
`;

const AP = DATA.athleteParams;
const CAPTURED_STANCE_WIDTH = AP ? AP.stanceWidth : 1.2;
if (AP) {{
    document.getElementById('athlete-info').innerHTML = `
        <span class="lbl">Body scale:</span> <span class="val">${{AP.bodyScale.toFixed(2)}}</span>
        <span class="lbl" style="margin-left:8px">Torso:</span> <span class="val">${{AP.torsoRatio.toFixed(2)}}</span>
        <span class="lbl" style="margin-left:8px">Thigh:</span> <span class="val">${{AP.thighRatio.toFixed(2)}}</span>
        <span class="lbl" style="margin-left:8px">Shin:</span> <span class="val">${{AP.shinRatio.toFixed(2)}}</span><br>
        <span class="lbl">Stance:</span> <span class="val">${{AP.stanceWidth.toFixed(2)}}x</span>
        <span class="lbl" style="margin-left:8px">Toe-out:</span> <span class="val">${{AP.toeOut.toFixed(1)}}°</span>
        <span class="lbl" style="margin-left:8px">Dorsi:</span> <span class="val">${{AP.dorsiRatio.toFixed(3)}}</span><br>
        <span class="lbl">Lean:</span> <span class="val">${{AP.forwardLean.toFixed(1)}}°</span>
        <span class="lbl" style="margin-left:8px">Max knee:</span> <span class="val">${{AP.maxKneeFlex.toFixed(1)}}°</span>
    `;
    // Pre-populate sandbox sliders
    const sliderInit = {{
        'sb-body-scale': [AP.bodyScale, 'sb-body-scale-val', '', 2],
        'sb-torso-ratio': [AP.torsoRatio, 'sb-torso-ratio-val', '', 2],
        'sb-thigh-ratio': [AP.thighRatio, 'sb-thigh-ratio-val', '', 2],
        'sb-shin-ratio': [AP.shinRatio, 'sb-shin-ratio-val', '', 2],
        'sb-shoulder-width-ratio': [AP.shoulderWidthRatio || 1.0, 'sb-shoulder-width-ratio-val', '', 2],
        'sb-foot-ratio': [AP.footRatio || 1.0, 'sb-foot-ratio-val', '', 2],
        'sb-stance-width': [AP.stanceWidth, 'sb-stance-width-val', 'x', 2],
        'sb-toe-out': [AP.toeOut, 'sb-toe-out-val', '°', 0],
        'sb-d-knee-flex': [0, 'sb-d-knee-flex-val', '°', 0],
        'sb-d-dorsi': [0, 'sb-d-dorsi-val', '°', 1],
        'sb-d-dorsi-l': [0, 'sb-d-dorsi-l-val', '°', 1],
        'sb-d-dorsi-r': [0, 'sb-d-dorsi-r-val', '°', 1],
        'sb-d-forward-lean': [0, 'sb-d-forward-lean-val', '°', 0],
        'sb-d-valgus': [0, 'sb-d-valgus-val', '°', 1],
        'sb-d-valgus-l': [0, 'sb-d-valgus-l-val', '°', 1],
        'sb-d-valgus-r': [0, 'sb-d-valgus-r-val', '°', 1],
        'sb-d-knee-tracking': [0, 'sb-d-knee-tracking-val', '', 2],
    }};
    for (const [id, [val, valId, suf, dec]] of Object.entries(sliderInit)) {{
        const el = document.getElementById(id);
        if (el) {{
            el.value = val;
            const vEl = document.getElementById(valId);
            if (vEl) vEl.textContent = dec > 0 ? parseFloat(val).toFixed(dec) + suf : Math.round(val) + suf;
        }}
    }}
}} else {{
    document.getElementById('athlete-info').innerHTML = '<span class="lbl">Not available</span>';
}}

// Populate sandbox baseline
document.getElementById('sb-baseline-results').innerHTML = `
    <span class="lbl">Peak trunk offset:</span> <span class="val">${{baselineData.peakTrunkOffset.toFixed(1)}}°</span><br>
    <span class="lbl">Peak knee flex:</span> <span class="val">${{baselineData.peakKneeFlex.toFixed(1)}}°</span><br>
    <span class="lbl">Peak dorsiflexion:</span> <span class="val">${{baselineData.peakDorsi.toFixed(1)}}°</span><br>
    <span class="lbl">Lean thresholds:</span> <span class="val">${{LEAN_T.mild.toFixed(0)}}° / ${{LEAN_T.moderate.toFixed(0)}}° / ${{LEAN_T.severe.toFixed(0)}}°</span><br>
    <span class="lbl">Valgus thresholds:</span> <span class="val">${{VALG_T.mild.toFixed(0)}}° / ${{VALG_T.moderate.toFixed(0)}}° / ${{VALG_T.severe.toFixed(0)}}°</span>
`;

// ======== THREE.JS SETUP ========
const canvas = document.getElementById('three-canvas');
const container = document.getElementById('scene-container');
const renderer = new THREE.WebGLRenderer({{ canvas, antialias: true }});
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setClearColor(0x0a0a1a);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 50);
camera.position.set(2.0, 1.0, 2.0);
camera.lookAt(0, 0.7, 0);
const orbitCtrl = new OrbitControls(camera, canvas);
orbitCtrl.target.set(0, 0.7, 0);
orbitCtrl.enableDamping = true;
orbitCtrl.dampingFactor = 0.08;
scene.add(new THREE.AmbientLight(0x404060, 0.6));
const dl = new THREE.DirectionalLight(0xffffff, 0.8);
dl.position.set(3, 5, 3);
scene.add(dl);
scene.add(new THREE.GridHelper(4, 20, 0x222244, 0x1a1a30));
// Joint and bone materials
const matN = new THREE.MeshPhongMaterial({{ color: 0x40e0a0, emissive: 0x103020 }});
const matF = new THREE.MeshPhongMaterial({{ color: 0xff4444, emissive: 0x401010 }});
const matB = new THREE.MeshPhongMaterial({{ color: 0x3090d0, emissive: 0x102030 }});
const matBF = new THREE.MeshPhongMaterial({{ color: 0xff6666, emissive: 0x301010 }});
const sGeo = new THREE.SphereGeometry(0.018, 12, 8);
const jm = [], js = [];
for (let i = 0; i < 19; i++) {{ const m = new THREE.Mesh(sGeo, matN.clone()); scene.add(m); jm.push(m); js.push('n'); }}
const bm = [];
for (const [a, b] of BONE_CONNECTIONS) {{
    const g = new THREE.CylinderGeometry(0.006, 0.006, 1, 6); g.translate(0, 0.5, 0);
    const m = new THREE.Mesh(g, matB.clone()); scene.add(m); bm.push({{ mesh: m, a, b }});
}}

// COM / BOS / Ghost / Midfoot visuals (sandbox mode)
const comSphere = new THREE.Mesh(new THREE.SphereGeometry(0.012, 10, 7), new THREE.MeshPhongMaterial({{ color: 0xff2222, emissive: 0x550000, transparent: true, opacity: 0.9 }}));
scene.add(comSphere); comSphere.visible = false;
const comDiscGeo = new THREE.CircleGeometry(0.025, 16);
const comDisc = new THREE.Mesh(comDiscGeo, new THREE.MeshBasicMaterial({{ color: 0xff3333, transparent: true, opacity: 0.7 }}));
comDisc.rotation.x = -Math.PI / 2; comDisc.position.y = 0.001; scene.add(comDisc); comDisc.visible = false;
const comLineGeo = new THREE.BufferGeometry();
comLineGeo.setAttribute('position', new THREE.Float32BufferAttribute([0,0,0, 0,2,0], 3));
const comLineMat = new THREE.LineDashedMaterial({{ color: 0xff3333, dashSize: 0.03, gapSize: 0.02, transparent: true, opacity: 0.6 }});
const comLine = new THREE.Line(comLineGeo, comLineMat); scene.add(comLine); comLine.visible = false;
const bosGeo = new THREE.BufferGeometry();
const bosLineMat = new THREE.LineBasicMaterial({{ color: 0x44ff88, transparent: true, opacity: 0.5 }});
const bosLine = new THREE.LineLoop(bosGeo, bosLineMat); bosLine.position.y = 0.002; scene.add(bosLine); bosLine.visible = false;
const ghostTorsoGeo = new THREE.BufferGeometry();
ghostTorsoGeo.setAttribute('position', new THREE.Float32BufferAttribute([0,0,0, 0,1,0], 3));
const ghostTorsoLine = new THREE.Line(ghostTorsoGeo, new THREE.LineDashedMaterial({{ color: 0x00e5ff, dashSize: 0.04, gapSize: 0.03, transparent: true, opacity: 0.55 }}));
scene.add(ghostTorsoLine); ghostTorsoLine.visible = false;
const midfootLineGeo = new THREE.BufferGeometry();
midfootLineGeo.setAttribute('position', new THREE.Float32BufferAttribute([0,0,0, 0,2,0], 3));
const midfootLine = new THREE.Line(midfootLineGeo, new THREE.LineDashedMaterial({{ color: 0xf0a040, dashSize: 0.025, gapSize: 0.02, transparent: true, opacity: 0.45 }}));
scene.add(midfootLine); midfootLine.visible = false;
const midfootDiscGeo = new THREE.CircleGeometry(0.018, 12);
const midfootDisc = new THREE.Mesh(midfootDiscGeo, new THREE.MeshBasicMaterial({{ color: 0xf0a040, transparent: true, opacity: 0.5 }}));
midfootDisc.rotation.x = -Math.PI / 2; midfootDisc.position.y = 0.001; scene.add(midfootDisc); midfootDisc.visible = false;

// Barbell
const barbellGroup = new THREE.Group(); scene.add(barbellGroup);
const barMat = new THREE.MeshPhongMaterial({{ color: 0x888899, emissive: 0x111122 }});
const plateMat = new THREE.MeshPhongMaterial({{ color: 0x333344, emissive: 0x080810 }});
const barGeo = new THREE.CylinderGeometry(0.014, 0.014, 1.6, 10);
const barMesh = new THREE.Mesh(barGeo, barMat); barMesh.rotation.x = Math.PI / 2; barbellGroup.add(barMesh);
const plateMeshes = [];
for (let i = 0; i < 4; i++) {{
    const pGeo = new THREE.CylinderGeometry(0.05, 0.05, 0.04, 16);
    const pMesh = new THREE.Mesh(pGeo, plateMat.clone()); pMesh.rotation.x = Math.PI / 2;
    barbellGroup.add(pMesh); plateMeshes.push(pMesh);
}}
barbellGroup.visible = false;

// ======== STATE ========
let viewMode = 'replay'; // 'replay' or 'sandbox'
let curRep = 0, curFrame = 0, playing = true, lastT = performance.now(), speed = 1.0, frameAcc = 0;
const reps = DATA.reps, dataFps = DATA.fps;
let repFilter = -1;
let _barbellPos = null;

// ======== REPLAY CONTROLS ========
const rbc = document.getElementById('rep-buttons');
const allBtn = document.createElement('button'); allBtn.className='rep-btn active'; allBtn.textContent='All'; allBtn.dataset.idx='-1'; rbc.appendChild(allBtn);
for (let i = 0; i < reps.length; i++) {{
    const b = document.createElement('button'); b.className='rep-btn'; b.textContent=`Rep ${{i+2}}`; b.dataset.idx=String(i); rbc.appendChild(b);
}}
function onRepClick(e) {{
    if (!e.target.classList.contains('rep-btn')) return;
    e.currentTarget.querySelectorAll('.rep-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    repFilter = parseInt(e.target.dataset.idx);
    curRep = repFilter === -1 ? 0 : repFilter;
    curFrame = 0;
}}
rbc.addEventListener('click', onRepClick);

const scrub = document.getElementById('frame-scrubber'), fv = document.getElementById('frame-val');
scrub.addEventListener('input', () => {{ curFrame = parseInt(scrub.value); playing = false; document.getElementById('play-btn').innerHTML = '&#9654;'; }});
document.getElementById('play-btn').addEventListener('click', () => {{ playing = !playing; document.getElementById('play-btn').innerHTML = playing ? '&#9646;&#9646;' : '&#9654;'; }});
const ss = document.getElementById('speed-slider'), sv = document.getElementById('speed-val');
ss.addEventListener('input', () => {{ speed = parseFloat(ss.value); sv.textContent = speed.toFixed(1) + 'x'; }});

// ======== SANDBOX REP BUTTONS (shared frame timing) ========
const sbRbc = document.getElementById('sb-rep-buttons');
const sbAllBtn = document.createElement('button'); sbAllBtn.className='rep-btn active'; sbAllBtn.textContent='All'; sbAllBtn.dataset.idx='-1'; sbRbc.appendChild(sbAllBtn);
for (let i = 0; i < reps.length; i++) {{
    const b = document.createElement('button'); b.className='rep-btn'; b.textContent=`Rep ${{i+2}}`; b.dataset.idx=String(i); sbRbc.appendChild(b);
}}
sbRbc.addEventListener('click', onRepClick);
const sbScrub = document.getElementById('sb-frame-scrubber'), sbFv = document.getElementById('sb-frame-val');
sbScrub.addEventListener('input', () => {{ curFrame = parseInt(sbScrub.value); playing = false; document.getElementById('sb-play-btn').innerHTML = '&#9654;'; }});
document.getElementById('sb-play-btn').addEventListener('click', () => {{ playing = !playing; document.getElementById('sb-play-btn').innerHTML = playing ? '&#9646;&#9646;' : '&#9654;'; }});
const sbSs = document.getElementById('sb-speed-slider'), sbSv = document.getElementById('sb-speed-val');
sbSs.addEventListener('input', () => {{ speed = parseFloat(sbSs.value); sbSv.textContent = speed.toFixed(1) + 'x'; }});

// ======== SANDBOX SLIDER BINDINGS ========
let _slidersModified = false;
let _stanceWidthTouched = false;
function bindSlider(id, valId, suffix, decimals) {{
    const slider = document.getElementById(id);
    const valSpan = document.getElementById(valId);
    if (!slider || !valSpan) return;
    slider.addEventListener('input', () => {{
        _slidersModified = true;
        const v = parseFloat(slider.value);
        valSpan.textContent = decimals > 0 ? v.toFixed(decimals) + suffix : Math.round(v) + suffix;
    }});
}}
function bindSliderDelta(id, valId, suffix, decimals) {{
    const slider = document.getElementById(id);
    const valSpan = document.getElementById(valId);
    if (!slider || !valSpan) return;
    slider.addEventListener('input', () => {{
        _slidersModified = true;
        const v = parseFloat(slider.value);
        const sign = v > 0 ? '+' : '';
        valSpan.textContent = sign + (decimals > 0 ? v.toFixed(decimals) : Math.round(v)) + suffix;
    }});
}}
bindSlider('sb-body-scale', 'sb-body-scale-val', '', 2);
bindSlider('sb-torso-ratio', 'sb-torso-ratio-val', '', 2);
bindSlider('sb-thigh-ratio', 'sb-thigh-ratio-val', '', 2);
bindSlider('sb-shin-ratio', 'sb-shin-ratio-val', '', 2);
bindSlider('sb-shoulder-width-ratio', 'sb-shoulder-width-ratio-val', '', 2);
bindSlider('sb-foot-ratio', 'sb-foot-ratio-val', '', 2);
(function() {{
    const slider = document.getElementById('sb-stance-width');
    const valSpan = document.getElementById('sb-stance-width-val');
    if (!slider || !valSpan) return;
    slider.addEventListener('input', () => {{
        _slidersModified = true;
        _stanceWidthTouched = true;
        const v = parseFloat(slider.value);
        valSpan.textContent = v.toFixed(2) + 'x';
    }});
}})();
bindSlider('sb-toe-out', 'sb-toe-out-val', '°', 0);
bindSliderDelta('sb-d-knee-flex', 'sb-d-knee-flex-val', '°', 0);
bindSliderDelta('sb-d-dorsi', 'sb-d-dorsi-val', '°', 1);
bindSliderDelta('sb-d-dorsi-l', 'sb-d-dorsi-l-val', '°', 1);
bindSliderDelta('sb-d-dorsi-r', 'sb-d-dorsi-r-val', '°', 1);
bindSliderDelta('sb-d-forward-lean', 'sb-d-forward-lean-val', '°', 0);
bindSliderDelta('sb-d-valgus', 'sb-d-valgus-val', '°', 1);
bindSliderDelta('sb-d-valgus-l', 'sb-d-valgus-l-val', '°', 1);
bindSliderDelta('sb-d-valgus-r', 'sb-d-valgus-r-val', '°', 1);
bindSlider('sb-d-knee-tracking', 'sb-d-knee-tracking-val', '', 2);
bindSlider('sb-barbell-weight', 'sb-barbell-weight-val', ' kg', 0);
bindSlider('sb-body-mass', 'sb-body-mass-val', ' kg', 0);
// Speed slider updates playback rate only, not pose — skip _slidersModified


// ======== KINODYNAMICS SLIDER BINDINGS ========
bindSliderDelta('kino-dorsi', 'kino-dorsi-val', '°', 1);
bindSlider('kino-stance', 'kino-stance-val', ' cm', 1);
bindSlider('kino-toe', 'kino-toe-val', '°', 1);
bindSlider('kino-kneetrack', 'kino-kneetrack-val', '×', 1);
let _kinoShowOriginal = false;
const _kinoOrigCheckbox = document.getElementById('kino-show-original');
if (_kinoOrigCheckbox) _kinoOrigCheckbox.addEventListener('change', () => {{
    _kinoShowOriginal = _kinoOrigCheckbox.checked;
}});

// Ghost skeleton meshes for original pose overlay
const matGhost = new THREE.MeshPhongMaterial({{ color: 0x4488aa, emissive: 0x102030, transparent: true, opacity: 0.35 }});
const matBGhost = new THREE.MeshPhongMaterial({{ color: 0x336688, emissive: 0x081820, transparent: true, opacity: 0.25 }});
const ghostJoints = [], ghostBones = [];
for (let i = 0; i < 19; i++) {{ const m = new THREE.Mesh(sGeo, matGhost); m.visible = false; scene.add(m); ghostJoints.push(m); }}
for (const [a, b] of BONE_CONNECTIONS) {{
    const g = new THREE.CylinderGeometry(0.004, 0.004, 1, 4); g.translate(0, 0.5, 0);
    const m = new THREE.Mesh(g, matBGhost); m.visible = false; scene.add(m); ghostBones.push({{ mesh: m, a, b }});
}}
function updateGhostSkeleton(kpts, visible) {{
    for (let i = 0; i < 19; i++) {{
        if (visible && kpts) {{
            ghostJoints[i].position.set(kpts[i*3], kpts[i*3+1], kpts[i*3+2]);
            ghostJoints[i].visible = true;
        }} else {{ ghostJoints[i].visible = false; }}
    }}
    for (const bone of ghostBones) {{
        if (visible && kpts) {{
            const pa = ghostJoints[bone.a].position, pb = ghostJoints[bone.b].position;
            const d = new THREE.Vector3().subVectors(pb, pa), l = d.length(); d.normalize();
            bone.mesh.position.copy(pa); bone.mesh.scale.set(1, l, 1);
            bone.mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0), d);
            bone.mesh.visible = true;
        }} else {{ bone.mesh.visible = false; }}
    }}
}}

// ======== MODE SWITCHING ========
document.getElementById('tab-replay').addEventListener('click', () => {{
    viewMode = 'replay';
    document.getElementById('tab-replay').classList.add('active');
    document.getElementById('tab-sandbox').classList.remove('active');
    document.getElementById('replay-panel').style.display = '';
    document.getElementById('sandbox-panel').style.display = 'none';
    hideSandboxVisuals();
}});
document.getElementById('tab-sandbox').addEventListener('click', () => {{
    viewMode = 'sandbox';
    document.getElementById('tab-sandbox').classList.add('active');
    document.getElementById('tab-replay').classList.remove('active');
    document.getElementById('sandbox-panel').style.display = '';
    document.getElementById('replay-panel').style.display = 'none';
}});
{{
    const sp = new URLSearchParams(location.search);
    if (location.hash === '#sandbox' || sp.has('sandbox')) {{
        document.getElementById('tab-sandbox').click();
        for (const [k, v] of sp.entries()) {{
            const el = document.getElementById(k);
            if (el && el.type === 'range') {{
                el.value = v;
                el.dispatchEvent(new Event('input'));
            }}
        }}
    }}
}}

function hideSandboxVisuals() {{
    ghostTorsoLine.visible = false;
    midfootLine.visible = false; midfootDisc.visible = false;
    barbellGroup.visible = false;
    updateGhostSkeleton(null, false);
}}

// ======== FAULT CLASSIFICATION ========
function classifyLean(trunkAngleDeg) {{
    const o = 180 - trunkAngleDeg;
    return o >= LEAN_T.severe ? 'severe' : o >= LEAN_T.moderate ? 'moderate' : o >= LEAN_T.mild ? 'mild' : 'none';
}}
function classifyValgus(valgusDeg) {{
    return valgusDeg >= VALG_T.severe ? 'severe' : valgusDeg >= VALG_T.moderate ? 'moderate' : valgusDeg >= VALG_T.mild ? 'mild' : 'none';
}}
function sb(s) {{ return `<span class="severity-indicator sev-${{s}}">${{s.toUpperCase()}}</span>`; }}

// ======== REPLAY UPDATE ========
function updateReplay(fd) {{
    if (!fd) return;
    const k = fd.kpts, a = fd.angles;
    const ls = classifyLean(a.trunk_flexion);
    const vl = classifyValgus(Math.abs(a.knee_valgus_l)), vr = classifyValgus(Math.abs(a.knee_valgus_r));
    const vs = vl!=='none'||vr!=='none' ? (vl==='severe'||vr==='severe'?'severe':vl==='moderate'||vr==='moderate'?'moderate':'mild') : 'none';
    const fj = new Set();
    if (ls !== 'none') [0,1,2,3,4,5,6].forEach(j => fj.add(j));
    if (vs !== 'none') [13,14].forEach(j => fj.add(j));
    for (let i = 0; i < 19; i++) {{
        if (!k[i]) continue;
        jm[i].position.set(k[i][0], k[i][1], k[i][2]);
        jm[i].visible = true;
        const t = fj.has(i) ? 'f' : 'n';
        if (t !== js[i]) {{ jm[i].material = (t === 'f' ? matF : matN).clone(); js[i] = t; }}
    }}
    const fb = new Set();
    if (ls !== 'none') {{ fb.add('5-6'); fb.add('5-11'); fb.add('6-12'); fb.add('0-5'); fb.add('0-6'); }}
    if (vs !== 'none') {{ fb.add('11-13'); fb.add('13-15'); fb.add('12-14'); fb.add('14-16'); }}
    for (const bone of bm) {{
        const pa = jm[bone.a].position, pb = jm[bone.b].position;
        const d = new THREE.Vector3().subVectors(pb, pa), l = d.length(); d.normalize();
        bone.mesh.position.copy(pa); bone.mesh.scale.set(1, l, 1);
        bone.mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0), d);
        bone.mesh.material = fb.has(`${{bone.a}}-${{bone.b}}`) ? matBF : matB;
    }}
    // COM / BOS from captured keypoints
    const rkpts = new Float64Array(19 * 3);
    for (let i = 0; i < 19; i++) {{ if (k[i]) {{ rkpts[i*3]=k[i][0]; rkpts[i*3+1]=k[i][1]; rkpts[i*3+2]=k[i][2]; }} }}
    const rFootLen = AP ? (AP.foot_avg_m || REF.foot_len) : REF.foot_len;
    const rCom = computeCOM(rkpts, 0, 75, rFootLen);
    const rBos = computeBOS(rkpts, 0, rFootLen);
    const rBal = isBalanced(rCom, rBos);
    updateCOMVisuals(rCom, rBos, rBal);
    const to = (180 - a.trunk_flexion).toFixed(1);
    document.getElementById('angles-info').innerHTML = `
        <span class="lbl">Knee Flex:</span> <span class="val">${{a.knee_flex.toFixed(1)}}°</span><br>
        <span class="lbl">Trunk Angle:</span> <span class="val">${{a.trunk_flexion.toFixed(1)}}°</span> (offset: ${{to}}°)<br>
        <span class="lbl">Valgus L/R:</span> <span class="val">${{a.knee_valgus_l.toFixed(1)}}° / ${{a.knee_valgus_r.toFixed(1)}}°</span><br>
        <span class="lbl">Dorsi L/R:</span> <span class="val">${{a.dorsi_l.toFixed(1)}}° / ${{a.dorsi_r.toFixed(1)}}°</span><br>
        <span class="lbl">Hip Flex L/R:</span> <span class="val">${{a.hip_flex_l.toFixed(1)}}° / ${{a.hip_flex_r.toFixed(1)}}°</span>`;
    const fl = [];
    if (ls !== 'none') fl.push('Forward Lean ' + sb(ls));
    if (vs !== 'none') fl.push('Knee Valgus ' + sb(vs));
    document.getElementById('faults-info').innerHTML = fl.length ? fl.join('<br>') : '<span class="val-green">Clean</span>';
    document.getElementById('info-overlay').innerHTML = `
        <span class="lbl">Rep:</span> <span class="val">${{curRep+2}}</span>
        <span class="lbl" style="margin-left:12px">Frame:</span> <span class="val">${{curFrame+1}}/${{reps[curRep].length}}</span><br>
        <span class="lbl">Knee:</span> <span class="val">${{a.knee_flex.toFixed(1)}}°</span>
        <span class="lbl" style="margin-left:8px">Trunk:</span> <span class="val">${{a.trunk_flexion.toFixed(1)}}°</span>`;
}}

// ======== FK ENGINE (from fault_visualizer) ========
function computeSquatPose(phase, params, lockedShoulder) {{
    const {{ maxKneeFlex, forwardLean, kneeValgus, stanceWidth, toeOut, dorsiRatio,
             bodyScale, torsoRatio, thighRatio, shinRatio, shoulderWidthRatio,
             barbellWeight: bw }} = params;
    const deg2rad = Math.PI / 180, rad2deg = 180 / Math.PI;
    const profile = phase; // phase-matched: phase IS the normalized depth (0=standing, 1=peak)
    const kneeFlexDeg = maxKneeFlex * profile;
    const kneeFlexRad = kneeFlexDeg * deg2rad;
    const ankleDF = dorsiRatio * kneeFlexRad;
    const extraLeanRad = (forwardLean * deg2rad) * profile;
    const valgusRad = (kneeValgus * deg2rad) * profile;
    const toeOutRad = toeOut * deg2rad;

    const hw = REF.hip_width * bodyScale;
    const ankleZ = (hw / 2) * stanceWidth;
    const thl = REF.thigh_len * bodyScale * thighRatio;
    const shl = REF.shin_len * bodyScale * shinRatio;
    const tl = REF.torso_len * bodyScale * torsoRatio;
    const sw = REF.shoulder_width * bodyScale * (shoulderWidthRatio || 1.0);
    const ual = REF.upper_arm * bodyScale;
    const fal = REF.forearm * bodyScale;
    const headH = REF.head_offset * bodyScale;

    const kpts = new Float64Array(19 * 3);
    function set(idx, x, y, z) {{ kpts[idx*3]=x; kpts[idx*3+1]=y; kpts[idx*3+2]=z; }}
    function get(idx) {{ return [kpts[idx*3], kpts[idx*3+1], kpts[idx*3+2]]; }}
    const fr = params.footRatio || 1.0;
    const fl = REF.foot_len * bodyScale * fr;

    const shinTilt = ankleDF;
    const thighDirAngle = shinTilt - kneeFlexRad;
    const valgusShift = shl * Math.sin(valgusRad);

    function placeLeg(side, ax, ay, az) {{
        const sgn = side;
        const fx = Math.cos(toeOutRad), fz = sgn * Math.sin(toeOutRad);
        const lx = -fz, lz = fx;
        const medialSign = (side < 0) ? 1 : -1;
        const mx = medialSign * lx, mz = medialSign * lz;
        const kx = ax + shl * Math.sin(shinTilt) * fx + valgusShift * mx;
        const ky = ay + shl * Math.cos(shinTilt);
        const kz = az + shl * Math.sin(shinTilt) * fz + valgusShift * mz;
        const tf = thl * Math.sin(thighDirAngle), tu = thl * Math.cos(thighDirAngle);
        const hx = kx + tf * fx, hy = ky + tu, hz = kz + tf * fz;
        return {{ kx, ky, kz, hx, hy, hz }};
    }}

    set(15, 0, 0, -ankleZ); set(16, 0, 0, ankleZ);
    set(17, fl * Math.cos(toeOutRad), 0, -ankleZ - fl * Math.sin(toeOutRad));
    set(18, fl * Math.cos(toeOutRad), 0, ankleZ + fl * Math.sin(toeOutRad));
    const L = placeLeg(-1, 0, 0, -ankleZ), R = placeLeg(+1, 0, 0, ankleZ);
    set(13, L.kx, L.ky, L.kz); set(14, R.kx, R.ky, R.kz);
    const hipY = (L.hy + R.hy) / 2, hipX = (L.hx + R.hx) / 2;
    set(11, hipX, hipY, -hw/2); set(12, hipX, hipY, hw/2);

    const lHip = get(11), rHip = get(12);
    const hipMidX = (lHip[0] + rHip[0]) / 2, hipMidY = (lHip[1] + rHip[1]) / 2;

    let totalTrunkLean;
    if (lockedShoulder) {{
        const baseAngle = Math.atan2(lockedShoulder.x - hipMidX, lockedShoulder.y - hipMidY);
        const leanDelta = ((forwardLean - (lockedShoulder.refLean || forwardLean)) * deg2rad) * profile;
        totalTrunkLean = Math.max(0, baseAngle + leanDelta);
    }} else if (bw && bw > 0) {{
        const heelOffset = 0.06;
        const midfootX = (fl / 2 - heelOffset) * Math.cos(toeOutRad);
        const A = tl + 0.04, B = -0.05, C = midfootX - hipMidX;
        const Rv = Math.sqrt(A*A + B*B), phi = Math.atan2(B, A);
        const sinArg = Math.max(-1, Math.min(1, C / Rv));
        totalTrunkLean = Math.max(0, Math.asin(sinArg) - phi + extraLeanRad);
    }} else {{
        const heelOffset = 0.06;
        const midfootX = (fl / 2 - heelOffset) * Math.cos(toeOutRad);
        const sinArg = Math.max(-1, Math.min(1, (midfootX - hipMidX) / tl));
        totalTrunkLean = Math.max(0, Math.asin(sinArg) + extraLeanRad);
    }}

    const sMidX = hipMidX + tl * Math.sin(totalTrunkLean);
    const sMidY = hipMidY + tl * Math.cos(totalTrunkLean);
    set(5, sMidX, sMidY, -sw/2); set(6, sMidX, sMidY, sw/2);

    const headX = sMidX + headH * Math.sin(totalTrunkLean) * 0.5;
    const headY = sMidY + headH;
    set(0, headX, headY, 0);
    set(1, headX, headY + 0.02, -0.03 * bodyScale);
    set(2, headX, headY + 0.02, 0.03 * bodyScale);
    set(3, headX, headY - 0.01, -0.06 * bodyScale);
    set(4, headX, headY - 0.01, 0.06 * bodyScale);

    // Arms: hanging default
    const lS = get(5), rS = get(6);
    const armFwd = 0.05 * profile, armDown = 0.15 + 0.1 * profile;
    set(7, lS[0] + armFwd, lS[1] - ual * 0.7 - armDown, lS[2]);
    set(8, rS[0] + armFwd, rS[1] - ual * 0.7 - armDown, rS[2]);
    const lE = get(7), rE = get(8);
    set(9, lE[0] + 0.02, lE[1] - fal * 0.5, lE[2]);
    set(10, rE[0] + 0.02, rE[1] - fal * 0.5, rE[2]);

    const trunkAngleDeg = 180 - (totalTrunkLean * rad2deg);
    const valgusActiveDeg = kneeValgus * profile;
    const dorsiDeg = ankleDF * rad2deg;
    const totalTrunkLeanDeg = totalTrunkLean * rad2deg;

    return {{ kpts, avgKneeDeg: kneeFlexDeg, trunkAngleDeg, valgusActiveDeg, dorsiDeg,
              totalTrunkLeanDeg, hipMidX, hipMidY, shoulderMidX: sMidX, shoulderMidY: sMidY,
              toeOutRad, tl, sw, totalTrunkLean }};
}}

// ======== PER-SIDE DELTA FK ========
// Rodrigues rotation: rotate vector v around unit axis ax by angle ang (radians)
function _rotVec(v, ax, ang) {{
    const c = Math.cos(ang), s = Math.sin(ang), t = 1 - c;
    const d = v[0]*ax[0] + v[1]*ax[1] + v[2]*ax[2];
    const cr = [ax[1]*v[2]-ax[2]*v[1], ax[2]*v[0]-ax[0]*v[2], ax[0]*v[1]-ax[1]*v[0]];
    return [v[0]*c+cr[0]*s+ax[0]*d*t, v[1]*c+cr[1]*s+ax[1]*d*t, v[2]*c+cr[2]*s+ax[2]*d*t];
}}
function _norm(v) {{ const l=Math.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2])||1e-9; return [v[0]/l,v[1]/l,v[2]/l]; }}

function computePerSidePose(fd, deltas, bodyParams, lockedShoulder, compensated, applyStanceOverride) {{
    const k = fd.kpts, a = fd.angles;
    const deg2rad = Math.PI / 180, rad2deg = 180 / Math.PI;
    const bs = bodyParams.bodyScale || 1.0;
    const shl = REF.shin_len * bs * (bodyParams.shinRatio || 1.0);
    const thl = REF.thigh_len * bs * (bodyParams.thighRatio || 1.0);
    const tl = REF.torso_len * bs * (bodyParams.torsoRatio || 1.0);
    const sw = REF.shoulder_width * bs * (bodyParams.shoulderWidthRatio || 1.0);
    const fl = REF.foot_len * bs * (bodyParams.footRatio || 1.0);
    const headH = REF.head_offset * bs;
    const toeOutRad = (bodyParams.toeOut || 15) * deg2rad;

    // Phase: 0=standing, 1=squat bottom — scale joint angle deltas so top of rep matches captured
    const phase = fd.phase || 0;

    // Delta amounts (degrees), scaled by phase
    let dDorsiL = ((deltas.dorsi || 0) + (deltas.dorsiL || 0)) * phase;
    let dDorsiR = ((deltas.dorsi || 0) + (deltas.dorsiR || 0)) * phase;
    let dKF     = (deltas.kneeFlex || 0) * phase;
    let dValL   = ((deltas.valgus || 0) + (deltas.valgusL || 0)) * phase;
    let dValR   = ((deltas.valgus || 0) + (deltas.valgusR || 0)) * phase;
    let dLean   = (deltas.forwardLean || 0) * phase;

    const kpts = new Float64Array(19 * 3);
    function set(idx, x, y, z) {{ kpts[idx*3]=x; kpts[idx*3+1]=y; kpts[idx*3+2]=z; }}

    // Captured ankle positions (original, for angle computation)
    const capAL = k[15]||[0,0,0], capAR = k[16]||[0,0,0];
    const cKL = k[13]||capAL, cKR = k[14]||capAR;
    const cHL = k[11]||cKL, cHR = k[12]||cKR;

    // Stance width: in compensated mode keep captured ankles unless stance slider was touched
    const hipWidth = REF.hip_width * bs;
    let stanceShift = 0;
    let aL, aR;
    if (compensated && !applyStanceOverride) {{
        aL = [capAL[0], capAL[1], capAL[2]];
        aR = [capAR[0], capAR[1], capAR[2]];
    }} else if (compensated && applyStanceOverride) {{
        // Delta from captured baseline ratio — zero shift at slider == CAPTURED_STANCE_WIDTH
        const stanceDeltaRatio = (bodyParams.stanceWidth || CAPTURED_STANCE_WIDTH) - CAPTURED_STANCE_WIDTH;
        stanceShift = (hipWidth / 2) * stanceDeltaRatio;
        aL = [capAL[0], capAL[1], capAL[2] - stanceShift];
        aR = [capAR[0], capAR[1], capAR[2] + stanceShift];
    }} else {{
        const capturedHalfSpread = (capAR[2] - capAL[2]) / 2;
        const targetHalfSpread = (hipWidth / 2) * (bodyParams.stanceWidth || CAPTURED_STANCE_WIDTH);
        stanceShift = targetHalfSpread - capturedHalfSpread;
        aL = [capAL[0], capAL[1], capAL[2] - stanceShift];
        aR = [capAR[0], capAR[1], capAR[2] + stanceShift];
    }}

    set(15, aL[0], aL[1], aL[2]);
    set(16, aR[0], aR[1], aR[2]);

    // Feet: in compensated mode always derive from toe-out slider; otherwise use captured
    if (compensated) {{
        set(17, aL[0]-fl*Math.cos(toeOutRad), aL[1], aL[2]-fl*Math.sin(toeOutRad));
        set(18, aR[0]-fl*Math.cos(toeOutRad), aR[1], aR[2]+fl*Math.sin(toeOutRad));
    }} else {{
        if (k[17]) set(17, k[17][0], k[17][1], k[17][2] - stanceShift);
        else set(17, aL[0]-fl*Math.cos(toeOutRad), aL[1], aL[2]-fl*Math.sin(toeOutRad));
        if (k[18]) set(18, k[18][0], k[18][1], k[18][2] + stanceShift);
        else set(18, aR[0]-fl*Math.cos(toeOutRad), aR[1], aR[2]+fl*Math.sin(toeOutRad));
    }}

    // Per-leg biomechanical FK chain: ankle (planted) -> shin -> knee -> thigh -> hip
    // Dorsiflexion rotates the shin forward; knee flex angle is preserved from capture;
    // hip position is a free output of the chain (not pinned to captured height).
    // autoHipRotation: when true, fully rotate leg to track toe direction (hip int/ext rotation)
    function adjustLeg(ankle, capAnkle, capKnee, capHip, dDorsi, dKnee, dValgus, side, toeDir, kneeTrackBlend, autoHipRotation) {{
        // Angles from CAPTURED geometry (original positions, unaffected by stance shift)
        const capShinVec = [capKnee[0]-capAnkle[0], capKnee[1]-capAnkle[1], capKnee[2]-capAnkle[2]];
        const capThighVec = [capHip[0]-capKnee[0], capHip[1]-capKnee[1], capHip[2]-capKnee[2]];
        const capShinLen = Math.sqrt(capShinVec[0]*capShinVec[0]+capShinVec[1]*capShinVec[1]+capShinVec[2]*capShinVec[2]) || shl;
        const capThighLen = Math.sqrt(capThighVec[0]*capThighVec[0]+capThighVec[1]*capThighVec[1]+capThighVec[2]*capThighVec[2]) || thl;

        // Captured knee flexion (preserved regardless of knee tracking rotation)
        const capShinDir = _norm(capShinVec);
        const capThighDir = _norm(capThighVec);

        // Hip internal/external rotation: rotate entire leg to track toe direction
        let rotatedShinDir = capShinDir;
        let hipRotationRad = 0;
        const capShinGroundAngle = Math.atan2(capShinVec[2], capShinVec[0]);

        // autoHipRotation is a 0-1 blend (phase-scaled in compensated mode)
        const effectiveBlend = (autoHipRotation || 0) + (kneeTrackBlend || 0);
        if (effectiveBlend > 0 && toeDir) {{
            const toeGroundAngle = Math.atan2(toeDir[2], toeDir[0]);
            // Normalized angular difference (handles atan2 wraparound near +/-pi)
            let angleDiff = toeGroundAngle - capShinGroundAngle;
            if (angleDiff > Math.PI) angleDiff -= 2 * Math.PI;
            if (angleDiff < -Math.PI) angleDiff += 2 * Math.PI;
            const blendAmt = Math.min(1.0, effectiveBlend);
            hipRotationRad = -blendAmt * angleDiff;
            rotatedShinDir = _rotVec(capShinDir, [0, 1, 0], hipRotationRad);
        }}

        // Sagittal plane from (possibly rotated) shin ground projection
        const rGndX = rotatedShinDir[0], rGndZ = rotatedShinDir[2];
        const gLen = Math.sqrt(rGndX*rGndX + rGndZ*rGndZ) || 1e-6;
        const fwd = [rGndX/gLen, 0, rGndZ/gLen];
        const lat = [fwd[2], 0, -fwd[0]];
        const kneeDot = capShinDir[0]*capThighDir[0] + capShinDir[1]*capThighDir[1] + capShinDir[2]*capThighDir[2];
        const capturedKneeFlexRad = Math.acos(Math.max(-1, Math.min(1, kneeDot)));

        // Rotate shin by dorsiflexion delta (forward tilt around lateral axis)
        let newShinDir = _rotVec(rotatedShinDir, lat, dDorsi * deg2rad);
        if (Math.abs(dValgus) > 0.001) {{
            newShinDir = _rotVec(newShinDir, fwd, dValgus * deg2rad * side);
        }}

        // New knee: from (possibly shifted) ankle along rotated shin
        const newKnee = [ankle[0]+newShinDir[0]*capShinLen, ankle[1]+newShinDir[1]*capShinLen, ankle[2]+newShinDir[2]*capShinLen];

        // Thigh: preserve knee angle (+ delta), rotate shin backward by that amount
        const newKneeFlexRad = Math.max(0, capturedKneeFlexRad + dKnee * deg2rad);
        const newThighDir = _rotVec(newShinDir, lat, -newKneeFlexRad);
        const newHip = [newKnee[0]+newThighDir[0]*capThighLen, newKnee[1]+newThighDir[1]*capThighLen, newKnee[2]+newThighDir[2]*capThighLen];

        return {{ knee: newKnee, hip: newHip, hipRotationRad }};
    }}

    // Knee-over-toes: toe direction + blend factor from slider
    const toeDirL = [kpts[17*3]-kpts[15*3], 0, kpts[17*3+2]-kpts[15*3+2]];
    const toeDirR = [kpts[18*3]-kpts[16*3], 0, kpts[18*3+2]-kpts[16*3+2]];
    const kneeTrackBlend = (deltas.kneeTracking || 0) * phase;

    // In compensated mode, hip rotation blend scales with phase (0=standing, 1=depth)
    // At standing the shin is nearly vertical so ground-plane angle is unreliable
    const hipRotBlend = compensated ? phase : 0;
    const L = adjustLeg(aL, capAL, cKL, cHL, dDorsiL, dKF, dValL, -1, toeDirL, kneeTrackBlend, hipRotBlend);
    const R = adjustLeg(aR, capAR, cKR, cHR, dDorsiR, dKF, dValR, +1, toeDirR, kneeTrackBlend, hipRotBlend);
    set(13, L.knee[0], L.knee[1], L.knee[2]);
    set(14, R.knee[0], R.knee[1], R.knee[2]);
    if (compensated) {{
        // Pelvis is rigid: enforce fixed hip-to-hip distance regardless of leg rotation
        const hipMidZ = (L.hip[2] + R.hip[2]) / 2;
        set(11, L.hip[0], L.hip[1], hipMidZ - hipWidth / 2);
        set(12, R.hip[0], R.hip[1], hipMidZ + hipWidth / 2);
    }} else {{
        set(11, L.hip[0], L.hip[1], k[11] ? k[11][2] : L.hip[2]);
        set(12, R.hip[0], R.hip[1], k[12] ? k[12][2] : R.hip[2]);
    }}

    const hipMidX = (L.hip[0]+R.hip[0])/2, hipMidY = (L.hip[1]+R.hip[1])/2;

    // Midfoot target from actual rendered toe/ankle positions (single source of truth)
    const ankleMidX = (aL[0] + aR[0]) / 2;
    const footComX = (kpts[15*3] + kpts[17*3] + kpts[16*3] + kpts[18*3]) / 4;
    // Center of pressure sits ~27% from ankle toward toe, not at 50% midpoint
    const heelOffset = 0.06 * bs;
    const footLength = REF.foot_len * bs;
    const midfootRatio = (footLength / 2 - heelOffset) / footLength;
    const toeMidX = (kpts[17*3] + kpts[18*3]) / 2;
    const midfootTargetX = ankleMidX + midfootRatio * (toeMidX - ankleMidX);
    const stanceRatio = bodyParams.stanceWidth || CAPTURED_STANCE_WIDTH;
    const stanceLeanShift = (compensated && applyStanceOverride)
        ? 0.05 * (CAPTURED_STANCE_WIDTH - stanceRatio) : 0;
    const targetX = midfootTargetX + stanceLeanShift;
    const kneeMidX = (L.knee[0] + R.knee[0]) / 2;

    // Analytical COM solve using same segment model as computeCOM
    const S = SEGMENT_MASS;
    const mFoot = S.foot_l.frac + S.foot_r.frac;
    const mShank = S.shank_l.frac + S.shank_r.frac;
    const mThigh = S.thigh_l.frac + S.thigh_r.frac;
    const mUpper = S.trunk.frac + S.head.frac + S.upper_arm_l.frac + S.upper_arm_r.frac + S.forearm_l.frac + S.forearm_r.frac;
    const mTotal = mFoot + mShank + mThigh + mUpper;
    const sinCoeff = (S.trunk.frac * 0.5 * tl + S.head.frac * (tl + headH * 0.5) + (S.upper_arm_l.frac + S.upper_arm_r.frac + S.forearm_l.frac + S.forearm_r.frac) * tl) / mTotal;

    const newLowerCOMx = (mShank * (ankleMidX + kneeMidX) / 2 + mThigh * (kneeMidX + hipMidX) / 2 + mFoot * footComX) / mTotal;
    const newB = (mUpper / mTotal) * hipMidX + newLowerCOMx;
    const newSinTrunk = (targetX - newB) / sinCoeff;
    const clampedSin = Math.max(-1, Math.min(1, newSinTrunk));
    const comTrunkLean = Math.asin(clampedSin);

    // Captured trunk lean from shoulder/hip positions
    const capHipMidX = (cHL[0] + cHR[0]) / 2;
    const capHipMidY = (cHL[1] + cHR[1]) / 2;
    const capturedTrunkLean = lockedShoulder ? Math.atan2(lockedShoulder.x - capHipMidX, lockedShoulder.y - capHipMidY) : 0;

    // Phase-weighted blend: at standing use captured trunk; at depth use COM-balanced trunk
    let comWeight;
    if (compensated) {{
        // Soft attractor: proportional to total slider magnitude across ALL deltas
        const rawDorsiMag = Math.abs((deltas.dorsi||0)+(deltas.dorsiL||0)) + Math.abs((deltas.dorsi||0)+(deltas.dorsiR||0));
        const rawKfMag = Math.abs(deltas.kneeFlex||0);
        const rawKneeTrackMag = Math.abs(deltas.kneeTracking||0);
        const stanceChangeMag = applyStanceOverride
            ? Math.abs(stanceRatio - CAPTURED_STANCE_WIDTH) * 50 : 0;
        const toeOutChangeMag = Math.abs((bodyParams.toeOut||15) - 15);
        const totalDeltaMag = rawDorsiMag + rawKfMag + rawKneeTrackMag + stanceChangeMag + toeOutChangeMag;
        const phaseBlendComp = Math.min(1, Math.max(0, (phase - 0.1) * 3));
        const deltaBlendComp = Math.min(1, totalDeltaMag / 15);
        comWeight = phaseBlendComp * deltaBlendComp * 0.5;
    }} else {{
        const legDeltaMag = Math.sqrt(dDorsiL * dDorsiL + dDorsiR * dDorsiR + dKF * dKF);
        const phaseBlend = Math.min(1, Math.max(0, (phase - 0.15) * 5));
        const deltaBlend = Math.min(1, legDeltaMag / 15);
        comWeight = phaseBlend * deltaBlend;
    }}
    let totalTrunkLean = capturedTrunkLean * (1 - comWeight) + comTrunkLean * comWeight + dLean * deg2rad;

    const sMidX = hipMidX + tl * Math.sin(totalTrunkLean);
    const sMidY = hipMidY + tl * Math.cos(totalTrunkLean);
    set(5, sMidX, sMidY, k[5] ? k[5][2] : -sw/2);
    set(6, sMidX, sMidY, k[6] ? k[6][2] : sw/2);

    // Head & arms: offset from delta-FK shoulders using captured relative positions
    if (k[5] && k[6]) {{
        const capSMid = [(k[5][0]+k[6][0])/2, (k[5][1]+k[6][1])/2, (k[5][2]+k[6][2])/2];
        const fkSMid = [sMidX, sMidY, (kpts[5*3+2]+kpts[6*3+2])/2];
        for (const hIdx of [0, 1, 2, 3, 4]) {{
            if (k[hIdx]) {{
                kpts[hIdx*3]   = fkSMid[0] + (k[hIdx][0] - capSMid[0]);
                kpts[hIdx*3+1] = fkSMid[1] + (k[hIdx][1] - capSMid[1]);
                kpts[hIdx*3+2] = fkSMid[2] + (k[hIdx][2] - capSMid[2]);
            }}
        }}
        for (const [armJoints, sIdx] of [[[7, 9], 5], [[8, 10], 6]]) {{
            const fkS = [kpts[sIdx*3], kpts[sIdx*3+1], kpts[sIdx*3+2]];
            const capS = k[sIdx];
            for (const jIdx of armJoints) {{
                if (k[jIdx]) {{
                    kpts[jIdx*3]   = fkS[0] + (k[jIdx][0] - capS[0]);
                    kpts[jIdx*3+1] = fkS[1] + (k[jIdx][1] - capS[1]);
                    kpts[jIdx*3+2] = fkS[2] + (k[jIdx][2] - capS[2]);
                }}
            }}
        }}
    }} else {{
        const headX = sMidX + headH * Math.sin(totalTrunkLean) * 0.5;
        const headY = sMidY + headH;
        set(0, headX, headY, 0);
        set(1, headX, headY+0.02, -0.03*bs); set(2, headX, headY+0.02, 0.03*bs);
        set(3, headX, headY-0.01, -0.06*bs); set(4, headX, headY-0.01, 0.06*bs);
        const ual = REF.upper_arm * bs, fal = REF.forearm * bs;
        set(7, sMidX, sMidY-ual*0.7-0.15, k[5]?k[5][2]:-sw/2);
        set(8, sMidX, sMidY-ual*0.7-0.15, k[6]?k[6][2]:sw/2);
        set(9, kpts[7*3]+0.02, kpts[7*3+1]-fal*0.5, kpts[7*3+2]);
        set(10, kpts[8*3]+0.02, kpts[8*3+1]-fal*0.5, kpts[8*3+2]);
    }}

    // Effective per-side angles for display
    const dorsiLDeg = a.dorsi_l + dDorsiL;
    const dorsiRDeg = a.dorsi_r + dDorsiR;
    const kfLDeg = (a.knee_flex_l || a.knee_flex) + dKF;
    const kfRDeg = (a.knee_flex_r || a.knee_flex) + dKF;
    const valLDeg = a.knee_valgus_l + dValL;
    const valRDeg = a.knee_valgus_r + dValR;
    const trunkAngleDeg = 180 - (totalTrunkLean * rad2deg);
    const avgKneeDeg = (kfLDeg + kfRDeg) / 2;
    const avgDorsiDeg = (dorsiLDeg + dorsiRDeg) / 2;

    // Hip internal/external rotation from leg chain
    // Left leg: external rotation = negative hipRotationRad (toward -Z)
    // Right leg: external rotation = positive hipRotationRad (toward +Z)
    // Normalize so positive = external for both sides
    const hipRotLDeg = -L.hipRotationRad * rad2deg;
    const hipRotRDeg = R.hipRotationRad * rad2deg;

    return {{ kpts, trunkAngleDeg, avgKneeDeg, dorsiDeg: avgDorsiDeg,
              totalTrunkLeanDeg: totalTrunkLean * rad2deg,
              dorsiLDeg, dorsiRDeg, kfLDeg, kfRDeg, valLDeg, valRDeg,
              hipRotLDeg, hipRotRDeg,
              hipMidX, hipMidY, shoulderMidX: sMidX, shoulderMidY: sMidY }};
}}

// ======== CONSTRAINED CHAIN SOLVER ========
const JOINT_LIMITS = {{
    ankle: {{ min: 0, max: 45 * Math.PI / 180 }},
    knee:  {{ min: 0, max: 140 * Math.PI / 180 }},
    hip:   {{ min: 0, max: 130 * Math.PI / 180 }},
    trunk: {{ min: 0, max: 90 * Math.PI / 180 }},
}};

class ConstrainedChainSolver {{
    constructor(bodyScale, torsoRatio, thighRatio, shinRatio, toeOut, footRatio) {{
        this.shinLen = REF.shin_len * bodyScale * shinRatio;
        this.thighLen = REF.thigh_len * bodyScale * thighRatio;
        this.torsoLen = REF.torso_len * bodyScale * torsoRatio;
        this.headOffset = REF.head_offset * bodyScale;
        this.toeOutRad = toeOut * Math.PI / 180;
        this.heelOffset = 0.06;
        const scaledFootLen = REF.foot_len * bodyScale * (footRatio || 1.0);
        this.midfootX = (scaledFootLen / 2 - this.heelOffset) * Math.cos(this.toeOutRad);
        const S = SEGMENT_MASS;
        this.massFoot  = S.foot_l.frac + S.foot_r.frac;
        this.massShank = S.shank_l.frac + S.shank_r.frac;
        this.massThigh = S.thigh_l.frac + S.thigh_r.frac;
        this.massTrunk = S.trunk.frac;
        this.massHead  = S.head.frac;
        this.massArms  = S.upper_arm_l.frac + S.upper_arm_r.frac + S.forearm_l.frac + S.forearm_r.frac;
        this.massTotal = this.massFoot + this.massShank + this.massThigh + this.massTrunk + this.massHead + this.massArms;
    }}
    solve(ankleRad, targetHipY, barbellWeight, bodyMass) {{
        const clamped = Math.max(JOINT_LIMITS.ankle.min, Math.min(JOINT_LIMITS.ankle.max, ankleRad));
        const kneeResult = this._solveKneeFromDepth(clamped, targetHipY);
        if (!kneeResult.valid) return {{ valid: false, reason: 'depth_infeasible' }};
        const kneeRad = Math.max(JOINT_LIMITS.knee.min, Math.min(JOINT_LIMITS.knee.max, kneeResult.kneeRad));
        const hipPos = this._computeHipPosition(clamped, kneeRad);
        const lowerCOMx = this._computeLowerBodyCOMx(clamped, kneeRad);
        let trunkRad;
        if (barbellWeight > 0) {{
            trunkRad = this._solveTrunkWithBarbell(hipPos.x, lowerCOMx, barbellWeight, bodyMass);
        }} else {{
            trunkRad = this._solveTrunkFromCOM(hipPos.x, lowerCOMx, 0, 0);
        }}
        if (trunkRad === null) return {{ valid: false, reason: 'com_infeasible' }};
        trunkRad = Math.max(JOINT_LIMITS.trunk.min, Math.min(JOINT_LIMITS.trunk.max, trunkRad));
        const thighAngle = clamped - kneeRad;
        const hipFlexion = trunkRad - thighAngle;
        const deg = 180 / Math.PI;
        return {{ valid: true, ankle: clamped, knee: kneeRad, hip: hipFlexion, trunk: trunkRad,
                  ankleDeg: clamped * deg, kneeDeg: kneeRad * deg, hipDeg: hipFlexion * deg, trunkDeg: trunkRad * deg,
                  hipX: hipPos.x, hipY: hipPos.y }};
    }}
    _solveKneeFromDepth(ankleRad, targetHipY) {{
        const remaining = targetHipY - this.shinLen * Math.cos(ankleRad);
        const cosArg = remaining / this.thighLen;
        if (Math.abs(cosArg) > 1) return {{ valid: false }};
        const thighAngle = ankleRad - Math.acos(cosArg);
        return {{ valid: true, kneeRad: ankleRad - thighAngle }};
    }}
    _computeHipPosition(ankleRad, kneeRad) {{
        const thighAngle = ankleRad - kneeRad;
        return {{ x: this.shinLen * Math.sin(ankleRad) + this.thighLen * Math.sin(thighAngle),
                  y: this.shinLen * Math.cos(ankleRad) + this.thighLen * Math.cos(thighAngle) }};
    }}
    _computeLowerBodyCOMx(ankleRad, kneeRad) {{
        const kneeX = this.shinLen * Math.sin(ankleRad);
        const thighAngle = ankleRad - kneeRad;
        const shankCOMx = 0.5 * kneeX;
        const thighCOMx = kneeX + 0.5 * this.thighLen * Math.sin(thighAngle);
        return (this.massShank * shankCOMx + this.massThigh * thighCOMx + this.massFoot * this.midfootX) / this.massTotal;
    }}
    _solveTrunkFromCOM(hipX, lowerCOMx, barContribX, barFrac) {{
        const bodyFrac = 1 - barFrac;
        const upperMass = this.massTrunk + this.massHead + this.massArms;
        const A = (this.massTrunk * 0.5 * this.torsoLen +
                   this.massHead * (this.torsoLen + this.headOffset * 0.5) +
                   this.massArms * this.torsoLen) / this.massTotal * bodyFrac;
        const B = upperMass / this.massTotal * hipX * bodyFrac + lowerCOMx * bodyFrac + barContribX;
        const sinTrunk = (this.midfootX - B) / A;
        if (Math.abs(sinTrunk) > 1) return null;
        return Math.asin(sinTrunk);
    }}
    _solveTrunkWithBarbell(hipX, lowerCOMx, barbellWeight, bodyMass) {{
        const barFrac = barbellWeight / (bodyMass + barbellWeight);
        let trunkRad = this._solveTrunkFromCOM(hipX, lowerCOMx, 0, 0) || 0.2;
        for (let i = 0; i < 3; i++) {{
            const barX = hipX + 0.04 * Math.sin(trunkRad) - 0.05 * Math.cos(trunkRad);
            const solved = this._solveTrunkFromCOM(hipX, lowerCOMx, barX * barFrac, barFrac);
            if (solved === null) return trunkRad;
            trunkRad = solved;
        }}
        return trunkRad;
    }}
}}

// ======== KINODYNAMICS SOLVER (20-DOF what-if optimizer) ========
class KinodynamicsSolver {{
    constructor(skelDef) {{
        const nj = skelDef.n_joints, nd = skelDef.n_dof;
        this.nj = nj; this.nd = nd;
        this.joints = skelDef.joints;
        this.dofMap = skelDef.dof_map;
        this.jointMasses = new Float64Array(skelDef.joint_masses);
        this.totalMass = 0;
        for (let i = 0; i < nj; i++) this.totalMass += this.jointMasses[i];
        this.parentIdx = new Int32Array(nj);
        this.offsets = new Float64Array(nj * 3);
        this.nameToIdx = {{}};
        this.dofStart = new Int32Array(nj);
        this.dofCount = new Int32Array(nj);
        let cursor = 0;
        for (let i = 0; i < nj; i++) {{
            const jd = this.joints[i];
            this.nameToIdx[jd.name] = i;
            this.dofStart[i] = cursor;
            this.dofCount[i] = jd.dof_axes.length;
            cursor += jd.dof_axes.length;
            this.offsets[i*3] = jd.offset[0];
            this.offsets[i*3+1] = jd.offset[1];
            this.offsets[i*3+2] = jd.offset[2];
        }}
        for (let i = 0; i < nj; i++) {{
            this.parentIdx[i] = this.joints[i].parent !== null
                ? this.nameToIdx[this.joints[i].parent] : -1;
        }}
        this.boundsLo = new Float64Array(nd);
        this.boundsHi = new Float64Array(nd);
        for (let i = 0; i < nd; i++) {{
            this.boundsLo[i] = skelDef.bounds[i][0];
            this.boundsHi[i] = skelDef.bounds[i][1];
        }}
        this.desc = this._buildDesc();
        this._torqueJoints = ['L_ankle','R_ankle','L_knee','R_knee','L_hip','R_hip']
            .map(n => this.nameToIdx[n]).filter(x => x !== undefined);
        this._lAnkle = this.nameToIdx['L_ankle'];
        this._rAnkle = this.nameToIdx['R_ankle'];
        this._trunk  = this.nameToIdx['trunk'];
        this._lKnee  = this.nameToIdx['L_knee'];
        this._rKnee  = this.nameToIdx['R_knee'];
        this._lHip   = this.nameToIdx['L_hip'];
        this._rHip   = this.nameToIdx['R_hip'];
        this._lToe   = this.nameToIdx['L_toe'];
        this._rToe   = this.nameToIdx['R_toe'];
        this._Rw = new Float64Array(nj * 9);
        this._symmetryPairs = [
            ['L_hip','R_hip','rx',false],
            ['L_hip','R_hip','ry',true],
            ['L_knee','R_knee','rx',false],
            ['L_ankle','R_ankle','rx',false],
            ['L_ankle','R_ankle','ry',true],
        ].map(([lj,rj,ax,mirror]) => [this.dofMap[lj+'.'+ax], this.dofMap[rj+'.'+ax], mirror])
         .filter(([l,r]) => l!==undefined && r!==undefined);
    }}
    _buildDesc() {{
        const n = this.nj;
        const ch = Array.from({{length: n}}, () => []);
        for (let i = 0; i < n; i++) {{
            if (this.parentIdx[i] >= 0) ch[this.parentIdx[i]].push(i);
        }}
        const d = Array.from({{length: n}}, () => new Set());
        for (let i = n-1; i >= 0; i--) {{
            for (const c of ch[i]) {{ d[i].add(c); for (const x of d[c]) d[i].add(x); }}
        }}
        return d.map(s => Int32Array.from([...s].sort((a,b) => a-b)));
    }}
    _axIdx(a) {{ return a === 'x' ? 0 : a === 'y' ? 1 : 2; }}
    _rot3(out, off, axis, t) {{
        const c = Math.cos(t), s = Math.sin(t);
        out[off]=1;out[off+1]=0;out[off+2]=0;
        out[off+3]=0;out[off+4]=1;out[off+5]=0;
        out[off+6]=0;out[off+7]=0;out[off+8]=1;
        if (axis===0) {{ out[off+4]=c;out[off+5]=-s;out[off+7]=s;out[off+8]=c; }}
        else if (axis===1) {{ out[off]=c;out[off+2]=s;out[off+6]=-s;out[off+8]=c; }}
        else {{ out[off]=c;out[off+1]=-s;out[off+3]=s;out[off+4]=c; }}
    }}
    _mul33(C, co, A, ao, B, bo) {{
        for (let i=0;i<3;i++) for (let j=0;j<3;j++)
            C[co+i*3+j] = A[ao+i*3]*B[bo+j] + A[ao+i*3+1]*B[bo+3+j] + A[ao+i*3+2]*B[bo+6+j];
    }}
    fk(q) {{
        const {{nj, joints, _Rw: Rw}} = this;
        const pos = new Float64Array(nj * 3);
        const tA = new Float64Array(9), tB = new Float64Array(9), tC = new Float64Array(9);
        for (let i = 0; i < nj; i++) {{
            const jd = joints[i], s0 = this.dofStart[i], nc = this.dofCount[i];
            if (this.parentIdx[i] < 0) {{
                for (let k=0;k<nc;k++) {{ const ax=jd.dof_axes[k]; if(ax[0]==='t') pos[i*3+this._axIdx(ax[1])]=q[s0+k]; }}
                let ro=i*9; Rw[ro]=1;Rw[ro+1]=0;Rw[ro+2]=0;Rw[ro+3]=0;Rw[ro+4]=1;Rw[ro+5]=0;Rw[ro+6]=0;Rw[ro+7]=0;Rw[ro+8]=1;
                for (let k=0;k<nc;k++) {{ const ax=jd.dof_axes[k]; if(ax[0]==='r') {{
                    this._rot3(tA,0,this._axIdx(ax[1]),q[s0+k]); this._mul33(tB,0,Rw,ro,tA,0);
                    for(let m=0;m<9;m++) Rw[ro+m]=tB[m];
                }} }}
            }} else {{
                const pi=this.parentIdx[i], pr=pi*9;
                const ox=this.offsets[i*3], oy=this.offsets[i*3+1], oz=this.offsets[i*3+2];
                pos[i*3]  =pos[pi*3]  +Rw[pr]*ox+Rw[pr+1]*oy+Rw[pr+2]*oz;
                pos[i*3+1]=pos[pi*3+1]+Rw[pr+3]*ox+Rw[pr+4]*oy+Rw[pr+5]*oz;
                pos[i*3+2]=pos[pi*3+2]+Rw[pr+6]*ox+Rw[pr+7]*oy+Rw[pr+8]*oz;
                tA[0]=1;tA[1]=0;tA[2]=0;tA[3]=0;tA[4]=1;tA[5]=0;tA[6]=0;tA[7]=0;tA[8]=1;
                for (let k=0;k<nc;k++) {{ const ax=jd.dof_axes[k]; if(ax[0]==='r') {{
                    this._rot3(tB,0,this._axIdx(ax[1]),q[s0+k]); this._mul33(tC,0,tA,0,tB,0);
                    for(let m=0;m<9;m++) tA[m]=tC[m];
                }} }}
                this._mul33(Rw,i*9,Rw,pr,tA,0);
            }}
        }}
        return {{ pos, Rw: new Float64Array(Rw) }};
    }}
    fkJac(q) {{
        const {{nj, nd, joints, _Rw: Rw}} = this;
        const pos = new Float64Array(nj*3);
        const J = new Float64Array(nj*3*nd);
        const tA=new Float64Array(9), tB=new Float64Array(9), tC=new Float64Array(9);
        // Forward pass
        for (let i=0;i<nj;i++) {{
            const jd=joints[i], s0=this.dofStart[i], nc=this.dofCount[i];
            if (this.parentIdx[i]<0) {{
                for(let k=0;k<nc;k++) {{ const ax=jd.dof_axes[k]; if(ax[0]==='t') pos[i*3+this._axIdx(ax[1])]=q[s0+k]; }}
                let ro=i*9; Rw[ro]=1;Rw[ro+1]=0;Rw[ro+2]=0;Rw[ro+3]=0;Rw[ro+4]=1;Rw[ro+5]=0;Rw[ro+6]=0;Rw[ro+7]=0;Rw[ro+8]=1;
                for(let k=0;k<nc;k++) {{ const ax=jd.dof_axes[k]; if(ax[0]==='r') {{
                    this._rot3(tA,0,this._axIdx(ax[1]),q[s0+k]); this._mul33(tB,0,Rw,ro,tA,0);
                    for(let m=0;m<9;m++) Rw[ro+m]=tB[m];
                }} }}
            }} else {{
                const pi=this.parentIdx[i], pr=pi*9;
                const ox=this.offsets[i*3],oy=this.offsets[i*3+1],oz=this.offsets[i*3+2];
                pos[i*3]  =pos[pi*3]  +Rw[pr]*ox+Rw[pr+1]*oy+Rw[pr+2]*oz;
                pos[i*3+1]=pos[pi*3+1]+Rw[pr+3]*ox+Rw[pr+4]*oy+Rw[pr+5]*oz;
                pos[i*3+2]=pos[pi*3+2]+Rw[pr+6]*ox+Rw[pr+7]*oy+Rw[pr+8]*oz;
                tA[0]=1;tA[1]=0;tA[2]=0;tA[3]=0;tA[4]=1;tA[5]=0;tA[6]=0;tA[7]=0;tA[8]=1;
                for(let k=0;k<nc;k++) {{ const ax=jd.dof_axes[k]; if(ax[0]==='r') {{
                    this._rot3(tB,0,this._axIdx(ax[1]),q[s0+k]); this._mul33(tC,0,tA,0,tB,0);
                    for(let m=0;m<9;m++) tA[m]=tC[m];
                }} }}
                this._mul33(Rw,i*9,Rw,pr,tA,0);
            }}
        }}
        // Jacobian pass
        for (let i=0;i<nj;i++) {{
            const jd=joints[i], s0=this.dofStart[i], nc=this.dofCount[i], di=this.desc[i];
            if (this.parentIdx[i]<0) {{
                tA[0]=1;tA[1]=0;tA[2]=0;tA[3]=0;tA[4]=1;tA[5]=0;tA[6]=0;tA[7]=0;tA[8]=1;
                for (let k=0;k<nc;k++) {{
                    const ax=jd.dof_axes[k], col=s0+k;
                    if (ax[0]==='t') {{
                        const dim=this._axIdx(ax[1]);
                        for(let j=0;j<nj;j++) J[(j*3+dim)*nd+col]=1.0;
                    }} else {{
                        const aidx=this._axIdx(ax[1]);
                        const ux=aidx===0?1:0, uy=aidx===1?1:0, uz=aidx===2?1:0;
                        const wax=tA[0]*ux+tA[1]*uy+tA[2]*uz;
                        const way=tA[3]*ux+tA[4]*uy+tA[5]*uz;
                        const waz=tA[6]*ux+tA[7]*uy+tA[8]*uz;
                        for (const j of di) {{
                            const dx=pos[j*3]-pos[i*3], dy=pos[j*3+1]-pos[i*3+1], dz=pos[j*3+2]-pos[i*3+2];
                            J[(j*3  )*nd+col]=way*dz-waz*dy;
                            J[(j*3+1)*nd+col]=waz*dx-wax*dz;
                            J[(j*3+2)*nd+col]=wax*dy-way*dx;
                        }}
                        this._rot3(tB,0,aidx,q[s0+k]); this._mul33(tC,0,tA,0,tB,0);
                        for(let m=0;m<9;m++) tA[m]=tC[m];
                    }}
                }}
            }} else {{
                const pr=this.parentIdx[i]*9;
                tA[0]=1;tA[1]=0;tA[2]=0;tA[3]=0;tA[4]=1;tA[5]=0;tA[6]=0;tA[7]=0;tA[8]=1;
                for (let k=0;k<nc;k++) {{
                    const ax=jd.dof_axes[k], col=s0+k;
                    if (ax[0]==='r') {{
                        const aidx=this._axIdx(ax[1]);
                        const ux=aidx===0?1:0, uy=aidx===1?1:0, uz=aidx===2?1:0;
                        const rpx=tA[0]*ux+tA[1]*uy+tA[2]*uz;
                        const rpy=tA[3]*ux+tA[4]*uy+tA[5]*uz;
                        const rpz=tA[6]*ux+tA[7]*uy+tA[8]*uz;
                        const wax=Rw[pr]*rpx+Rw[pr+1]*rpy+Rw[pr+2]*rpz;
                        const way=Rw[pr+3]*rpx+Rw[pr+4]*rpy+Rw[pr+5]*rpz;
                        const waz=Rw[pr+6]*rpx+Rw[pr+7]*rpy+Rw[pr+8]*rpz;
                        for (const j of di) {{
                            const dx=pos[j*3]-pos[i*3], dy=pos[j*3+1]-pos[i*3+1], dz=pos[j*3+2]-pos[i*3+2];
                            J[(j*3  )*nd+col]=way*dz-waz*dy;
                            J[(j*3+1)*nd+col]=waz*dx-wax*dz;
                            J[(j*3+2)*nd+col]=wax*dy-way*dx;
                        }}
                        this._rot3(tB,0,aidx,q[s0+k]); this._mul33(tC,0,tA,0,tB,0);
                        for(let m=0;m<9;m++) tA[m]=tC[m];
                    }}
                }}
            }}
        }}
        return {{ pos, J }};
    }}
    comFromPos(pos) {{
        let cx=0, cy=0, cz=0;
        for (let j=0;j<this.nj;j++) {{
            const m=this.jointMasses[j];
            cx+=m*pos[j*3]; cy+=m*pos[j*3+1]; cz+=m*pos[j*3+2];
        }}
        const t=this.totalMass;
        return [cx/t, cy/t, cz/t];
    }}
    comJac(J) {{
        const {{nd, nj, totalMass}}=this;
        const cj=new Float64Array(3*nd);
        for (let j=0;j<nj;j++) {{
            const m=this.jointMasses[j]/totalMass;
            for (let d=0;d<nd;d++) {{
                cj[d]       +=m*J[(j*3  )*nd+d];
                cj[nd+d]    +=m*J[(j*3+1)*nd+d];
                cj[2*nd+d]  +=m*J[(j*3+2)*nd+d];
            }}
        }}
        return cj;
    }}
    supportBounds(pos) {{
        const la=this._lAnkle, ra=this._rAnkle;
        return [
            Math.min(pos[la*3],pos[ra*3])-0.05,
            Math.max(pos[la*3],pos[ra*3])+0.05,
            (pos[la*3+2]+pos[ra*3+2])*0.5-0.10,
            (pos[la*3+2]+pos[ra*3+2])*0.5+0.15,
        ];
    }}
    combinedCostAndGrad(q, qRef, weights, supBounds, dofWeights) {{
        const nd=this.nd;
        const {{pos, J}}=this.fkJac(q);
        const com=this.comFromPos(pos);
        const cj=this.comJac(J);
        let tc=0;
        const tg=new Float64Array(nd);
        // 1. Pose deviation
        const wPd=weights.pose_deviation!==undefined?weights.pose_deviation:1.0;
        for (let i=0;i<nd;i++) {{
            const diff=q[i]-qRef[i];
            const w=dofWeights?wPd*dofWeights[i]:wPd;
            tc+=0.5*w*diff*diff; tg[i]+=w*diff;
        }}
        // 2. Torque proxy
        const wTp=weights.torque_proxy!==undefined?weights.torque_proxy:0.5;
        if (wTp>0) for (const ji of this._torqueJoints) {{
            const dx=com[0]-pos[ji*3], dz=com[2]-pos[ji*3+2];
            tc+=0.5*wTp*(dx*dx+dz*dz);
            for (let d=0;d<nd;d++) tg[d]+=wTp*(dx*(cj[d]-J[(ji*3)*nd+d])+dz*(cj[2*nd+d]-J[(ji*3+2)*nd+d]));
        }}
        // 3. Load over midfoot (COM over midfoot center from ankle+toe midpoints)
        const wLm=weights.load_over_midfoot!==undefined?weights.load_over_midfoot:2.0;
        if (wLm>0) {{
            const la=this._lAnkle, ra=this._rAnkle, lt=this._lToe, rt=this._rToe;
            const mfx=0.25*(pos[la*3]+pos[lt*3]+pos[ra*3]+pos[rt*3]);
            const mfz=0.25*(pos[la*3+2]+pos[lt*3+2]+pos[ra*3+2]+pos[rt*3+2]);
            const dx=com[0]-mfx, dz=com[2]-mfz;
            tc+=0.5*wLm*(dx*dx+dz*dz);
            for (let d=0;d<nd;d++) {{
                const mjx=0.25*(J[(la*3)*nd+d]+J[(lt*3)*nd+d]+J[(ra*3)*nd+d]+J[(rt*3)*nd+d]);
                const mjz=0.25*(J[(la*3+2)*nd+d]+J[(lt*3+2)*nd+d]+J[(ra*3+2)*nd+d]+J[(rt*3+2)*nd+d]);
                tg[d]+=wLm*(dx*(cj[d]-mjx)+dz*(cj[2*nd+d]-mjz));
            }}
        }}
        // 4. Knee tracking over toes (lateral error perpendicular to toe direction)
        const wKt=weights.knee_tracking!==undefined?weights.knee_tracking:1.0;
        if (wKt>0) for (const [ki,ai,ti] of [[this._lKnee,this._lAnkle,this._lToe],[this._rKnee,this._rAnkle,this._rToe]]) {{
            let tdx=pos[ti*3]-pos[ai*3], tdz=pos[ti*3+2]-pos[ai*3+2];
            const tl=Math.sqrt(tdx*tdx+tdz*tdz);
            if (tl>1e-6) {{ tdx/=tl; tdz/=tl; }} else {{ tdx=0; tdz=1; }}
            const px=-tdz, pz=tdx;
            const krx=pos[ki*3]-pos[ai*3], krz=pos[ki*3+2]-pos[ai*3+2];
            const lateralErr=krx*px+krz*pz;
            tc+=0.5*wKt*lateralErr*lateralErr;
            for (let d=0;d<nd;d++) {{
                const dkrx=J[(ki*3)*nd+d]-J[(ai*3)*nd+d];
                const dkrz=J[(ki*3+2)*nd+d]-J[(ai*3+2)*nd+d];
                tg[d]+=wKt*lateralErr*(dkrx*px+dkrz*pz);
            }}
        }}
        // 5. Balance margin
        const wBm=weights.balance_margin!==undefined?weights.balance_margin:0.5;
        const margin=0.05;
        if (wBm>0) {{
            const [xMin,xMax,zMin,zMax]=supBounds;
            let dist;
            dist=com[0]-xMin; if(dist<margin) {{ const v=margin-dist; tc+=0.5*wBm*v*v; for(let d=0;d<nd;d++) tg[d]-=wBm*v*cj[d]; }}
            dist=xMax-com[0]; if(dist<margin) {{ const v=margin-dist; tc+=0.5*wBm*v*v; for(let d=0;d<nd;d++) tg[d]+=wBm*v*cj[d]; }}
            dist=com[2]-zMin; if(dist<margin) {{ const v=margin-dist; tc+=0.5*wBm*v*v; for(let d=0;d<nd;d++) tg[d]-=wBm*v*cj[2*nd+d]; }}
            dist=zMax-com[2]; if(dist<margin) {{ const v=margin-dist; tc+=0.5*wBm*v*v; for(let d=0;d<nd;d++) tg[d]+=wBm*v*cj[2*nd+d]; }}
        }}
        // 6. Symmetry
        const wSy=weights.symmetry!==undefined?weights.symmetry:0.0;
        if (wSy>0) {{
            for (const [li,ri,mirror] of this._symmetryPairs) {{
                const diff=mirror ? q[li]+q[ri] : q[li]-q[ri];
                tc+=0.5*wSy*diff*diff;
                if (mirror) {{ tg[li]+=wSy*diff; tg[ri]+=wSy*diff; }}
                else {{ tg[li]+=wSy*diff; tg[ri]-=wSy*diff; }}
            }}
        }}
        return {{ cost:tc, grad:tg, pos, J, com, cj }};
    }}
    _solve6(A,b) {{
        const M=new Float64Array(36),x=new Float64Array(6);
        for(let i=0;i<36;i++)M[i]=A[i]; for(let i=0;i<6;i++)x[i]=b[i];
        for(let c=0;c<6;c++){{
            let mv=Math.abs(M[c*6+c]),mr=c;
            for(let r=c+1;r<6;r++){{const v=Math.abs(M[r*6+c]);if(v>mv){{mv=v;mr=r;}}}}
            if(mv<1e-12)continue;
            if(mr!==c){{for(let k=0;k<6;k++){{const t=M[c*6+k];M[c*6+k]=M[mr*6+k];M[mr*6+k]=t;}}const t=x[c];x[c]=x[mr];x[mr]=t;}}
            const pv=M[c*6+c];
            for(let r=c+1;r<6;r++){{const f=M[r*6+c]/pv;for(let k=c+1;k<6;k++)M[r*6+k]-=f*M[c*6+k];M[r*6+c]=0;x[r]-=f*x[c];}}
        }}
        for(let i=5;i>=0;i--){{for(let j=i+1;j<6;j++)x[i]-=M[i*6+j]*x[j];x[i]=Math.abs(M[i*6+i])>1e-12?x[i]/M[i*6+i]:0;}}
        return x;
    }}
    whatifSolve(qFitted, perturbation, costWeights, maxIter, footTargetDelta) {{
        maxIter=maxIter||100;
        costWeights=costWeights||{{
            pose_deviation:1.0, torque_proxy:0.5,
            load_over_midfoot:2.0, knee_tracking:1.0, balance_margin:0.5
        }};
        const nd=this.nd, la=this._lAnkle, ra=this._rAnkle;
        const LOCK_WEIGHT=50.0;
        const r0=this.fkJac(qFitted);
        const fTgt=new Float64Array(6);
        for(let d=0;d<3;d++) {{ fTgt[d]=r0.pos[la*3+d]; fTgt[3+d]=r0.pos[ra*3+d]; }}
        if (footTargetDelta) for(let d=0;d<6;d++) fTgt[d]+=footTargetDelta[d];
        const sup=this.supportBounds(r0.pos);
        const qRef=new Float64Array(qFitted);
        const dofW=new Float64Array(nd).fill(1.0);
        const pertIdx=new Set();
        for (const key in perturbation) {{
            const idx=this.dofMap[key];
            if(idx!==undefined) {{ qRef[idx]+=perturbation[key]; dofW[idx]=LOCK_WEIGHT; pertIdx.add(idx); }}
        }}
        const MAX_WANDER=0.52;
        const tLo=new Float64Array(nd), tHi=new Float64Array(nd);
        for(let i=0;i<nd;i++) {{
            if(pertIdx.has(i)) {{ tLo[i]=this.boundsLo[i]; tHi[i]=this.boundsHi[i]; }}
            else {{ tLo[i]=Math.max(this.boundsLo[i],qFitted[i]-MAX_WANDER); tHi[i]=Math.min(this.boundsHi[i],qFitted[i]+MAX_WANDER); }}
        }}
        const lHipRx=this.dofMap['L_hip.rx'], rHipRx=this.dofMap['R_hip.rx'];
        if(lHipRx!==undefined) tLo[lHipRx]=Math.max(tLo[lHipRx],0.0);
        if(rHipRx!==undefined) tLo[rHipRx]=Math.max(tLo[rHipRx],0.0);
        for(let i=0;i<nd;i++) qRef[i]=Math.max(tLo[i],Math.min(tHi[i],qRef[i]));
        const fR=[la*3,la*3+1,la*3+2,ra*3,ra*3+1,ra*3+2];
        const clp=(v,i)=>Math.max(tLo[i],Math.min(tHi[i],v));
        const mkA=(J)=>{{
            const A=new Float64Array(36);
            for(let i=0;i<6;i++) for(let j=i;j<6;j++) {{
                let s=0; for(let k=0;k<nd;k++) s+=J[fR[i]*nd+k]*J[fR[j]*nd+k];
                A[i*6+j]=s; A[j*6+i]=s;
            }}
            for(let i=0;i<6;i++) A[i*6+i]+=1e-8;
            return A;
        }};
        const fErr=(pos)=>{{
            const e=new Float64Array(6);
            for(let d=0;d<3;d++) {{ e[d]=pos[la*3+d]-fTgt[d]; e[3+d]=pos[ra*3+d]-fTgt[3+d]; }}
            return e;
        }};
        const q=new Float64Array(qRef);
        for(let ws=0;ws<20;ws++) {{
            const {{pos,J}}=this.fkJac(q);
            const e=fErr(pos);
            let en=0; for(let i=0;i<6;i++) en+=e[i]*e[i];
            if(en<1e-16) break;
            const mu=this._solve6(mkA(J),e);
            for(let k=0;k<nd;k++) {{ let c=0; for(let i=0;i<6;i++) c+=mu[i]*J[fR[i]*nd+k]; q[k]=clp(q[k]-c,k); }}
        }}
        for(let iter=0;iter<maxIter;iter++) {{
            const r=this.combinedCostAndGrad(q,qRef,costWeights,sup,dofW);
            const J=r.J, pos=r.pos, grad=r.grad;
            const e=fErr(pos);
            const A=mkA(J);
            const v=new Float64Array(6);
            for(let i=0;i<6;i++) {{ let s=0; for(let k=0;k<nd;k++) s+=J[fR[i]*nd+k]*grad[k]; v[i]=s; }}
            const lam=this._solve6(A,v);
            const gP=new Float64Array(nd);
            for(let k=0;k<nd;k++) gP[k]=grad[k];
            for(let i=0;i<6;i++) for(let k=0;k<nd;k++) gP[k]-=lam[i]*J[fR[i]*nd+k];
            const mu=this._solve6(A,e);
            const dc=new Float64Array(nd);
            for(let i=0;i<6;i++) for(let k=0;k<nd;k++) dc[k]+=mu[i]*J[fR[i]*nd+k];
            let gn=0; for(let i=0;i<nd;i++) gn+=gP[i]*gP[i];
            let en=0; for(let i=0;i<6;i++) en+=e[i]*e[i];
            if(gn<1e-12&&en<1e-10) break;
            let alpha=0.1;
            for(let ls=0;ls<12;ls++) {{
                const qt=new Float64Array(nd);
                for(let i=0;i<nd;i++) qt[i]=clp(q[i]-alpha*gP[i]-dc[i],i);
                const rt=this.combinedCostAndGrad(qt,qRef,costWeights,sup,dofW);
                if(rt.cost<=r.cost-1e-4*alpha*gn||ls===11) {{ for(let i=0;i<nd;i++) q[i]=qt[i]; break; }}
                alpha*=0.5;
            }}
        }}
        return q;
    }}
    static gaussianTaper(nFrames, bottomFrame, sigmaFrames) {{
        if(!sigmaFrames) sigmaFrames=nFrames/6.0;
        const taper=new Float64Array(nFrames);
        for(let t=0;t<nFrames;t++) {{ const d=(t-bottomFrame)/sigmaFrames; taper[t]=Math.exp(-0.5*d*d); }}
        return taper;
    }}
    warpRep(qTrajectory, bottomFrame, perturbation, costWeights, footTargetDelta) {{
        const nFrames=qTrajectory.length, nd=this.nd;
        const hasPert=Object.keys(perturbation).length>0;
        const hasFtd=footTargetDelta&&(Math.abs(footTargetDelta[0])>1e-6||Math.abs(footTargetDelta[3])>1e-6);
        if(!hasPert&&!hasFtd) return qTrajectory.map(q=>new Float64Array(q));
        const taper=KinodynamicsSolver.gaussianTaper(nFrames,bottomFrame);
        const qCorr=this.whatifSolve(qTrajectory[bottomFrame],perturbation,costWeights,100,footTargetDelta);
        const delta=new Float64Array(nd);
        for(let i=0;i<nd;i++) delta[i]=qCorr[i]-qTrajectory[bottomFrame][i];
        const result=new Array(nFrames);
        for(let t=0;t<nFrames;t++) {{
            const qc=new Float64Array(nd);
            for(let i=0;i<nd;i++) {{
                qc[i]=qTrajectory[t][i]+taper[t]*delta[i];
                qc[i]=Math.max(this.boundsLo[i],Math.min(this.boundsHi[i],qc[i]));
            }}
            result[t]=qc;
        }}
        return result;
    }}
}}

// ======== KINODYNAMICS HELPERS ========
let _kinoSolver = null, _kinoWarpedQ = null, _kinoWarpKey = '', _kinoSolveMs = 0;
if (KINO_DATA && KINO_DATA.skeleton_def) {{
    _kinoSolver = new KinodynamicsSolver(KINO_DATA.skeleton_def);
    const kinoLabel = document.getElementById('sb-kino-radio-label');
    if (kinoLabel) kinoLabel.style.display = 'flex';
}}
window.addEventListener('pywebviewready', function() {{
    if (_kinoSolver && KINO_DATA) {{
        const kr = document.querySelector('input[name="sb-solver-mode"][value="kinodynamics"]');
        if (kr) {{ kr.checked = true; kr.dispatchEvent(new Event('change', {{bubbles:true}})); }}
        document.getElementById('tab-sandbox').click();
        const ki = document.getElementById('sb-kino-info');
        if (ki) ki.innerHTML = '20-DOF SLSQP optimizer (Python) &bull; pywebview bridge';
    }}
}});

function kinoQToKeypoints(solver, q, origFrame, bodyParams) {{
    const {{pos, Rw}} = solver.fk(q);
    const nj = solver.nj;
    const kpts = new Float64Array(19 * 3);

    // Transform ALL FK positions: landmark space → vis space
    // vis_x = lm_z, vis_y = lm_y, vis_z = lm_x
    const vp = new Float64Array(nj * 3);
    for (let i = 0; i < nj; i++) {{
        vp[i*3]   = pos[i*3+2];
        vp[i*3+1] = pos[i*3+1];
        vp[i*3+2] = pos[i*3];
    }}
    // Ground (ankle min Y → 0) and center (hip midpoint X/Z → 0)
    const lai=solver._lAnkle, rai=solver._rAnkle, lhi=solver._lHip, rhi=solver._rHip;
    const ankMinY = Math.min(vp[lai*3+1], vp[rai*3+1]);
    const hipMX = (vp[lhi*3] + vp[rhi*3]) / 2;
    const hipMZ = (vp[lhi*3+2] + vp[rhi*3+2]) / 2;
    for (let i = 0; i < nj; i++) {{ vp[i*3] -= hipMX; vp[i*3+1] -= ankMinY; vp[i*3+2] -= hipMZ; }}

    // Assign lower-body joints
    for (const [si, ki] of [
        [solver._lHip,11],[solver._rHip,12],[solver._lKnee,13],[solver._rKnee,14],
        [solver._lAnkle,15],[solver._rAnkle,16]
    ]) {{ kpts[ki*3]=vp[si*3]; kpts[ki*3+1]=vp[si*3+1]; kpts[ki*3+2]=vp[si*3+2]; }}

    // Trunk local-Y in vis space (for shoulder/head placement)
    const ti=solver._trunk, tro=ti*9;
    const upVis = [Rw[tro+7], Rw[tro+4], Rw[tro+1]];
    const remTorso=0.22*(bodyParams.bodyScale||1.0);
    const smX=vp[ti*3]   + upVis[0]*remTorso;
    const smY=vp[ti*3+1] + upVis[1]*remTorso;
    const smZ=vp[ti*3+2] + upVis[2]*remTorso;
    const sw=REF.shoulder_width*(bodyParams.bodyScale||1.0)*(bodyParams.shoulderWidthRatio||1.0);
    kpts[5*3]=smX; kpts[5*3+1]=smY; kpts[5*3+2]=smZ-sw/2;
    kpts[6*3]=smX; kpts[6*3+1]=smY; kpts[6*3+2]=smZ+sw/2;
    const k=origFrame&&origFrame.kpts;
    if (k&&k[5]&&k[6]) {{
        const capSMid=[(k[5][0]+k[6][0])/2,(k[5][1]+k[6][1])/2,(k[5][2]+k[6][2])/2];
        const fkSMid=[smX,smY,(kpts[5*3+2]+kpts[6*3+2])/2];
        for(const hi of [0,1,2,3,4]) {{ if(k[hi]) {{
            kpts[hi*3]=fkSMid[0]+(k[hi][0]-capSMid[0]);
            kpts[hi*3+1]=fkSMid[1]+(k[hi][1]-capSMid[1]);
            kpts[hi*3+2]=fkSMid[2]+(k[hi][2]-capSMid[2]);
        }} }}
        for(const [arms,sIdx] of [[[7,9],5],[[8,10],6]]) {{
            const fkS=[kpts[sIdx*3],kpts[sIdx*3+1],kpts[sIdx*3+2]];
            const capS=k[sIdx];
            if(capS) for(const ai of arms) {{ if(k[ai]) {{
                kpts[ai*3]=fkS[0]+(k[ai][0]-capS[0]);
                kpts[ai*3+1]=fkS[1]+(k[ai][1]-capS[1]);
                kpts[ai*3+2]=fkS[2]+(k[ai][2]-capS[2]);
            }} }}
        }}
    }} else {{
        const bs=bodyParams.bodyScale||1.0;
        const headH=REF.head_offset*bs;
        const headX=smX+headH*0.3*upVis[0]/Math.max(upVis[1],0.3);
        const headY=smY+headH;
        kpts[0*3]=headX;kpts[0*3+1]=headY;kpts[0*3+2]=0;
        kpts[1*3]=headX;kpts[1*3+1]=headY+0.02;kpts[1*3+2]=-0.03*bs;
        kpts[2*3]=headX;kpts[2*3+1]=headY+0.02;kpts[2*3+2]=0.03*bs;
        kpts[3*3]=headX;kpts[3*3+1]=headY-0.01;kpts[3*3+2]=-0.06*bs;
        kpts[4*3]=headX;kpts[4*3+1]=headY-0.01;kpts[4*3+2]=0.06*bs;
        const ual=REF.upper_arm*bs, fal=REF.forearm*bs;
        kpts[7*3]=smX;kpts[7*3+1]=smY-ual*0.7-0.15;kpts[7*3+2]=-sw/2;
        kpts[8*3]=smX;kpts[8*3+1]=smY-ual*0.7-0.15;kpts[8*3+2]=sw/2;
        kpts[9*3]=kpts[7*3]+0.02;kpts[9*3+1]=kpts[7*3+1]-fal*0.5;kpts[9*3+2]=kpts[7*3+2];
        kpts[10*3]=kpts[8*3]+0.02;kpts[10*3+1]=kpts[8*3+1]-fal*0.5;kpts[10*3+2]=kpts[8*3+2];
    }}
    const fl=REF.foot_len*(bodyParams.bodyScale||1.0)*(bodyParams.footRatio||1.0);
    const la_ro=solver._lAnkle*9, ra_ro=solver._rAnkle*9;
    const lFwdX=Rw[la_ro+8], lFwdZ=Rw[la_ro+2];
    const lFwdLen=Math.sqrt(lFwdX*lFwdX+lFwdZ*lFwdZ)||1;
    kpts[17*3]=kpts[15*3]+(lFwdX/lFwdLen)*fl;
    kpts[17*3+1]=0;
    kpts[17*3+2]=kpts[15*3+2]+(lFwdZ/lFwdLen)*fl;
    const rFwdX=Rw[ra_ro+8], rFwdZ=Rw[ra_ro+2];
    const rFwdLen=Math.sqrt(rFwdX*rFwdX+rFwdZ*rFwdZ)||1;
    kpts[18*3]=kpts[16*3]+(rFwdX/rFwdLen)*fl;
    kpts[18*3+1]=0;
    kpts[18*3+2]=kpts[16*3+2]+(rFwdZ/rFwdLen)*fl;
    return kpts;
}}

function _getKinoSliders() {{
    return {{
        dorsi: parseFloat(document.getElementById('kino-dorsi')?.value||0),
        stance: parseFloat(document.getElementById('kino-stance')?.value||0),
        toe: parseFloat(document.getElementById('kino-toe')?.value||0),
        kneetrack: parseFloat(document.getElementById('kino-kneetrack')?.value||1),
    }};
}}

function computeKinodynamicsPose(fd, deltas, bodyParams, repIdx, frameIdx) {{
    if (!_kinoSolver||!KINO_DATA) return null;
    const kinoRep=KINO_DATA.reps[repIdx];
    if (!kinoRep||!kinoRep.q_trajectory||frameIdx>=kinoRep.q_trajectory.length) return null;
    const qFitted=new Float64Array(kinoRep.q_trajectory[frameIdx]);
    let qUsed;
    let origKpts=null;
    {{
        const d2r=Math.PI/180;
        const pert={{}};
        const ks=_getKinoSliders();
        const dDL=((deltas.dorsi+deltas.dorsiL)+ks.dorsi)*d2r;
        const dDR=((deltas.dorsi+deltas.dorsiR)+ks.dorsi)*d2r;
        if(Math.abs(dDL)>1e-6) pert['L_ankle.rx']=dDL;
        if(Math.abs(dDR)>1e-6) pert['R_ankle.rx']=dDR;
        const dKF=deltas.kneeFlex*d2r;
        if(Math.abs(dKF)>1e-6) {{ pert['L_knee.rx']=dKF; pert['R_knee.rx']=dKF; }}
        const dLean=deltas.forwardLean*d2r;
        if(Math.abs(dLean)>1e-6) pert['trunk.rx']=dLean;
        const dVL=(deltas.valgus+deltas.valgusL)*d2r;
        const dVR=(deltas.valgus+deltas.valgusR)*d2r;
        if(Math.abs(dVL)>1e-6) pert['L_hip.rz']=dVL;
        if(Math.abs(dVR)>1e-6) pert['R_hip.rz']=-dVR;
        const dToeL=ks.toe*d2r, dToeR=ks.toe*d2r;
        if(Math.abs(dToeL)>1e-6) pert['L_ankle.ry']=dToeL;
        if(Math.abs(dToeR)>1e-6) pert['R_ankle.ry']=-dToeR;
        const stanceDeltaM=ks.stance*0.01;
        let footTargetDelta=null;
        if(Math.abs(stanceDeltaM)>1e-6) footTargetDelta=new Float64Array([-stanceDeltaM/2,0,0, stanceDeltaM/2,0,0]);
        const costW={{
            pose_deviation:1.0, torque_proxy:0.5,
            load_over_midfoot:2.0, knee_tracking:ks.kneetrack, balance_margin:0.5,
            symmetry:0.5
        }};
        const repBounds=KINO_DATA.rep_boundaries;
        const bottom=repBounds&&repBounds[repIdx]!==undefined
            ? (Array.isArray(repBounds[repIdx]) ? repBounds[repIdx][2] : Math.floor(kinoRep.q_trajectory.length/2))
            : Math.floor(kinoRep.q_trajectory.length/2);
        const warpKey=JSON.stringify([repIdx,pert,stanceDeltaM,ks.kneetrack]);
        if(warpKey!==_kinoWarpKey) {{
            _kinoWarpKey=warpKey;
            const t0=performance.now();
            if (window.pywebview && window.pywebview.api) {{
                const ftdJson=footTargetDelta ? JSON.stringify(Array.from(footTargetDelta)) : null;
                const cwJson=JSON.stringify(costW);
                window.pywebview.api.warp_rep(repIdx, JSON.stringify(pert), ftdJson, cwJson).then(function(res) {{
                    if (res && res.warped_q) {{
                        _kinoWarpedQ=res.warped_q.map(function(q) {{ return new Float64Array(q); }});
                        _kinoSolveMs=res.solve_ms||0;
                    }}
                }});
            }} else {{
                const qTraj=kinoRep.q_trajectory.map(q=>new Float64Array(q));
                _kinoWarpedQ=_kinoSolver.warpRep(qTraj,bottom,pert,costW,footTargetDelta);
                _kinoSolveMs=performance.now()-t0;
            }}
        }}
        qUsed=_kinoWarpedQ ? _kinoWarpedQ[frameIdx] : qFitted;
        if (_kinoShowOriginal && fd && fd.kpts) {{
            origKpts=new Float64Array(19*3);
            const ok=fd.kpts;
            for(let i=0;i<19;i++){{ if(ok[i]){{ origKpts[i*3]=ok[i][0];origKpts[i*3+1]=ok[i][1];origKpts[i*3+2]=ok[i][2]; }} }}
        }}
    }}
    const kpts=kinoQToKeypoints(_kinoSolver,qUsed,fd,bodyParams);
    const dm=_kinoSolver.dofMap, deg=180/Math.PI;
    const kfLDeg=qUsed[dm['L_knee.rx']]*deg;
    const kfRDeg=qUsed[dm['R_knee.rx']]*deg;
    const dorsiLDeg=qUsed[dm['L_ankle.rx']]*deg;
    const dorsiRDeg=qUsed[dm['R_ankle.rx']]*deg;
    const valLDeg=fd.angles.knee_valgus_l+(deltas.valgus+deltas.valgusL);
    const valRDeg=fd.angles.knee_valgus_r+(deltas.valgus+deltas.valgusR);
    const {{pos:fkPos,Rw:fkRw}}=_kinoSolver.fk(qUsed);
    const ti=_kinoSolver._trunk, tro=ti*9;
    const localY=[fkRw[tro+1],fkRw[tro+4],fkRw[tro+7]];
    const leanRad=Math.atan2(Math.sqrt(localY[0]*localY[0]+localY[2]*localY[2]),localY[1]);
    const trunkAngleDeg=180-leanRad*deg;
    return {{
        kpts, trunkAngleDeg,
        totalTrunkLeanDeg: leanRad*deg,
        avgKneeDeg: (kfLDeg+kfRDeg)/2,
        dorsiDeg: (dorsiLDeg+dorsiRDeg)/2,
        dorsiLDeg, dorsiRDeg, kfLDeg, kfRDeg, valLDeg, valRDeg,
        origKpts,
    }};
}}

function computeConstrainedSquatPose(phase, params, solverMode, lockedShoulder) {{
    if (solverMode !== 'compensated') return computeSquatPose(phase, params, lockedShoulder);
    const {{ maxKneeFlex, stanceWidth, toeOut, dorsiRatio, bodyScale, torsoRatio, thighRatio, shinRatio,
             shoulderWidthRatio, barbellWeight: bw, bodyMass: bMass, ankleOverrideDeg, kneeValgus }} = params;
    const deg2rad = Math.PI / 180;
    const profile = phase;
    const refParams = {{ ...params, forwardLean: 0, kneeValgus: 0 }};
    const refPose = computeSquatPose(phase, refParams);
    const targetHipY = refPose.hipMidY;
    let ankleRad;
    if (ankleOverrideDeg !== undefined && ankleOverrideDeg !== null) {{
        ankleRad = ankleOverrideDeg * deg2rad * profile;
    }} else {{
        ankleRad = dorsiRatio * maxKneeFlex * deg2rad * profile;
    }}
    const solver = new ConstrainedChainSolver(bodyScale, torsoRatio, thighRatio, shinRatio, toeOut, params.footRatio);
    const result = solver.solve(ankleRad, targetHipY, bw || 0, bMass || 75);
    if (!result.valid) {{
        const fallback = computeSquatPose(phase, params, lockedShoulder);
        fallback.solverResult = result;
        return fallback;
    }}
    const solvedDorsiRatio = result.knee > 0.001 ? (result.ankle / result.knee) : dorsiRatio;
    const solvedParams = {{ ...params,
        maxKneeFlex: profile > 0.001 ? result.kneeDeg / profile : maxKneeFlex,
        dorsiRatio: solvedDorsiRatio,
        forwardLean: 0,
        kneeValgus: kneeValgus,
    }};
    const pose = computeSquatPose(phase, solvedParams);
    const tl = REF.torso_len * bodyScale * torsoRatio;
    const sw = REF.shoulder_width * bodyScale * (shoulderWidthRatio || 1.0);
    const kpts = pose.kpts;
    function set(idx, x, y, z) {{ kpts[idx*3]=x; kpts[idx*3+1]=y; kpts[idx*3+2]=z; }}
    const hipMidX = pose.hipMidX, hipMidY = pose.hipMidY;
    const sMidX = hipMidX + tl * Math.sin(result.trunk);
    const sMidY = hipMidY + tl * Math.cos(result.trunk);
    set(5, sMidX, sMidY, -sw/2); set(6, sMidX, sMidY, sw/2);
    const headH = REF.head_offset * bodyScale;
    const headX = sMidX + headH * Math.sin(result.trunk) * 0.5;
    const headY = sMidY + headH;
    set(0, headX, headY, 0);
    set(1, headX, headY+0.02, -0.03*bodyScale);
    set(2, headX, headY+0.02, 0.03*bodyScale);
    set(3, headX, headY-0.01, -0.06*bodyScale);
    set(4, headX, headY-0.01, 0.06*bodyScale);
    const ual = REF.upper_arm * bodyScale, fal = REF.forearm * bodyScale;
    const armFwd = 0.05 * profile, armDown = 0.15 + 0.1 * profile;
    const lS = [sMidX, sMidY, -sw/2], rS = [sMidX, sMidY, sw/2];
    set(7, lS[0]+armFwd, lS[1]-ual*0.7-armDown, lS[2]);
    set(8, rS[0]+armFwd, rS[1]-ual*0.7-armDown, rS[2]);
    const lE = [kpts[7*3], kpts[7*3+1], kpts[7*3+2]], rE = [kpts[8*3], kpts[8*3+1], kpts[8*3+2]];
    set(9, lE[0]+0.02, lE[1]-fal*0.5, lE[2]);
    set(10, rE[0]+0.02, rE[1]-fal*0.5, rE[2]);
    return {{ kpts, avgKneeDeg: result.kneeDeg, trunkAngleDeg: 180 - result.trunkDeg,
              valgusActiveDeg: (kneeValgus||0) * profile, dorsiDeg: result.ankleDeg,
              totalTrunkLeanDeg: result.trunkDeg, hipMidX, hipMidY, shoulderMidX: sMidX, shoulderMidY: sMidY,
              toeOutRad: toeOut * deg2rad, tl, sw, totalTrunkLean: result.trunk, solverResult: result }};
}}

// ======== COM / BOS / BALANCE ========
function computeCOM(kpts, bw, bodyMass, footLen) {{
    function g(i) {{ return {{ x: kpts[i*3], y: kpts[i*3+1], z: kpts[i*3+2] }}; }}
    const lS = g(5), rS = g(6), lH = g(11), rH = g(12);
    const sMid = {{ x:(lS.x+rS.x)/2, y:(lS.y+rS.y)/2, z:(lS.z+rS.z)/2 }};
    const hMid = {{ x:(lH.x+rH.x)/2, y:(lH.y+rH.y)/2, z:(lH.z+rH.z)/2 }};
    const segCOMs = {{ head: g(0), trunk: {{ x:(sMid.x+hMid.x)/2, y:(sMid.y+hMid.y)/2, z:(sMid.z+hMid.z)/2 }} }};
    for (const [key, seg] of Object.entries(SEGMENT_MASS)) {{
        if (!seg.joints || seg.joints[0] === null || seg.joints[1] === null) continue;
        if (key === 'head' || key === 'trunk' || key.startsWith('foot')) continue;
        const a = g(seg.joints[0]), b = g(seg.joints[1]);
        segCOMs[key] = {{ x:(a.x+b.x)/2, y:(a.y+b.y)/2, z:(a.z+b.z)/2 }};
    }}
    const aL = g(15), aR = g(16), kL = g(13), kR = g(14);
    const _tL = g(17), _tR = g(18);
    const _fl = footLen || REF.foot_len;
    function _footFwd(ankle, knee) {{ const dx=ankle.x-knee.x, dz=ankle.z-knee.z, l=Math.sqrt(dx*dx+dz*dz)||1; return {{x:dx/l,z:dz/l}}; }}
    function _hasToe(t) {{ return Math.abs(t.x)+Math.abs(t.y)+Math.abs(t.z) > 1e-6; }}
    const tL = _hasToe(_tL) ? _tL : (function(){{ const f=_footFwd(aL,kL); return {{x:aL.x+f.x*_fl,y:aL.y,z:aL.z+f.z*_fl}}; }})();
    const tR = _hasToe(_tR) ? _tR : (function(){{ const f=_footFwd(aR,kR); return {{x:aR.x+f.x*_fl,y:aR.y,z:aR.z+f.z*_fl}}; }})();
    segCOMs.foot_l = {{ x:(aL.x+tL.x)/2, y:aL.y, z:(aL.z+tL.z)/2 }};
    segCOMs.foot_r = {{ x:(aR.x+tR.x)/2, y:aR.y, z:(aR.z+tR.z)/2 }};
    let totalFrac = 0;
    const bodyFracs = {{}};
    for (const [key, seg] of Object.entries(SEGMENT_MASS)) {{
        if (segCOMs[key]) {{ bodyFracs[key] = seg.frac; totalFrac += seg.frac; }}
    }}
    for (const k of Object.keys(bodyFracs)) bodyFracs[k] /= totalFrac;
    const barFrac = bw > 0 ? bw / (bodyMass + bw) : 0;
    const bodyF = 1 - barFrac;
    let cx=0, cy=0, cz=0;
    for (const [key, frac] of Object.entries(bodyFracs)) {{
        const c = segCOMs[key]; if (!c) continue;
        cx += c.x * frac * bodyF; cy += c.y * frac * bodyF; cz += c.z * frac * bodyF;
    }}
    if (bw > 0 && _barbellPos) {{ cx += _barbellPos.x * barFrac; cy += _barbellPos.y * barFrac; cz += _barbellPos.z * barFrac; }}
    return {{ x:cx, y:cy, z:cz, groundX:cx, groundZ:cz }};
}}

function computeBOS(kpts, toeOutRad, footLen) {{
    function g(i) {{ return {{ x: kpts[i*3], y: kpts[i*3+1], z: kpts[i*3+2] }}; }}
    const aL = g(15), aR = g(16), kL = g(13), kR = g(14);
    const _tL = g(17), _tR = g(18);
    const _fl = footLen || REF.foot_len;
    function _footFwd(ankle, knee) {{ const dx=ankle.x-knee.x, dz=ankle.z-knee.z, l=Math.sqrt(dx*dx+dz*dz)||1; return {{x:dx/l,z:dz/l}}; }}
    function _hasToe(t) {{ return Math.abs(t.x)+Math.abs(t.y)+Math.abs(t.z) > 1e-6; }}
    const tL = _hasToe(_tL) ? _tL : (function(){{ const f=_footFwd(aL,kL); return {{x:aL.x+f.x*_fl,y:aL.y,z:aL.z+f.z*_fl}}; }})();
    const tR = _hasToe(_tR) ? _tR : (function(){{ const f=_footFwd(aR,kR); return {{x:aR.x+f.x*_fl,y:aR.y,z:aR.z+f.z*_fl}}; }})();
    const halfW = 0.05, heelOff = 0.06, toeOff = footLen - heelOff;
    function footRect(ankle, toe) {{
        const dx=toe.x-ankle.x, dz=toe.z-ankle.z, l=Math.sqrt(dx*dx+dz*dz)||1;
        const fx=dx/l, fz=dz/l, lx=-fz, lz=fx;
        return [
            {{ x:ankle.x-fx*heelOff-lx*halfW, z:ankle.z-fz*heelOff-lz*halfW }},
            {{ x:ankle.x-fx*heelOff+lx*halfW, z:ankle.z-fz*heelOff+lz*halfW }},
            {{ x:ankle.x+fx*toeOff+lx*halfW, z:ankle.z+fz*toeOff+lz*halfW }},
            {{ x:ankle.x+fx*toeOff-lx*halfW, z:ankle.z+fz*toeOff-lz*halfW }},
        ];
    }}
    const pts = [...footRect(aL, tL), ...footRect(aR, tR)];
    return convexHull2D(pts);
}}
function convexHull2D(points) {{
    if (points.length <= 3) return points;
    let start = 0;
    for (let i = 1; i < points.length; i++) {{
        if (points[i].x < points[start].x || (points[i].x === points[start].x && points[i].z < points[start].z)) start = i;
    }}
    const hull = []; let cur = start;
    do {{
        hull.push(points[cur]); let next = (cur+1) % points.length;
        for (let i = 0; i < points.length; i++) {{
            if (i === cur || i === next) continue;
            const cross = (points[next].x-points[cur].x)*(points[i].z-points[cur].z) - (points[next].z-points[cur].z)*(points[i].x-points[cur].x);
            if (cross < 0) next = i;
        }}
        cur = next;
    }} while (cur !== start && hull.length < points.length + 1);
    return hull;
}}
function isBalanced(com, bos) {{
    const px=com.groundX, pz=com.groundZ; let inside=false; const n=bos.length;
    for (let i=0,j=n-1; i<n; j=i++) {{
        const xi=bos[i].x,zi=bos[i].z,xj=bos[j].x,zj=bos[j].z;
        if (((zi>pz)!==(zj>pz)) && (px<(xj-xi)*(pz-zi)/(zj-zi)+xi)) inside=!inside;
    }}
    let minDist=Infinity;
    for (let i=0,j=n-1; i<n; j=i++) {{
        const ax=bos[j].x,az=bos[j].z,bx=bos[i].x,bz=bos[i].z;
        const ex=bx-ax,ez=bz-az,t=Math.max(0,Math.min(1,((px-ax)*ex+(pz-az)*ez)/(ex*ex+ez*ez+1e-9)));
        const dx=px-(ax+t*ex),dz=pz-(az+t*ez); minDist=Math.min(minDist,Math.sqrt(dx*dx+dz*dz));
    }}
    let cx=0,cz2=0; for (const pt of bos) {{ cx+=pt.x; cz2+=pt.z; }} cx/=n; cz2/=n;
    let avgR=0; for (const pt of bos) avgR+=Math.sqrt((pt.x-cx)**2+(pt.z-cz2)**2); avgR/=n;
    return {{ inside, marginRatio: inside ? minDist/(avgR+1e-9) : -minDist/(avgR+1e-9) }};
}}

function getBarbellPosition(pose) {{
    const {{ shoulderMidX, shoulderMidY, totalTrunkLean, sw }} = pose;
    const s = Math.sin(totalTrunkLean), c = Math.cos(totalTrunkLean);
    const bx = shoulderMidX + 0.04*s + 0.05*(-c);
    const by = shoulderMidY + 0.04*c + 0.05*s;
    _barbellPos = {{ x:bx, y:by, z:0 }};
    return {{ x:bx, y:by, z:0, trunkLean: totalTrunkLean, sw }};
}}
function updateBarbellVisuals(bw, barPos, sw) {{
    if (!bw || bw <= 0) {{ barbellGroup.visible = false; return; }}
    barbellGroup.visible = true;
    const barLen = sw * 2.4; barMesh.scale.set(1, barLen, 1);
    barbellGroup.position.set(barPos.x, barPos.y, barPos.z); barbellGroup.rotation.set(0,0,0);
    const plateR = 0.05 + (bw/200)*0.15, halfBar = barLen/2;
    const spacings = [0.10, 0.16];
    for (let i = 0; i < 4; i++) {{
        const side = i < 2 ? -1 : 1, slot = i % 2;
        plateMeshes[i].scale.set(plateR/0.05, plateR/0.05, 1);
        plateMeshes[i].position.set(0, 0, side*(halfBar-0.06-spacings[slot]));
    }}
}}
function updateCOMVisuals(com, bos, bal) {{
    if (!com || !bos) {{ comSphere.visible=false; comDisc.visible=false; comLine.visible=false; bosLine.visible=false; return; }}
    comSphere.position.set(com.x,com.y,com.z); comSphere.visible=true;
    comDisc.position.set(com.groundX,0.002,com.groundZ); comDisc.visible=true;
    const lp = new Float32Array([com.groundX,0.003,com.groundZ, com.x,com.y,com.z]);
    comLineGeo.setAttribute('position', new THREE.Float32BufferAttribute(lp, 3));
    comLine.computeLineDistances(); comLine.visible=true;
    const bp = []; for (const pt of bos) bp.push(pt.x, 0.002, pt.z);
    bosGeo.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(bp), 3));
    bosLine.visible=true;
    comSphere.material.color.setHex(bal.inside ? 0x22ff22 : 0xff2222);
    comDisc.material.color.setHex(bal.inside ? 0x22ff22 : 0xff2222);
    bosLineMat.color.setHex(bal.inside ? 0x44ff88 : 0xff6644);
}}
function updateGhostTorso(pose, optLean) {{
    if (optLean === null || optLean === undefined) {{ ghostTorsoLine.visible = false; return; }}
    const testP = AP ? {{ ...AP, forwardLean: optLean }} : {{ forwardLean: optLean }};
    const fd = reps[curRep] && reps[curRep][curFrame];
    const ph = fd && fd.phase !== undefined ? fd.phase : 0;
    const gp = computeSquatPose(ph, testP);
    const gPos = new Float32Array([gp.hipMidX, gp.hipMidY, 0, gp.shoulderMidX, gp.shoulderMidY, 0]);
    ghostTorsoGeo.setAttribute('position', new THREE.Float32BufferAttribute(gPos, 3));
    ghostTorsoLine.computeLineDistances(); ghostTorsoLine.visible = true;
}}

let _cachedOptimal = null, _lastOptKey = '';
function getOptimalCached(params) {{
    const key = JSON.stringify([params.maxKneeFlex, params.stanceWidth, params.toeOut, params.dorsiRatio,
                                params.bodyScale, params.torsoRatio, params.thighRatio, params.shinRatio,
                                params.barbellWeight, params.bodyMass]);
    if (key !== _lastOptKey) {{
        _lastOptKey = key;
        _cachedOptimal = null;
        const bw = params.barbellWeight || 0, bm = params.bodyMass || 75;
        for (let d = 0; d <= 60; d += 0.5) {{
            const tp = {{ ...params, forwardLean: d }};
            const pose = computeSquatPose(0.5, tp); // peak = phase 0.5 on sin profile? No - peak = 1.0 since phase = depth
            const scaledFl = REF.foot_len * (params.bodyScale || 1.0) * (params.footRatio || 1.0);
            const bos = computeBOS(pose.kpts, pose.toeOutRad, scaledFl);
            const com = computeCOM(pose.kpts, bw, bm, scaledFl);
            const bal = isBalanced(com, bos);
            if (bal.inside && bal.marginRatio >= 0.20) {{ _cachedOptimal = d; break; }}
        }}
    }}
    return _cachedOptimal;
}}

// ======== THRESHOLD BARS ========
function renderThresholdBars() {{
    const leanBar = document.getElementById('sb-lean-threshold-bar');
    const valgusBar = document.getElementById('sb-valgus-threshold-bar');
    if (!leanBar || !valgusBar) return;
    const lMax = 60;
    leanBar.innerHTML = `<div class="band" style="width:${{LEAN_T.mild/lMax*100}}%; background:#2ecc71"></div>` +
        `<div class="band" style="width:${{(LEAN_T.moderate-LEAN_T.mild)/lMax*100}}%; background:#f1c40f"></div>` +
        `<div class="band" style="width:${{(LEAN_T.severe-LEAN_T.moderate)/lMax*100}}%; background:#e67e22"></div>` +
        `<div class="band" style="width:${{Math.max(0,(lMax-LEAN_T.severe))/lMax*100}}%; background:#e74c3c"></div>`;
    const vMax = 25;
    valgusBar.innerHTML = `<div class="band" style="width:${{VALG_T.mild/vMax*100}}%; background:#2ecc71"></div>` +
        `<div class="band" style="width:${{(VALG_T.moderate-VALG_T.mild)/vMax*100}}%; background:#f1c40f"></div>` +
        `<div class="band" style="width:${{(VALG_T.severe-VALG_T.moderate)/vMax*100}}%; background:#e67e22"></div>` +
        `<div class="band" style="width:${{Math.max(0,(vMax-VALG_T.severe))/vMax*100}}%; background:#e74c3c"></div>`;
}}
renderThresholdBars();

// ======== SANDBOX PARAM READER ========
function getSbSolverMode() {{
    const checked = document.querySelector('input[name="sb-solver-mode"]:checked');
    return checked ? checked.value : 'independent';
}}
document.querySelectorAll('input[name="sb-solver-mode"]').forEach(radio => {{
    radio.addEventListener('change', () => {{
        const mode = getSbSolverMode();
        document.getElementById('sb-compensated-controls').style.display = mode === 'compensated' ? '' : 'none';
        document.getElementById('sb-kino-controls').style.display = mode === 'kinodynamics' ? '' : 'none';
        const kfEl = document.getElementById('sb-kino-faults');
        if (kfEl) kfEl.style.display = mode === 'kinodynamics' ? '' : 'none';
    }});
}});
// Ankle override slider binding
(function() {{
    const sl = document.getElementById('sb-ankle-override');
    const vl = document.getElementById('sb-ankle-override-val');
    if (sl && vl) sl.addEventListener('input', () => {{ vl.textContent = parseFloat(sl.value).toFixed(1) + '°'; }});
}})();

function _sv(id) {{ const el = document.getElementById(id); return el ? parseFloat(el.value) : 0; }}

function getSandboxBodyParams() {{
    return {{
        bodyScale: _sv('sb-body-scale'),
        torsoRatio: _sv('sb-torso-ratio'),
        thighRatio: _sv('sb-thigh-ratio'),
        shinRatio: _sv('sb-shin-ratio'),
        shoulderWidthRatio: _sv('sb-shoulder-width-ratio'),
        footRatio: _sv('sb-foot-ratio'),
        stanceWidth: _sv('sb-stance-width'),
        toeOut: _sv('sb-toe-out'),
    }};
}}

function getSandboxDeltas() {{
    return {{
        kneeFlex: _sv('sb-d-knee-flex'),
        dorsi: _sv('sb-d-dorsi'),
        dorsiL: _sv('sb-d-dorsi-l'),
        dorsiR: _sv('sb-d-dorsi-r'),
        forwardLean: _sv('sb-d-forward-lean'),
        valgus: _sv('sb-d-valgus'),
        valgusL: _sv('sb-d-valgus-l'),
        valgusR: _sv('sb-d-valgus-r'),
        kneeTracking: _sv('sb-d-knee-tracking'),
    }};
}}

// ======== SANDBOX UPDATE ========

function updateSandbox(fd) {{
    if (!fd || !fd.kpts) return;
    const k = fd.kpts;
    const a = fd.angles;
    const deltas = getSandboxDeltas();
    const bodyParams = getSandboxBodyParams();
    const solverMode = getSbSolverMode();

    let kpts, trunkAngleDeg, avgKneeDeg, dorsiDeg, totalTrunkLeanDeg;
    let dorsiLDeg, dorsiRDeg, kfLDeg, kfRDeg, valLDeg, valRDeg;
    let hipRotLDeg = 0, hipRotRDeg = 0;

    let _kinoOrigKpts = null;
    if (solverMode === 'kinodynamics' && _kinoSolver && KINO_DATA && _slidersModified) {{
        const kinoResult = computeKinodynamicsPose(fd, deltas, bodyParams, curRep, curFrame);
        if (kinoResult) {{
            ({{ kpts, trunkAngleDeg, avgKneeDeg, dorsiDeg, totalTrunkLeanDeg,
                dorsiLDeg, dorsiRDeg, kfLDeg, kfRDeg, valLDeg, valRDeg }} = kinoResult);
            _kinoOrigKpts = kinoResult.origKpts;
        }} else {{
            kpts = new Float64Array(19 * 3);
            for (let i = 0; i < 19; i++) {{ if (!k[i]) continue; kpts[i*3]=k[i][0]; kpts[i*3+1]=k[i][1]; kpts[i*3+2]=k[i][2]; }}
            trunkAngleDeg = a.trunk_flexion; avgKneeDeg = a.knee_flex;
            dorsiDeg = (a.dorsi_l + a.dorsi_r) / 2; totalTrunkLeanDeg = 180 - a.trunk_flexion;
            dorsiLDeg = a.dorsi_l; dorsiRDeg = a.dorsi_r;
            kfLDeg = a.knee_flex_l || a.knee_flex; kfRDeg = a.knee_flex_r || a.knee_flex;
            valLDeg = a.knee_valgus_l; valRDeg = a.knee_valgus_r;
        }}
    }} else if (!_slidersModified) {{
        // No sliders touched: use captured data directly (exact 1:1 match)
        kpts = new Float64Array(19 * 3);
        for (let i = 0; i < 19; i++) {{ if (!k[i]) continue; kpts[i*3]=k[i][0]; kpts[i*3+1]=k[i][1]; kpts[i*3+2]=k[i][2]; }}
        trunkAngleDeg = a.trunk_flexion;
        avgKneeDeg = a.knee_flex;
        dorsiDeg = (a.dorsi_l + a.dorsi_r) / 2;
        totalTrunkLeanDeg = 180 - a.trunk_flexion;
        dorsiLDeg = a.dorsi_l; dorsiRDeg = a.dorsi_r;
        kfLDeg = a.knee_flex_l || a.knee_flex; kfRDeg = a.knee_flex_r || a.knee_flex;
        valLDeg = a.knee_valgus_l; valRDeg = a.knee_valgus_r;
    }} else if (solverMode === 'compensated' && _slidersModified) {{
        // Compensated mode: per-side FK with symmetry + knee-over-toes constraints
        const lockedShoulder = (k[5] && k[6]) ?
            {{ x: (k[5][0]+k[6][0])/2, y: (k[5][1]+k[6][1])/2 }} : null;
        const pose = computePerSidePose(fd, deltas, bodyParams, lockedShoulder, true, _stanceWidthTouched);
        ({{ kpts, trunkAngleDeg, avgKneeDeg, dorsiDeg, totalTrunkLeanDeg,
            dorsiLDeg, dorsiRDeg, kfLDeg, kfRDeg, valLDeg, valRDeg,
            hipRotLDeg, hipRotRDeg }} = pose);
    }} else {{
        // Independent mode: per-side delta FK from captured angles
        const lockedShoulder = (k[5] && k[6]) ?
            {{ x: (k[5][0]+k[6][0])/2, y: (k[5][1]+k[6][1])/2 }} : null;
        const pose = computePerSidePose(fd, deltas, bodyParams, lockedShoulder);
        ({{ kpts, trunkAngleDeg, avgKneeDeg, dorsiDeg, totalTrunkLeanDeg,
            dorsiLDeg, dorsiRDeg, kfLDeg, kfRDeg, valLDeg, valRDeg,
            hipRotLDeg, hipRotRDeg }} = pose);
    }}

    // Fault classification from effective per-side valgus
    const faultValgus = Math.max(Math.abs(valLDeg), Math.abs(valRDeg));
    const leanSev = classifyLean(trunkAngleDeg);
    const valgusSev = classifyValgus(faultValgus);
    const fj = new Set();
    if (leanSev !== 'none') [0,1,2,3,4,5,6].forEach(j => fj.add(j));
    if (valgusSev !== 'none') [13,14].forEach(j => fj.add(j));

    for (let i = 0; i < 19; i++) {{
        jm[i].position.set(kpts[i*3], kpts[i*3+1], kpts[i*3+2]);
        jm[i].visible = true;
        const t = fj.has(i) ? 'f' : 'n';
        if (t !== js[i]) {{ jm[i].material = (t === 'f' ? matF : matN).clone(); js[i] = t; }}
    }}
    const fb = new Set();
    if (leanSev !== 'none') {{ fb.add('5-6'); fb.add('5-11'); fb.add('6-12'); fb.add('0-5'); fb.add('0-6'); }}
    if (valgusSev !== 'none') {{ fb.add('11-13'); fb.add('13-15'); fb.add('12-14'); fb.add('14-16'); }}
    for (const bone of bm) {{
        const pa = jm[bone.a].position, pb = jm[bone.b].position;
        const d = new THREE.Vector3().subVectors(pb, pa), l = d.length(); d.normalize();
        bone.mesh.position.copy(pa); bone.mesh.scale.set(1, l, 1);
        bone.mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0), d);
        bone.mesh.material = fb.has(`${{bone.a}}-${{bone.b}}`) ? matBF : matB;
    }}

    hideSandboxVisuals();
    updateGhostSkeleton(_kinoOrigKpts, solverMode === 'kinodynamics' && _kinoShowOriginal && !!_kinoOrigKpts);

    // COM / BOS
    const sbFootLen = AP ? (AP.foot_avg_m || REF.foot_len) : REF.foot_len;
    const sbCom = computeCOM(kpts, 0, 75, sbFootLen);
    const sbBos = computeBOS(kpts, 0, sbFootLen);
    const sbBal = isBalanced(sbCom, sbBos);
    updateCOMVisuals(sbCom, sbBos, sbBal);

    const leanOff = (180 - trunkAngleDeg).toFixed(1);
    const hipRotStr = (hipRotLDeg !== 0 || hipRotRDeg !== 0)
        ? `<br><span class="lbl">Hip Rot L/R:</span> <span class="val">${{hipRotLDeg.toFixed(1)}}° / ${{hipRotRDeg.toFixed(1)}}°</span> <span class="val" style="opacity:0.5">(ext+)</span>`
        : '';
    document.getElementById('sb-angles-info').innerHTML = `
        <span class="lbl">Knee Flex L/R:</span> <span class="val">${{kfLDeg.toFixed(1)}}° / ${{kfRDeg.toFixed(1)}}°</span>
        <span class="val" style="opacity:0.5">(avg ${{avgKneeDeg.toFixed(1)}}°)</span><br>
        <span class="lbl">Trunk Angle:</span> <span class="val">${{trunkAngleDeg.toFixed(1)}}°</span> (offset: ${{leanOff}}°)
        ${{leanSev !== 'none' ? sb(leanSev) : ''}}<br>
        <span class="lbl">Dorsi L/R:</span> <span class="val">${{dorsiLDeg.toFixed(1)}}° / ${{dorsiRDeg.toFixed(1)}}°</span>
        <span class="val" style="opacity:0.5">(avg ${{dorsiDeg.toFixed(1)}}°)</span><br>
        <span class="lbl">Valgus L/R:</span> <span class="val">${{valLDeg.toFixed(1)}}° / ${{valRDeg.toFixed(1)}}°</span>
        ${{valgusSev !== 'none' ? sb(valgusSev) : ''}}<br>
        <span class="lbl">Hip Flex L/R:</span> <span class="val">${{a.hip_flex_l.toFixed(1)}}° / ${{a.hip_flex_r.toFixed(1)}}°</span>
        ${{hipRotStr}}<br>
        <span class="lbl">Phase:</span> <span class="val">${{(fd.phase || 0).toFixed(3)}}</span>
        ${{_slidersModified ? '<span style="color:#4ecdc4; margin-left:8px">&Delta; active</span>' : ''}}
        ${{solverMode==='kinodynamics' ? '<br><span class="lbl">Solver:</span> <span style="color:#4ecdc4">Kino</span> <span class="val">'+_kinoSolveMs.toFixed(1)+'ms</span>' : ''}}`;

    const kinoInfoEl = document.getElementById('sb-kino-info');
    if (kinoInfoEl && solverMode === 'kinodynamics') {{
        kinoInfoEl.innerHTML = `20-DOF soft-cost optimizer &bull; ${{_kinoSolveMs.toFixed(1)}}ms warp`;
    }}

    const kinoFaultsEl = document.getElementById('sb-kino-faults');
    const kinoFaultsInfo = document.getElementById('kino-faults-info');
    const kinoSolveTimeEl = document.getElementById('kino-solve-time');
    if (solverMode === 'kinodynamics' && KINO_DATA) {{
        if (kinoFaultsEl) kinoFaultsEl.style.display = '';
        if (kinoSolveTimeEl) kinoSolveTimeEl.textContent = _kinoSolveMs.toFixed(1) + 'ms';
        const repFaults = KINO_DATA.reps[curRep] && KINO_DATA.reps[curRep].faults;
        if (kinoFaultsInfo && repFaults && repFaults.length) {{
            kinoFaultsInfo.innerHTML = repFaults.map(f =>
                `<div class="fault-item" style="margin:4px 0; padding:4px 8px; border-left:3px solid ${{f.severity==='severe'?'#ff6b6b':f.severity==='moderate'?'#ffa726':'#ffee58'}}">` +
                `<b>${{f.type}}</b> <span class="severity-indicator sev-${{f.severity}}">${{f.severity.toUpperCase()}}</span>` +
                (f.message ? `<br><span style="font-size:11px; color:#999">${{f.message}}</span>` : '') +
                `</div>`
            ).join('');
        }} else if (kinoFaultsInfo) {{
            kinoFaultsInfo.innerHTML = '<span style="color:#4ecdc4">No faults detected</span>';
        }}
    }} else {{
        if (kinoFaultsEl) kinoFaultsEl.style.display = 'none';
        if (kinoSolveTimeEl) kinoSolveTimeEl.textContent = '';
    }}

    document.getElementById('info-overlay').innerHTML = `
        <span style="color:${{solverMode==='kinodynamics'?'#4ecdc4':'#4ecdc4'}}">SANDBOX${{solverMode==='kinodynamics'?' [KINO]':''}}</span>
        <span class="lbl" style="margin-left:8px">Rep:</span> <span class="val">${{curRep+2}}</span>
        <span class="lbl" style="margin-left:8px">Frame:</span> <span class="val">${{curFrame+1}}</span><br>
        <span class="lbl">Knee:</span> <span class="val">${{avgKneeDeg.toFixed(1)}}°</span>
        <span class="lbl" style="margin-left:8px">Trunk:</span> <span class="val">${{trunkAngleDeg.toFixed(1)}}°</span>
        <span class="lbl" style="margin-left:8px">Dorsi:</span> <span class="val">${{dorsiDeg.toFixed(1)}}°</span>`;
}}

// ======== RESIZE ========
function resize() {{ const w=container.clientWidth, h=container.clientHeight; renderer.setSize(w,h); camera.aspect=w/h; camera.updateProjectionMatrix(); }}
window.addEventListener('resize', resize); resize();

// ======== MAIN ANIMATION LOOP ========
function animate(now) {{
    requestAnimationFrame(animate);
    const dt = (now - lastT) / 1000; lastT = now;
    if (!reps.length) return;
    const r = reps[curRep]; if (!r || !r.length) return;

    // Frame advancement (shared between modes)
    if (playing) {{
        frameAcc += dt * dataFps * speed;
        while (frameAcc >= 1) {{
            frameAcc -= 1; curFrame++;
            if (curFrame >= r.length) {{
                if (repFilter === -1) curRep = (curRep + 1) % reps.length;
                curFrame = 0;
            }}
        }}
    }}
    if (curFrame >= r.length) curFrame = r.length - 1;

    // Update scrubbers (whichever panel is visible)
    scrub.max = r.length - 1; scrub.value = curFrame;
    fv.textContent = `${{curFrame+1}}/${{r.length}}`;
    sbScrub.max = r.length - 1; sbScrub.value = curFrame;
    sbFv.textContent = `${{curFrame+1}}/${{r.length}}`;

    const fd = r[curFrame];

    if (viewMode === 'sandbox') {{
        updateSandbox(fd);
    }} else {{
        updateReplay(fd);
        hideSandboxVisuals();
    }}

    orbitCtrl.update();
    renderer.render(scene, camera);
}}
requestAnimationFrame(animate);
</script>
</body>
</html>"""


def launch_viewer_from_html(
    html,
    skeleton,
    q_trajectory_per_rep,
    rep_boundaries=None,
    **kwargs,
):
    """Open the visualizer in a native PyWebView window with Python solver.

    Parameters
    ----------
    html : str — output of ``build_html()``
    skeleton : SkeletonModel with joint_masses set
    q_trajectory_per_rep : list of (T, n_dof) ndarrays
    rep_boundaries : list of [start, end, bottom] per rep
    **kwargs : forwarded to ``launch_viewer()``
    """
    from biomechanics.viewer import launch_viewer

    launch_viewer(html, skeleton, q_trajectory_per_rep, rep_boundaries, **kwargs)


def _extract_data_from_html(html_path):
    """Extract the embedded DATA JSON from an existing HTML file."""
    text = Path(html_path).read_text()
    m = re.search(r'const DATA = ({.*?});\s*\n', text, re.DOTALL)
    if not m:
        print("ERROR: Could not find embedded DATA in HTML file.")
        sys.exit(1)
    return json.loads(m.group(1))


def _vis_to_skeleton3d(kpts_vis):
    """Invert the vis-space transform to reconstruct a Skeleton3D (19 COCO keypoints).

    vis_x = mp_z, vis_y = -mp_y, vis_z = -mp_x  →  mp_x = -vis_z, mp_y = -vis_y, mp_z = vis_x
    """
    from biomechanics.utils.types import Point3D, Skeleton3D
    points = []
    for i in range(min(19, len(kpts_vis))):
        vx, vy, vz = kpts_vis[i]
        points.append(Point3D(x=-vz, y=-vy, z=vx, confidence=1.0))
    return Skeleton3D(keypoints=points)


def _find_latest_html(recordings_dir):
    """Return the most recent .html file in recordings_dir, or None."""
    htmls = sorted(recordings_dir.glob("squat_*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    return htmls[0] if htmls else None


def _run_refit(html_path, no_open=False, use_viewer=False, diagnose=False):
    """Re-run the kinodynamics pipeline on an existing recording."""
    from collections import deque as _deque
    from biomechanics.skeleton.anthropometry import calibrate_skeleton
    from biomechanics.optimizer.ik import fit_trajectory, _fk_jac, _build_descendants
    from biomechanics.optimizer.landmark_adapter import skeleton3d_to_landmarks
    from biomechanics.optimizer.angle_extract import q_to_joint_angles
    from biomechanics.skeleton.forward_kin import load_reference_point, midfoot_xz
    from biomechanics.faults.rules import (
        ForwardLeanRule, KneeValgusRule, LimitedDorsiflexionRule, BarDriftRule,
    )

    print(f"Refitting kinodynamics from: {html_path}")
    data = _extract_data_from_html(html_path)
    replay_reps = data["reps"]
    fps = data["fps"]
    athlete_params = data.get("athleteParams")
    baseline = data["baseline"]

    weight_kg = (athlete_params or {}).get("weightKg", 75.0)

    # Reconstruct Skeleton3D objects per rep
    all_rep_skels = []
    for rep_frames in replay_reps:
        skels = []
        for f in rep_frames:
            if f is not None and f.get("kpts"):
                skels.append(_vis_to_skeleton3d(f["kpts"]))
            else:
                skels.append(None)
        all_rep_skels.append(skels)

    # Gather all landmarks for per-segment skeleton calibration
    all_calibration_landmarks = []
    for rep_skels in all_rep_skels:
        for s3d in rep_skels:
            if s3d is not None:
                all_calibration_landmarks.append(skeleton3d_to_landmarks(s3d))
    calibration_landmarks = np.stack(all_calibration_landmarks)
    skeleton_obj = calibrate_skeleton(calibration_landmarks, weight_kg)
    print(f"  Calibrated skeleton: scale={skeleton_obj._scale_factor:.3f}")

    q_traj_per_rep = []
    kino_rep_bounds = []
    faults_per_rep = []
    joint_angles_per_rep = []
    foot_targets_per_rep = []

    desc = _build_descendants(skeleton_obj)
    _lai = skeleton_obj.joint_index("L_ankle")
    _rai = skeleton_obj.joint_index("R_ankle")

    for ri, rep_skels in enumerate(all_rep_skels):
        valid_skels = [s for s in rep_skels if s is not None]
        if not valid_skels:
            q_traj_per_rep.append(np.zeros((0, skeleton_obj.n_dof)))
            kino_rep_bounds.append([0, 0, 0])
            faults_per_rep.append([])
            joint_angles_per_rep.append([])
            foot_targets_per_rep.append(np.zeros((0, 2, 3)))
            continue

        n_frames = len(valid_skels)
        n_joints = skeleton_obj.n_joints
        landmarks = np.zeros((n_frames, n_joints, 4))
        for fi, skel in enumerate(valid_skels):
            landmarks[fi] = skeleton3d_to_landmarks(skel)

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
        print(f"  Rep {ri + 2}: fitting IK trajectory ({n_frames} frames, "
              f"init knee={np.degrees(init_knee_rad):.0f}°)...")
        q_traj = fit_trajectory(skeleton_obj, landmarks, q_init=q_init,
                                weights=ik_weights, reg_weights=reg_weights,
                                q_ref=q_init.copy())
        q_traj_per_rep.append(q_traj)

        af = JointAngleFilter(min_cutoff=1.0, beta=0.007)
        _dt = DerivativeTracker(smoothing_alpha=0.3)
        rep_angles = []
        for fi in range(n_frames):
            raw = q_to_joint_angles(skeleton_obj, q_traj[fi], frame_index=fi)
            filtered = af.filter_angles(raw)
            filtered.timestamp = fi / max(fps, 1.0)
            _dt.update(filtered)
            rep_angles.append(filtered)

        ja_ser = []
        for a in rep_angles:
            ja_ser.append({
                "knee_flex": a.avg_knee_flexion,
                "knee_flex_l": a.knee_flexion_l,
                "knee_flex_r": a.knee_flexion_r,
                "trunk_flexion": a.trunk_flexion,
                "knee_valgus_l": a.knee_valgus_l,
                "knee_valgus_r": a.knee_valgus_r,
                "dorsi_l": a.ankle_dorsiflexion_l,
                "dorsi_r": a.ankle_dorsiflexion_r,
                "hip_flex_l": a.hip_flexion_l,
                "hip_flex_r": a.hip_flexion_r,
            })
        joint_angles_per_rep.append(ja_ser)

        rules = [ForwardLeanRule(), KneeValgusRule(),
                 LimitedDorsiflexionRule(), BarDriftRule()]
        history = _deque(maxlen=90)
        rep_faults = []

        for fi, angles in enumerate(rep_angles):
            history.append(angles)
            skel_state = None
            try:
                lr = load_reference_point(skeleton_obj, q_traj[fi])
                mf = midfoot_xz(skeleton_obj, q_traj[fi])
                skel_state = {
                    "load_reference_xz": [float(lr[0]), float(lr[2])],
                    "midfoot_xz": [float(mf[0]), float(mf[1])],
                }
            except Exception:
                pass
            for rule in rules:
                rule.set_frame_context(skeleton_state=skel_state)
                fault = rule.evaluate(angles, history,
                                      in_rep=True, rep_number=ri + 2)
                if fault:
                    rep_faults.append({
                        "type": fault.fault_type,
                        "severity": fault.severity.value,
                        "message": fault.message,
                        "frame": fi,
                        "details": fault.details,
                    })

        if rep_angles:
            for rule in rules:
                rule.set_frame_context()
                fault = rule.evaluate(rep_angles[-1], history,
                                      in_rep=False, rep_number=ri + 2)
                if fault:
                    rep_faults.append({
                        "type": fault.fault_type,
                        "severity": fault.severity.value,
                        "message": fault.message,
                        "frame": n_frames - 1,
                        "details": fault.details,
                    })
        faults_per_rep.append(rep_faults)

        bottom = 0
        max_kf = 0.0
        for fi, a in enumerate(rep_angles):
            if a.avg_knee_flexion > max_kf:
                max_kf = a.avg_knee_flexion
                bottom = fi
        kino_rep_bounds.append([0, n_frames - 1, bottom])

        ft = np.zeros((n_frames, 2, 3))
        for fi in range(n_frames):
            pos, _ = _fk_jac(skeleton_obj, q_traj[fi], desc)
            ft[fi, 0] = pos[_lai]
            ft[fi, 1] = pos[_rai]
        foot_targets_per_rep.append(ft)

        print(f"    bottom={bottom} max_knee={max_kf:.1f}° faults={len(rep_faults)}")

    kino_state = serialize_kinodynamics_state(
        skeleton_obj, q_traj_per_rep,
        foot_targets_per_rep=foot_targets_per_rep,
        faults_per_rep=faults_per_rep,
        rep_boundaries=kino_rep_bounds,
        joint_angles_per_rep=joint_angles_per_rep,
    )
    print(f"  Kinodynamics: {len(q_traj_per_rep)} reps serialized")

    # ── Diagnosis pipeline (--diagnose inside refit) ─────────────────────
    diagnosis_artifact_path = None
    if diagnose and q_traj_per_rep:
        try:
            from biomechanics.diagnosis import HypothesisEngine, SetFeatures, RepKinematicSummary
            from biomechanics.diagnosis.solver_driver import FormSolverDriver
            from biomechanics.diagnosis.rep_bottom_extractor import extract_bottom_q
            import json as _json
            from datetime import datetime as _dt

            print("\n  Running diagnosis pipeline (refit)...")
            refit_timestamp = _dt.now().strftime("%Y%m%d_%H%M%S")
            ap = athlete_params or {}

            per_rep_summaries = []
            for ri, ja_list in enumerate(joint_angles_per_rep):
                if not ja_list:
                    continue
                rep_number = ri + 2

                bottom_idx = kino_rep_bounds[ri][2] if ri < len(kino_rep_bounds) else 0
                bottom_angles = ja_list[min(bottom_idx, len(ja_list) - 1)]

                trunk_pitch = 180.0 - bottom_angles.get("trunk_flexion", 180.0)
                max_valgus_l = max((abs(a.get("knee_valgus_l", 0.0)) for a in ja_list), default=0.0)
                max_valgus_r = max((abs(a.get("knee_valgus_r", 0.0)) for a in ja_list), default=0.0)
                max_dorsi_l = max((a.get("dorsi_l", 0.0) for a in ja_list), default=0.0)
                max_dorsi_r = max((a.get("dorsi_r", 0.0) for a in ja_list), default=0.0)

                rep_frames = replay_reps[ri] if ri < len(replay_reps) else []
                hip_y_l = hip_y_r = knee_y_l = knee_y_r = 0.0
                if rep_frames and bottom_idx < len(rep_frames):
                    bf = rep_frames[bottom_idx]
                    if bf and bf.get("kpts"):
                        kpts = bf["kpts"]
                        if isinstance(kpts, dict):
                            hip_y_l = float(kpts.get(11, kpts.get("11", [0, 0, 0]))[1]) * 100
                            hip_y_r = float(kpts.get(12, kpts.get("12", [0, 0, 0]))[1]) * 100
                            knee_y_l = float(kpts.get(13, kpts.get("13", [0, 0, 0]))[1]) * 100
                            knee_y_r = float(kpts.get(14, kpts.get("14", [0, 0, 0]))[1]) * 100
                        elif isinstance(kpts, (list, np.ndarray)):
                            kpts_arr = np.array(kpts)
                            if kpts_arr.shape[0] > 14:
                                hip_y_l = float(kpts_arr[11, 1]) * 100
                                hip_y_r = float(kpts_arr[12, 1]) * 100
                                knee_y_l = float(kpts_arr[13, 1]) * 100
                                knee_y_r = float(kpts_arr[14, 1]) * 100

                max_knee_flex = max((a.get("knee_flex", 0.0) for a in ja_list), default=0.0)
                if max_knee_flex < 60:
                    depth_class_int = 0
                elif max_knee_flex < 90:
                    depth_class_int = 1
                elif max_knee_flex < 100:
                    depth_class_int = 2
                else:
                    depth_class_int = 3

                per_rep_summaries.append(RepKinematicSummary(
                    rep_number=rep_number,
                    trunk_pitch_at_bottom=round(trunk_pitch, 2),
                    knee_valgus_l=round(max_valgus_l, 2),
                    knee_valgus_r=round(max_valgus_r, 2),
                    ankle_df_l_max=round(max_dorsi_l, 2),
                    ankle_df_r_max=round(max_dorsi_r, 2),
                    hip_y_l_at_bottom=round(hip_y_l, 2),
                    hip_y_r_at_bottom=round(hip_y_r, 2),
                    knee_y_l_at_bottom=round(knee_y_l, 2),
                    knee_y_r_at_bottom=round(knee_y_r, 2),
                    stance_width_ratio=ap.get("stanceWidth", 1.2),
                    foot_direction_angle_l=ap.get("toeOut", 15.0),
                    foot_direction_angle_r=ap.get("toeOut", 15.0),
                    depth_class_int=depth_class_int,
                ))

            femur_m = ap.get("femur_avg_m", 0.42)
            torso_m = ap.get("torso_avg_m", 0.50)
            anthro_dict = {
                "femur_torso_ratio": femur_m / torso_m if torso_m > 0 else 1.0,
                "shoulder_width": ap.get("shoulder_width_m", 0.36),
                "hip_width": ap.get("hip_width_m", 0.28),
            }

            avg_dorsi = np.mean([
                (s.ankle_df_l_max + s.ankle_df_r_max) / 2.0
                for s in per_rep_summaries
            ]) if per_rep_summaries else 0.0
            rom_dict = {
                "dorsiflexion_drop": 0.0,
                "avg_depth": float(avg_dorsi),
            }

            set_features = SetFeatures(
                user_id=0,
                set_id=refit_timestamp,
                rep_count=len(per_rep_summaries),
                per_rep_kinematics=per_rep_summaries,
                anthropometry=anthro_dict,
                rom=rom_dict,
            )

            engine = HypothesisEngine()
            diagnosis_result = engine.diagnose(set_features)
            print(f"    Symptoms: {len(diagnosis_result.detected_symptoms)}, "
                  f"Immediate causes: {len(diagnosis_result.immediate_causes)}, "
                  f"Confidence: {diagnosis_result.confidence:.2f}")

            rep_severity_scores = {}
            for symptom in diagnosis_result.detected_symptoms:
                for rep_num in symptom.contributing_reps:
                    rep_severity_scores[rep_num] = rep_severity_scores.get(rep_num, 0.0) + symptom.severity

            eligible_reps = {k: v for k, v in rep_severity_scores.items() if k >= 2}
            if not eligible_reps and q_traj_per_rep:
                eligible_reps = {2: 0.0}

            solver_results = []
            if eligible_reps:
                worst_rep_num = max(eligible_reps, key=eligible_reps.get)
                worst_traj_idx = worst_rep_num - 2

                if 0 <= worst_traj_idx < len(q_traj_per_rep) and q_traj_per_rep[worst_traj_idx].shape[0] > 0:
                    bottom_frame_idx, q_at_bottom = extract_bottom_q(
                        q_traj_per_rep[worst_traj_idx], skeleton_obj
                    )

                    if diagnosis_result.combined_perturbation:
                        driver = FormSolverDriver(skeleton_obj)
                        form_result = driver.solve(q_at_bottom, diagnosis_result, anthro_dict)
                        solver_results.append({
                            "rep_number": worst_rep_num,
                            "bottom_frame_index": bottom_frame_idx,
                            "q_observed_at_bottom": q_at_bottom.tolist(),
                            **form_result.model_dump(),
                        })
                        print(f"    Solver: rep {worst_rep_num}, converged={form_result.converged}, "
                              f"relaxations={form_result.relaxations}")
                    else:
                        solver_results.append({
                            "rep_number": worst_rep_num,
                            "bottom_frame_index": bottom_frame_idx,
                            "q_observed_at_bottom": q_at_bottom.tolist(),
                            "q_corrected": None,
                            "converged": False,
                            "applied_perturbation": {},
                            "relaxations": [],
                            "cost_terms_used": [],
                        })
                        print(f"    No immediate causes — stored observed pose for rep {worst_rep_num}")

            diagnosis_artifact_path = html_path.with_name(f"diagnosis_output_{refit_timestamp}.json")
            diagnosis_artifact = {
                "diagnosis": diagnosis_result.model_dump(),
                "solver_results": solver_results,
                "metadata": {
                    "timestamp": refit_timestamp,
                    "anthropometry": anthro_dict,
                    "rep_count": len(per_rep_summaries),
                    "height_m": float(skeleton_obj._height_m),
                    "weight_kg": float(skeleton_obj._total_weight_kg),
                },
            }
            diagnosis_artifact_path.write_text(_json.dumps(diagnosis_artifact, indent=2, default=str))
            print(f"    Diagnosis artifact: {diagnosis_artifact_path}")

        except ImportError as e:
            print(f"  Diagnosis not available: {e}")
        except Exception as e:
            print(f"  Diagnosis pipeline error: {e}")
            import traceback
            traceback.print_exc()

    html = build_html(baseline, replay_reps, fps, athlete_params, kino_state)
    html_path.write_text(html)
    print(f"Wrote: {html_path}")
    if not no_open:
        if use_viewer and diagnosis_artifact_path and diagnosis_artifact_path.exists():
            try:
                from biomechanics.viewer.app import launch_diagnosis_viewer
                print("Launching diagnosis viewer...")
                launch_diagnosis_viewer(str(diagnosis_artifact_path), skeleton=skeleton_obj)
            except ImportError as e:
                print(f"  Diagnosis viewer not available: {e}")
                import webbrowser
                webbrowser.open(f"file://{html_path.resolve()}")
        elif use_viewer:
            try:
                from biomechanics.viewer.app import launch_viewer
                launch_viewer(html, skeleton_obj, q_traj_per_rep,
                              rep_boundaries=kino_rep_bounds)
            except ImportError:
                import webbrowser
                webbrowser.open(f"file://{html_path.resolve()}")
        else:
            import webbrowser
            webbrowser.open(f"file://{html_path.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="Capture squats and visualize in 3D")
    parser.add_argument("--output", "-o", default=None,
                        help="Output video path (default: recordings/squat_YYYYMMDD_HHMMSS.mp4)")
    parser.add_argument("--camera", "-c", type=int, default=0, help="Camera device ID")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open HTML in browser")
    parser.add_argument("--replay", "-r", default=None, metavar="HTML",
                        help="Regenerate HTML from an existing recording (path to .html file)")
    parser.add_argument("--refit", default=None, nargs="?", const="latest", metavar="HTML",
                        help="Re-run kinodynamics IK on existing recording (default: latest)")
    parser.add_argument("--viewer", action="store_true",
                        help="Open in PyWebView window with Python-backed kinodynamics solver")
    parser.add_argument("--diagnose", action="store_true",
                        help="Run hypothesis engine diagnosis + form solver after capture")
    args = parser.parse_args()

    if args.refit is not None:
        recordings_dir = Path(__file__).parent.parent / "recordings"
        if args.refit == "latest":
            html_path = _find_latest_html(recordings_dir)
            if html_path is None:
                print("ERROR: No recordings found in recordings/")
                sys.exit(1)
        else:
            html_path = Path(args.refit)
        if not html_path.exists():
            print(f"ERROR: File not found: {html_path}")
            sys.exit(1)
        _run_refit(html_path, no_open=args.no_open, use_viewer=args.viewer, diagnose=args.diagnose)
        return

    if args.replay:
        replay_path = Path(args.replay)
        if not replay_path.exists():
            print(f"ERROR: File not found: {replay_path}")
            sys.exit(1)
        data = _extract_data_from_html(replay_path)
        html = build_html(data["baseline"], data["reps"], data["fps"], data.get("athleteParams"))
        replay_path.write_text(html)
        print(f"Regenerated: {replay_path}")
        if not args.no_open:
            webbrowser.open(f"file://{replay_path.resolve()}")
        return

    recordings_dir = Path(__file__).parent.parent / "recordings"
    recordings_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    video_path = Path(args.output) if args.output else recordings_dir / f"squat_{timestamp}.mp4"
    html_path = video_path.with_suffix(".html")
    memory_png_path = video_path.with_name(video_path.stem + "_memory_profile.png")

    profiler = MemoryProfiler()
    if profiler.enabled:
        print(f"  Memory profiling enabled → {memory_png_path}")

    print("=" * 50)
    print("  SQUAT CAPTURE & 3D REPLAY")
    print("=" * 50)
    print(f"  Video → {video_path}")
    print(f"  HTML  → {html_path}")
    print(f"  Reps to capture: {TARGET_REPS}")
    print("=" * 50)

    profiler.start()
    try:
        frames_data, reps, rep_boundaries, fps, bone_cstr, skeletons_3d = run_capture(args.camera, video_path, profiler)
    finally:
        profiler.stop()
        report_path = profiler.generate_report(memory_png_path, title_prefix="Squat Capture")
        if report_path:
            print(f"Memory profile saved: {report_path}")

    if len(reps) < 2:
        print(f"ERROR: Need at least 2 reps, got {len(reps)}.")
        sys.exit(1)

    print(f"\nProcessing {len(reps)} reps...")
    print(f"  Using rep 1 as baseline, replaying reps 2-{len(reps)}")

    rep_frame_slices = []
    for start, end in rep_boundaries:
        rep_slice = [f for f in frames_data[start:end + 1] if f is not None]
        rep_frame_slices.append(rep_slice)

    for s in rep_frame_slices:
        ground_and_center(s)
        add_phase_to_rep(s)

    baseline = compute_baseline(rep_frame_slices[0])
    print(f"  Baseline trunk offset: {baseline['peakTrunkOffset']}°")
    print(f"  Lean thresholds: {baseline['leanThresholds']}")
    print(f"  Valgus thresholds: {baseline['valgusThresholds']}")

    athlete_params = compute_athlete_params(frames_data, rep_boundaries, bone_cstr)
    if athlete_params:
        print(f"  Athlete params:")
        print(f"    Stance width: {athlete_params['stanceWidth']}x  Toe-out: {athlete_params['toeOut']}°")
        print(f"    Dorsi ratio: {athlete_params['dorsiRatio']}  Body scale: {athlete_params['bodyScale']}")
        print(f"    Proportions: torso={athlete_params['torsoRatio']} thigh={athlete_params['thighRatio']} shin={athlete_params['shinRatio']}")

    from db.anthropometry_utils import save_anthropometry_to_file
    save_anthropometry_to_file(bone_cstr)

    replay_reps = rep_frame_slices[1:]

    kino_state = None
    skeleton_obj = None
    q_traj_per_rep = None
    kino_rep_bounds = None

    try:
        from collections import deque as _deque
        from biomechanics.skeleton.anthropometry import scale_skeleton
        from biomechanics.optimizer.ik import fit_trajectory, _fk_jac, _build_descendants
        from biomechanics.optimizer.landmark_adapter import skeleton3d_to_landmarks
        from biomechanics.optimizer.angle_extract import q_to_joint_angles
        from biomechanics.skeleton.forward_kin import load_reference_point, midfoot_xz
        from biomechanics.faults.rules import (
            ForwardLeanRule, KneeValgusRule, LimitedDorsiflexionRule, BarDriftRule,
        )

        weight_kg = (athlete_params or {}).get("weightKg", 75.0)

        # Estimate effective scale from observed landmark segment lengths
        # (MediaPipe world landmarks may not match stated height)
        _REF_THIGH = 0.45
        _REF_SHANK = 0.43
        _REF_LEG = _REF_THIGH + _REF_SHANK
        seg_lens = []
        for s3d in skeletons_3d:
            if s3d is None:
                continue
            lm = skeleton3d_to_landmarks(s3d)
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
            avg_ref_seg = (_REF_THIGH + _REF_SHANK) / 2
            effective_height = 1.75 * (median_seg / avg_ref_seg)
            print(f"  Landmark scale: median segment={median_seg:.3f}m → "
                  f"effective height={effective_height:.2f}m")
        else:
            effective_height = (athlete_params or {}).get("heightM", 1.78)

        skeleton_obj = scale_skeleton(effective_height, weight_kg)

        q_traj_per_rep = []
        kino_rep_bounds = []
        faults_per_rep = []
        joint_angles_per_rep = []
        foot_targets_per_rep = []

        desc = _build_descendants(skeleton_obj)
        _lai = skeleton_obj.joint_index("L_ankle")
        _rai = skeleton_obj.joint_index("R_ankle")

        for ri, (start, end) in enumerate(rep_boundaries[1:]):
            rep_skels = [s for s in skeletons_3d[start:end + 1] if s is not None]
            if not rep_skels:
                q_traj_per_rep.append(np.zeros((0, skeleton_obj.n_dof)))
                kino_rep_bounds.append([0, 0, 0])
                faults_per_rep.append([])
                joint_angles_per_rep.append([])
                foot_targets_per_rep.append(np.zeros((0, 2, 3)))
                continue

            n_frames = len(rep_skels)
            n_joints = skeleton_obj.n_joints
            landmarks = np.zeros((n_frames, n_joints, 4))
            for fi, skel in enumerate(rep_skels):
                landmarks[fi] = skeleton3d_to_landmarks(skel)

            # Per-joint weights: pelvis/trunk lower (approximate), limbs higher
            ik_weights = np.array([0.5, 0.3, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.3, 0.8, 0.8])
            # Squat-appropriate initial guess (neutral_q has straight legs → local min)
            q_init = skeleton_obj.neutral_q()
            # Set initial pelvis position from observed pelvis landmarks
            q_init[0] = float(np.median(landmarks[:, 0, 0]))
            q_init[1] = float(np.median(landmarks[:, 0, 1]))
            q_init[2] = float(np.median(landmarks[:, 0, 2]))
            # Estimate knee/hip flexion from hip-ankle vertical ratio
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
            print(f"  Rep {ri + 2}: fitting IK trajectory ({n_frames} frames, "
                  f"init knee={np.degrees(init_knee_rad):.0f}°)...")
            q_traj = fit_trajectory(skeleton_obj, landmarks, q_init=q_init,
                                    weights=ik_weights, reg_weights=reg_weights,
                                    q_ref=q_init.copy())
            q_traj_per_rep.append(q_traj)

            af = JointAngleFilter(min_cutoff=1.0, beta=0.007)
            _dt = DerivativeTracker(smoothing_alpha=0.3)
            rep_angles = []
            for fi in range(n_frames):
                raw = q_to_joint_angles(skeleton_obj, q_traj[fi],
                                        frame_index=fi)
                filtered = af.filter_angles(raw)
                filtered.timestamp = fi / max(fps, 1.0)
                _dt.update(filtered)
                rep_angles.append(filtered)

            ja_ser = []
            for a in rep_angles:
                ja_ser.append({
                    "knee_flex": a.avg_knee_flexion,
                    "knee_flex_l": a.knee_flexion_l,
                    "knee_flex_r": a.knee_flexion_r,
                    "trunk_flexion": a.trunk_flexion,
                    "knee_valgus_l": a.knee_valgus_l,
                    "knee_valgus_r": a.knee_valgus_r,
                    "dorsi_l": a.ankle_dorsiflexion_l,
                    "dorsi_r": a.ankle_dorsiflexion_r,
                    "hip_flex_l": a.hip_flexion_l,
                    "hip_flex_r": a.hip_flexion_r,
                })
            joint_angles_per_rep.append(ja_ser)

            rules = [ForwardLeanRule(), KneeValgusRule(),
                     LimitedDorsiflexionRule(), BarDriftRule()]
            history = _deque(maxlen=90)
            rep_faults = []

            for fi, angles in enumerate(rep_angles):
                history.append(angles)
                skel_state = None
                try:
                    lr = load_reference_point(skeleton_obj, q_traj[fi])
                    mf = midfoot_xz(skeleton_obj, q_traj[fi])
                    skel_state = {
                        "load_reference_xz": [float(lr[0]), float(lr[2])],
                        "midfoot_xz": [float(mf[0]), float(mf[1])],
                    }
                except Exception:
                    pass
                for rule in rules:
                    rule.set_frame_context(skeleton_state=skel_state)
                    fault = rule.evaluate(angles, history,
                                          in_rep=True, rep_number=ri + 2)
                    if fault:
                        rep_faults.append({
                            "type": fault.fault_type,
                            "severity": fault.severity.value,
                            "message": fault.message,
                            "frame": fi,
                            "details": fault.details,
                        })

            if rep_angles:
                for rule in rules:
                    rule.set_frame_context()
                    fault = rule.evaluate(rep_angles[-1], history,
                                          in_rep=False, rep_number=ri + 2)
                    if fault:
                        rep_faults.append({
                            "type": fault.fault_type,
                            "severity": fault.severity.value,
                            "message": fault.message,
                            "frame": n_frames - 1,
                            "details": fault.details,
                        })
            faults_per_rep.append(rep_faults)

            bottom = 0
            max_kf = 0.0
            for fi, a in enumerate(rep_angles):
                if a.avg_knee_flexion > max_kf:
                    max_kf = a.avg_knee_flexion
                    bottom = fi
            kino_rep_bounds.append([0, n_frames - 1, bottom])

            ft = np.zeros((n_frames, 2, 3))
            for fi in range(n_frames):
                pos, _ = _fk_jac(skeleton_obj, q_traj[fi], desc)
                ft[fi, 0] = pos[_lai]
                ft[fi, 1] = pos[_rai]
            foot_targets_per_rep.append(ft)

            print(f"    bottom={bottom} max_knee={max_kf:.1f}° faults={len(rep_faults)}")

        kino_state = serialize_kinodynamics_state(
            skeleton_obj, q_traj_per_rep,
            foot_targets_per_rep=foot_targets_per_rep,
            faults_per_rep=faults_per_rep,
            rep_boundaries=kino_rep_bounds,
            joint_angles_per_rep=joint_angles_per_rep,
        )
        print(f"  Kinodynamics: {len(q_traj_per_rep)} reps serialized")
    except ImportError as e:
        print(f"  Kinodynamics not available: {e}")
    except Exception as e:
        print(f"  Kinodynamics pipeline error: {e}")
        import traceback
        traceback.print_exc()

    # ── Diagnosis pipeline (--diagnose) ──────────────────────────────────
    if args.diagnose and skeleton_obj is not None and q_traj_per_rep:
        try:
            from biomechanics.diagnosis import HypothesisEngine, SetFeatures, RepKinematicSummary
            from biomechanics.diagnosis.solver_driver import FormSolverDriver
            from biomechanics.diagnosis.rep_bottom_extractor import extract_bottom_q
            import json as _json

            print("\n  Running diagnosis pipeline...")

            # Build RepKinematicSummary for ALL reps from raw frame data
            per_rep_summaries = []
            for rep_idx, (start, end) in enumerate(rep_boundaries):
                rep_frames = [f for f in frames_data[start:end + 1] if f is not None]
                if not rep_frames:
                    continue

                # Find bottom frame (max knee flexion) within this rep's raw frames
                max_kf_frame_idx = 0
                max_kf_val = 0.0
                max_valgus_l = 0.0
                max_valgus_r = 0.0
                max_dorsi_l = 0.0
                max_dorsi_r = 0.0
                for fi, frame in enumerate(rep_frames):
                    angles = frame["angles"]
                    if angles["knee_flex"] > max_kf_val:
                        max_kf_val = angles["knee_flex"]
                        max_kf_frame_idx = fi
                    max_valgus_l = max(max_valgus_l, abs(angles["knee_valgus_l"]))
                    max_valgus_r = max(max_valgus_r, abs(angles["knee_valgus_r"]))
                    max_dorsi_l = max(max_dorsi_l, angles["dorsi_l"])
                    max_dorsi_r = max(max_dorsi_r, angles["dorsi_r"])

                bottom_frame = rep_frames[max_kf_frame_idx]
                bottom_angles = bottom_frame["angles"]
                bottom_kpts = np.array(bottom_frame["kpts"])

                trunk_pitch = 180.0 - bottom_angles["trunk_flexion"]
                hip_y_l = float(bottom_kpts[11, 1]) if len(bottom_kpts) > 12 else 0.0
                hip_y_r = float(bottom_kpts[12, 1]) if len(bottom_kpts) > 12 else 0.0
                knee_y_l = float(bottom_kpts[13, 1]) if len(bottom_kpts) > 14 else 0.0
                knee_y_r = float(bottom_kpts[14, 1]) if len(bottom_kpts) > 14 else 0.0

                depth_class = reps[rep_idx].depth_class if reps[rep_idx].depth_class is not None else 0

                per_rep_summaries.append(RepKinematicSummary(
                    rep_number=rep_idx + 1,
                    trunk_pitch_at_bottom=round(trunk_pitch, 2),
                    knee_valgus_l=round(max_valgus_l, 2),
                    knee_valgus_r=round(max_valgus_r, 2),
                    ankle_df_l_max=round(max_dorsi_l, 2),
                    ankle_df_r_max=round(max_dorsi_r, 2),
                    hip_y_l_at_bottom=round(hip_y_l * 100, 2),
                    hip_y_r_at_bottom=round(hip_y_r * 100, 2),
                    knee_y_l_at_bottom=round(knee_y_l * 100, 2),
                    knee_y_r_at_bottom=round(knee_y_r * 100, 2),
                    stance_width_ratio=(athlete_params or {}).get("stanceWidth", 1.2),
                    foot_direction_angle_l=(athlete_params or {}).get("toeOut", 15.0),
                    foot_direction_angle_r=(athlete_params or {}).get("toeOut", 15.0),
                    depth_class_int=depth_class,
                ))

            # Build anthropometry and ROM dicts from athlete_params
            ap = athlete_params or {}
            femur_m = ap.get("femur_avg_m", 0.42)
            torso_m = ap.get("torso_avg_m", 0.50)
            anthro_dict = {
                "femur_torso_ratio": femur_m / torso_m if torso_m > 0 else 1.0,
                "shoulder_width": ap.get("shoulder_width_m", 0.36),
                "hip_width": ap.get("hip_width_m", 0.28),
            }

            avg_depth_degrees = np.mean([s.ankle_df_l_max + s.ankle_df_r_max
                                         for s in per_rep_summaries]) / 2.0 if per_rep_summaries else 0.0
            rom_dict = {
                "dorsiflexion_drop": max_dorsi_l - per_rep_summaries[-1].ankle_df_l_max if per_rep_summaries else 0.0,
                "avg_depth": float(avg_depth_degrees),
            }

            set_features = SetFeatures(
                user_id=0,
                set_id=timestamp,
                rep_count=len(per_rep_summaries),
                per_rep_kinematics=per_rep_summaries,
                anthropometry=anthro_dict,
                rom=rom_dict,
            )

            engine = HypothesisEngine()
            diagnosis_result = engine.diagnose(set_features)
            print(f"    Symptoms: {len(diagnosis_result.detected_symptoms)}, "
                  f"Immediate causes: {len(diagnosis_result.immediate_causes)}, "
                  f"Confidence: {diagnosis_result.confidence:.2f}")

            # Find worst rep (highest severity contribution among reps with q_trajectory)
            rep_severity_scores: dict[int, float] = {}
            for symptom in diagnosis_result.detected_symptoms:
                for rep_num in symptom.contributing_reps:
                    rep_severity_scores[rep_num] = rep_severity_scores.get(rep_num, 0.0) + symptom.severity

            # Only consider reps 2+ (which have q_trajectories)
            eligible_reps = {k: v for k, v in rep_severity_scores.items() if k >= 2}
            if not eligible_reps and q_traj_per_rep:
                eligible_reps = {2: 0.0}

            solver_results = []
            if eligible_reps and diagnosis_result.combined_perturbation:
                worst_rep_num = max(eligible_reps, key=eligible_reps.get)
                worst_traj_idx = worst_rep_num - 2  # q_traj_per_rep is 0-indexed for reps 2+

                if 0 <= worst_traj_idx < len(q_traj_per_rep) and q_traj_per_rep[worst_traj_idx].shape[0] > 0:
                    bottom_frame_idx, q_at_bottom = extract_bottom_q(
                        q_traj_per_rep[worst_traj_idx], skeleton_obj
                    )

                    driver = FormSolverDriver(skeleton_obj)
                    form_result = driver.solve(q_at_bottom, diagnosis_result, anthro_dict)

                    solver_results.append({
                        "rep_number": worst_rep_num,
                        "bottom_frame_index": bottom_frame_idx,
                        "q_observed_at_bottom": q_at_bottom.tolist(),
                        **form_result.model_dump(),
                    })
                    print(f"    Solver: rep {worst_rep_num}, converged={form_result.converged}, "
                          f"relaxations={form_result.relaxations}")

            # Write diagnosis artifact
            diagnosis_output_path = video_path.with_name(f"diagnosis_output_{timestamp}.json")
            diagnosis_artifact = {
                "diagnosis": diagnosis_result.model_dump(),
                "solver_results": solver_results,
                "metadata": {
                    "timestamp": timestamp,
                    "anthropometry": anthro_dict,
                    "rep_count": len(per_rep_summaries),
                    "height_m": float(skeleton_obj._height_m),
                    "weight_kg": float(skeleton_obj._total_weight_kg),
                },
            }
            diagnosis_output_path.write_text(_json.dumps(diagnosis_artifact, indent=2, default=str))
            print(f"    Diagnosis artifact: {diagnosis_output_path}")

        except ImportError as e:
            print(f"  Diagnosis not available: {e}")
        except Exception as e:
            print(f"  Diagnosis pipeline error: {e}")
            import traceback
            traceback.print_exc()

    html = build_html(baseline, replay_reps, fps, athlete_params, kino_state)
    html_path.write_text(html)
    print(f"\nVideo saved: {video_path}")
    print(f"HTML saved:  {html_path}")

    if args.viewer and skeleton_obj and q_traj_per_rep:
        print("Launching PyWebView kinodynamics viewer...")
        launch_viewer_from_html(html, skeleton_obj, q_traj_per_rep, kino_rep_bounds)
    elif not args.no_open:
        webbrowser.open(f"file://{html_path.resolve()}")


if __name__ == "__main__":
    main()
