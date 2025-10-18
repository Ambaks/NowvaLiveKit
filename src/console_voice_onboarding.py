"""
Console Voice Onboarding
Voice-based onboarding that runs directly in the terminal (no browser)
"""

import asyncio
import os
import subprocess
import sys
from typing import Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from livekit.agents import AgentSession, Agent, llm
from livekit.plugins import deepgram, openai, silero, inworld


class ConsoleOnboardingAgent(Agent):
    """Voice agent for console-based onboarding"""

    def __init__(self):
        super().__init__(
            instructions="""
You are Nova, a friendly AI fitness coach helping onboard a new user to Nowva.

YOUR TASK:
1. Welcome the user warmly to Nowva
2. Briefly explain (1 sentence): Nowva tracks form and provides coaching
3. Ask "What's your name?"
4. After they respond, ask "And what's your email address?"
5. Confirm by repeating: "Just to confirm - your name is [NAME] and email is [EMAIL], correct?"
6. If they confirm, call save_user_info immediately

IMPORTANT:
- Keep responses VERY SHORT - 1 sentence per turn
- Don't repeat information the user already gave
- Call save_user_info as soon as user confirms
""",
            tools=[
                llm.FunctionTool(
                    name="save_user_info",
                    description="Save the user's name and email after confirmation",
                    parameters={
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "User's name"},
                            "email": {"type": "string", "description": "User's email"}
                        },
                        "required": ["name", "email"]
                    },
                    func=self.save_user_info
                )
            ]
        )

    async def save_user_info(self, name: str, email: str):
        """Save user information"""
        global onboarding_result
        onboarding_result['username'] = name
        onboarding_result['email'] = email
        onboarding_result['completed'] = True

        print(f"\n{'='*50}")
        print(f"✓ Information collected:")
        print(f"  Name: {name}")
        print(f"  Email: {email}")
        print(f"{'='*50}\n")

        return f"Perfect! Welcome aboard, {name}!"

    async def on_enter(self):
        """Start onboarding"""
        await self.session.generate_reply(
            instructions="Give a brief welcome (1 sentence) and ask for their name."
        )


async def run_console_voice_onboarding() -> Optional[Tuple[str, str]]:
    """
    Run voice onboarding in console by launching the onboarding agent

    Returns:
        Tuple of (first_name, email) if successful, None otherwise
    """
    print("\n" + "="*60)
    print("CONSOLE VOICE ONBOARDING")
    print("="*60)
    print("\nStarting voice agent in console mode...")
    print("You'll be able to speak with Nova directly via your microphone.")
    print("\nPress Ctrl+C anytime to cancel and use text onboarding instead.\n")

    try:
        # Path to onboarding agent
        onboarding_agent_path = Path(__file__).parent / 'onboarding_agent.py'

        # Run the onboarding agent in console mode
        process = subprocess.Popen(
            [sys.executable, str(onboarding_agent_path), 'console'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Monitor output for completion
        first_name = None
        email = None

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
                    break

        except KeyboardInterrupt:
            print("\n\nOnboarding cancelled by user")
            process.terminate()
            process.wait()
            return None

        # Wait for process to finish
        process.wait()

        # Check if we got the data
        if first_name and email:
            return (first_name, email)

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
