#!/usr/bin/env python3
"""
Multi-camera triangulated squat visualizer.

Captures synchronized frames from 3 cameras, triangulates 2D poses into
true 3D via DLT, runs the same IK + rep counting pipeline as the
single-camera visualizer, and generates the same interactive HTML dashboard.

Designed for headless operation (no cv2.imshow) — all feedback via terminal.

Usage:
    python calibrated_test_visualizer/visualize_triangulated.py --height 188.5
    python calibrated_test_visualizer/visualize_triangulated.py --calibration outputs/calibration.json
"""

import argparse
import json
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

# Add src/ to path for biomechanics imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import cv2
import numpy as np

from biomechanics.pose.rtmpose import RTMPoseEstimator
from biomechanics.kinematics.analytical_ik import AnalyticalIKSolver
from biomechanics.kinematics.valgus import TriangulatedValgusEstimator
from biomechanics.faults.rep_counter import RepCounter, RepCounterConfig
from biomechanics.utils.filters import JointAngleFilter
from biomechanics.utils.derivatives import DerivativeTracker
from biomechanics.utils.velocity_clamp import VelocityClamp
from biomechanics.utils.bone_constraints import BoneLengthConstraints
from biomechanics.utils.position_filter import KeypointPositionSmoother
from biomechanics.utils.standing_gate import StandingPoseGate
from biomechanics.utils.types import MultiViewPose, Skeleton2D

from biomechanics.triangulation import (
    MultiCameraCapture,
    TPoseCalibrator,
    DLTTriangulator,
)

# Import build_html from the original visualizer (synced to server by run_test.sh).
# The small helper functions are copied below for clarity.
from visualize_video_squats import build_html

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TARGET_REPS = 5
CALIBRATION_FRAMES = 30
JITTER_THRESHOLD = 8.0


# ---------------------------------------------------------------------------
# Helper functions (copied from visualize_video_squats.py for isolation)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Phase 0: Camera discovery
# ---------------------------------------------------------------------------

def discover_cameras(requested_ids=None):
    """Detect available cameras or validate requested IDs."""
    if requested_ids:
        print(f"Using requested camera IDs: {requested_ids}")
        return requested_ids

    print("Detecting cameras...")
    found = MultiCameraCapture.detect_cameras(max_id=10)
    print(f"  Found {len(found)} camera(s): {found}")

    if len(found) < 2:
        print("ERROR: Need at least 2 cameras for triangulation.")
        sys.exit(1)

    if len(found) > 3:
        found = found[:3]
        print(f"  Using first 3: {found}")

    return found


# ---------------------------------------------------------------------------
# Phase 1: T-Pose calibration
# ---------------------------------------------------------------------------

def run_tpose_calibration(camera_ids, height_m, resolution, n_frames=30):
    """Capture T-pose frames and calibrate camera extrinsics."""
    print(f"\n{'='*50}")
    print(f"  T-POSE CALIBRATION")
    print(f"{'='*50}")
    print(f"  Height: {height_m:.1f} cm ({height_m/100:.3f} m)")
    print(f"  Cameras: {camera_ids}")
    print(f"  Frames to capture: {n_frames}")
    print(f"{'='*50}")

    pose_estimator = RTMPoseEstimator(confidence_threshold=0.3)

    print("\nStand in T-pose (arms extended horizontally, feet shoulder-width).")
    print("Stay still...")

    for i in range(3, 0, -1):
        print(f"  Capturing in {i}...")
        time.sleep(1)

    print("  Capturing...")

    capture = MultiCameraCapture(
        device_ids=camera_ids,
        resolution=resolution,
    )
    capture.start()
    time.sleep(0.5)

    frames_per_camera = {str(cid): [] for cid in camera_ids}
    captured = 0

    while captured < n_frames:
        result = capture.get_synced_frames()
        if result is None:
            continue

        synced_frames, _ = result
        for cam_id, frame in synced_frames.items():
            frames_per_camera[cam_id].append(frame)
        captured += 1

        if captured % 10 == 0:
            print(f"  {captured}/{n_frames} frames captured")

    capture.release()
    print(f"  {captured} frames captured from {len(camera_ids)} cameras.")

    calibrator = TPoseCalibrator(
        pose_estimator=pose_estimator,
        focal_length_factor=0.8,
    )

    height_m_val = height_m / 100.0
    result = calibrator.calibrate(frames_per_camera, height_m_val, resolution)

    print(f"\nCalibration results:")
    for cam_id, cam_cal in result.cameras.items():
        print(f"  Camera {cam_id}: reprojection error = {cam_cal.reprojection_error:.1f} px")

    pose_estimator.release()
    return result


# ---------------------------------------------------------------------------
# Phase 2 & 3: Stabilization + Recording (triangulated)
# ---------------------------------------------------------------------------

def run_triangulated_capture(camera_ids, calibration, output_dir, resolution, target_reps=5):
    """Run multi-camera capture with triangulation, record video + data."""
    print(f"\n{'='*50}")
    print(f"  TRIANGULATED CAPTURE")
    print(f"{'='*50}")

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    video_path = output_dir / f"squat_tri_{timestamp_str}.mp4"
    primary_cam = str(camera_ids[0])

    pose_estimator = RTMPoseEstimator(confidence_threshold=0.3)
    ik = AnalyticalIKSolver()
    valgus_estimator = TriangulatedValgusEstimator()
    angle_filter = JointAngleFilter(min_cutoff=1.0, beta=0.007)
    deriv_tracker = DerivativeTracker(smoothing_alpha=0.3)
    rep_counter = RepCounter(RepCounterConfig(
        entry_knee_angle=30.0,
        exit_knee_angle=25.0,
        min_depth_knee_angle=95.0,
        min_rep_duration_frames=15,
    ))

    standing_gate = StandingPoseGate(
        min_confidence=0.5,
        max_knee_flexion_deg=20.0,
        max_trunk_flexion_deg=25.0,
        min_torso_length_m=0.25,
        max_torso_length_m=0.80,
        required_consecutive_frames=5,
    )
    velocity_clamp = VelocityClamp(max_velocity_m_per_s=4.0, target_fps=30)
    bone_constraints = BoneLengthConstraints(
        calibration_frames=30, tolerance=0.15, standing_gate=standing_gate,
    )
    position_smoother = KeypointPositionSmoother(min_cutoff=1.2, beta=3.0, d_cutoff=1.0)
    proportions_applied = False

    triangulator = DLTTriangulator(
        calibration=calibration,
        min_views=2,
        max_reprojection_error=15.0,
    )

    capture = MultiCameraCapture(
        device_ids=camera_ids,
        resolution=resolution,
    )
    capture.start()
    time.sleep(0.5)

    # --- Stabilization phase ---
    print("\n=== STABILIZATION ===")
    print("Stand still with full body visible...")

    kpt_positions = deque(maxlen=CALIBRATION_FRAMES)
    stabilized = False
    frame_idx = 0

    while not stabilized:
        result = capture.get_synced_frames()
        if result is None:
            continue

        synced_frames, ref_ts = result
        views = {}
        for cam_id, frame in synced_frames.items():
            skeleton_2d = pose_estimator.estimate(frame)
            if skeleton_2d is not None:
                views[cam_id] = skeleton_2d

        if len(views) < 2:
            continue

        multi_view = MultiViewPose(views=views, timestamp=ref_ts, frame_index=frame_idx)
        skeleton_3d = triangulator.triangulate(multi_view)

        if skeleton_3d is not None:
            standing_gate.check(skeleton_3d)
            skeleton_3d = velocity_clamp.clamp(skeleton_3d)
            skeleton_3d = bone_constraints.enforce(skeleton_3d)
            skeleton_3d = position_smoother.smooth(skeleton_3d)

            # Track stability via primary camera 2D keypoints
            if primary_cam in views:
                pts = [(kp.x, kp.y) for kp in views[primary_cam].keypoints[:17]
                       if kp.confidence > 0.3]
                if len(pts) >= 12:
                    kpt_positions.append(pts[:12])

            if bone_constraints.is_calibrated and len(kpt_positions) >= CALIBRATION_FRAMES:
                min_len = min(len(p) for p in kpt_positions)
                trimmed = [p[:min_len] for p in kpt_positions]
                arr = np.array(trimmed)
                jitter = arr.std(axis=0).mean()
                if jitter < JITTER_THRESHOLD:
                    stabilized = True

            bone_status = "done" if bone_constraints.is_calibrated else f"calibrating [{bone_constraints._frame_count}/{bone_constraints._calibration_frames}]"
            if frame_idx % 30 == 0:
                print(f"  Bone calibration: {bone_status}")

        frame_idx += 1

    if (
        not proportions_applied
        and bone_constraints.is_calibrated
        and bone_constraints.body_proportions is not None
    ):
        ik.set_body_proportions(bone_constraints.body_proportions)
        proportions_applied = True

    print("Stabilization complete.\n")

    # --- Recording phase ---
    print("=== RECORDING ===")
    print(f"Perform {target_reps} squats.\n")

    angle_filter = JointAngleFilter(min_cutoff=1.0, beta=0.007)
    deriv_tracker = DerivativeTracker(smoothing_alpha=0.3)

    w, h = resolution
    fps = 30.0
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video_writer = cv2.VideoWriter(str(video_path), fourcc, fps, (w, h))

    frames_data = []
    reps = []
    rep_boundaries = []
    current_rep_start = None
    prev_in_rep = False
    rec_frame_idx = 0
    rec_start_time = time.time()

    while len(reps) < target_reps:
        result = capture.get_synced_frames()
        if result is None:
            continue

        synced_frames, ref_ts = result

        # Record primary camera to video
        if primary_cam in synced_frames:
            video_writer.write(synced_frames[primary_cam])

        # Run pose estimation on each camera
        views = {}
        for cam_id, frame in synced_frames.items():
            skeleton_2d = pose_estimator.estimate(frame)
            if skeleton_2d is not None:
                views[cam_id] = skeleton_2d

        if len(views) < 2:
            frames_data.append(None)
            rec_frame_idx += 1
            continue

        multi_view = MultiViewPose(views=views, timestamp=ref_ts, frame_index=rec_frame_idx)
        skeleton_3d = triangulator.triangulate(multi_view)

        if skeleton_3d is None:
            frames_data.append(None)
            rec_frame_idx += 1
            continue

        # Pre-IK filters (reduced for triangulated data)
        skeleton_3d = velocity_clamp.clamp(skeleton_3d)
        skeleton_3d = bone_constraints.enforce(skeleton_3d)
        skeleton_3d = position_smoother.smooth(skeleton_3d)

        raw_angles = ik.solve(skeleton_3d)

        # Mode-aware valgus estimation (3D abduction — this visualizer is triangulated)
        vr = valgus_estimator.estimate(None, skeleton_3d)
        raw_angles.knee_valgus_l = vr.valgus_l
        raw_angles.knee_valgus_r = vr.valgus_r
        raw_angles.foot_confidence_l = vr.foot_confidence_l
        raw_angles.foot_confidence_r = vr.foot_confidence_r
        raw_angles.knee_ankle_sep_ratio = vr.kasr
        raw_angles.hip_rotation_l = vr.hip_rotation_l
        raw_angles.hip_rotation_r = vr.hip_rotation_r

        raw_angles.timestamp = time.time()
        angles = angle_filter.filter_angles(raw_angles)
        angles.timestamp = raw_angles.timestamp

        derivs = deriv_tracker.update(angles)
        rep_data, _ = rep_counter.update(angles, derivs)
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
            elapsed = time.time() - rec_start_time
            print(f"  Rep {rep_data.rep_number}: depth={rep_data.max_depth_angle:.1f}°  ({elapsed:.1f}s)")

        fd = extract_frame_data(skeleton_3d, angles, rec_frame_idx)
        frames_data.append(fd)
        rec_frame_idx += 1

    print(f"\n{target_reps} reps captured!")

    video_writer.release()
    capture.release()
    pose_estimator.release()

    fps_stats = {cam_id: 0.0 for cam_id in [str(c) for c in camera_ids]}
    print(f"\nRecording stats:")
    print(f"  Total frames: {rec_frame_idx}")
    print(f"  Video saved: {video_path}")

    return frames_data, reps, rep_boundaries, fps, bone_constraints, video_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Multi-camera triangulated squat capture")
    parser.add_argument("--height", type=float, default=188.5,
                        help="Athlete height in cm (default: 188.5)")
    parser.add_argument("--camera-ids", type=str, default=None,
                        help="Comma-separated camera device IDs (default: auto-detect)")
    parser.add_argument("--calibration", type=str, default=None,
                        help="Path to existing calibration JSON (skip T-pose)")
    parser.add_argument("--reps", type=int, default=TARGET_REPS,
                        help=f"Number of reps to capture (default: {TARGET_REPS})")
    parser.add_argument("--output-dir", type=str,
                        default=str(Path(__file__).parent / "outputs"),
                        help="Output directory")
    parser.add_argument("--no-open", action="store_true",
                        help="Don't auto-open HTML in browser")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    resolution = (1280, 720)

    print("=" * 60)
    print("  MULTI-CAMERA TRIANGULATED SQUAT CAPTURE")
    print("=" * 60)

    # Phase 0: Camera discovery
    requested_ids = None
    if args.camera_ids:
        requested_ids = [int(x.strip()) for x in args.camera_ids.split(",")]

    camera_ids = discover_cameras(requested_ids)

    # Phase 1: T-Pose calibration (or load existing)
    if args.calibration:
        print(f"\nLoading existing calibration: {args.calibration}")
        calibration = TPoseCalibrator.load_calibration(args.calibration)
    else:
        calibration = run_tpose_calibration(
            camera_ids, args.height, resolution, n_frames=CALIBRATION_FRAMES,
        )
        cal_path = output_dir / f"calibration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        TPoseCalibrator.save_calibration(calibration, str(cal_path))
        print(f"Calibration saved: {cal_path}")

    # Phases 2-3: Stabilization + Recording
    frames_data, reps, rep_boundaries, fps, bone_cstr, video_path = run_triangulated_capture(
        camera_ids, calibration, output_dir, resolution, target_reps=args.reps,
    )

    if len(reps) < 2:
        print(f"ERROR: Need at least 2 reps, got {len(reps)}.")
        sys.exit(1)

    # Phase 4: Generate output
    print(f"\n{'='*50}")
    print(f"  GENERATING OUTPUT")
    print(f"{'='*50}")
    print(f"Processing {len(reps)} reps...")
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

    replay_reps = rep_frame_slices[1:]

    html = build_html(baseline, replay_reps, fps, athlete_params)
    html_path = video_path.with_suffix(".html")
    html_path.write_text(html)

    print(f"\nVideo saved: {video_path}")
    print(f"HTML saved:  {html_path}")

    if not args.no_open:
        import webbrowser
        webbrowser.open(f"file://{html_path.resolve()}")

    print("\nDone!")


if __name__ == "__main__":
    main()
