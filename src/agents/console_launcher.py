"""
Console Voice Onboarding
Voice-based onboarding that runs directly in the terminal (no browser)
"""

import asyncio
import os
import subprocess
import sys
import time
import threading
from typing import Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from livekit.agents import AgentSession, Agent, llm
from livekit.plugins import openai


async def run_console_voice_agent(user_id: Optional[str] = None):
    """
    Run voice agent in console mode - doesn't terminate, runs continuously

    Args:
        user_id: Optional user ID for existing users, None for new onboarding

    Returns:
        subprocess.Popen: The running agent process
    """
    print("\n" + "="*60)
    print("NOVA VOICE AGENT")
    print("="*60)
    print("\nStarting Nova voice agent in console mode...")
    print("You'll be able to speak with Nova directly via your microphone.")
    print("\nAgent will continue running. Press Ctrl+C in main.py to exit.\n")

    try:
        # Path to voice agent (same directory now)
        voice_agent_path = Path(__file__).parent / 'voice_agent.py'

        # Run the voice agent in console mode
        process = subprocess.Popen(
            [sys.executable, str(voice_agent_path), 'console'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Monitor output in background thread
        def print_output():
            try:
                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    print(line, end='')
            except Exception as e:
                print(f"[VOICE AGENT] Output stream error: {e}")

        output_thread = threading.Thread(target=print_output, daemon=True)
        output_thread.start()

        return process

    except Exception as e:
        print(f"\nError starting voice agent: {e}")
        import traceback
        traceback.print_exc()
        return None


async def run_console_voice_onboarding() -> Optional[Tuple[str, str]]:
    """
    Run voice onboarding in console by launching the voice agent
    DEPRECATED: This is kept for backwards compatibility but now just monitors for completion

    Returns:
        Tuple of (first_name, email) if successful, None otherwise
    """
    print("\n" + "="*60)
    print("CONSOLE VOICE ONBOARDING")
    print("="*60)
    print("\nStarting voice agent in onboarding mode...")
    print("You'll be able to speak with Nova directly via your microphone.")
    print("\nPress Ctrl+C anytime to cancel and use text onboarding instead.\n")

    try:
        # Path to voice agent (same directory now)
        voice_agent_path = Path(__file__).parent / 'voice_agent.py'

        # Run the voice agent in console mode
        process = subprocess.Popen(
            [sys.executable, str(voice_agent_path), 'console'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Monitor output for onboarding completion markers
        first_name = None
        email = None
        onboarding_complete = False

        try:
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break

                # Print output
                print(line, end='')

                # Look for completion markers
                if 'ONBOARDING_FIRST_NAME:' in line:
                    first_name = line.split('ONBOARDING_FIRST_NAME:')[1].strip()
                elif 'ONBOARDING_EMAIL:' in line:
                    email = line.split('ONBOARDING_EMAIL:')[1].strip()
                elif 'ONBOARDING_COMPLETE' in line:
                    # Data captured - wait for welcome message then return process handle
                    onboarding_complete = True
                    print("[WRAPPER] Onboarding data captured...")
                    print("[WRAPPER] Agent will continue running in main menu mode")
                    # Wait for welcome message to finish
                    time.sleep(11)
                    break

        except KeyboardInterrupt:
            print("\n\nOnboarding cancelled by user")
            process.terminate()
            process.wait()
            return None

        # Check if we got the data
        if first_name and email:
            # Return the data but DON'T terminate process - it continues to main menu
            return (first_name, email, process)  # Return process handle too

        return None

    except Exception as e:
        print(f"\nError during voice onboarding: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    # Test the console onboarding
    async def test():
        result = await run_console_voice_onboarding()
        if result:
            username, email = result
            print(f"\n✓ Onboarding successful!")
            print(f"  Username: {username}")
            print(f"  Email: {email}")
        else:
            print("\n✗ Onboarding failed")

    asyncio.run(test())
