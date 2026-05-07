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
import sys
import time
import webbrowser
from collections import deque
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

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
        ankle_dx = l_ankle[0] - r_ankle[0]
        ankle_dz = l_ankle[2] - r_ankle[2]
        ankle_xz_dist = np.sqrt(ankle_dx**2 + ankle_dz**2)
        stance_widths.append(ankle_xz_dist / props.hip_width)

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


def run_capture(camera_id, video_output_path):
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
            else:
                frames_data.append(None)

            rec_frame_idx += 1

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

    return frames_data, reps, rep_boundaries, fps, bone_constraints


def build_html(baseline, replay_reps_data, fps, athlete_params=None):
    data_json = json.dumps({
        "baseline": baseline,
        "reps": replay_reps_data,
        "fps": fps,
        "athleteParams": athlete_params,
    })

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
            <div class="section-title"><span class="dot"></span> Chain Solver</div>
            <div class="slider-row" style="gap:12px">
                <label style="display:flex; align-items:center; gap:4px; cursor:pointer">
                    <input type="radio" name="sb-solver-mode" value="independent" checked> Independent
                </label>
                <label style="display:flex; align-items:center; gap:4px; cursor:pointer">
                    <input type="radio" name="sb-solver-mode" value="compensated"> Compensated
                </label>
            </div>
            <div id="sb-compensated-controls" style="display:none">
                <div class="slider-row"><label>Ankle dorsi override</label><input type="range" id="sb-ankle-override" min="0" max="45" value="15" step="0.5"><span class="value" id="sb-ankle-override-val">15°</span></div>
                <div class="mono" id="sb-solved-angles" style="margin-top:6px; font-size:11px"></div>
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
bindSlider('sb-stance-width', 'sb-stance-width-val', 'x', 2);
bindSlider('sb-toe-out', 'sb-toe-out-val', '°', 0);
bindSliderDelta('sb-d-knee-flex', 'sb-d-knee-flex-val', '°', 0);
bindSliderDelta('sb-d-dorsi', 'sb-d-dorsi-val', '°', 1);
bindSliderDelta('sb-d-dorsi-l', 'sb-d-dorsi-l-val', '°', 1);
bindSliderDelta('sb-d-dorsi-r', 'sb-d-dorsi-r-val', '°', 1);
bindSliderDelta('sb-d-forward-lean', 'sb-d-forward-lean-val', '°', 0);
bindSliderDelta('sb-d-valgus', 'sb-d-valgus-val', '°', 1);
bindSliderDelta('sb-d-valgus-l', 'sb-d-valgus-l-val', '°', 1);
bindSliderDelta('sb-d-valgus-r', 'sb-d-valgus-r-val', '°', 1);
bindSlider('sb-barbell-weight', 'sb-barbell-weight-val', ' kg', 0);
bindSlider('sb-body-mass', 'sb-body-mass-val', ' kg', 0);
bindSlider('sb-speed-slider', 'sb-speed-val', 'x', 1);

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

function hideSandboxVisuals() {{
    ghostTorsoLine.visible = false;
    midfootLine.visible = false; midfootDisc.visible = false;
    barbellGroup.visible = false;
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

function computePerSidePose(fd, deltas, bodyParams, lockedShoulder) {{
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

    // Delta amounts (degrees)
    const dDorsiL = (deltas.dorsi || 0) + (deltas.dorsiL || 0);
    const dDorsiR = (deltas.dorsi || 0) + (deltas.dorsiR || 0);
    const dKF     = deltas.kneeFlex || 0;
    const dValL   = (deltas.valgus || 0) + (deltas.valgusL || 0);
    const dValR   = (deltas.valgus || 0) + (deltas.valgusR || 0);
    const dLean   = deltas.forwardLean || 0;

    const kpts = new Float64Array(19 * 3);
    function set(idx, x, y, z) {{ kpts[idx*3]=x; kpts[idx*3+1]=y; kpts[idx*3+2]=z; }}

    // Captured positions
    const aL = k[15]||[0,0,0], aR = k[16]||[0,0,0];
    const cKL = k[13]||aL, cKR = k[14]||aR;
    const cHL = k[11]||cKL, cHR = k[12]||cKR;
    set(15, aL[0], aL[1], aL[2]);
    set(16, aR[0], aR[1], aR[2]);

    // Feet from captured foot_index positions (preserve captured direction)
    if (k[17]) set(17, k[17][0], k[17][1], k[17][2]);
    else set(17, aL[0]-fl*Math.cos(toeOutRad), aL[1], aL[2]-fl*Math.sin(toeOutRad));
    if (k[18]) set(18, k[18][0], k[18][1], k[18][2]);
    else set(18, aR[0]-fl*Math.cos(toeOutRad), aR[1], aR[2]+fl*Math.sin(toeOutRad));

    // Per-leg rotation-based adjustment
    // For each leg: derive the forward direction from the captured shin,
    // then rotate shin & thigh by the delta angles.
    function adjustLeg(ankle, capKnee, capHip, dDorsi, dKnee, dValgus, side) {{
        // Captured shin and thigh vectors
        const shinVec = [capKnee[0]-ankle[0], capKnee[1]-ankle[1], capKnee[2]-ankle[2]];
        const thighVec = [capHip[0]-capKnee[0], capHip[1]-capKnee[1], capHip[2]-capKnee[2]];

        // Forward direction: shin ground projection
        const gLen = Math.sqrt(shinVec[0]*shinVec[0] + shinVec[2]*shinVec[2]) || 1e-6;
        const fwd = [shinVec[0]/gLen, 0, shinVec[2]/gLen];

        // Lateral axis: perpendicular to forward in ground plane
        // Chosen so positive rotation = more forward tilt (dorsiflexion)
        const lat = [fwd[2], 0, -fwd[0]];

        // Rotate shin by dorsi delta around lateral axis
        let newShinDir = _rotVec(_norm(shinVec), lat, dDorsi * deg2rad);
        // Rotate shin by valgus delta around forward axis
        // Positive valgus = medial collapse: for left leg rotate toward +Z, for right toward -Z
        if (Math.abs(dValgus) > 0.001) {{
            newShinDir = _rotVec(newShinDir, fwd, dValgus * deg2rad * side);
        }}
        const newKnee = [ankle[0]+newShinDir[0]*shl, ankle[1]+newShinDir[1]*shl, ankle[2]+newShinDir[2]*shl];

        // Thigh: rotate by (dDorsi - dKnee) around lateral axis
        // dDorsi propagates the shin tilt change through the knee joint
        // dKnee additionally opens/closes the knee angle
        let newThighDir = _rotVec(_norm(thighVec), lat, (dDorsi - dKnee) * deg2rad);
        const newHip = [newKnee[0]+newThighDir[0]*thl, newKnee[1]+newThighDir[1]*thl, newKnee[2]+newThighDir[2]*thl];

        return {{ knee: newKnee, hip: newHip }};
    }}

    const L = adjustLeg(aL, cKL, cHL, dDorsiL, dKF, dValL, -1);
    const R = adjustLeg(aR, cKR, cHR, dDorsiR, dKF, dValR, +1);
    set(13, L.knee[0], L.knee[1], L.knee[2]);
    set(14, R.knee[0], R.knee[1], R.knee[2]);
    set(11, L.hip[0], L.hip[1], k[11] ? k[11][2] : L.hip[2]);
    set(12, R.hip[0], R.hip[1], k[12] ? k[12][2] : R.hip[2]);

    const hipMidX = (L.hip[0]+R.hip[0])/2, hipMidY = (L.hip[1]+R.hip[1])/2;

    // Trunk angle from locked shoulder
    let totalTrunkLean;
    if (lockedShoulder) {{
        totalTrunkLean = Math.max(0, Math.atan2(lockedShoulder.x - hipMidX, lockedShoulder.y - hipMidY)
            + (dLean * deg2rad));
    }} else {{
        totalTrunkLean = 0;
    }}

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

    return {{ kpts, trunkAngleDeg, avgKneeDeg, dorsiDeg: avgDorsiDeg,
              totalTrunkLeanDeg: totalTrunkLean * rad2deg,
              dorsiLDeg, dorsiRDeg, kfLDeg, kfRDeg, valLDeg, valRDeg,
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
    function footFwd(ankle, knee) {{ const dx=ankle.x-knee.x, dz=ankle.z-knee.z, l=Math.sqrt(dx*dx+dz*dz)||1; return {{x:dx/l,z:dz/l}}; }}
    const fL = footFwd(aL, kL), fR = footFwd(aR, kR);
    const _fl = footLen || REF.foot_len;
    segCOMs.foot_l = {{ x:aL.x+fL.x*_fl*0.5, y:aL.y, z:aL.z+fL.z*_fl*0.5 }};
    segCOMs.foot_r = {{ x:aR.x+fR.x*_fl*0.5, y:aR.y, z:aR.z+fR.z*_fl*0.5 }};
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
    const halfW = 0.05, heelOff = 0.06, toeOff = footLen - heelOff;
    function footRect(ankle, knee) {{
        const dx=ankle.x-knee.x, dz=ankle.z-knee.z, l=Math.sqrt(dx*dx+dz*dz)||1;
        const fx=dx/l, fz=dz/l, lx=-fz, lz=fx;
        return [
            {{ x:ankle.x-fx*heelOff-lx*halfW, z:ankle.z-fz*heelOff-lz*halfW }},
            {{ x:ankle.x-fx*heelOff+lx*halfW, z:ankle.z-fz*heelOff+lz*halfW }},
            {{ x:ankle.x+fx*toeOff+lx*halfW, z:ankle.z+fz*toeOff+lz*halfW }},
            {{ x:ankle.x+fx*toeOff-lx*halfW, z:ankle.z+fz*toeOff-lz*halfW }},
        ];
    }}
    const pts = [...footRect(aL, kL), ...footRect(aR, kR)];
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
        document.getElementById('sb-compensated-controls').style.display = getSbSolverMode() === 'compensated' ? '' : 'none';
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
    }};
}}

// ======== SANDBOX UPDATE ========

function updateSandbox(fd) {{
    if (!fd || !fd.kpts) return;
    const k = fd.kpts;
    const a = fd.angles;
    const deltas = getSandboxDeltas();
    const bodyParams = getSandboxBodyParams();

    let kpts, trunkAngleDeg, avgKneeDeg, dorsiDeg, totalTrunkLeanDeg;
    let dorsiLDeg, dorsiRDeg, kfLDeg, kfRDeg, valLDeg, valRDeg;

    if (!_slidersModified) {{
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
    }} else {{
        // Sliders modified: per-side delta FK from captured angles
        // Locked shoulder from captured data (shoulder midpoint of this frame)
        const lockedShoulder = (k[5] && k[6]) ?
            {{ x: (k[5][0]+k[6][0])/2, y: (k[5][1]+k[6][1])/2 }} : null;
        const pose = computePerSidePose(fd, deltas, bodyParams, lockedShoulder);
        ({{ kpts, trunkAngleDeg, avgKneeDeg, dorsiDeg, totalTrunkLeanDeg,
            dorsiLDeg, dorsiRDeg, kfLDeg, kfRDeg, valLDeg, valRDeg }} = pose);
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

    // COM / BOS
    const sbFootLen = AP ? (AP.foot_avg_m || REF.foot_len) : REF.foot_len;
    const sbCom = computeCOM(kpts, 0, 75, sbFootLen);
    const sbBos = computeBOS(kpts, 0, sbFootLen);
    const sbBal = isBalanced(sbCom, sbBos);
    updateCOMVisuals(sbCom, sbBos, sbBal);

    const leanOff = (180 - trunkAngleDeg).toFixed(1);
    document.getElementById('sb-angles-info').innerHTML = `
        <span class="lbl">Knee Flex L/R:</span> <span class="val">${{kfLDeg.toFixed(1)}}° / ${{kfRDeg.toFixed(1)}}°</span>
        <span class="val" style="opacity:0.5">(avg ${{avgKneeDeg.toFixed(1)}}°)</span><br>
        <span class="lbl">Trunk Angle:</span> <span class="val">${{trunkAngleDeg.toFixed(1)}}°</span> (offset: ${{leanOff}}°)
        ${{leanSev !== 'none' ? sb(leanSev) : ''}}<br>
        <span class="lbl">Dorsi L/R:</span> <span class="val">${{dorsiLDeg.toFixed(1)}}° / ${{dorsiRDeg.toFixed(1)}}°</span>
        <span class="val" style="opacity:0.5">(avg ${{dorsiDeg.toFixed(1)}}°)</span><br>
        <span class="lbl">Valgus L/R:</span> <span class="val">${{valLDeg.toFixed(1)}}° / ${{valRDeg.toFixed(1)}}°</span>
        ${{valgusSev !== 'none' ? sb(valgusSev) : ''}}<br>
        <span class="lbl">Hip Flex L/R:</span> <span class="val">${{a.hip_flex_l.toFixed(1)}}° / ${{a.hip_flex_r.toFixed(1)}}°</span><br>
        <span class="lbl">Phase:</span> <span class="val">${{(fd.phase || 0).toFixed(3)}}</span>
        ${{_slidersModified ? '<span style="color:#4ecdc4; margin-left:8px">&Delta; active</span>' : ''}}`;

    document.getElementById('info-overlay').innerHTML = `
        <span style="color:#4ecdc4">SANDBOX</span>
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


def main():
    parser = argparse.ArgumentParser(description="Capture squats and visualize in 3D")
    parser.add_argument("--output", "-o", default=None,
                        help="Output video path (default: recordings/squat_YYYYMMDD_HHMMSS.mp4)")
    parser.add_argument("--camera", "-c", type=int, default=0, help="Camera device ID")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open HTML in browser")
    args = parser.parse_args()

    recordings_dir = Path(__file__).parent.parent / "recordings"
    recordings_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    video_path = Path(args.output) if args.output else recordings_dir / f"squat_{timestamp}.mp4"
    html_path = video_path.with_suffix(".html")

    print("=" * 50)
    print("  SQUAT CAPTURE & 3D REPLAY")
    print("=" * 50)
    print(f"  Video → {video_path}")
    print(f"  HTML  → {html_path}")
    print(f"  Reps to capture: {TARGET_REPS}")
    print("=" * 50)

    frames_data, reps, rep_boundaries, fps, bone_cstr = run_capture(args.camera, video_path)

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

    replay_reps = rep_frame_slices[1:]

    html = build_html(baseline, replay_reps, fps, athlete_params)
    html_path.write_text(html)
    print(f"\nVideo saved: {video_path}")
    print(f"HTML saved:  {html_path}")

    if not args.no_open:
        webbrowser.open(f"file://{html_path.resolve()}")


if __name__ == "__main__":
    main()
