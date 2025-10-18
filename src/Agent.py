import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from livekit import agents
from livekit.agents import AgentSession, Agent, RunContext
from livekit.plugins import deepgram, openai, silero, inworld

# Use the official Inworld plugin!


class VoiceAssistant(Agent):
    """Voice assistant with conversational AI capabilities"""

    def __init__(self, initial_state: str = "main_menu", onboarding_callback=None) -> None:
        """
        Initialize Voice Assistant

        Args:
            initial_state: Starting state - 'onboarding', 'main_menu', or 'workout'
            onboarding_callback: Callback function to handle onboarding data
        """
        self.state = initial_state
        self.onboarding_callback = onboarding_callback
        self.onboarding_data = {
            'step': 'welcome',  # welcome, ask_username, confirm_username, ask_email, confirm_email, complete
            'username': None,
            'email': None,
            'temp_username': None,
            'temp_email': None
        }

        super().__init__(
            instructions=
"""
IMPORTANT RULES (must follow exactly)
- You may include inline audio markups to indicate non-verbal vocalizations. Use only these markups: [breathe], [sigh], [laugh], [cough], [happy]
- **Never** speak the markup words aloud. The markups are non-spoken controls and must NOT appear as audible words in the output.
- Other markups may appear inline but avoid placing any non-verbal token inside the middle of a clause that contains active instruction (e.g., do not put [breathe] between an action verb and its object).
- Keep replies short by default: 1–2 short sentences (6–18 words each). If detail is needed, ask "Want more?" then pause.
- Use punctuation (., !, …, —), asterisks for emphasis (*word*), and explicit filler words (uhh, ummm, yeah) where you want them spoken.
- Confirm before triggering UI actions (e.g., "Want me to open that for you?") and wait for confirmation before sending action markers.

ROLE & VOICE
You are Nova — a warm, confident, friendly American-male strength coach voice for the Nova smart squat rack. Speak like a helpful friend at the gym: upbeat, calm, slightly expressive, with natural conversational patterns. Keep the personality consistent: encouraging but concise.

OUTPUT FORMAT (must follow)
- Return only the spoken reply text (plain text). You may include the allowed inline audio markups listed above. Do NOT output SSML, code blocks, token definitions, or documentation.
- Do NOT spell or read markup names aloud (e.g., never say "[breathe]").
- Use punctuation (ellipses and em-dashes) and asterisks for emphasis. Insert filler words explicitly where you want them spoken.

MARKUP PLACEMENT & USAGE RULES
- [breathe] is for short, natural boundary pauses. Place it between clauses, not inside an action phrase.
- [sigh] is for empathy or mild disappointment; use rarely and at the end of a sentence.
- [laugh] (gentle) may follow a congratulatory line; don’t use during active sets.
- [cough] and [happy] are allowed for expressive moments but must not interrupt instructions.
- Never place any non-verbal markup in the middle of a direct instruction (e.g., avoid: "Push [breathe] through the bar").

TONE & STYLE RULES
- Coaching: energetic, use exclamation points for encouragement. Example: "Nice — two more! Push through!"
- Instruction: crisp and clear, fewer fillers. Example: "Lower slowly... chest up."
- Empathy: slower with ellipses. Example: "Oh — that sounds rough... I’d pause and check with a doctor."
- Emphasis: use *asterisks* to stress a word. Example: "Drive through your *heels*."
- Fillers: use intentionally and sparingly at utterance starts (e.g., "Yeah, ummm... let's warm up").

INTERACTION PATTERNS
Feature navigation
- Listen → clarify in one short question → confirm → offer to open feature.
  Example: "You want a new program? Want me to open the builder for you?"

S&C Questions
- Give a quick answer (1–2 short sentences). Offer to expand.
  Example: "Keep knees tracking over toes — don't let them cave. Want tips?"

Injuries / Safety
- Empathize, advise medical evaluation, and offer conservative program adjustments only after clearance.
  Example: "Oh — that hurts... I’d stop and check with a doc."

Goals & Programs
- Ask one specific follow-up question, show interest, then suggest a relevant feature.
  Example: "Nice goal. Strength or endurance you're after?"

ACTION CONFIRMATION
- For any UI or system action, ask a short confirmation first ("Want me to open that for you?"). Wait for explicit user confirmation before returning the action marker.

EXAMPLES (valid outputs — plain text only, may include allowed markups)
- "Hey — I’m Nova. Ready to get started?"
- "[breathe]Nice, lower the bar slow... chest up."
- "You’ve got this — two more! [laugh] Push through!"
- "Oh — that sounds rough... [sigh] I’d pause and check with a doctor."
- "Drive through your *heels* and exhale at the top."

FORBIDDEN (never do these)
- Speak or spell markup tokens aloud ("breath", "short_pause", etc.)
- Output SSML, XML, code blocks, or documentation in spoken replies
- Overuse non-verbal markups — keep 0–2 non-verbals per short utterance

ERROR HANDLING & EDGE CASES
- If unsure how to respond briefly, ask one clarifying question.
- If the raw LLM output contains literal markup names or disallowed tokens, convert them into punctuation or remove them before sending to TTS.
- If the user asks about markups or SSML explicitly, you may explain how they work. Otherwise do not define them.

FINAL NOTE
Be concise, human, and helpful. Use the allowed inline markups only as controls — they are not spoken words. When in doubt, say less not more.

"""

        )

    async def on_enter(self):
        """Entry point when agent session starts"""
        if self.state == "onboarding":
            await self._start_onboarding()
        elif self.state == "main_menu":
            await self._show_main_menu()
        elif self.state == "workout":
            await self._start_workout()

    async def on_user_speech(self, transcript: str):
        """Handle user speech during onboarding"""
        if self.state != "onboarding":
            return

        step = self.onboarding_data['step']

        if step == 'ask_username':
            # Extract username from speech
            self.onboarding_data['temp_username'] = transcript.strip()
            self.onboarding_data['step'] = 'confirm_username'
            await self._confirm_username()

        elif step == 'confirm_username':
            # Check if user confirmed
            lower_transcript = transcript.lower()
            if any(word in lower_transcript for word in ['yes', 'yeah', 'correct', 'right', 'yep', 'sure']):
                self.onboarding_data['username'] = self.onboarding_data['temp_username']
                self.onboarding_data['step'] = 'ask_email'
                await self._ask_email()
            else:
                # User said no, ask again
                self.onboarding_data['step'] = 'ask_username'
                await self._ask_username()

        elif step == 'ask_email':
            # Extract email from speech
            self.onboarding_data['temp_email'] = transcript.strip()
            self.onboarding_data['step'] = 'confirm_email'
            await self._confirm_email()

        elif step == 'confirm_email':
            # Check if user confirmed
            lower_transcript = transcript.lower()
            if any(word in lower_transcript for word in ['yes', 'yeah', 'correct', 'right', 'yep', 'sure']):
                self.onboarding_data['email'] = self.onboarding_data['temp_email']
                self.onboarding_data['step'] = 'complete'
                await self._complete_onboarding()
            else:
                # User said no, ask again
                self.onboarding_data['step'] = 'ask_email'
                await self._ask_email()

    async def _start_onboarding(self):
        """Start onboarding flow for new users"""
        self.onboarding_data['step'] = 'welcome'
        await self.session.generate_reply(
            instructions="""You are starting the onboarding process for a new user.

            Welcome them warmly to Nowva, the AI-powered smart squat rack.
            Briefly explain that Nowva helps them:
            - Track their form with real-time pose estimation
            - Get coaching feedback during workouts
            - Build custom programs
            - Manage their performance over time

            Keep it brief and friendly - 2-3 sentences max.
            End with: "Let's get you set up!"
            """
        )
        # Move to next step
        self.onboarding_data['step'] = 'ask_username'
        await self._ask_username()

    async def _ask_username(self):
        """Ask user for their username"""
        await self.session.generate_reply(
            instructions="""Ask the user for their username.
            Be casual and friendly. Say something like:
            "What would you like your username to be?" or "What's your name?"
            Keep it short - one sentence."""
        )

    async def _confirm_username(self):
        """Confirm username by spelling it out"""
        username = self.onboarding_data['temp_username']
        # Spell it out letter by letter
        spelled = ', '.join(username)
        await self.session.generate_reply(
            instructions=f"""The user said their name is: {username}

            Confirm by spelling it out: {spelled}
            Then ask "Is that correct?"

            Keep it brief and clear."""
        )

    async def _ask_email(self):
        """Ask user for their email"""
        await self.session.generate_reply(
            instructions="""Now ask the user for their email address.
            Say something casual like:
            "Great! And what's your email address?"
            Keep it short - one sentence."""
        )

    async def _confirm_email(self):
        """Confirm email by spelling it out"""
        email = self.onboarding_data['temp_email']
        # Spell it out with @ and dots
        spelled = email.replace('@', ' at ').replace('.', ' dot ')
        await self.session.generate_reply(
            instructions=f"""The user said their email is: {email}

            Confirm by saying it clearly: {spelled}
            Then ask "Is that correct?"

            Keep it brief."""
        )

    async def _complete_onboarding(self):
        """Complete onboarding and notify callback"""
        username = self.onboarding_data['username']
        email = self.onboarding_data['email']

        await self.session.generate_reply(
            instructions=f"""Perfect! The user's account is being created.

            Say something encouraging like:
            "Awesome! You're all set, {username}. Let's get started!"

            Keep it enthusiastic but brief."""
        )

        # Trigger callback with collected data
        if self.onboarding_callback:
            self.onboarding_callback(username, email)

    async def _show_main_menu(self):
        """Show main menu to returning users"""
        await self.session.generate_reply(
            instructions="""Generate a brief, enthusiastic welcome message for Nova AI,
                            a voice assistant for a smart squat rack. Mention features like posture tracking,
                            coaching, program creation, performance management, and ask what they require of you."""
        )

    async def _start_workout(self):
        """Start workout mode"""
        await self.session.generate_reply(
            instructions="""The user is starting a workout.
            Welcome them and let them know you're ready to track their form and count reps.
            Keep it brief and energetic."""
        )

    def set_state(self, new_state: str):
        """Change agent state"""
        self.state = new_state
        print(f"Agent state changed to: {new_state}")

    
        


async def entrypoint(ctx: agents.JobContext):
    """Main entry point for the voice agent using official Inworld plugin"""

    # Get initial state from room metadata if available
    initial_state = ctx.room.metadata.get('agent_state', 'main_menu') if ctx.room.metadata else 'main_menu'

    # Callback for onboarding data
    onboarding_complete = asyncio.Event()
    collected_data = {}

    def on_onboarding_complete(username: str, email: str):
        """Called when onboarding is complete"""
        collected_data['username'] = username
        collected_data['email'] = email
        onboarding_complete.set()

    # Initialize agent session with complete pipeline
    session = AgentSession(
        # Speech-to-Text: Deepgram Nova 2
        stt=deepgram.STT(
            model="nova-3",
            language="en",
            smart_format=True,
        ),

        # Language Model: OpenAI GPT
        llm=openai.LLM(
            model=os.getenv("LLM_CHOICE", "gpt-5-realtime"),
            temperature=0.8,
        ),

        # Text-to-Speech: Official Inworld Plugin
        tts=inworld.TTS(
            voice="Dennis",  # Voice ID
            model="inworld-tts-1-max",  # or "inworld-tts-1-max" for higher quality
            # Optional parameters:
            temperature=0.8,  # Controls randomness (0.6-1.0 recommended)
            # speed=1.0,  # Speaking speed (0.5-1.5, where 1.0 is normal)
            pitch=0,  # Voice pitch adjustment (negative=lower, positive=higher)
        ),

        # Voice Activity Detection: Silero
        vad=silero.VAD.load(
            min_speech_duration=0.1,
            min_silence_duration=0.3,
        ),
    )

    # Create agent instance
    agent = VoiceAssistant(
        initial_state=initial_state,
        onboarding_callback=on_onboarding_complete
    )

    # Start the session
    await session.start(
        room=ctx.room,
        agent=agent,
    )

    print(f"Voice agent started in room: {ctx.room.name}")
    print(f"Agent state: {initial_state}")

    # If in onboarding mode, wait for completion and store data in room metadata
    if initial_state == 'onboarding':
        await onboarding_complete.wait()
        # Store collected data in room metadata so main.py can retrieve it
        # Note: This is a simplified approach. In production, you'd use proper data channels
        print(f"Onboarding complete: {collected_data['username']}, {collected_data['email']}")


if __name__ == "__main__":
    # Run the agent
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
        )
    )