"""
Nova Voice Agent - Mode-Aware Voice Assistant
Handles onboarding, main menu, and workout modes with function calling
"""

import asyncio
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory (src/) to path when running as subprocess
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()

from livekit import agents
from livekit.agents import AgentSession, Agent, RunContext
from livekit.agents.llm import function_tool
from livekit.plugins import openai
# Note: Realtime API handles STT+LLM+TTS - no separate plugins needed

# User management imports
from auth.user_management import create_user_account

# State management imports
from core.agent_state import AgentState

# IPC communication
from core.ipc_communication import IPCClient

# Prompt imports
from agents.prompts import ONBOARDING_PROMPT, get_main_menu_prompt, get_workout_prompt


class NovaVoiceAgent(Agent):
    """Mode-aware voice agent that handles all user interactions"""

    def __init__(self, state: AgentState = None, ipc_client: IPCClient = None) -> None:
        # State management
        self.state = state if state else AgentState()
        self.ipc_client = ipc_client  # IPC to communicate with main.py

        # Onboarding-specific tracking
        self.temp_first_name = None
        self.temp_email = None
        self.first_name_confirmed = False
        self.email_confirmed = False
        self.first_name_retry_count = 0
        self.email_retry_count = 0
        self.max_retries = 3

        # Get initial instructions based on mode
        instructions = self._get_instructions_for_mode()

        super().__init__(instructions=instructions)

    def _get_instructions_for_mode(self) -> str:
        """Get instructions based on current mode"""
        mode = self.state.get_mode()

        if mode == "onboarding":
            return self._get_onboarding_instructions()
        elif mode == "main_menu":
            return self._get_main_menu_instructions()
        elif mode == "workout":
            return self._get_workout_instructions()
        else:
            return self._get_onboarding_instructions()


    def _get_onboarding_instructions(self) -> str:
        """Instructions for onboarding mode"""
        return ONBOARDING_PROMPT


    def _get_main_menu_instructions(self) -> str:
        """Instructions for main menu mode"""
        user = self.state.get_user()
        name = user.get("name", "there")
        return get_main_menu_prompt(name)

    def _get_workout_instructions(self) -> str:
        """Instructions for workout mode"""
        user = self.state.get_user()
        name = user.get("name", "there")
        return get_workout_prompt(name)

    async def on_enter(self):
        """Entry point - generate appropriate greeting based on mode"""
        mode = self.state.get_mode()

        if mode == "onboarding":
            await self.session.generate_reply(
                instructions="Start the onboarding. Say: 'Hey! It's great to meet you, I'm Nova, your AI coach for the Nowva smart rack. What's your first name?'"
            )
        elif mode == "main_menu":
            # Main menu mode - greet returning users
            user = self.state.get_user()
            name = user.get("name", "there")

            await self.session.generate_reply(
                instructions=f"Welcome {name} back to the main menu. Say: 'Hey {name}, welcome back! Ready to start a workout or check your progress?' Keep it friendly and brief."
            )
        elif mode == "workout":
            user = self.state.get_user()
            name = user.get("name", "there")
            await self.session.generate_reply(
                instructions=f"Start the workout mode. Say: 'Alright {name}, let's do this! I'm tracking your form and counting reps. When you're ready, step up to the rack.'"
            )

    # Tool 1: Capture first name
    @function_tool
    async def capture_first_name(self, context: RunContext, first_name: str):
        """
        Call this when the user has clearly stated their first name for the FIRST time.
        Extract ONLY the actual name, ignoring filler words like "um", "uh", "like", "my name is".

        Args:
            first_name: The user's first name as they spoke it, without filler words
        """
        self.temp_first_name = first_name.strip()

        print(f"[DEBUG] Captured first name: {self.temp_first_name}")

        # Spell out the name for confirmation (with hyphens)
        spelled_name = "-".join(list(self.temp_first_name.upper()))

        # Return instruction to the LLM
        return None, f"You just captured the name '{self.temp_first_name}'. Now confirm it by spelling it out letter by letter as '{spelled_name}' (with hyphens between letters). Ask if that's correct. Keep it short and natural."

    # Tool 2: Confirm first name is correct
    @function_tool
    async def confirm_first_name_correct(self, context: RunContext):
        """
        Call this when the user confirms their name is correct after you spelled it out letter-by-letter.
        Only call this if they expressed agreement (yes, correct, right, sounds good, etc.)
        """
        self.first_name_confirmed = True

        print(f"[DEBUG] First name '{self.temp_first_name}' confirmed by user!")

        # Return instruction to the LLM
        return None, "The user confirmed their name is correct. Now ask for their email address. Keep it short and natural."

    # Tool 3: First name was incorrect - retry OR correct with new name
    @function_tool
    async def first_name_incorrect_retry(self, context: RunContext, corrected_name: str = None):
        """
        Call this when the user indicates their name was NOT correct.

        The user might respond in two ways:
        1. Simple disagreement: "no", "wrong", "that's not right"
           → Set corrected_name to None, and we'll ask again

        2. Disagreement with correction: "no, my name is Bake", "actually it's Tom", "no, it's Sarah"
           → Extract the corrected name and pass it as corrected_name parameter
           → This will immediately capture and confirm the new name

        Args:
            corrected_name: The corrected name if user provided it, None if they just said no
        """
        self.first_name_retry_count += 1

        print(f"[DEBUG] First name was incorrect, retry attempt {self.first_name_retry_count}/{self.max_retries}")

        if self.first_name_retry_count >= self.max_retries:
            return None, "Too many retry attempts. Say: 'Having trouble with the name. Let's try text input instead - what's your name?' (This should trigger fallback to text mode)"

        if corrected_name:
            # User provided a correction directly - capture it and confirm
            self.temp_first_name = corrected_name.strip()

            print(f"[DEBUG] User provided corrected first name: {self.temp_first_name}")

            # Spell out the corrected name for confirmation (with hyphens)
            spelled_name = "-".join(list(self.temp_first_name.upper()))

            return None, f"The user corrected their name to '{self.temp_first_name}'. Now confirm it by spelling it out letter by letter as '{spelled_name}' (with hyphens between letters). Ask if that's correct. Keep it short and natural."
        else:
            # User just said no without providing correction - ask again
            self.temp_first_name = None
            self.first_name_confirmed = False

            print(f"[DEBUG] User said name was incorrect, asking again...")

            return None, "The user said their name was not correct. Say 'No problem!' and ask for their name again."

    # Tool 4: Capture email
    @function_tool
    async def capture_email(self, context: RunContext, email: str):
        """
        Call this when the user has clearly stated their email address for the FIRST time.
        Convert spoken format to standard email format (e.g., 'john at gmail dot com' becomes 'john@gmail.com').

        Args:
            email: The user's email address in standard format with @ and dots
        """
        # Normalize email format
        normalized_email = email.strip().lower()
        normalized_email = normalized_email.replace(" at ", "@").replace(" dot ", ".").replace("dot com", ".com").replace("dot org", ".org")

        # Validate email format with regex
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(email_pattern, normalized_email)

        if match:
            self.temp_email = match.group(0)
        else:
            # Fallback: use normalized email even if not perfectly valid
            self.temp_email = normalized_email

        print(f"[DEBUG] Captured email: {self.temp_email}")

        # Return instruction to the LLM
        return None, f"You just captured the email '{self.temp_email}'. Now read it back naturally and ask if it's correct. Keep it short."

    # Tool 5: Confirm email is correct
    @function_tool
    async def confirm_email_correct(self, context: RunContext):
        """
        Call this when the user confirms their email is correct after you read it back naturally.
        Only call this if they expressed agreement.
        """
        self.email_confirmed = True

        print(f"[DEBUG] Email '{self.temp_email}' confirmed by user!")

        # Create user account in database
        user_id = None
        username = None
        try:
            user, username = create_user_account(self.temp_first_name, self.temp_email)
            user_id = str(user.id)
            print(f"ONBOARDING_USERNAME: {username}")
            print(f"ONBOARDING_USER_ID: {user_id}")

            # Update state with user information
            self.state.update_user(
                id=user_id,
                name=self.temp_first_name,
                email=self.temp_email,
                username=username
            )

            # Mark onboarding complete in state
            # DON'T mark main_menu as visited yet - let on_enter handle first greeting
            self.state.switch_mode("main_menu")
            self.state.save_state()

            print("\n[ONBOARDING] User account created successfully")
            print("[ONBOARDING] State updated - ready for main menu")

        except Exception as e:
            print(f"[ERROR] User account creation failed: {str(e)}")
            # Continue even if database creation fails

        # Output markers for main.py to capture
        print(f"ONBOARDING_FIRST_NAME: {self.temp_first_name}")
        print(f"ONBOARDING_EMAIL: {self.temp_email}")
        print(f"ONBOARDING_COMPLETE")

        # Return instruction to the LLM - welcome + brief feature intro in ONE message
        # After this returns, the agent will speak and then we can exit
        result = None, f"Say warmly and enthusiastically: 'Welcome aboard, {self.temp_first_name}! You're all set up. [breathe] I'm Nova, your AI fitness coach. I'll track your form, count your reps, and help you build custom programs. Ready to get started?' Keep it energetic but natural."

        return result

    # Tool 6: Email was incorrect - retry OR correct with new email
    @function_tool
    async def email_incorrect_retry(self, context: RunContext, corrected_email: str = None):
        """
        Call this when the user indicates their email was NOT correct.

        The user might respond in two ways:
        1. Simple disagreement: "no", "wrong", "that's not right"
           → Set corrected_email to None, and we'll ask again

        2. Disagreement with correction: "no, it's john@gmail.com", "actually bake at example dot com"
           → Extract the corrected email and pass it as corrected_email parameter
           → This will immediately capture and confirm the new email

        Args:
            corrected_email: The corrected email if user provided it, None if they just said no
        """
        self.email_retry_count += 1

        print(f"[DEBUG] Email was incorrect, retry attempt {self.email_retry_count}/{self.max_retries}")

        if self.email_retry_count >= self.max_retries:
            return None, "Too many retry attempts. Say: 'Having trouble with the email. Let's try text input instead - what's your email?' (This should trigger fallback to text mode)"

        if corrected_email:
            # User provided a correction directly - capture it and confirm
            # Normalize email format
            normalized_email = corrected_email.strip().lower()
            normalized_email = normalized_email.replace(" at ", "@").replace(" dot ", ".").replace("dot com", ".com").replace("dot org", ".org")

            # Validate email format with regex
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            match = re.search(email_pattern, normalized_email)

            if match:
                self.temp_email = match.group(0)
            else:
                # Fallback: use normalized email even if not perfectly valid
                self.temp_email = normalized_email

            print(f"[DEBUG] User provided corrected email: {self.temp_email}")

            return None, f"The user corrected their email to '{self.temp_email}'. Now read it back naturally and ask if it's correct. Keep it short."
        else:
            # User just said no without providing correction - ask again
            self.temp_email = None
            self.email_confirmed = False

            print(f"[DEBUG] User said email was incorrect, asking again...")

            return None, "The user said their email was not correct. Say 'No worries!' and ask for their email again."

    # ===== MAIN MENU TOOLS =====

    @function_tool
    async def start_workout(self, context: RunContext):
        """
        Call this when the user wants to start a workout.
        User might say: "start workout", "let's train", "I'm ready", "begin workout"
        """
        print("[MAIN MENU] User requested to start workout")

        # Switch to workout mode (main.py monitors state file)
        self.state.switch_mode("workout")
        self.state.save_state()
        print("[STATE] Switched to workout mode - main.py will detect and start pose estimation")

        # Return instruction to transition to workout mode
        user = self.state.get_user()
        name = user.get("name", "there")

        return None, f"The user wants to start a workout. Say enthusiastically: 'Alright {name}, let's do this! I'm tracking your form and counting reps. When you're ready, step up to the rack.' Keep it energetic."

    @function_tool
    async def view_progress(self, context: RunContext):
        """
        Call this when the user wants to view their progress, stats, or history.
        User might say: "show my progress", "how am I doing", "view stats", "my history"
        """
        print("[MAIN MENU] User requested to view progress")

        # TODO: Fetch actual progress data from database
        user = self.state.get_user()
        name = user.get("name", "there")

        # For now, placeholder response
        return None, f"The user wants to see their progress. Say: '{name}, you're doing great! This feature is coming soon - I'll be able to show you your workout history, personal records, and progress charts.' Keep it encouraging."

    @function_tool
    async def update_profile(self, context: RunContext):
        """
        Call this when the user wants to update their profile or settings.
        User might say: "update profile", "change settings", "edit my info"
        """
        print("[MAIN MENU] User requested to update profile")

        user = self.state.get_user()
        name = user.get("name", "there")

        # For now, placeholder response
        return None, f"The user wants to update their profile. Say: '{name}, profile updates are coming soon! For now, you can ask me to change specific things and I'll note them down.' Keep it helpful."

    # ===== WORKOUT TOOLS =====

    @function_tool
    async def end_workout(self, context: RunContext):
        """
        Call this when the user wants to end/stop their workout.
        User might say: "stop workout", "I'm done", "end session", "finish"
        """
        print("[WORKOUT] User requested to end workout")

        # Switch back to main menu mode (main.py monitors state file)
        self.state.switch_mode("main_menu")
        self.state.set("workout.active", False)
        self.state.save_state()
        print("[STATE] Switched to main_menu mode - main.py will detect and stop pose estimation")

        user = self.state.get_user()
        name = user.get("name", "there")

        return None, f"The user wants to end the workout. Say: 'Great work today, {name}! You crushed it. Returning to the main menu.' Keep it celebratory."


async def entrypoint(ctx: agents.JobContext):
    """Main entry point for Nova voice agent"""

    # Initialize state management
    # Check if user_id is provided in room metadata (for returning users)
    user_id = ctx.room.metadata.get('user_id') if ctx.room.metadata else None

    # If no user_id from metadata, try to find the most recent state file
    # (for console mode where metadata isn't available)
    if not user_id:
        import glob
        state_files = glob.glob('.agent_state_*.json')
        if state_files:
            # Get most recently modified state file
            latest_state = max(state_files, key=os.path.getmtime)
            # Extract user_id from filename
            user_id = latest_state.replace('.agent_state_', '').replace('.json', '')
            print(f"[NOVA] Found recent state file for user: {user_id}")

    state = AgentState(user_id=user_id)

    print(f"[NOVA] Starting with mode: {state.get_mode()}")
    if user_id:
        print(f"[NOVA] Loaded existing user: {user_id}")

    # IPC is not needed - state file is used for communication with main.py
    ipc_client = None

    # Initialize OpenAI Realtime API model
    # Replaces separate STT (Deepgram) + LLM (OpenAI) + TTS (Inworld)
    realtime_model = openai.realtime.RealtimeModel(
        voice=os.getenv("REALTIME_VOICE", "alloy"),
        temperature=float(os.getenv("REALTIME_TEMPERATURE", "0.8")),
        turn_detection={
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 500,
        },
        modalities=["audio", "text"],
    )

    # Initialize agent session with Realtime model
    session = AgentSession(
        llm=realtime_model,
    )

    # Create agent with state management and IPC - tools are automatically registered via @function_tool decorators
    agent = NovaVoiceAgent(state=state, ipc_client=ipc_client)

    await session.start(
        room=ctx.room,
        agent=agent,
    )

    print(f"Nova voice agent started in room: {ctx.room.name}")
    print(f"Agent state: {state}")


if __name__ == "__main__":
    import signal
    import sys

    # Flag to track if we're shutting down
    shutting_down = False

    def signal_handler(signum, frame):
        """Handle shutdown signals gracefully"""
        global shutting_down
        if not shutting_down:
            shutting_down = True
            print("\n[SHUTDOWN] Gracefully shutting down agent...")
            sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the agent
    try:
        agents.cli.run_app(
            agents.WorkerOptions(
                entrypoint_fnc=entrypoint,
            )
        )
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Agent stopped by user")
        sys.exit(0)
    except Exception as e:
        # Suppress termios errors during shutdown
        if "termios" not in str(e).lower():
            print(f"[ERROR] {e}")
        sys.exit(0)