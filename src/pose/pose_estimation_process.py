"""
Biomechanics Pipeline Process

Replaces the old pose_estimation_process.py with the full layered pipeline.
Launched as a subprocess by main.py when workout mode starts.
Communicates with the voice agent via the existing IPC system.
"""

import select
import sys
import os
import time
from pathlib import Path

# Add src/ to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2

from core.ipc_communication import IPCClient, _recv_framed
from biomechanics.pipeline import BiomechanicsPipeline
from biomechanics.coaching.ipc_bridge import IPCBridge
from biomechanics.coaching.session_tracker import SessionTracker
from biomechanics.config import load_pipeline_config
from biomechanics.viz import draw_skeleton, draw_fps, FPSCounter


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

    try:
        while True:
            # Check for incoming messages (rest_start, etc.)
            incoming = _check_incoming_message()
            if incoming:
                if incoming.get("type") == "rest_start":
                    rest_seconds = incoming.get("rest_seconds", 30)
                    rest_end_time = time.time() + rest_seconds
                    resting = True
                    print(f"[REST] Starting {rest_seconds}s rest timer")

            result = pipeline.process_frame()

            if not resting:
                # Normal mode: send biomechanics data
                bridge.send_frame_data(result)

                for fault in result.faults:
                    bridge.send_fault(fault)

                if result.rep_data:
                    session_tracker.on_rep_complete(result.rep_data)

                session_tracker.check_set_timeout(time.time())

            # Display video feed
            frame = pipeline.last_frame
            if frame is not None:
                display = frame.copy()
                if result.skeleton_2d is not None:
                    draw_skeleton(display, result.skeleton_2d)
                fps_counter.update()
                draw_fps(display, fps_counter.fps)

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


if __name__ == "__main__":
    cam0 = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    cam1 = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    exercise = sys.argv[3] if len(sys.argv) > 3 else "Barbell Back Squat"

    run_biomechanics_pipeline(cam0_id=cam0, cam1_id=cam1, exercise_name=exercise)
