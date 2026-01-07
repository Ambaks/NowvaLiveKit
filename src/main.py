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

from core.session_manager import SessionManager
from core.ipc_communication import IPCServer
from core.session_logger import SessionLogger
from db import init_db, get_db
from db.models import User
from agents.console_launcher import run_console_voice_onboarding
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
        self.pose_process = None
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
                self.state.save_state()
                print("[SIGNAL] State reset to main_menu")
            except Exception as e:
                print(f"[SIGNAL] Error resetting state: {e}")
        # Re-raise to allow normal shutdown
        raise KeyboardInterrupt

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

    def start_pose_estimation(self, cam0_id: int = 0, cam1_id: int = 1):
        """
        Start pose estimation process

        Args:
            cam0_id: First camera ID
            cam1_id: Second camera ID
        """
        print("\nStarting pose estimation process...")

        # Start pose estimation as subprocess
        pose_script = Path(__file__).parent / 'pose' / 'pose_estimation_process.py'

        self.pose_process = subprocess.Popen(
            [sys.executable, str(pose_script), str(cam0_id), str(cam1_id)],
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

        # Initialize database
        print("\nInitializing database...")
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
            from core.agent_state import AgentState
            self.state = AgentState(user_id=self.current_user['user_id'])

            # ALWAYS reset to main_menu mode on startup for safety
            # (prevents "ready to squat" if app crashed during workout)
            current_mode = self.state.get_mode()
            print(f"[STATE] Previous mode was '{current_mode}' - resetting to main_menu for safety")
            self.state.switch_mode("main_menu")
            self.state.set("workout.active", False)
            self.state.save_state()

            # Small delay to ensure state file is written before voice agent loads it
            await asyncio.sleep(0.5)

            # Start voice agent for returning user
            from agents.console_launcher import run_console_voice_agent
            voice_agent_process = await run_console_voice_agent(user_id=self.current_user['user_id'])

        else:
            # Run onboarding - returns (success, agent_process)
            success, voice_agent_process = await self.run_onboarding()

            if not success:
                print("Onboarding failed. Exiting.")
                return

            # Load state for new user
            from core.agent_state import AgentState
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

                # Detect mode changes
                if current_mode != last_mode:
                    print(f"\n[STATE CHANGE] {last_mode} → {current_mode}")
                    self.session_logger.log_system_event("mode_change", {
                        "from_mode": last_mode,
                        "to_mode": current_mode
                    })
                    last_mode = current_mode

                # Handle workout mode
                if current_mode == "workout" and not pose_running:
                    print("\n" + "="*50)
                    print("STARTING WORKOUT SESSION")
                    print("="*50)

                    # Start IPC server for pose estimation communication
                    if not self.ipc_server:
                        print("[IPC] Starting IPC server...")

                        def ipc_message_handler(message: dict):
                            """Handle messages from pose estimation"""
                            msg_type = message.get('type')

                            if msg_type == 'rep_count':
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

                        ipc_thread = self.start_ipc_server()
                        self.ipc_server.message_callback = ipc_message_handler
                        await asyncio.sleep(1)
                        print("[IPC] Server ready")

                    self.start_pose_estimation()
                    pose_running = True
                    print("[POSE] Pose estimation started")

                elif current_mode != "workout" and pose_running:
                    print("\n" + "="*50)
                    print("ENDING WORKOUT SESSION")
                    print("="*50)
                    if self.pose_process:
                        self.pose_process.terminate()
                        self.pose_process.wait()
                    pose_running = False
                    print("[POSE] Pose estimation stopped")

                # Sleep briefly to avoid busy loop
                await asyncio.sleep(0.1)

        except KeyboardInterrupt:
            print("\n\n" + "="*50)
            print("SHUTTING DOWN")
            print("="*50)

        # Cleanup
        print("\nCleaning up...")

        # Reset state to main_menu before shutdown for safety
        if self.state:
            print("Resetting state to main_menu...")
            self.state.switch_mode("main_menu")
            self.state.set("workout.active", False)
            self.state.save_state()

        if voice_agent_process:
            print("Stopping voice agent...")
            voice_agent_process.terminate()
            voice_agent_process.wait()

        if pose_running and self.pose_process:
            print("Stopping pose estimation...")
            self.pose_process.terminate()
            self.pose_process.wait()

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
    app = NowvaApp()
    await app.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nApplication interrupted by user. Exiting.")
