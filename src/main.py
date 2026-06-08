#!/usr/bin/env python3
"""
Nowva Main Application
Orchestrates voice agent and pose estimation with IPC communication
"""

import asyncio
import os
import sys
import signal
import threading
import subprocess
import logging
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from agent.core.session_manager import SessionManager
from agent.core.ipc_communication import IPCServer
from agent.core.session_logger import SessionLogger
from db import init_db, get_db
from db.models import User
from agent.agents.console_launcher import run_console_voice_onboarding, terminate_process_group
from auth.user_management import create_user_account
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Suppress SQLAlchemy INFO logs
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)


class NowvaApp:
    """Main Nowva application orchestrator"""

    def __init__(self):
        self.session_manager = SessionManager()
        self.session_logger = SessionLogger.get_instance()
        self.ipc_server = None
        self.coaching_ipc = None  # Second IPC server for forwarding to voice agent
        self.pose_process = None
        self.fastapi_process = None
        self.current_user = None
        self.state = None  # Track state for cleanup

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals by resetting state"""
        print("\n[SIGNAL] Received shutdown signal - cleaning up state...")
        if self.state:
            try:
                self.state.switch_mode("main_menu")
                self.state.set("workout.active", False)
                self.state.set("shutdown_requested", False)
                self.state.save_state()
                print("[SIGNAL] State reset to main_menu")
            except Exception as e:
                print(f"[SIGNAL] Error resetting state: {e}")
        # Re-raise to allow normal shutdown
        raise KeyboardInterrupt

    def _start_fastapi_server(self):
        """Start the FastAPI backend server as a subprocess."""
        project_root = str(Path(__file__).parent.parent)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).parent)
        env["DYLD_FALLBACK_LIBRARY_PATH"] = f"/opt/homebrew/lib:{env.get('DYLD_FALLBACK_LIBRARY_PATH', '')}"

        self.fastapi_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api.main:app", "--port", "8000"],
            cwd=project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        print(f"[FASTAPI] Server started (PID: {self.fastapi_process.pid})")

    def check_session(self):
        """Check if user has an existing session"""
        return self.session_manager.session_exists()

    def load_user_from_session(self):
        """Load user from existing session"""
        session = self.session_manager.load_session()
        if not session:
            return None

        user_id = session.get('user_id')
        username = session.get('username')

        return {
            'user_id': user_id,
            'username': username,
            'email': session.get('email')
        }

    def create_user(self, first_name: str, email: str):
        """
        Create new user in database using auth system

        Args:
            first_name: User's first name
            email: User's email

        Returns:
            tuple of (user_id, username) if successful, (None, None) otherwise
        """
        try:
            # Use the auth system's create_user_account which handles:
            # - Duplicate checking
            # - Username generation
            # - Password creation
            user, username = create_user_account(first_name, email)

            if user:
                print(f"User account ready: {username} (ID: {user.id})")
                return user.id, username

            return None, None

        except Exception as e:
            print(f"Error creating user: {e}")
            return None, None

    def start_ipc_server(self):
        """Start IPC server in a separate thread"""
        def ipc_message_handler(message: dict):
            """Handle messages from pose estimation process"""
            msg_type = message.get('type')
            value = message.get('value')

            if msg_type == 'rep_count':
                print(f"[IPC] Rep count: {value}")
            elif msg_type == 'feedback':
                print(f"[IPC] Form feedback: {value}")
            elif msg_type == 'status':
                print(f"[IPC] Status: {value}")
            elif msg_type == 'error':
                print(f"[IPC] Error: {value}")

        # Initialize IPC server
        self.ipc_server = IPCServer()

        def run_server():
            self.ipc_server.start(message_callback=ipc_message_handler)
            self.ipc_server.listen()

        # Start server in thread
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        print("IPC Server started in background thread")

        return server_thread

    def start_pose_estimation(self, cam0_id: int = 0, cam1_id: int = 1,
                              exercise_name: str = "Barbell Back Squat",
                              calibration_file: str = None,
                              calibration_mode: bool = False):
        """
        Start pose estimation process

        Args:
            cam0_id: First camera ID
            cam1_id: Second camera ID
            exercise_name: Name of the exercise for coaching cues
            calibration_file: Path to existing calibration JSON (if returning user)
            calibration_mode: If True, run calibration phase before workout
        """
        print("\nStarting pose estimation process...")

        # Start pose estimation as subprocess
        pose_script = Path(__file__).parent / 'biomechanics' / 'pipeline_process.py'

        cmd = [sys.executable, str(pose_script), str(cam0_id), str(cam1_id), exercise_name]
        if calibration_file:
            cmd.extend(["--calibration-file", calibration_file])
        if calibration_mode:
            cmd.append("--calibration-mode")

        self.pose_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Print pose process output
        def print_output():
            for line in self.pose_process.stdout:
                print(f"[Pose] {line.strip()}")

        output_thread = threading.Thread(target=print_output, daemon=True)
        output_thread.start()

        print("Pose estimation process started")

    async def run_onboarding(self):
        """
        Run voice-based onboarding flow

        Returns:
            Tuple of (success: bool, agent_process: subprocess.Popen or None)
        """
        print("\n" + "="*50)
        print("VOICE ONBOARDING")
        print("="*50)
        print("\nStarting voice-based onboarding...")
        print("The voice agent will:")
        print("1. Welcome you to Nowva")
        print("2. Explain the product")
        print("3. Ask for your name")
        print("4. Ask for your email")
        print("5. Confirm your information")
        print("6. Transition to main menu\n")

        # Run voice onboarding - returns (first_name, email, process)
        result = await run_console_voice_onboarding()

        if not result:
            print("\nVoice onboarding failed. Exiting.")
            return (False, None)

        first_name, email, agent_process = result

        # Note: User is already created by voice_agent
        # We just need to retrieve the user from the database and save the session
        # The first_name from onboarding is the user's first name
        # We need to get the actual username from the database
        try:
            from db import get_db
            from db.models import User

            db = next(get_db())
            user = db.query(User).filter(User.email == email).first()

            if not user:
                print("Failed to retrieve user after onboarding")
                return (False, agent_process)

            user_id = str(user.id)
            actual_username = user.username

        except Exception as e:
            print(f"Error retrieving user: {e}")
            return (False, agent_process)

        # Save session
        if self.session_manager.save_session(user_id, actual_username, email):
            self.current_user = {
                'user_id': user_id,
                'username': actual_username,
                'email': email
            }
            print(f"\n✓ Onboarding complete! Agent continuing in main menu mode...")
            return (True, agent_process)

        return (False, agent_process)


    async def run(self):
        """Main application loop with voice agent coordination"""
        # Start session logging
        self.session_logger.start_session()
        self.session_logger.log_system_event("app_started")

        print("\n" + "="*60)
        print("NOWVA - AI-Powered Smart Squat Rack")
        print("="*60)

        # Start FastAPI backend server
        print("\nStarting FastAPI backend...")
        self._start_fastapi_server()

        # Initialize database (skips if tables already exist)
        init_db()

        voice_agent_process = None

        # Check for existing session
        if self.check_session():
            self.current_user = self.load_user_from_session()
            print("\n" + "="*50)
            print("RETURNING USER")
            print("="*50)
            print(f"\nWelcome back, {self.current_user['username']}!")
            print("\nStarting voice agent in main menu mode...\n")

            # Load existing user's state
            from agent.core.agent_state import AgentState
            self.state = AgentState(user_id=self.current_user['user_id'])

            # ALWAYS reset to main_menu mode on startup for safety
            # (prevents "ready to squat" if app crashed during workout)
            current_mode = self.state.get_mode()
            print(f"[STATE] Previous mode was '{current_mode}' - resetting to main_menu for safety")
            self.state.switch_mode("main_menu")
            self.state.set("workout.active", False)
            self.state.set("workout.greeting_done", False)
            self.state.set("shutdown_requested", False)
            self.state.save_state()

            # Small delay to ensure state file is written before voice agent loads it
            await asyncio.sleep(0.5)

            # Start voice agent for returning user
            from agent.agents.console_launcher import run_console_voice_agent
            voice_agent_process = await run_console_voice_agent(user_id=self.current_user['user_id'])

        else:
            # Run onboarding - returns (success, agent_process)
            success, voice_agent_process = await self.run_onboarding()

            if not success:
                print("Onboarding failed. Exiting.")
                return

            # Load state for new user
            from agent.core.agent_state import AgentState
            self.state = AgentState(user_id=self.current_user['user_id'])

        if not voice_agent_process:
            print("Error: Voice agent failed to start. Exiting.")
            return

        print("\n" + "="*50)
        print("SYSTEM READY")
        print("="*50)
        print("\nVoice agent is running and listening...")
        print("Speak to Nova to interact!")
        print("\nMonitoring for state changes...")
        print("Press Ctrl+C to exit.\n")

        # Main monitoring loop - watches state and controls pose estimation
        # Synchronously monitors voice agent output on main thread
        pose_running = False
        last_mode = self.state.get_mode()

        # Set stdout to line-buffered mode for immediate output
        import sys
        sys.stdout.flush()

        try:
            while True:
                # Check if voice agent is still running
                if voice_agent_process.poll() is not None:
                    print("\n[SYSTEM] Voice agent terminated")
                    break

                # Synchronously read voice agent output (main thread, blocking with short timeout)
                # This uses select for Unix-like systems
                try:
                    import select
                    if voice_agent_process.stdout:
                        # Wait up to 50ms for data to be available
                        ready, _, _ = select.select([voice_agent_process.stdout], [], [], 0.05)
                        if ready:
                            # Data is available, read one line
                            line = voice_agent_process.stdout.readline()
                            if line:
                                print(line, end='')
                                sys.stdout.flush()
                except Exception as e:
                    # select() might not work on all platforms, continue anyway
                    pass

                # Reload state to check for changes
                self.state.reload_state()
                current_mode = self.state.get_mode()

                # Check for graceful shutdown request from voice agent
                if self.state.get("shutdown_requested", False):
                    print("\n[SYSTEM] Shutdown requested by user via voice agent")
                    self.session_logger.log_system_event("shutdown_requested")
                    # Wait for goodbye speech to finish playing
                    await asyncio.sleep(5)
                    break

                # Detect mode changes
                if current_mode != last_mode:
                    print(f"\n[STATE CHANGE] {last_mode} → {current_mode}")
                    self.session_logger.log_system_event("mode_change", {
                        "from_mode": last_mode,
                        "to_mode": current_mode
                    })
                    last_mode = current_mode

                # Handle workout mode — only start if workout session is fully configured
                # (workout.current_session is set by confirm_quick_exercise/start_workout)
                has_workout_session = self.state.get("workout.current_session") is not None
                if current_mode == "workout" and not pose_running and has_workout_session:
                    # Start IPC servers immediately so the voice agent's
                    # CoachingService can connect while the greeting plays.
                    # Only the pose estimation (camera window) waits for
                    # greeting_done to avoid interrupting speech.

                    # Start coaching IPC server for forwarding messages to voice agent
                    if not self.coaching_ipc:
                        print("[COACHING IPC] Starting coaching IPC server...")
                        self.coaching_ipc = IPCServer(socket_path="/tmp/nowva_coaching.sock")

                        def coaching_message_handler(message: dict):
                            """Handle messages FROM voice agent (reverse direction)."""
                            msg_type = message.get("type")
                            if msg_type == "rest_start":
                                rest_sec = message.get("rest_seconds", 30)
                                print(f"[COACHING IPC] Received rest_start ({rest_sec}s) from voice agent")
                                if self.ipc_server and self.ipc_server.client_socket:
                                    try:
                                        self.ipc_server.send_message(message)
                                        print(f"[REST] Forwarded rest_start to pose process")
                                    except Exception as e:
                                        print(f"[REST] Failed to forward to pose process: {e}")
                            elif msg_type == "workout_complete":
                                print("[COACHING IPC] Received workout_complete from voice agent")
                                if self.ipc_server and self.ipc_server.client_socket:
                                    try:
                                        self.ipc_server.send_message(message)
                                        print("[COACHING IPC] Forwarded workout_complete to pose process")
                                    except Exception as e:
                                        print(f"[COACHING IPC] Failed to forward workout_complete: {e}")

                        def run_coaching_server():
                            self.coaching_ipc.start(message_callback=coaching_message_handler)
                            self.coaching_ipc.listen()

                        coaching_thread = threading.Thread(target=run_coaching_server, daemon=True)
                        coaching_thread.start()
                        print("[COACHING IPC] Waiting for voice agent to connect...")

                    # Start IPC server for pose estimation communication
                    if not self.ipc_server:
                        print("[IPC] Starting IPC server...")

                        def ipc_message_handler(message: dict):
                            """Handle messages from pose estimation / biomechanics pipeline"""
                            msg_type = message.get('type')

                            # --- New biomechanics message types ---
                            if msg_type == 'rep_complete':
                                rep_num = message.get('rep_number')
                                depth = message.get('depth_category', '')
                                print(f"[BIOMECH] Rep {rep_num} complete — {depth}")
                            elif msg_type == 'fault':
                                print(f"[BIOMECH] Fault: {message.get('fault_type')} ({message.get('severity')})")
                            elif msg_type == 'set_complete':
                                print(f"[BIOMECH] Set {message.get('set_number')} complete — {message.get('total_reps')} reps")
                            elif msg_type == 'cache_cues':
                                cues = message.get('cues', {})
                                print(f"[BIOMECH] Caching {len(cues)} audio cues for {message.get('exercise_name')}")
                            elif msg_type == 'play_cue':
                                print(f"[BIOMECH] Play cue: {message.get('cue')}")
                            elif msg_type == 'rest_complete':
                                print("[BIOMECH] Rest timer expired")
                            elif msg_type == 'calibration_rep':
                                rep = message.get('rep_number', 0)
                                total = message.get('total_required', 5)
                                print(f"[BIOMECH] Calibration rep {rep}/{total}")
                            elif msg_type == 'calibration_complete':
                                print(f"[BIOMECH] Calibration complete for {message.get('movement_pattern')}")
                            elif msg_type == 'diagnosis_complete':
                                print(f"[BIOMECH] Diagnosis complete — confidence={message.get('diagnosis', {}).get('confidence', 0):.2f}")
                            elif msg_type == 'assessment_rep':
                                rep = message.get('rep_number', 0)
                                total = message.get('total_required', 2)
                                print(f"[BIOMECH] Assessment rep {rep}/{total} (round {message.get('round', 1)})")
                            elif msg_type == 'assessment_result':
                                passed = message.get('passed', False)
                                print(f"[BIOMECH] Assessment result: {'PASSED' if passed else 'NEEDS CORRECTION'} (round {message.get('round', 1)})")
                            elif msg_type == 'pipeline_status':
                                print(f"[BIOMECH] Pipeline: {message.get('status')}")
                            # --- Legacy / backward-compatible types ---
                            elif msg_type == 'rep_count':
                                value = message.get('value')
                                print(f"[IPC] Rep count: {value}")
                            elif msg_type == 'feedback':
                                value = message.get('value')
                                print(f"[IPC] Form feedback: {value}")
                            elif msg_type == 'status':
                                value = message.get('value')
                                print(f"[IPC] Status: {value}")
                            elif msg_type == 'error':
                                value = message.get('value')
                                print(f"[IPC] Error: {value}")

                            # Forward coaching-relevant messages to voice agent
                            if msg_type in ('cache_cues', 'fault', 'rep_complete', 'rest_complete', 'frame_data', 'calibration_rep', 'calibration_complete', 'diagnosis_complete', 'assessment_result', 'assessment_rep'):
                                if self.coaching_ipc and self.coaching_ipc.client_socket:
                                    try:
                                        self.coaching_ipc.send_message(message)
                                    except Exception as e:
                                        print(f"[COACHING IPC] Forward failed: {e}")
                                else:
                                    print(f"[COACHING IPC] No voice agent connected — dropping {msg_type}")

                        # Create IPC server directly with the correct handler
                        # (avoids race condition with start_ipc_server's old handler)
                        self.ipc_server = IPCServer()

                        def run_server():
                            self.ipc_server.start(message_callback=ipc_message_handler)
                            self.ipc_server.listen()

                        ipc_thread = threading.Thread(target=run_server, daemon=True)
                        ipc_thread.start()
                        await asyncio.sleep(1)
                        print("[IPC] Server ready")

                    # Wait for greeting to finish before opening camera window
                    # (window popup can cancel TTS speech on some platforms)
                    if not self.state.get("workout.greeting_done", False):
                        continue

                    print("\n" + "="*50)
                    print("STARTING WORKOUT SESSION")
                    print("="*50)

                    if getattr(self, 'simulate_mode', False):
                        print("[SIMULATE] Skipping real pose estimation — use simulate_squat_workout.py")
                    else:
                        # Read exercise name from state (set by voice agent)
                        exercise_name = self.state.get("workout.exercise_name", "Barbell Back Squat")
                        if not exercise_name:
                            session_data = self.state.get("workout.current_session")
                            if session_data and session_data.get("exercises"):
                                exercise_name = session_data["exercises"][0].get("exercise_name", "Barbell Back Squat")
                            else:
                                exercise_name = "Barbell Back Squat"

                        # Check for calibration state
                        cal_mode = bool(self.state.get("calibration.active"))
                        cal_file = None
                        cal_profile = self.state.get("workout.calibration_profile")
                        if cal_profile and not cal_mode:
                            # Write calibration profile to temp file for pipeline
                            import json, tempfile
                            cal_file = os.path.join(tempfile.gettempdir(), f"nowva_cal_{id(self)}.json")
                            with open(cal_file, "w") as f:
                                json.dump(cal_profile, f)
                            print(f"[CALIBRATION] Wrote calibration profile to {cal_file}")

                        self.start_pose_estimation(
                            exercise_name=exercise_name,
                            calibration_file=cal_file,
                            calibration_mode=cal_mode,
                        )
                    pose_running = True
                    print("[POSE] Pose estimation started" if not getattr(self, 'simulate_mode', False) else "[SIMULATE] IPC servers ready — waiting for simulator")

                elif current_mode != "workout" and pose_running:
                    print("\n" + "="*50)
                    print("ENDING WORKOUT SESSION")
                    print("="*50)
                    if self.pose_process:
                        self.pose_process.terminate()
                        self.pose_process.wait()
                    if self.coaching_ipc:
                        self.coaching_ipc.stop()
                        self.coaching_ipc = None
                        print("[COACHING IPC] Stopped")
                    if self.ipc_server:
                        self.ipc_server.stop()
                        self.ipc_server = None
                        print("[IPC] Server stopped")
                    pose_running = False
                    print("[POSE] Pose estimation stopped")

                # Sleep briefly to avoid busy loop
                await asyncio.sleep(0.1)

        except KeyboardInterrupt:
            print("\n\n" + "="*50)
            print("SHUTTING DOWN")
            print("="*50)

        # Ignore further signals during cleanup so it can't be interrupted
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)

        # Cleanup
        print("\nCleaning up...")

        # Reset state to main_menu before shutdown for safety
        if self.state:
            print("Resetting state to main_menu...")
            self.state.switch_mode("main_menu")
            self.state.set("workout.active", False)
            self.state.set("shutdown_requested", False)
            self.state.save_state()

        if voice_agent_process:
            print("Stopping voice agent...")
            terminate_process_group(voice_agent_process)

        if pose_running and self.pose_process:
            print("Stopping pose estimation...")
            self.pose_process.terminate()
            self.pose_process.wait()

        if self.coaching_ipc:
            print("Stopping coaching IPC server...")
            self.coaching_ipc.stop()

        if self.fastapi_process:
            print("Stopping FastAPI server...")
            self.fastapi_process.terminate()
            self.fastapi_process.wait()

        if self.ipc_server:
            print("Stopping IPC server...")
            self.ipc_server.stop()

        # End session and generate summary
        self.session_logger.log_system_event("app_shutdown")
        summary = self.session_logger.end_session()

        # Print summary
        print("\n" + summary)
        print(f"\nSession log saved to: {self.session_logger.get_log_path()}")

        print("\nGoodbye!")


async def main():
    """Entry point"""
    import argparse
    parser = argparse.ArgumentParser(description="Nowva Main Application")
    parser.add_argument("--simulate", action="store_true",
                        help="Skip real pose estimation (use simulate_squat_workout.py instead)")
    args = parser.parse_args()

    app = NowvaApp()
    app.simulate_mode = args.simulate
    await app.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nApplication interrupted by user. Exiting.")
