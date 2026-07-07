"""
Biomechanics Pipeline Process

Replaces the old pose_estimation_process.py with the full layered pipeline.
Launched as a subprocess by main.py when workout mode starts.
Communicates with the voice agent via the existing IPC system.
"""

from __future__ import annotations

import json
import logging
import select
import signal
import sys
import os
import time
import webbrowser
from pathlib import Path

# Add src/ to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np

from agent.core.ipc_communication import IPCClient, _recv_framed
from biomechanics.pipeline import BiomechanicsPipeline
from biomechanics.calibration import (
    CalibrationTracker,
    build_calibration_profile,
    apply_calibration_to_rule_engine,
    extract_thresholds_from_rule_engine,
    get_movement_pattern,
)
from biomechanics.coaching.ipc_bridge import IPCBridge
from biomechanics.coaching.session_tracker import SessionTracker
from biomechanics.config import load_pipeline_config
from biomechanics.utils.types import CocoKeypoints as CK
from biomechanics.diagnosis.bridge import build_anthro_dict, build_rom_dict
from biomechanics.diagnosis.demo_builder import build_demo_data
from biomechanics.diagnosis.engine import HypothesisEngine
from biomechanics.diagnosis.rep_scoring import score_set
from biomechanics.diagnosis.types import SetFeatures
from biomechanics.viz import draw_skeleton, draw_fps, FPSCounter, precreate_window, animate_window_fullscreen
from biomechanics.viz.demo_ws_bridge import DemoWSBridge, DEMO_WS_PORT
from biomechanics.viz.set_plots import plot_hip_position, plot_hip_velocity, make_output_dir
from biomechanics.analysis.set_finalizer import SetDataCollector, finalize_set
from biomechanics.viz.html_dashboard import generate_session_dashboard


# Ensure gate diagnostics are visible on stderr
logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")

DEMO_START_TIMEOUT_S = 10.0
DEMO_INACTIVITY_TIMEOUT_S = 45.0
# Covers settle + final hold + morph-out (~2.2s) plus browser latency.
DEMO_FINISH_TIMEOUT_S = 6.0

# --- HUD styling (BGR brand palette) ---
HUD_CYAN = (255, 229, 0)
HUD_VIOLET = (246, 92, 139)
HUD_INK = (245, 240, 235)
HUD_PANEL = (16, 5, 5)
HUD_PANEL_ALPHA = 0.62
HUD_FONT = cv2.FONT_HERSHEY_DUPLEX


def _draw_rounded_rect(img, pt1, pt2, color, radius, thickness):
    x1, y1 = pt1
    x2, y2 = pt2
    if thickness < 0:
        cv2.rectangle(img, (x1 + radius, y1), (x2 - radius, y2), color, -1)
        cv2.rectangle(img, (x1, y1 + radius), (x2, y2 - radius), color, -1)
        for cx, cy in ((x1 + radius, y1 + radius), (x2 - radius, y1 + radius),
                       (x1 + radius, y2 - radius), (x2 - radius, y2 - radius)):
            cv2.circle(img, (cx, cy), radius, color, -1, cv2.LINE_AA)
    else:
        cv2.line(img, (x1 + radius, y1), (x2 - radius, y1), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x1 + radius, y2), (x2 - radius, y2), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x1, y1 + radius), (x1, y2 - radius), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x2, y1 + radius), (x2, y2 - radius), color, thickness, cv2.LINE_AA)
        cv2.ellipse(img, (x1 + radius, y1 + radius), (radius, radius), 180, 0, 90, color, thickness, cv2.LINE_AA)
        cv2.ellipse(img, (x2 - radius, y1 + radius), (radius, radius), 270, 0, 90, color, thickness, cv2.LINE_AA)
        cv2.ellipse(img, (x1 + radius, y2 - radius), (radius, radius), 90, 0, 90, color, thickness, cv2.LINE_AA)
        cv2.ellipse(img, (x2 - radius, y2 - radius), (radius, radius), 0, 0, 90, color, thickness, cv2.LINE_AA)


def _draw_hud_pill(frame, text, align="right", accent=HUD_CYAN, font_scale=0.55, y=16):
    """Glass HUD pill: dark alpha-blended rounded rect, accent dot, uppercase text."""
    label = text.upper()
    text_thickness = 2 if font_scale > 0.8 else 1
    (tw, th), _ = cv2.getTextSize(label, HUD_FONT, font_scale, text_thickness)
    pad_x = max(14, int(th * 0.9))
    pad_y = max(10, int(th * 0.55))
    dot_gap = pad_x - 2
    pill_h = th + pad_y * 2
    pill_w = tw + pad_x * 2 + dot_gap
    frame_h, frame_w = frame.shape[:2]
    x = frame_w - pill_w - 16 if align == "right" else 16
    x2, y2 = x + pill_w, y + pill_h
    if x < 0 or y < 0 or x2 > frame_w or y2 > frame_h:
        return frame
    radius = pill_h // 2

    # Alpha-blend the panel over the frame (ROI-only — cheap)
    roi = frame[y:y2, x:x2]
    panel = roi.copy()
    _draw_rounded_rect(panel, (0, 0), (pill_w - 1, pill_h - 1), HUD_PANEL, radius, -1)
    cv2.addWeighted(panel, HUD_PANEL_ALPHA, roi, 1 - HUD_PANEL_ALPHA, 0, dst=roi)

    border = tuple(int(c * 0.5) for c in accent)
    _draw_rounded_rect(frame, (x, y), (x2 - 1, y2 - 1), border, radius, 1)

    cy = y + pill_h // 2
    cv2.circle(frame, (x + pad_x, cy), 3, accent, -1, cv2.LINE_AA)
    cv2.putText(frame, label, (x + pad_x + dot_gap, y + pad_y + th),
                HUD_FONT, font_scale, HUD_INK, text_thickness, cv2.LINE_AA)
    return frame


def _draw_wordmark(frame):
    frame_h = frame.shape[0]
    cv2.putText(frame, "N O W V A", (18, frame_h - 18),
                HUD_FONT, 0.5, (150, 138, 112), 1, cv2.LINE_AA)


def _save_calibration_report(peaks: dict, profile: dict, cal_reps: int, out_dir: str):
    """Save calibration_profile.json and calibration_profile.md to output dir."""
    # JSON
    cal_json = {
        "calibration_reps": cal_reps,
        "peaks": peaks,
        "profile": {k: v for k, v in profile.items() if k != "defaults"},
        "defaults": profile.get("defaults", {}),
    }
    json_path = str(Path(out_dir) / "calibration_profile.json")
    with open(json_path, "w") as f:
        json.dump(cal_json, f, indent=2)
    print(f"  Saved: {json_path}")

    # Markdown
    defaults = profile.get("defaults", {})
    kv = profile["knee_valgus"]
    fl = profile["forward_lean"]
    ba = profile["bilateral_asymmetry"]
    hr = profile["heel_rise"]
    dp = profile.get("depth", {})
    d_kv = defaults.get("knee_valgus", {})
    d_fl = defaults.get("forward_lean", {})
    d_ba = defaults.get("bilateral_asymmetry", {})
    d_hr = defaults.get("heel_rise", {})
    d_dp = defaults.get("depth", {})

    md_lines = [
        f"# Calibration Profile ({cal_reps} reps)",
        "",
        "## Observed Peaks",
        "",
        "| Signal | Value |",
        "|--------|-------|",
        f"| Trunk Flexion (peak) | {peaks['trunk_flexion']:.1f}° |",
        *[f"| Hip Adduction Rep {i+1} | {p:.1f}° |" for i, p in enumerate(peaks.get('hip_adduction_per_rep', []))],
        f"| **Hip Adduction (avg → band)** | **±{peaks['hip_adduction']:.1f}°** |",
        f"| Bilateral Asymmetry (peak) | {peaks['asymmetry']:.1f}° |",
        f"| Dorsiflexion Drop (peak) | {peaks['dorsiflexion_drop']:.1f}° |",
        f"| **Avg Squat Depth** | **{peaks.get('avg_depth', 0):.1f}°** |",
        *[f"| Squat Depth Rep {i+1} | {d:.1f}° |" for i, d in enumerate(peaks.get('depth_per_rep', []))],
        "",
        "## Calibrated Thresholds",
        "",
        "### Fault Thresholds (Mild / Moderate / Severe)",
        "",
        "| Fault | Calibrated | Default |",
        "|-------|-----------|---------|",
        f"| Knee Valgus | {kv['mild']:.1f}° / {kv['moderate']:.1f}° / {kv['severe']:.1f}° | {d_kv.get('mild', '-')}° / {d_kv.get('moderate', '-')}° / {d_kv.get('severe', '-')}° |",
        f"| Forward Lean | {fl['mild']:.1f}° / {fl['moderate']:.1f}° / {fl['severe']:.1f}° | {d_fl.get('mild', '-')}° / {d_fl.get('moderate', '-')}° / {d_fl.get('severe', '-')}° |",
        f"| Bilateral Asymmetry | {ba['mild']:.1f}° / {ba['moderate']:.1f}° / {ba['severe']:.1f}° | {d_ba.get('mild', '-')}° / {d_ba.get('moderate', '-')}° / {d_ba.get('severe', '-')}° |",
        f"| Heel Rise | {hr['threshold_degrees']:.1f}° | {d_hr.get('threshold_degrees', '-')}° |",
        "",
        "### Depth Thresholds",
        "",
        "| Category | Calibrated | Default |",
        "|----------|-----------|---------|",
        f"| Deep Squat (below parallel) | {dp.get('parallel_threshold', '-')}° | {d_dp.get('parallel_threshold', '-')}° |",
        f"| Parallel | {dp.get('half_threshold', '-')}° | {d_dp.get('half_threshold', '-')}° |",
        f"| Half Squat | {dp.get('quarter_threshold', '-')}° | {d_dp.get('quarter_threshold', '-')}° |",
        "",
    ]
    md_path = str(Path(out_dir) / "calibration_profile.md")
    with open(md_path, "w") as f:
        f.write("\n".join(md_lines))
    print(f"  Saved: {md_path}")


def _extract_athlete_params(pipeline) -> dict | None:
    """Extract athlete body proportions from calibrated bone constraints."""
    if not (
        pipeline._bone_constraints.is_calibrated
        and pipeline._bone_constraints.body_proportions is not None
    ):
        return None
    proportions = pipeline._bone_constraints.body_proportions
    shoulder_width = pipeline._bone_constraints._calibrated_lengths.get(
        (CK.LEFT_SHOULDER, CK.RIGHT_SHOULDER), 0.40,
    )
    foot_l = pipeline._bone_constraints._calibrated_lengths.get(
        (CK.LEFT_ANKLE, CK.LEFT_FOOT_INDEX), 0.26,
    )
    foot_r = pipeline._bone_constraints._calibrated_lengths.get(
        (CK.RIGHT_ANKLE, CK.RIGHT_FOOT_INDEX), 0.26,
    )
    return {
        "shoulder_width_m": shoulder_width,
        "femur_avg_m": proportions.femur_length_avg,
        "torso_avg_m": proportions.torso_length_avg,
        "hip_width_m": proportions.hip_width,
        "tibia_avg_m": proportions.tibia_length_avg,
        "foot_avg_m": (foot_l + foot_r) / 2.0,
    }


def _serialize_diagnosis(diagnosis_result, score_summary) -> tuple[dict, dict]:
    """Convert diagnosis engine output into JSON-serializable dicts for IPC."""
    per_rep = score_summary.per_rep_scores
    n = len(per_rep)
    diagnosis_dict = {
        "confidence": diagnosis_result.confidence,
        "detected_symptoms": [
            {"symptom_id": s.symptom_id, "severity": s.severity, "contributing_reps": s.contributing_reps}
            for s in diagnosis_result.detected_symptoms
        ],
        "immediate_causes": [
            {"cause_id": c.cause_id, "score": c.score, "explanation": c.explanation, "parameter_delta": c.parameter_delta}
            for c in diagnosis_result.immediate_causes
        ],
        "session_causes": [
            {"cause_id": c.cause_id, "score": c.score, "explanation": c.explanation}
            for c in diagnosis_result.session_causes
        ],
        "contextual_notes": [
            {"cause_id": c.cause_id, "score": c.score, "explanation": c.explanation}
            for c in diagnosis_result.contextual_notes
        ],
        "combined_perturbation": diagnosis_result.combined_perturbation,
    }
    scoring_dict = {
        "mean_score": score_summary.mean_score,
        "per_dimension": {
            "depth": round(sum(r.depth_score for r in per_rep) / n, 3) if n else 0,
            "trunk_control": round(sum(r.trunk_control_score for r in per_rep) / n, 3) if n else 0,
            "knee_tracking": round(sum(r.knee_tracking_score for r in per_rep) / n, 3) if n else 0,
            "symmetry": round(sum(r.symmetry_score for r in per_rep) / n, 3) if n else 0,
        },
        "best_rep": score_summary.best_rep_number,
        "worst_rep": score_summary.worst_rep_number,
        "trend_slope": score_summary.trend_slope,
    }
    return diagnosis_dict, scoring_dict


def _poll_incoming_message(ipc_client: IPCClient):
    """Non-blocking check for a message from main.py."""
    try:
        sock = ipc_client.client_socket
        if sock is None:
            return None
        ready, _, _ = select.select([sock], [], [], 0)
        if ready:
            return _recv_framed(sock)
    except Exception:
        pass
    return None


def _skeleton_pixels(skeleton_2d) -> np.ndarray | None:
    keypoints = skeleton_2d.keypoints
    if len(keypoints) < 17:
        return None
    if any(kp.confidence <= 0 for kp in keypoints[:17]):
        return None
    return np.array([[kp.x, kp.y] for kp in keypoints[:17]], dtype=np.float32)


def _wait_for_start_capture(ipc_client: IPCClient) -> bool:
    """Block until a start_capture message arrives over IPC. Returns False on disconnect."""
    sock = ipc_client.client_socket
    if sock is None:
        return False
    while True:
        try:
            msg = _recv_framed(sock)
            if msg is None:
                return False
            if msg.get("type") == "start_capture":
                return True
        except Exception:
            return False


def run_biomechanics_pipeline(
    cam0_id: int = 0,
    cam1_id: int = 1,
    config_path: str = None,
    exercise_name: str = "Barbell Back Squat",
    calibration_file: str = None,
    calibration_mode: bool = False,
    calibration_reps: int = 5,
    preload: bool = False,
):
    """
    Run the full biomechanics pipeline as a subprocess.

    This is called by main.py when workout mode starts.
    Connects to the existing IPC server and sends real-time
    coaching data to the voice agent.

    When preload=True the subprocess loads config + pose model eagerly
    (without opening the camera) and waits for a start_capture IPC
    message before opening the camera and entering the frame loop.
    This lets main.py overlap model loading with the voice greeting.
    """
    print("\n=== Biomechanics Pipeline Starting ===")

    # Handle SIGTERM gracefully so finally blocks run when main.py terminates us
    def _sigterm_handler(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, _sigterm_handler)

    # Connect to IPC server (started by main.py)
    ipc_client = IPCClient()
    if not ipc_client.connect(timeout=10):
        print("Failed to connect to IPC server. Exiting.")
        return

    # Load config
    config = load_pipeline_config(config_path)
    # Override camera device from CLI arg
    config.capture.device_id = cam0_id

    # Initialize pipeline
    try:
        pipeline = BiomechanicsPipeline(
            config, exercise_name=exercise_name, defer_capture=preload,
        )

        if preload:
            pipeline.preload_pose_model()
            print("[PRELOAD] Pose model loaded — waiting for start_capture signal")
            ipc_client.send_message({"type": "pipeline_status", "status": "preloaded"})

            if not _wait_for_start_capture(ipc_client):
                print("[PRELOAD] IPC disconnected while waiting for start_capture")
                ipc_client.disconnect()
                return

            pipeline.start_capture()
            print("[PRELOAD] Camera opened — entering frame loop")

        # Multi-camera calibration (if needed)
        if pipeline._multi_camera and pipeline._multi_camera_provider is not None:
            if not pipeline._multi_camera_provider.is_calibrated:
                height_m = float(os.getenv("NOWVA_USER_HEIGHT_M", "1.885"))
                print(f"[MULTI-CAM] Running T-pose calibration (height={height_m}m)...")
                pipeline._multi_camera_provider.calibrate(
                    height_m=height_m,
                    save_path="outputs/calibration.json",
                )
                print("[MULTI-CAM] Calibration complete")

        bridge = IPCBridge(ipc_client)
        session_tracker = SessionTracker(bridge, config=config.coaching)

        # Pre-cache coaching cues for the exercise
        bridge.prepare_exercise(exercise_name)

        ipc_client.send_message({"type": "status", "value": "initialized"})
        bridge.send_pipeline_status("running", {})

        print(f"Pipeline initialized for: {exercise_name}")
        print(f"Running at target {config.target_fps} FPS")
        print("Press Ctrl+C to stop\n")

    except Exception as e:
        print(f"Pipeline initialization failed: {e}")
        ipc_client.send_message({"type": "error", "value": str(e)})
        ipc_client.disconnect()
        return

    fps_counter = FPSCounter()
    window_name = f"Nowva — {exercise_name}"
    precreate_window(window_name)
    _window_animated = False
    session_output = os.environ.get("NOWVA_SESSION_OUTPUT_DIR")
    out_dir = make_output_dir(base=os.path.join(session_output, "output") if session_output else "output")

    # --- Apply existing calibration if provided ---
    if calibration_file and os.path.exists(calibration_file):
        try:
            with open(calibration_file, "r") as f:
                cal_profile = json.load(f)
            apply_calibration_to_rule_engine(pipeline._rule_engine, cal_profile)
            print(f"[CALIBRATION] Loaded calibration from {calibration_file}")
        except Exception as e:
            print(f"[CALIBRATION] Failed to load calibration file: {e}")

    # --- Assessment + Calibration phase (if no existing calibration) ---
    if calibration_mode:
        movement_pattern = get_movement_pattern(exercise_name) or "squat"

        # ============================================================
        #  PHASE 1: PRE-WORKOUT FORM ASSESSMENT (2-rep loop)
        # ============================================================
        ASSESSMENT_TARGET_REPS = 1

        print(f"\n{'='*60}")
        print(f"  ASSESSMENT PHASE ({ASSESSMENT_TARGET_REPS} bodyweight squats)")
        print(f"{'='*60}\n")

        # Wait for readiness gate + bone constraint calibration
        print("  [ASSESSMENT] Waiting for readiness gate + bone constraints...")
        try:
            while not (pipeline.is_ready and pipeline._bone_constraints.is_calibrated):
                result = pipeline.process_frame()

                frame = pipeline.last_frame
                if frame is not None:
                    display = frame.copy()
                    if result.skeleton_2d is not None:
                        draw_skeleton(display, result.skeleton_2d)
                    fps_counter.update()
                    draw_fps(display, fps_counter.fps)

                    current, required = pipeline._readiness_gate.progress
                    _draw_hud_pill(display, f"WAITING {current}/{required}", accent=HUD_VIOLET)
                    _draw_wordmark(display)

                    if not _window_animated:
                        animate_window_fullscreen(window_name)
                        _window_animated = True
                    cv2.imshow(window_name, display)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        print("\nAssessment stopped early by user")
                        cv2.destroyAllWindows()
                        pipeline.release()
                        ipc_client.disconnect()
                        return

                total_ms = sum(result.latency_ms.values())
                target_ms = 1000.0 / config.target_fps
                if total_ms < target_ms:
                    time.sleep((target_ms - total_ms) / 1000.0)
        except KeyboardInterrupt:
            print("\nAssessment stopped by user")
            cv2.destroyAllWindows()
            pipeline.release()
            ipc_client.disconnect()
            return

        # Extract athlete params from bone constraints
        athlete_params = _extract_athlete_params(pipeline)
        if athlete_params is not None:
            baseline_stub = {"peakDorsi": 35.0, "peakKneeFlex": 120.0}
            session_tracker.set_athlete_params(athlete_params, baseline_stub)
            print(
                f"  [ASSESSMENT] Athlete params set: "
                f"shoulder={athlete_params['shoulder_width_m']:.3f}m "
                f"femur={athlete_params['femur_avg_m']:.3f}m "
                f"tibia={athlete_params['tibia_avg_m']:.3f}m"
            )
        else:
            print("  [ASSESSMENT] WARNING: Bone constraints not calibrated — diagnosis unavailable")

        def _run_demo_phase(demo_data) -> bool:
            """Drive the choreographed demo from agent messages. Returns False if user quit."""
            bridge = DemoWSBridge()
            bridge.start()
            time.sleep(0.3)
            webbrowser.open(f"http://localhost:{DEMO_WS_PORT}")
            time.sleep(1.0)
            bridge.send_init(demo_data)

            phase_start = time.time()
            last_message_time = phase_start
            finishing = False
            finish_deadline = 0.0
            demo_started = False
            started_ack_sent = False

            try:
                while True:
                    result = pipeline.process_frame()

                    if result.skeleton_3d is not None:
                        bridge.send_live_pose(result.skeleton_3d.to_numpy())

                    if not started_ack_sent and bridge.wait_started(timeout=0):
                        ipc_client.send_message({"type": "demo_started"})
                        started_ack_sent = True

                    incoming = _poll_incoming_message(ipc_client)
                    if incoming is not None:
                        last_message_time = time.time()
                        msg_type = incoming.get("type")
                        if msg_type == "demo_start":
                            bridge.send_event({"type": "demo_start"})
                            demo_started = True
                        elif msg_type == "demo_cue":
                            bridge.send_event({
                                "type": "demo_cue",
                                "cue_index": int(incoming.get("cue_index", 0)),
                            })
                        elif msg_type == "demo_end":
                            bridge.send_event({"type": "demo_end"})
                            finishing = True
                            finish_deadline = time.time() + DEMO_FINISH_TIMEOUT_S

                    now = time.time()
                    if finishing:
                        if bridge.wait_done(timeout=0):
                            return True
                        if now > finish_deadline:
                            print("  [DEMO] Viewer never confirmed done — ending demo")
                            return True
                    if not demo_started and now - phase_start > DEMO_START_TIMEOUT_S:
                        print("  [DEMO] No demo_start received — skipping demo")
                        return True
                    if demo_started and not finishing and now - last_message_time > DEMO_INACTIVITY_TIMEOUT_S:
                        print("  [DEMO] Agent went silent mid-demo — ending demo")
                        bridge.send_event({"type": "demo_end"})
                        finishing = True
                        finish_deadline = now + DEMO_FINISH_TIMEOUT_S

                    frame = pipeline.last_frame
                    if frame is not None:
                        display = frame.copy()
                        if result.skeleton_2d is not None:
                            draw_skeleton(display, result.skeleton_2d)
                        fps_counter.update()
                        cv2.imshow(window_name, display)
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            print("\nDemo stopped early by user")
                            return False

                    total_ms = sum(result.latency_ms.values())
                    target_ms = 1000.0 / config.target_fps
                    if total_ms < target_ms:
                        time.sleep((target_ms - total_ms) / 1000.0)
            finally:
                bridge.stop()

        # Assessment loop: collect reps, diagnose, repeat until no immediate causes
        assessment_passed = False
        assessment_round = 0
        demo_played = False

        try:
            while not assessment_passed:
                assessment_round += 1
                assessment_reps_done = 0
                pipeline.rep_counter.reset()
                pipeline.rep_counter.set_assessment_mode(True)
                if pipeline._bilstm is not None:
                    pipeline._bilstm.set_assessment_mode(True)
                session_tracker.set_assessment_mode(True)
                session_tracker.reset_rep_buffers()
                session_tracker.current_set_reps = []
                session_tracker.set_active = False

                print(f"\n  [ASSESSMENT] Round {assessment_round} — collecting {ASSESSMENT_TARGET_REPS} reps")

                while assessment_reps_done < ASSESSMENT_TARGET_REPS:
                    result = pipeline.process_frame()

                    if pipeline.is_ready and result.skeleton_3d is not None:
                        bridge.send_frame_data(result)
                        for fault in result.faults:
                            bridge.send_fault(fault)

                        if result.rep_data is not None:
                            bottom_kpts = None
                            bottom_angles = None
                            standing_kpts = None
                            if hasattr(pipeline, 'consume_bottom_frame'):
                                bottom_kpts, bottom_angles = pipeline.consume_bottom_frame()
                            if hasattr(pipeline, 'consume_standing_frame'):
                                standing_kpts = pipeline.consume_standing_frame()

                            session_tracker.on_rep_complete(
                                result.rep_data,
                                bottom_kpts=bottom_kpts,
                                bottom_angles=bottom_angles,
                                standing_kpts=standing_kpts,
                            )
                            assessment_reps_done += 1

                            depth = result.rep_data.max_depth_angle
                            print(f"  [ASSESSMENT REP {assessment_reps_done}/{ASSESSMENT_TARGET_REPS}] depth={depth:.1f}°")

                            ipc_client.send_message({
                                "type": "assessment_rep",
                                "rep_number": assessment_reps_done,
                                "total_required": ASSESSMENT_TARGET_REPS,
                                "round": assessment_round,
                                "depth_angle": round(depth, 1),
                            })

                    # Display
                    frame = pipeline.last_frame
                    if frame is not None:
                        display = frame.copy()
                        if result.skeleton_2d is not None:
                            draw_skeleton(display, result.skeleton_2d)
                        fps_counter.update()
                        draw_fps(display, fps_counter.fps)

                        _draw_hud_pill(
                            display,
                            f"ASSESSMENT  ROUND {assessment_round}",
                            accent=HUD_CYAN,
                        )
                        _draw_hud_pill(
                            display,
                            f"REP {assessment_reps_done}/{ASSESSMENT_TARGET_REPS}",
                            align="left", accent=HUD_CYAN, font_scale=1.1, y=48,
                        )
                        _draw_wordmark(display)

                        cv2.imshow(window_name, display)
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            print("\nAssessment stopped early by user")
                            cv2.destroyAllWindows()
                            pipeline.release()
                            ipc_client.disconnect()
                            return

                    total_ms = sum(result.latency_ms.values())
                    target_ms = 1000.0 / config.target_fps
                    if total_ms < target_ms:
                        time.sleep((target_ms - total_ms) / 1000.0)

                # --- Run diagnosis on assessment reps ---
                kinematic_buffer = list(session_tracker._rep_kinematic_buffer)

                if kinematic_buffer and athlete_params is not None:
                    anthro = build_anthro_dict(athlete_params)
                    rom = build_rom_dict(athlete_params, baseline_stub)
                    set_features = SetFeatures(
                        user_id=0,
                        set_id=f"assessment_{assessment_round}",
                        rep_count=len(kinematic_buffer),
                        per_rep_kinematics=kinematic_buffer,
                        anthropometry=anthro,
                        rom=rom,
                    )
                    diagnosis_result = HypothesisEngine().diagnose(set_features)
                    score_summary = score_set(kinematic_buffer, anthro, rom)

                    has_immediate = len(diagnosis_result.immediate_causes) > 0
                    diagnosis_dict, scoring_dict = _serialize_diagnosis(diagnosis_result, score_summary)

                    print(f"\n  [ASSESSMENT] Diagnosis: confidence={diagnosis_result.confidence:.2f}")
                    print(f"  [ASSESSMENT] Immediate causes: {len(diagnosis_result.immediate_causes)}")
                    print(f"  [ASSESSMENT] Session causes: {len(diagnosis_result.session_causes)}")
                    print(f"  [ASSESSMENT] Form score: {round(score_summary.mean_score * 100)}/100")

                    # Build demo data before announcing the result so the
                    # choreography is ready the moment the agent reacts.
                    pending_demo = None
                    if has_immediate and not demo_played:
                        observed_kpts = session_tracker.bottom_frame_for_rep(
                            score_summary.worst_rep_number
                        )
                        if observed_kpts is not None:
                            pending_demo = build_demo_data(
                                observed_kpts, diagnosis_result, anthro=anthro, rom=rom,
                            )
                    if pending_demo is not None:
                        print(f"  [DEMO] Pose stack ready: {len(pending_demo.cues)} cue(s)")

                    ipc_client.send_message({
                        "type": "assessment_result",
                        "round": assessment_round,
                        "passed": not has_immediate,
                        "diagnosis": diagnosis_dict,
                        "scoring": scoring_dict,
                        "demo": {
                            "available": pending_demo is not None,
                            "cues": [cue.model_dump() for cue in pending_demo.cues]
                            if pending_demo is not None else [],
                        },
                    })

                    if not has_immediate:
                        assessment_passed = True
                        print(f"\n  [ASSESSMENT] PASSED after {assessment_round} round(s)")
                    else:
                        print(f"  [ASSESSMENT] Issues found — user needs to correct and retry")
                        if pending_demo is not None:
                            demo_played = True
                            if not _run_demo_phase(pending_demo):
                                cv2.destroyAllWindows()
                                pipeline.release()
                                ipc_client.disconnect()
                                return
                        pipeline.reset_readiness_gate()
                        # Wait for readiness gate again before next round
                        while not pipeline.is_ready:
                            result = pipeline.process_frame()
                            frame = pipeline.last_frame
                            if frame is not None:
                                display = frame.copy()
                                if result.skeleton_2d is not None:
                                    draw_skeleton(display, result.skeleton_2d)
                                fps_counter.update()
                                draw_fps(display, fps_counter.fps)

                                current, required = pipeline._readiness_gate.progress
                                _draw_hud_pill(display, f"WAITING {current}/{required}", accent=HUD_VIOLET)
                                _draw_wordmark(display)

                                cv2.imshow(window_name, display)
                                if cv2.waitKey(1) & 0xFF == ord('q'):
                                    cv2.destroyAllWindows()
                                    pipeline.release()
                                    ipc_client.disconnect()
                                    return
                            total_ms = sum(result.latency_ms.values())
                            target_ms = 1000.0 / config.target_fps
                            if total_ms < target_ms:
                                time.sleep((target_ms - total_ms) / 1000.0)
                else:
                    # No kinematic data (athlete_params missing) — pass through
                    print("  [ASSESSMENT] No kinematic data — skipping diagnosis, passing assessment")
                    ipc_client.send_message({
                        "type": "assessment_result",
                        "round": assessment_round,
                        "passed": True,
                        "diagnosis": {},
                        "scoring": {},
                    })
                    assessment_passed = True

        except KeyboardInterrupt:
            print("\nAssessment stopped by user")
            cv2.destroyAllWindows()
            pipeline.release()
            ipc_client.disconnect()
            return

        # Reset pipeline state for calibration
        pipeline.reset_readiness_gate()
        pipeline.rep_counter.reset()
        pipeline.rep_counter.set_assessment_mode(False)
        if pipeline._bilstm is not None:
            pipeline._bilstm.reset()
            pipeline._bilstm.set_assessment_mode(False)
        session_tracker.set_assessment_mode(False)
        session_tracker.reset_rep_buffers()
        session_tracker.current_set_reps = []
        session_tracker.set_active = False
        session_tracker.current_set_number = 0

        # ============================================================
        #  PHASE 2: CALIBRATION (5-rep threshold calibration)
        # ============================================================
        print(f"\n{'='*60}")
        print(f"  CALIBRATION PHASE ({calibration_reps} bodyweight squats)")
        print(f"{'='*60}\n")

        tracker = CalibrationTracker(target_reps=calibration_reps)
        cal_set_collector = SetDataCollector()

        try:
            while not tracker.is_complete:
                result = pipeline.process_frame()

                if pipeline.is_ready and result.skeleton_3d is not None:
                    cal_set_collector.record_frame(result, result.skeleton_3d)

                    if result.joint_angles is not None:
                        tracker.record_frame(result.joint_angles, in_rep=pipeline.rep_counter.in_rep)

                    # Count reps but do NOT report faults during calibration
                    if result.rep_data is not None:
                        depth = result.rep_data.max_depth_angle
                        tracker.on_rep_complete(depth)
                        print(f"  [CAL REP {tracker.reps_completed}/{calibration_reps}] depth={depth:.1f}°")

                        # Notify voice agent of calibration rep
                        ipc_client.send_message({
                            "type": "calibration_rep",
                            "rep_number": tracker.reps_completed,
                            "total_required": calibration_reps,
                            "depth_angle": round(depth, 1),
                        })

                # Display
                frame = pipeline.last_frame
                if frame is not None:
                    display = frame.copy()
                    if result.skeleton_2d is not None:
                        draw_skeleton(display, result.skeleton_2d)
                    fps_counter.update()
                    draw_fps(display, fps_counter.fps)

                    if pipeline.is_ready:
                        _draw_hud_pill(display, "CALIBRATING", accent=HUD_CYAN)
                    else:
                        current, required = pipeline._readiness_gate.progress
                        _draw_hud_pill(display, f"WAITING {current}/{required}", accent=HUD_VIOLET)

                    _draw_hud_pill(
                        display,
                        f"REP {tracker.reps_completed}/{calibration_reps}",
                        align="left", accent=HUD_CYAN, font_scale=1.1, y=48,
                    )
                    _draw_wordmark(display)

                    cv2.imshow(window_name, display)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        print("\nCalibration stopped early by user")
                        cv2.destroyAllWindows()
                        pipeline.release()
                        ipc_client.disconnect()
                        return

                # Throttle
                total_ms = sum(result.latency_ms.values())
                target_ms = 1000.0 / config.target_fps
                if total_ms < target_ms:
                    time.sleep((target_ms - total_ms) / 1000.0)

            # --- Calibration complete ---
            peaks = tracker.get_peaks()
            cal_profile = build_calibration_profile(peaks, config)
            apply_calibration_to_rule_engine(pipeline._rule_engine, cal_profile)

            # Build real baseline from calibration peaks
            cal_athlete_params = _extract_athlete_params(pipeline)
            cal_baseline = {
                "peakDorsi": peaks["dorsiflexion_drop"],
                "peakKneeFlex": peaks["avg_depth"],
            }

            # Send calibration results + athlete data to voice agent
            cal_complete_msg = {
                "type": "calibration_complete",
                "movement_pattern": movement_pattern,
                "peaks": peaks,
                "thresholds": {k: v for k, v in cal_profile.items() if k != "defaults"},
            }
            if cal_athlete_params is not None:
                cal_complete_msg["athlete_params"] = cal_athlete_params
                cal_complete_msg["baseline"] = cal_baseline
            ipc_client.send_message(cal_complete_msg)

            print(f"\n{'='*60}")
            print(f"  CALIBRATION COMPLETE ({tracker.reps_completed} reps)")
            print(f"  Peak trunk flexion: {peaks['trunk_flexion']:.1f}°")
            print(f"  Avg hip adduction:  {peaks['hip_adduction']:.1f}°")
            print(f"  Peak asymmetry:     {peaks['asymmetry']:.1f}°")
            print(f"  Peak dorsi drop:    {peaks['dorsiflexion_drop']:.1f}°")
            print(f"  Avg squat depth:    {peaks.get('avg_depth', 0):.1f}°")
            print(f"{'='*60}\n")

            # Save calibration report
            _save_calibration_report(peaks, cal_profile, calibration_reps, out_dir)

            # Wire athlete params for diagnosis engine
            if cal_athlete_params is not None:
                session_tracker.set_athlete_params(cal_athlete_params, cal_baseline)
                print(
                    f"  [DIAGNOSIS] Athlete params set: "
                    f"shoulder={cal_athlete_params['shoulder_width_m']:.3f}m "
                    f"femur={cal_athlete_params['femur_avg_m']:.3f}m "
                    f"tibia={cal_athlete_params['tibia_avg_m']:.3f}m"
                )
            else:
                print("  [DIAGNOSIS] Bone constraints not yet calibrated — diagnosis unavailable")

            # Reset pipeline for workout phase
            pipeline.reset_readiness_gate()
            gate_knee = tracker.standing_knee_flexion + 10.0
            pipeline._readiness_gate.max_knee_flexion_deg = gate_knee
            print(f"  [GATE] Standing knee threshold raised to {gate_knee:.1f}°")
            pipeline.rep_counter.reset()
            if pipeline._bilstm is not None:
                pipeline._bilstm.reset()

        except KeyboardInterrupt:
            print("\nCalibration stopped by user")
            cv2.destroyAllWindows()
            pipeline.release()
            ipc_client.disconnect()
            return

    # Main processing loop
    # Rest timer state
    resting = False
    rest_end_time = 0.0
    rest_total_seconds = 0.0
    workout_finished = False

    def _check_incoming_message():
        """Non-blocking check for messages from main.py."""
        return _poll_incoming_message(ipc_client)

    def _draw_rest_timer(frame, remaining_seconds, total_seconds=0.0):
        """Draw a centered rest countdown with a remaining-time progress arc."""
        h, w = frame.shape[:2]
        mins = int(remaining_seconds) // 60
        secs = int(remaining_seconds) % 60
        timer_text = f"{mins}:{secs:02d}" if mins > 0 else f"{secs}"

        # Semi-transparent dark navy overlay
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), HUD_PANEL, -1)
        cv2.addWeighted(overlay, 0.68, frame, 0.32, 0, frame)

        cx, cy = w // 2, h // 2
        ring_radius = min(160, h // 3)

        # Track ring + remaining-time arc (clockwise from 12 o'clock)
        cv2.circle(frame, (cx, cy), ring_radius, (70, 55, 45), 2, cv2.LINE_AA)
        if total_seconds > 0:
            frac = max(0.0, min(1.0, remaining_seconds / total_seconds))
            cv2.ellipse(
                frame, (cx, cy), (ring_radius, ring_radius),
                -90, 0, 360 * frac, HUD_CYAN, 4, cv2.LINE_AA,
            )

        label = " ".join("REST")
        (label_w, _), _ = cv2.getTextSize(label, HUD_FONT, 0.9, 1)
        cv2.putText(
            frame, label, (cx - label_w // 2, cy - ring_radius // 3),
            HUD_FONT, 0.9, (205, 195, 175), 1, cv2.LINE_AA,
        )

        (timer_w, timer_h), _ = cv2.getTextSize(timer_text, HUD_FONT, 3.0, 4)
        cv2.putText(
            frame, timer_text, (cx - timer_w // 2, cy + timer_h // 2 + ring_radius // 6),
            HUD_FONT, 3.0, HUD_INK, 4, cv2.LINE_AA,
        )

    def _draw_readiness_indicator(frame, is_ready, progress):
        """Draw a readiness gate status pill in the top-right corner."""
        if is_ready:
            _draw_hud_pill(frame, "COLLECTING", accent=HUD_CYAN)
        else:
            current, required = progress
            _draw_hud_pill(frame, f"WAITING {current}/{required}", accent=HUD_VIOLET)

    def _format_set_summary(summary):
        """Format a set summary dict into a context_str-style log line."""
        parts = [
            f"Set {summary['set_number']} complete: {summary['total_reps']} reps.",
            f"{summary['clean_reps']}/{summary['total_reps']} clean reps.",
        ]
        if summary["avg_depth"]:
            parts.append(f"Average depth: {summary['avg_depth']}°.")
        if summary["depth_consistency"]:
            parts.append(f"Depth consistency: {summary['depth_consistency']}°.")
        if summary["fault_summary"]:
            fault_lines = []
            for fault_type, stats in summary["fault_summary"].items():
                fault_lines.append(
                    f"{fault_type}: {stats['count']}x (avg severity {stats['avg_severity']})"
                )
            parts.append(f"Faults: {'; '.join(fault_lines)}.")
        return " ".join(parts)

    # --- Data collection for post-session plots ---
    plot_timestamps = []
    plot_hip_l = []
    plot_hip_r = []
    plot_vel_l = []
    plot_vel_r = []
    plot_rep_events = []

    # --- Per-set rich data collection ---
    set_collector = SetDataCollector()
    set_collector.thresholds = extract_thresholds_from_rule_engine(pipeline._rule_engine)
    set_plot_data = []
    completed_sets = 0

    try:
        while True:
            # Check for incoming messages (rest_start, etc.)
            incoming = _check_incoming_message()
            if incoming:
                if incoming.get("type") == "rest_start":
                    rest_seconds = incoming.get("rest_seconds", 30)
                    rest_end_time = time.time() + rest_seconds
                    rest_total_seconds = float(rest_seconds)
                    resting = True
                    pipeline.reset_readiness_gate()

                    # Finalize the just-completed set
                    if session_tracker.set_active:
                        session_tracker.force_end_set()
                        if session_tracker.last_set_summary:
                            print(f"[SET] {_format_set_summary(session_tracker.last_set_summary)}")
                    completed_sets += 1
                    if set_collector.has_enough_data():
                        print(f"\n  Generating set {completed_sets} plots...")
                        plot_result = finalize_set(set_collector, completed_sets, out_dir)
                        if plot_result is not None:
                            set_plot_data.append(plot_result)
                    else:
                        set_collector.reset()

                    print(f"[REST] Starting {rest_seconds}s rest timer")
                elif incoming.get("type") == "assessment_mode":
                    session_tracker.set_assessment_mode(incoming.get("enabled", False))
                    print(f"[PIPELINE] Assessment mode {'enabled' if incoming.get('enabled') else 'disabled'}")
                elif incoming.get("type") == "workout_complete":
                    workout_finished = True
                    print("[PIPELINE] Workout complete — stopping rep counting")

                    # Finalize the last set (no rest_start is sent for it)
                    if session_tracker.set_active:
                        session_tracker.force_end_set()
                        if session_tracker.last_set_summary:
                            print(f"[SET] {_format_set_summary(session_tracker.last_set_summary)}")
                    completed_sets += 1
                    if set_collector.has_enough_data():
                        print(f"\n  Generating set {completed_sets} plots...")
                        plot_result = finalize_set(set_collector, completed_sets, out_dir)
                        if plot_result is not None:
                            set_plot_data.append(plot_result)
                    else:
                        set_collector.reset()

                    # Generate session dashboard now while we can
                    if set_plot_data:
                        generate_session_dashboard(
                            set_plot_data, {"exercise": exercise_name},
                            out_dir, auto_open=False,
                        )

            result = pipeline.process_frame()

            # Collect data for post-session plots
            if result.joint_angles is not None:
                t = result.timestamp
                plot_timestamps.append(t)
                plot_hip_l.append(result.joint_angles.hip_flexion_l)
                plot_hip_r.append(result.joint_angles.hip_flexion_r)
                if len(plot_timestamps) >= 2:
                    dt = plot_timestamps[-1] - plot_timestamps[-2]
                    if dt > 0:
                        plot_vel_l.append((plot_hip_l[-1] - plot_hip_l[-2]) / dt)
                        plot_vel_r.append((plot_hip_r[-1] - plot_hip_r[-2]) / dt)
                    else:
                        plot_vel_l.append(0.0)
                        plot_vel_r.append(0.0)
                else:
                    plot_vel_l.append(0.0)
                    plot_vel_r.append(0.0)
                if result.rep_data is not None:
                    plot_rep_events.append((t, result.rep_data.rep_number))

            # Collect per-set rich data
            if pipeline.is_ready and result.skeleton_3d is not None and not resting and not workout_finished:
                set_collector.record_frame(result, result.skeleton_3d)

            if not resting and not workout_finished:
                # Normal mode: send biomechanics data
                bridge.send_frame_data(result)

                for fault in result.faults:
                    bridge.send_fault(fault)
                    set_collector.record_fault(fault)

                if result.rep_data:
                    bottom_kpts, bottom_angles = pipeline.consume_bottom_frame()
                    standing_kpts = pipeline.consume_standing_frame()
                    session_tracker.on_rep_complete(
                        result.rep_data,
                        bottom_kpts=bottom_kpts,
                        bottom_angles=bottom_angles,
                        standing_kpts=standing_kpts,
                    )

                if session_tracker.check_set_timeout(time.time()):
                    pipeline.reset_readiness_gate()
                    if session_tracker.last_set_summary:
                        print(f"[SET] {_format_set_summary(session_tracker.last_set_summary)}")

                    # Finalize the timed-out set
                    completed_sets += 1
                    if set_collector.has_enough_data():
                        print(f"\n  Generating set {completed_sets} plots...")
                        plot_result = finalize_set(set_collector, completed_sets, out_dir)
                        if plot_result is not None:
                            set_plot_data.append(plot_result)
                    else:
                        set_collector.reset()

            # Display video feed
            frame = pipeline.last_frame
            if frame is not None:
                display = frame.copy()
                if result.skeleton_2d is not None:
                    draw_skeleton(display, result.skeleton_2d)
                fps_counter.update()
                draw_fps(display, fps_counter.fps)

                # Readiness gate indicator (always visible)
                _draw_readiness_indicator(
                    display, pipeline.is_ready, pipeline._readiness_gate.progress,
                )

                if resting:
                    remaining = max(0.0, rest_end_time - time.time())
                    if remaining <= 0:
                        resting = False
                        ipc_client.send_message({"type": "rest_complete"})
                        print("[REST] Timer expired — sent rest_complete")
                    else:
                        _draw_rest_timer(display, remaining, rest_total_seconds)
                else:
                    # Show rep count overlay
                    rep_count = pipeline.rep_counter.rep_count
                    _draw_hud_pill(
                        display, f"REPS {rep_count}",
                        align="left", accent=HUD_CYAN, font_scale=1.1, y=48,
                    )
                _draw_wordmark(display)

                if not _window_animated:
                    animate_window_fullscreen(window_name)
                    _window_animated = True
                cv2.imshow(window_name, display)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print("\nStopped by user (pressed 'q')")
                    break

            # Throttle to target FPS
            total_ms = sum(result.latency_ms.values())
            target_ms = 1000.0 / config.target_fps
            if total_ms < target_ms:
                time.sleep((target_ms - total_ms) / 1000.0)

    except KeyboardInterrupt:
        print("\nPipeline stopped by user")
    except SystemExit:
        print("\nPipeline terminated by parent process")
    except Exception as e:
        print(f"\nPipeline error: {e}")
        ipc_client.send_message({"type": "error", "value": str(e)})
    finally:
        # Block further shutdown signals so the data saving below cannot be
        # interrupted by main.py's terminate() arriving mid-save.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        cv2.destroyAllWindows()
        pipeline.release()
        try:
            bridge.send_pipeline_status("stopped", {})
            ipc_client.disconnect()
        except Exception:
            pass
        print("Biomechanics pipeline stopped")

        # Finalize any in-progress set
        if set_collector.has_enough_data() and not resting:
            if session_tracker.set_active:
                session_tracker.force_end_set()
                if session_tracker.last_set_summary:
                    print(f"[SET] {_format_set_summary(session_tracker.last_set_summary)}")
            completed_sets += 1
            print(f"\n  Generating set {completed_sets} plots...")
            plot_result = finalize_set(set_collector, completed_sets, out_dir)
            if plot_result is not None:
                set_plot_data.append(plot_result)
        else:
            # End any active set and print its summary
            if session_tracker.set_active:
                session_tracker.force_end_set()
                if session_tracker.last_set_summary:
                    print(f"[SET] {_format_set_summary(session_tracker.last_set_summary)}")

        # Generate session dashboard
        if set_plot_data:
            generate_session_dashboard(
                set_plot_data, {"exercise": exercise_name},
                out_dir, auto_open=False,
            )

        # Generate post-session plots
        if len(plot_timestamps) > 10:
            print(f"\nGenerating plots from {len(plot_timestamps)} frames...")
            plot_data = {
                "timestamps": np.array(plot_timestamps),
                "hip_flexion_l": np.array(plot_hip_l),
                "hip_flexion_r": np.array(plot_hip_r),
                "hip_velocity_l": np.array(plot_vel_l),
                "hip_velocity_r": np.array(plot_vel_r),
                "rep_events": plot_rep_events,
            }
            print(f"Plots will be saved to: {out_dir}\n")
            plot_hip_position(plot_data, out_dir)
            plot_hip_velocity(plot_data, out_dir)
            print(f"\nAll plots saved in: {out_dir}")
        else:
            print("Not enough data for plots (need >10 frames with joint angles).")


if __name__ == "__main__":
    cam0 = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    cam1 = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    exercise = sys.argv[3] if len(sys.argv) > 3 else "Barbell Back Squat"

    # Parse optional args
    cal_file = None
    cal_mode = False
    cal_reps = 5
    preload_flag = False
    i = 4
    while i < len(sys.argv):
        if sys.argv[i] == "--calibration-file" and i + 1 < len(sys.argv):
            cal_file = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--calibration-mode":
            cal_mode = True
            i += 1
        elif sys.argv[i] == "--calibration-reps" and i + 1 < len(sys.argv):
            cal_reps = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--preload":
            preload_flag = True
            i += 1
        else:
            i += 1

    run_biomechanics_pipeline(
        cam0_id=cam0,
        cam1_id=cam1,
        exercise_name=exercise,
        calibration_file=cal_file,
        calibration_mode=cal_mode,
        calibration_reps=cal_reps,
        preload=preload_flag,
    )
