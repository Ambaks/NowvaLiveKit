"""
Biomechanics Pipeline Process

Replaces the old pose_estimation_process.py with the full layered pipeline.
Launched as a subprocess by main.py when workout mode starts.
Communicates with the voice agent via the existing IPC system.
"""

import json
import logging
import select
import signal
import sys
import os
import time
from pathlib import Path

# Add src/ to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np

from core.ipc_communication import IPCClient, _recv_framed
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
from biomechanics.viz import draw_skeleton, draw_fps, FPSCounter
from biomechanics.viz.set_plots import plot_hip_position, plot_hip_velocity, make_output_dir
from biomechanics.analysis.set_finalizer import SetDataCollector, finalize_set
from biomechanics.viz.html_dashboard import generate_session_dashboard


# Ensure gate diagnostics are visible on stderr
logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")


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


def run_biomechanics_pipeline(
    cam0_id: int = 0,
    cam1_id: int = 1,
    config_path: str = None,
    exercise_name: str = "Barbell Back Squat",
    calibration_file: str = None,
    calibration_mode: bool = False,
    calibration_reps: int = 5,
):
    """
    Run the full biomechanics pipeline as a subprocess.

    This is called by main.py when workout mode starts.
    Connects to the existing IPC server and sends real-time
    coaching data to the voice agent.

    Args:
        calibration_file: Path to existing calibration JSON to load at startup.
        calibration_mode: If True, run a calibration phase before the workout loop.
        calibration_reps: Number of calibration reps to collect (default 5).
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
        pipeline = BiomechanicsPipeline(config, exercise_name=exercise_name)
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
    out_dir = make_output_dir()

    # --- Apply existing calibration if provided ---
    if calibration_file and os.path.exists(calibration_file):
        try:
            with open(calibration_file, "r") as f:
                cal_profile = json.load(f)
            apply_calibration_to_rule_engine(pipeline._rule_engine, cal_profile)
            print(f"[CALIBRATION] Loaded calibration from {calibration_file}")
        except Exception as e:
            print(f"[CALIBRATION] Failed to load calibration file: {e}")

    # --- Calibration phase (if no existing calibration) ---
    if calibration_mode:
        print(f"\n{'='*60}")
        print(f"  CALIBRATION PHASE ({calibration_reps} bodyweight squats)")
        print(f"{'='*60}\n")

        tracker = CalibrationTracker(target_reps=calibration_reps)
        cal_set_collector = SetDataCollector()
        movement_pattern = get_movement_pattern(exercise_name) or "squat"

        try:
            while not tracker.is_complete:
                result = pipeline.process_frame()

                if pipeline.is_ready and result.skeleton_3d is not None:
                    cal_set_collector.record_frame(result, result.skeleton_3d)

                    if result.joint_angles is not None:
                        tracker.record_frame(result.joint_angles)

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

                    h, w = display.shape[:2]
                    if pipeline.is_ready:
                        text = f"CALIBRATING  Rep {tracker.reps_completed}/{calibration_reps}"
                        color = (0, 200, 255)
                    else:
                        current, required = pipeline._readiness_gate.progress
                        text = f"WAITING {current}/{required}"
                        color = (0, 200, 255)

                    ts = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
                    x = w - ts[0] - 15
                    cv2.rectangle(display, (x - 5, 5), (x + ts[0] + 5, 35), (0, 0, 0), -1)
                    cv2.putText(display, text, (x, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

                    cv2.putText(
                        display, f"CALIBRATION  {tracker.reps_completed}/{calibration_reps}",
                        (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 200, 255), 3,
                    )

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

            # Send calibration results to voice agent
            ipc_client.send_message({
                "type": "calibration_complete",
                "movement_pattern": movement_pattern,
                "peaks": peaks,
                "thresholds": {k: v for k, v in cal_profile.items() if k != "defaults"},
            })

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
    workout_finished = False

    def _check_incoming_message():
        """Non-blocking check for messages from main.py."""
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

    def _draw_rest_timer(frame, remaining_seconds):
        """Draw a centered rest countdown timer on the video frame."""
        h, w = frame.shape[:2]
        mins = int(remaining_seconds) // 60
        secs = int(remaining_seconds) % 60
        timer_text = f"{mins}:{secs:02d}" if mins > 0 else f"{secs}"

        # Semi-transparent dark overlay
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

        # "REST" label
        label = "REST"
        label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 2.0, 4)[0]
        label_x = (w - label_size[0]) // 2
        cv2.putText(
            frame, label, (label_x, h // 2 - 50),
            cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 4,
        )

        # Countdown number
        timer_size = cv2.getTextSize(timer_text, cv2.FONT_HERSHEY_SIMPLEX, 4.0, 6)[0]
        timer_x = (w - timer_size[0]) // 2
        cv2.putText(
            frame, timer_text, (timer_x, h // 2 + 80),
            cv2.FONT_HERSHEY_SIMPLEX, 4.0, (0, 255, 0), 6,
        )

    def _draw_readiness_indicator(frame, is_ready, progress):
        """Draw a readiness gate status indicator in the top-right corner."""
        h, w = frame.shape[:2]
        if is_ready:
            text = "COLLECTING"
            color = (0, 255, 0)  # green
        else:
            current, required = progress
            text = f"WAITING {current}/{required}"
            color = (0, 200, 255)  # yellow

        text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
        x = w - text_size[0] - 15
        y = 30

        # Background for readability
        cv2.rectangle(
            frame, (x - 5, y - text_size[1] - 5), (x + text_size[0] + 5, y + 5),
            (0, 0, 0), -1,
        )
        cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

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
                    session_tracker.on_rep_complete(
                        result.rep_data,
                        bottom_kpts=bottom_kpts,
                        bottom_angles=bottom_angles,
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
                        _draw_rest_timer(display, remaining)
                else:
                    # Show rep count overlay
                    rep_count = pipeline.rep_counter.rep_count
                    cv2.putText(
                        display, f"Reps: {rep_count}", (20, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3,
                    )

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
        cv2.destroyAllWindows()
        pipeline.release()
        bridge.send_pipeline_status("stopped", {})
        ipc_client.disconnect()
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

    # Parse optional calibration args
    cal_file = None
    cal_mode = False
    cal_reps = 5
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
        else:
            i += 1

    run_biomechanics_pipeline(
        cam0_id=cam0,
        cam1_id=cam1,
        exercise_name=exercise,
        calibration_file=cal_file,
        calibration_mode=cal_mode,
        calibration_reps=cal_reps,
    )
