"""
Biomechanics Pipeline Process

Replaces the old pose_estimation_process.py with the full layered pipeline.
Launched as a subprocess by main.py when workout mode starts.
Communicates with the voice agent via the existing IPC system.
"""

import logging
import select
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
from biomechanics.coaching.ipc_bridge import IPCBridge
from biomechanics.coaching.session_tracker import SessionTracker
from biomechanics.config import load_pipeline_config
from biomechanics.viz import draw_skeleton, draw_fps, FPSCounter
from biomechanics.viz.set_plots import plot_hip_position, plot_hip_velocity, make_output_dir
from biomechanics.analysis.set_finalizer import SetDataCollector, finalize_set
from biomechanics.viz.html_dashboard import generate_session_dashboard


# Ensure gate diagnostics are visible on stderr
logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")


def run_biomechanics_pipeline(
    cam0_id: int = 0,
    cam1_id: int = 1,
    config_path: str = None,
    exercise_name: str = "Barbell Back Squat",
):
    """
    Run the full biomechanics pipeline as a subprocess.

    This is called by main.py when workout mode starts.
    Connects to the existing IPC server and sends real-time
    coaching data to the voice agent.
    """
    print("\n=== Biomechanics Pipeline Starting ===")

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
        pipeline = BiomechanicsPipeline(config)
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

    # Main processing loop
    fps_counter = FPSCounter()
    window_name = f"Nowva — {exercise_name}"

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
    set_plot_data = []
    completed_sets = 0
    out_dir = make_output_dir()

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

                if result.rep_data:
                    session_tracker.on_rep_complete(result.rep_data)

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

    run_biomechanics_pipeline(cam0_id=cam0, cam1_id=cam1, exercise_name=exercise)
