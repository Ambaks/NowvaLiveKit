#!/usr/bin/env python3
"""
Nowva Main Application
Orchestrates voice agent and pose estimation with IPC communication
"""

import asyncio
import os
import sys
import threading
import subprocess
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from session_manager import SessionManager
from ipc_communication import IPCServer
from db import init_db, get_db
from db.models import User
from console_voice_onboarding import run_console_voice_onboarding
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class NowvaApp:
    """Main Nowva application orchestrator"""

    def __init__(self):
        self.session_manager = SessionManager()
        self.ipc_server = None
        self.pose_process = None
        self.current_user = None

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

        print(f"\nWelcome back, {username}!")
        return {
            'user_id': user_id,
            'username': username,
            'email': session.get('email')
        }

    def create_user(self, username: str, email: str):
        """
        Create new user in database

        Args:
            username: User's username
            email: User's email

        Returns:
            user_id if successful, None otherwise
        """
        try:
            db = next(get_db())

            # Check if user already exists
            existing_user = db.query(User).filter(
                (User.username == username) | (User.email == email)
            ).first()

            if existing_user:
                print(f"User with username '{username}' or email '{email}' already exists")
                return existing_user.id

            # Create new user
            new_user = User(username=username, email=email)
            db.add(new_user)
            db.commit()
            db.refresh(new_user)

            print(f"Created new user: {username} (ID: {new_user.id})")
            return new_user.id

        except Exception as e:
            print(f"Error creating user: {e}")
            return None

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
        pose_script = Path(__file__).parent / 'pose_estimation_process.py'

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
            True if successful, False otherwise
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
        print("\nYou can also use text onboarding by pressing Ctrl+C\n")

        try:
            # Run voice onboarding
            result = await run_console_voice_onboarding()

            if not result:
                print("\nVoice onboarding failed or was cancelled.")
                print("Would you like to use text-based onboarding instead? (y/n)")
                choice = input().strip().lower()

                if choice == 'y':
                    return self._run_text_onboarding()
                return False

            username, email = result

        except KeyboardInterrupt:
            print("\n\nVoice onboarding cancelled.")
            print("Would you like to use text-based onboarding instead? (y/n)")
            choice = input().strip().lower()

            if choice == 'y':
                return self._run_text_onboarding()
            return False

        # Create user in database
        user_id = self.create_user(username, email)
        if not user_id:
            print("Failed to create user")
            return False

        # Save session
        if self.session_manager.save_session(user_id, username, email):
            self.current_user = {
                'user_id': user_id,
                'username': username,
                'email': email
            }
            print(f"\n✓ Onboarding complete! Welcome, {username}!")
            return True

        return False

    def _run_text_onboarding(self):
        """Fallback text-based onboarding"""
        print("\n" + "="*50)
        print("TEXT ONBOARDING")
        print("="*50)

        # Get username and email from console
        username = input("\nEnter your name: ").strip()
        email = input("Enter your email: ").strip()

        if not username or not email:
            print("Name and email are required!")
            return False

        # Create user in database
        user_id = self.create_user(username, email)
        if not user_id:
            print("Failed to create user")
            return False

        # Save session
        if self.session_manager.save_session(user_id, username, email):
            self.current_user = {
                'user_id': user_id,
                'username': username,
                'email': email
            }
            print(f"\n✓ Onboarding complete! Welcome, {username}!")
            return True

        return False

    def show_main_menu(self):
        """
        Show main menu

        NOTE: In the full implementation, the voice agent handles this.
        For now, we'll use a simple text menu.
        """
        print("\n" + "="*50)
        print("MAIN MENU")
        print("="*50)
        print("\nOptions:")
        print("1. Start workout")
        print("2. Ask a question (coming soon)")
        print("3. Exit")

        choice = input("\nEnter choice (1-3): ").strip()

        if choice == '1':
            return 'workout'
        elif choice == '2':
            return 'question'
        elif choice == '3':
            return 'exit'
        else:
            print("Invalid choice")
            return None

    async def run(self):
        """Main application loop"""
        print("\n" + "="*60)
        print("NOWVA - AI-Powered Smart Squat Rack")
        print("="*60)

        # Initialize database
        print("\nInitializing database...")
        init_db()

        # Check for existing session
        if self.check_session():
            self.current_user = self.load_user_from_session()
            # Skip to main menu
        else:
            # Run onboarding
            if not await self.run_onboarding():
                print("Onboarding failed. Exiting.")
                return

        # Main application loop
        while True:
            action = self.show_main_menu()

            if action == 'workout':
                # Start IPC server
                ipc_thread = self.start_ipc_server()

                # Wait a moment for server to start
                await asyncio.sleep(1)

                # Start pose estimation
                self.start_pose_estimation()

                print("\n" + "="*50)
                print("WORKOUT MODE")
                print("="*50)
                print("\nPose estimation is running with IPC enabled.")
                print("Check the pose estimation window for visual feedback.")
                print("IPC messages will appear here.\n")
                print("Press Ctrl+C to stop workout and return to menu.\n")

                try:
                    # Keep main thread alive
                    while self.pose_process and self.pose_process.poll() is None:
                        await asyncio.sleep(1)
                except KeyboardInterrupt:
                    print("\n\nStopping workout...")

                # Cleanup
                if self.pose_process:
                    self.pose_process.terminate()
                    self.pose_process.wait()
                if self.ipc_server:
                    self.ipc_server.stop()

                print("Workout stopped. Returning to main menu.\n")

            elif action == 'question':
                print("\nQuestion mode coming soon!")
                await asyncio.sleep(1)

            elif action == 'exit':
                print("\nGoodbye!")
                break
            else:
                continue


async def main():
    """Entry point"""
    app = NowvaApp()
    await app.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nApplication interrupted by user. Exiting.")
