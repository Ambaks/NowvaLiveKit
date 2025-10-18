"""
Voice Agent Runner
Helper to run LiveKit voice agents and communicate with main process
"""

import asyncio
import subprocess
import sys
import os
import time
from pathlib import Path
from typing import Optional, Tuple


class VoiceAgentRunner:
    """Runs LiveKit voice agent in subprocess and monitors output"""

    def __init__(self, agent_script: str = "onboarding_agent.py"):
        """
        Initialize voice agent runner

        Args:
            agent_script: Path to agent script (relative to src/)
        """
        self.agent_script = Path(__file__).parent / agent_script
        self.process = None
        self.collected_data = {}

    def start(self) -> bool:
        """
        Start voice agent process

        Returns:
            True if started successfully
        """
        if not self.agent_script.exists():
            print(f"Error: Agent script not found: {self.agent_script}")
            return False

        print("\n" + "="*60)
        print("STARTING VOICE AGENT")
        print("="*60)
        print("\nThe voice agent will open in your browser.")
        print("You'll need to:")
        print("1. Allow microphone access")
        print("2. Speak with the agent to provide your information")
        print("3. Wait for 'ONBOARDING COMPLETE' message\n")

        try:
            # Start agent process
            self.process = subprocess.Popen(
                [sys.executable, str(self.agent_script), "dev"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            print("Voice agent process started...")
            print("Waiting for agent to initialize...\n")

            return True

        except Exception as e:
            print(f"Error starting voice agent: {e}")
            return False

    def wait_for_completion(self, timeout: int = 300) -> Optional[Tuple[str, str]]:
        """
        Wait for onboarding to complete and extract user data

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            Tuple of (username, email) if successful, None otherwise
        """
        if not self.process:
            print("Agent process not started")
            return None

        start_time = time.time()
        username = None
        email = None
        onboarding_complete = False

        print("Listening to agent output...")
        print("(You can interact with the agent in your browser)\n")

        try:
            while time.time() - start_time < timeout:
                if self.process.poll() is not None:
                    print("Agent process terminated")
                    break

                # Read line from process output
                line = self.process.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue

                # Print agent output
                print(f"[Agent] {line.strip()}")

                # Look for onboarding completion markers
                if "ONBOARDING COMPLETE" in line:
                    onboarding_complete = True

                # Extract name and email from output
                if "Name:" in line:
                    username = line.split("Name:")[1].strip()
                if "Email:" in line:
                    email = line.split("Email:")[1].strip()

                # Check if we have everything
                if onboarding_complete and username and email:
                    print("\n✓ Onboarding data collected successfully!")
                    return (username, email)

            # Timeout
            print(f"\nTimeout: Onboarding not completed within {timeout} seconds")
            return None

        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
            return None

    def stop(self):
        """Stop voice agent process"""
        if self.process:
            print("\nStopping voice agent...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            print("Voice agent stopped")


async def run_onboarding_with_voice() -> Optional[Tuple[str, str]]:
    """
    Run voice-based onboarding flow

    Returns:
        Tuple of (username, email) if successful, None otherwise
    """
    runner = VoiceAgentRunner("onboarding_agent.py")

    if not runner.start():
        return None

    try:
        # Wait for onboarding to complete
        result = runner.wait_for_completion(timeout=300)
        return result

    finally:
        runner.stop()


if __name__ == "__main__":
    # Test the runner
    async def test():
        result = await run_onboarding_with_voice()
        if result:
            username, email = result
            print(f"\nTest successful!")
            print(f"Username: {username}")
            print(f"Email: {email}")
        else:
            print("\nTest failed - no data collected")

    asyncio.run(test())
