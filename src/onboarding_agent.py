"""
Onboarding Voice Agent with Function Calling
Handles new user onboarding with voice conversation using structured tool use
"""

import asyncio
import os
import re
from dotenv import load_dotenv

load_dotenv()

from livekit import agents
from livekit.agents import AgentSession, Agent, RunContext
from livekit.agents.llm import function_tool
from livekit.plugins import deepgram, openai, silero, inworld

# User management imports
from auth.user_management import create_user_account


# Shared data store for onboarding
onboarding_data = {
    'first_name': None,
    'email': None,
    'completed': False
}


class OnboardingAgent(Agent):
    """Agent specifically for onboarding new users using function calling"""

    def __init__(self) -> None:
        # Track what has been captured
        self.temp_first_name = None
        self.temp_email = None
        self.first_name_confirmed = False
        self.email_confirmed = False

        # Track retry attempts
        self.first_name_retry_count = 0
        self.email_retry_count = 0
        self.max_retries = 3

        super().__init__(
            instructions="""
You are Nova, a friendly AI fitness coach helping onboard a new user to the Nowva smart squat rack system.

IMPORTANT RULES:
- Keep responses SHORT: Maximum 1-2 sentences
- Be warm, natural, and conversational
- Let the user speak naturally - understand variations in how they express agreement or disagreement
- NEVER assume - always call the appropriate function based on what the user actually said
- Extract ONLY the actual name/email from user input, ignoring filler words like "um", "uh", "like", "my name is", etc.

ONBOARDING FLOW:

1. START:
   - Greet warmly: "Hey! I'm Nova, your AI coach for the Nowva smart rack. I'll track your form and help build programs. What's your first name?"

2. CAPTURE NAME:
   - When user states their name (e.g., "Um, I'd like Ben" or just "Tom"), call capture_first_name() with ONLY the name
   - Extract just the actual name: "Um my name is Sarah" → capture_first_name("Sarah")
   - After calling capture_first_name, I will tell you to confirm by spelling the name letter-by-letter with hyphens
   - You must then say something like: "Got it — Tom. That's T-O-M. Is that correct?"
   - Listen to their response carefully:
     * If they confirm (any form of agreement like "yes", "correct", "right", "sounds good"): call confirm_first_name_correct()
     * If they reject with just "no" or "wrong": call first_name_incorrect_retry() with corrected_name=None
     * If they reject AND provide correction ("no, my name is Bake", "actually it's Tom"): call first_name_incorrect_retry(corrected_name="Bake") with the NEW name extracted
   - DO NOT move forward until they confirm

3. AFTER FIRST NAME CONFIRMED:
   - You just learned their name. Acknowledge it positively and ask for their email address naturally.

4. CAPTURE EMAIL:
   - When user states their email (e.g., "john at gmail dot com"), call capture_email() with proper format (john@gmail.com)
   - Convert spoken words: "at" → "@", "dot" → "."
   - After calling capture_email, I will tell you to confirm it
   - You must then say something like: "Perfect. So that's john@gmail.com, as in J-O-H-N at gmail dot com — is that right?"
   - Listen to their response carefully:
     * If they confirm: call confirm_email_correct()
     * If they reject with just "no" or "wrong": call email_incorrect_retry() with corrected_email=None
     * If they reject AND provide correction ("no, it's john@example.com", "actually bake at gmail dot com"): call email_incorrect_retry(corrected_email="john@example.com") with the NEW email extracted
   - DO NOT move forward until they confirm

5. COMPLETE:
   - After confirm_email_correct() is called: They confirmed their details. Acknowledge warmly and indicate onboarding is complete.

CRITICAL RULES:
- Only call capture_first_name ONCE when you first hear their name (extract just the name)
- Only call capture_email ONCE when you first hear their email
- ALWAYS spell out the name letter by letter with HYPHENS (T-O-M not T.O.M) when confirming it
- NEVER include the first name when asking for or confirming email
- Let the user express confirmation/rejection naturally - understand context and intent
- Call the appropriate confirmation or retry function based on what they actually mean
"""
        )

    async def on_enter(self):
        """Entry point - start welcome message"""
        await self.session.generate_reply(
            instructions="Start the onboarding. Say: 'Hey! I'm Nova, your AI coach for the Nowva smart rack. I'll track your form and help build programs. What's your first name?'"
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

        # Save the data
        global onboarding_data
        onboarding_data['first_name'] = self.temp_first_name
        onboarding_data['email'] = self.temp_email
        onboarding_data['completed'] = True

        # Create user account in database
        try:
            user, username = create_user_account(self.temp_first_name, self.temp_email)
            print(f"ONBOARDING_USERNAME: {username}")
            print(f"ONBOARDING_USER_ID: {user.id}")
        except Exception as e:
            print(f"[ERROR] User account creation failed: {str(e)}")
            # Continue even if database creation fails


        # Return instruction to the LLM
        return None, "Onboarding is complete! Give them a warm acknowledgment and say you're ready to get started. Keep it brief and enthusiastic."

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


async def entrypoint(ctx: agents.JobContext):
    """Main entry point for onboarding agent"""

    # Initialize agent session
    session = AgentSession(
        stt=deepgram.STT(
            model="nova-3",
            language="en",
            smart_format=True,
        ),
        llm=openai.LLM(
            model=os.getenv("LLM_CHOICE", "gpt-4o-mini"),
            temperature=0.7,
        ),
        tts=inworld.TTS(
            voice="Dennis",
            model="inworld-tts-1-max",
            temperature=0.8,
            pitch=0,
        ),
        vad=silero.VAD.load(
            min_speech_duration=0.1,
            min_silence_duration=0.3,
        ),
    )

    # Create agent - tools are automatically registered via @function_tool decorators
    agent = OnboardingAgent()

    await session.start(
        room=ctx.room,
        agent=agent,
    )

    print(f"Onboarding agent started in room: {ctx.room.name}")


if __name__ == "__main__":
    # Run the agent
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
        )
    )