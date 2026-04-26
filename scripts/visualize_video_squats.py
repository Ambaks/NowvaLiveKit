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
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
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
    for kp in skeleton_2d.keypoints[:17]:
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
    return {
        "kpts": kpts_vis.tolist(),
        "angles": {
            "knee_flex": angles.avg_knee_flexion,
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
    width: 360px; background: #12122a; border-left: 1px solid #2a2a4a;
    overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 14px;
}}
h1 {{ font-size: 18px; font-weight: 600; color: #a0a0ff; margin-bottom: 4px; }}
.section {{
    background: #1a1a35; border: 1px solid #2a2a4a; border-radius: 8px; padding: 14px;
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
.slider-row label {{ font-size: 12px; color: #b0b0cc; min-width: 80px; flex-shrink: 0; }}
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
.sandbox-btn {{
    width: 100%; margin-top: 10px; padding: 8px 14px; border: 1px solid #6050a0;
    border-radius: 6px; background: #3a2a6a; color: #d0c0ff; font-size: 12px;
    font-weight: 600; cursor: pointer; transition: all 0.2s;
}}
.sandbox-btn:hover {{ background: #4a3a8a; border-color: #8070c0; }}
</style>
</head>
<body>
<div id="scene-container">
    <canvas id="three-canvas"></canvas>
    <div id="info-overlay"></div>
    <div id="ground-label">Drag to orbit | Scroll to zoom</div>
</div>
<div id="controls">
    <h1>Squat Video Replay</h1>
    <div class="section baseline">
        <div class="section-title"><span class="dot"></span> Baseline (Rep 1)</div>
        <div class="mono" id="baseline-info"></div>
    </div>
    <div class="section athlete">
        <div class="section-title"><span class="dot"></span> Athlete Stats</div>
        <div class="mono" id="athlete-info"></div>
        <button class="sandbox-btn" id="sandbox-btn">Open in Sandbox</button>
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
<script type="module">
import * as THREE from 'three';
import {{ OrbitControls }} from 'three/addons/controls/OrbitControls.js';

const DATA = {data_json};
const BONE_CONNECTIONS = [
    [0,1],[0,2],[1,3],[2,4],[5,6],[5,7],[7,9],[6,8],[8,10],
    [5,11],[6,12],[11,12],[11,13],[13,15],[12,14],[14,16],
];
const baseline = DATA.baseline;
const LEAN_T = baseline.leanThresholds;
const VALG_T = baseline.valgusThresholds;

document.getElementById('baseline-info').innerHTML = `
    <span class="lbl">Peak trunk offset:</span> <span class="val-green">${{baseline.peakTrunkOffset.toFixed(1)}}°</span><br>
    <span class="lbl">Peak knee flex:</span> <span class="val-green">${{baseline.peakKneeFlex.toFixed(1)}}°</span><br>
    <span class="lbl">Peak dorsiflexion:</span> <span class="val-green">${{baseline.peakDorsi.toFixed(1)}}°</span><br>
    <span class="lbl">Baseline valgus:</span> <span class="val-green">${{baseline.peakValgus.toFixed(1)}}°</span><br>
    <hr style="border-color:#2a2a4a; margin:6px 0">
    <span class="lbl">Lean thresholds:</span> <span class="val">${{LEAN_T.mild}}° / ${{LEAN_T.moderate}}° / ${{LEAN_T.severe}}°</span><br>
    <span class="lbl">Valgus thresholds:</span> <span class="val">${{VALG_T.mild}}° / ${{VALG_T.moderate}}° / ${{VALG_T.severe}}°</span>
`;

const AP = DATA.athleteParams;
if (AP) {{
    document.getElementById('athlete-info').innerHTML = `
        <span class="lbl">Hip width:</span> <span class="val">${{(AP.hip_width_m * 100).toFixed(1)}} cm</span>
        <span class="lbl" style="margin-left:8px">Shoulders:</span> <span class="val">${{(AP.shoulder_width_m * 100).toFixed(1)}} cm</span><br>
        <span class="lbl">Femur avg:</span> <span class="val">${{(AP.femur_avg_m * 100).toFixed(1)}} cm</span>
        <span class="lbl" style="margin-left:8px">Tibia:</span> <span class="val">${{(AP.tibia_avg_m * 100).toFixed(1)}} cm</span><br>
        <span class="lbl">Upper arm:</span> <span class="val">${{(AP.upper_arm_avg_m * 100).toFixed(1)}} cm</span>
        <span class="lbl" style="margin-left:8px">Forearm:</span> <span class="val">${{(AP.forearm_avg_m * 100).toFixed(1)}} cm</span><br>
        <span class="lbl">Torso avg:</span> <span class="val">${{(AP.torso_avg_m * 100).toFixed(1)}} cm</span><br>
        <hr style="border-color:#2a2a4a; margin:6px 0">
        <span class="lbl">Body scale:</span> <span class="val">${{AP.bodyScale.toFixed(2)}}</span>
        <span class="lbl" style="margin-left:8px">Arm:</span> <span class="val">${{AP.armRatio.toFixed(2)}}</span><br>
        <span class="lbl">Torso:</span> <span class="val">${{AP.torsoRatio.toFixed(2)}}</span>
        <span class="lbl" style="margin-left:8px">Thigh:</span> <span class="val">${{AP.thighRatio.toFixed(2)}}</span>
        <span class="lbl" style="margin-left:8px">Shin:</span> <span class="val">${{AP.shinRatio.toFixed(2)}}</span><br>
        <hr style="border-color:#2a2a4a; margin:6px 0">
        <span class="lbl">Stance width:</span> <span class="val">${{AP.stanceWidth.toFixed(2)}}x hip</span>
        <span class="lbl" style="margin-left:8px">Toe-out:</span> <span class="val">${{AP.toeOut.toFixed(1)}}°</span><br>
        <span class="lbl">Dorsi ratio:</span> <span class="val">${{AP.dorsiRatio.toFixed(3)}}</span>
        <span class="lbl" style="margin-left:8px">Max knee:</span> <span class="val">${{AP.maxKneeFlex.toFixed(1)}}°</span><br>
        <span class="lbl">Fwd lean:</span> <span class="val">${{AP.forwardLean.toFixed(1)}}°</span>
        <span class="lbl" style="margin-left:8px">Valgus:</span> <span class="val">${{AP.kneeValgus.toFixed(1)}}°</span><br>
        <span class="lbl">Shoulder flex:</span> <span class="val">${{AP.shoulderFlex.toFixed(1)}}°</span>
        <span class="lbl" style="margin-left:8px">Elbow flex:</span> <span class="val">${{AP.elbowFlex.toFixed(1)}}°</span>
    `;
    document.getElementById('sandbox-btn').addEventListener('click', () => {{
        const params = new URLSearchParams({{
            bodyScale: AP.bodyScale, torsoRatio: AP.torsoRatio,
            thighRatio: AP.thighRatio, shinRatio: AP.shinRatio,
            armRatio: AP.armRatio,
            upperArmRatio: AP.upperArmRatio, forearmRatio: AP.forearmRatio,
            shoulderWidthRatio: AP.shoulderWidthRatio,
            stanceWidth: AP.stanceWidth, toeOut: AP.toeOut,
            dorsiRatio: AP.dorsiRatio, maxKneeFlex: AP.maxKneeFlex,
            forwardLean: AP.forwardLean, kneeValgus: AP.kneeValgus,
            shoulderFlex: AP.shoulderFlex, elbowFlex: AP.elbowFlex,
        }});
        const vizUrl = new URL('../fault_visualizer.html', window.location.href);
        vizUrl.search = params.toString();
        window.open(vizUrl.href, '_blank');
    }});
}} else {{
    document.getElementById('athlete-info').innerHTML = '<span class="lbl">Not available (bone calibration incomplete)</span>';
    document.getElementById('sandbox-btn').style.display = 'none';
}}

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

const matN = new THREE.MeshPhongMaterial({{ color: 0x40e0a0, emissive: 0x103020 }});
const matF = new THREE.MeshPhongMaterial({{ color: 0xff4444, emissive: 0x401010 }});
const matB = new THREE.MeshPhongMaterial({{ color: 0x3090d0, emissive: 0x102030 }});
const matBF = new THREE.MeshPhongMaterial({{ color: 0xff6666, emissive: 0x301010 }});
const sGeo = new THREE.SphereGeometry(0.018, 12, 8);
const jm = [], js = [];
for (let i = 0; i < 17; i++) {{ const m = new THREE.Mesh(sGeo, matN.clone()); scene.add(m); jm.push(m); js.push('n'); }}
const bm = [];
for (const [a, b] of BONE_CONNECTIONS) {{
    const g = new THREE.CylinderGeometry(0.006, 0.006, 1, 6); g.translate(0, 0.5, 0);
    const m = new THREE.Mesh(g, matB.clone()); scene.add(m); bm.push({{ mesh: m, a, b }});
}}

let curRep = 0, curFrame = 0, playing = true, lastT = performance.now(), speed = 1.0, frameAcc = 0;
const reps = DATA.reps, fps = DATA.fps;
let repFilter = -1;

const rbc = document.getElementById('rep-buttons');
const ab = document.createElement('button'); ab.className='rep-btn active'; ab.textContent='All'; ab.dataset.idx='-1'; rbc.appendChild(ab);
for (let i = 0; i < reps.length; i++) {{
    const b = document.createElement('button'); b.className='rep-btn'; b.textContent=`Rep ${{i+2}}`; b.dataset.idx=String(i); rbc.appendChild(b);
}}
rbc.addEventListener('click', e => {{
    if (!e.target.classList.contains('rep-btn')) return;
    rbc.querySelectorAll('.rep-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    repFilter = parseInt(e.target.dataset.idx);
    curRep = repFilter === -1 ? 0 : repFilter;
    curFrame = 0;
}});

const scrub = document.getElementById('frame-scrubber'), fv = document.getElementById('frame-val');
scrub.addEventListener('input', () => {{ curFrame = parseInt(scrub.value); playing = false; document.getElementById('play-btn').innerHTML = '&#9654;'; }});
document.getElementById('play-btn').addEventListener('click', () => {{ playing = !playing; document.getElementById('play-btn').innerHTML = playing ? '&#9646;&#9646;' : '&#9654;'; }});
const ss = document.getElementById('speed-slider'), sv = document.getElementById('speed-val');
ss.addEventListener('input', () => {{ speed = parseFloat(ss.value); sv.textContent = speed.toFixed(1) + 'x'; }});

function clf(t) {{ const o=180-t; return o>=LEAN_T.severe?'severe':o>=LEAN_T.moderate?'moderate':o>=LEAN_T.mild?'mild':'none'; }}
function clv(v) {{ const a=Math.abs(v); return a>=VALG_T.severe?'severe':a>=VALG_T.moderate?'moderate':a>=VALG_T.mild?'mild':'none'; }}
function sb(s) {{ return `<span class="severity-indicator sev-${{s}}">${{s.toUpperCase()}}</span>`; }}

function upd(fd) {{
    if (!fd) return;
    const k=fd.kpts, a=fd.angles;
    const ls=clf(a.trunk_flexion), vl=clv(a.knee_valgus_l), vr=clv(a.knee_valgus_r);
    const vs=vl!=='none'||vr!=='none'?(vl==='severe'||vr==='severe'?'severe':vl==='moderate'||vr==='moderate'?'moderate':'mild'):'none';
    const fj=new Set();
    if(ls!=='none')[0,1,2,3,4,5,6].forEach(j=>fj.add(j));
    if(vs!=='none')[13,14].forEach(j=>fj.add(j));
    for(let i=0;i<17;i++){{
        jm[i].position.set(k[i][0],k[i][1],k[i][2]);
        const t=fj.has(i)?'f':'n';
        if(t!==js[i]){{ jm[i].material=(t==='f'?matF:matN).clone(); js[i]=t; }}
    }}
    const fb=new Set();
    if(ls!=='none'){{ fb.add('5-6');fb.add('5-11');fb.add('6-12'); }}
    if(vs!=='none'){{ fb.add('11-13');fb.add('13-15');fb.add('12-14');fb.add('14-16'); }}
    for(const b of bm){{
        const pa=jm[b.a].position,pb=jm[b.b].position;
        const d=new THREE.Vector3().subVectors(pb,pa),l=d.length(); d.normalize();
        b.mesh.position.copy(pa); b.mesh.scale.set(1,l,1);
        b.mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),d);
        b.mesh.material=fb.has(`${{b.a}}-${{b.b}}`)?matBF:matB;
    }}
    const to=(180-a.trunk_flexion).toFixed(1);
    document.getElementById('angles-info').innerHTML=`
        <span class="lbl">Knee Flex:</span> <span class="val">${{a.knee_flex.toFixed(1)}}°</span><br>
        <span class="lbl">Trunk Angle:</span> <span class="val">${{a.trunk_flexion.toFixed(1)}}°</span> (offset: ${{to}}°)<br>
        <span class="lbl">Valgus L/R:</span> <span class="val">${{a.knee_valgus_l.toFixed(1)}}° / ${{a.knee_valgus_r.toFixed(1)}}°</span><br>
        <span class="lbl">Dorsi L/R:</span> <span class="val">${{a.dorsi_l.toFixed(1)}}° / ${{a.dorsi_r.toFixed(1)}}°</span><br>
        <span class="lbl">Hip Flex L/R:</span> <span class="val">${{a.hip_flex_l.toFixed(1)}}° / ${{a.hip_flex_r.toFixed(1)}}°</span>`;
    const fl=[];
    if(ls!=='none')fl.push('Forward Lean '+sb(ls));
    if(vs!=='none')fl.push('Knee Valgus '+sb(vs));
    document.getElementById('faults-info').innerHTML=fl.length?fl.join('<br>'):'<span class="val-green">Clean</span>';
    document.getElementById('info-overlay').innerHTML=`
        <span class="lbl">Rep:</span> <span class="val">${{curRep+2}}</span>
        <span class="lbl" style="margin-left:12px">Frame:</span> <span class="val">${{curFrame+1}}/${{reps[curRep].length}}</span><br>
        <span class="lbl">Knee:</span> <span class="val">${{a.knee_flex.toFixed(1)}}°</span>
        <span class="lbl" style="margin-left:8px">Trunk:</span> <span class="val">${{a.trunk_flexion.toFixed(1)}}°</span>`;
}}

function resize(){{ const w=container.clientWidth,h=container.clientHeight; renderer.setSize(w,h); camera.aspect=w/h; camera.updateProjectionMatrix(); }}
window.addEventListener('resize',resize); resize();

function animate(now){{
    requestAnimationFrame(animate);
    const dt=(now-lastT)/1000; lastT=now;
    if(!reps.length)return;
    const r=reps[curRep]; if(!r||!r.length)return;
    if(playing){{
        frameAcc+=dt*fps*speed;
        while(frameAcc>=1){{ frameAcc-=1; curFrame++;
            if(curFrame>=r.length){{ if(repFilter===-1)curRep=(curRep+1)%reps.length; curFrame=0; }}
        }}
    }}
    if(curFrame>=r.length)curFrame=r.length-1;
    scrub.max=r.length-1; scrub.value=curFrame;
    fv.textContent=`${{curFrame+1}}/${{r.length}}`;
    upd(r[curFrame]);
    orbitCtrl.update(); renderer.render(scene,camera);
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
