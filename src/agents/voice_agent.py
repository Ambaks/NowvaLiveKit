"""
Nova Voice Agent - Mode-Aware Voice Assistant
Handles onboarding, main menu, and workout modes with function calling
"""

import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Optional
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
from agents.prompts import ONBOARDING_PROMPT, get_main_menu_prompt, get_workout_prompt, get_program_creation_prompt

# Database imports
from db.database import SessionLocal
from db.program_utils import has_any_programs

# Context summarization constants
MAX_CONTEXT_TOKENS = 28672  # OpenAI Realtime API limit
SUMMARY_TRIGGER_RATIO = 0.70  # Trigger at 70% capacity
SUMMARY_TRIGGER_TOKENS = int(MAX_CONTEXT_TOKENS * SUMMARY_TRIGGER_RATIO)  # ~20,070 tokens
KEEP_LAST_TURNS = 4  # Keep last 4 conversation items verbatim
SUMMARY_MODEL = os.getenv("CONTEXT_SUMMARY_MODEL", "gpt-4o-mini")  # Model for conversation summarization, fallback to gpt-4o-mini


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

        # Context summarization state
        self._current_token_count: int = 0
        self._is_summarizing: bool = False  # Guard against concurrent summarization
        self._summary_count: int = 0

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
        elif mode == "program_creation":
            return self._get_program_creation_instructions()
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

    def _get_program_creation_instructions(self) -> str:
        """Instructions for program creation mode"""
        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        # Try to get cached existing data from state first (set when entering program_creation mode)
        existing_data = self.state.get("program_creation.existing_data")

        # If no cached data, query database as fallback (shouldn't happen normally)
        if existing_data is None:
            print("[PROGRAM] No cached user data found, querying database (this shouldn't happen often)")
            existing_data = {}
            db = SessionLocal()
            try:
                from db.models import User
                db_user = db.query(User).filter(User.id == user_id).first()
                if db_user:
                    existing_data = {
                        "height_cm": db_user.height_cm,
                        "weight_kg": db_user.weight_kg,
                        "age": db_user.age,
                        "sex": db_user.sex
                    }
            except Exception as e:
                print(f"[PROGRAM] Error checking existing user data: {e}")
            finally:
                db.close()

        # Gather pre-captured parameters from state
        precaptured_params = {}
        if self.state.get("program_creation.precaptured_goal"):
            precaptured_params["goal"] = self.state.get("program_creation.precaptured_goal")
            precaptured_params["goal_raw"] = self.state.get("program_creation.precaptured_goal_raw", "")
        if self.state.get("program_creation.precaptured_duration"):
            precaptured_params["duration"] = self.state.get("program_creation.precaptured_duration")
        if self.state.get("program_creation.precaptured_frequency"):
            precaptured_params["frequency"] = self.state.get("program_creation.precaptured_frequency")
        if self.state.get("program_creation.precaptured_notes"):
            precaptured_params["notes"] = self.state.get("program_creation.precaptured_notes")
        if self.state.get("program_creation.precaptured_sport"):
            precaptured_params["sport"] = self.state.get("program_creation.precaptured_sport")
        if self.state.get("program_creation.precaptured_injuries"):
            precaptured_params["injuries"] = self.state.get("program_creation.precaptured_injuries")
        if self.state.get("program_creation.precaptured_session_duration"):
            precaptured_params["session_duration"] = self.state.get("program_creation.precaptured_session_duration")

        return get_program_creation_prompt(name, existing_data, precaptured_params)

    async def on_enter(self):
        """Entry point - generate appropriate greeting based on mode"""
        mode = self.state.get_mode()

        if mode == "onboarding":
            await self.session.generate_reply(
                instructions="Start the onboarding. Say something like: 'Hey! It's great to meet you, I'm Nova, your AI coach for the Nowva smart rack. What's your first name?'"
            )
        elif mode == "main_menu":
            # Main menu mode - greet returning users
            user = self.state.get_user()
            name = user.get("name", "there")

            await self.session.generate_reply(
                instructions=f"Welcome {name} back to the main menu. Say something like: 'Hey {name}, welcome back! You can start a workout, create or update a program, check your progress, or update your profile. What would you like to do?' Keep it friendly and conversational."
            )
        elif mode == "workout":
            user = self.state.get_user()
            name = user.get("name", "there")
            await self.session.generate_reply(
                instructions=f"Start the workout mode. Say something like: 'Alright {name}, let's do this! I'm tracking your form and counting reps. When you're ready, step up to the rack.'"
            )

    # ===== CONTEXT MANAGEMENT =====

    async def _truncate_conversation_history(self, context: RunContext, max_items: int = 10):
        """
        Truncate conversation history to prevent context window exhaustion.

        This method:
        - Keeps only the last N messages to save tokens
        - Preserves the system prompt automatically
        - Removes leading function calls to avoid orphaning responses
        - Is transparent to the agent (doesn't disrupt conversation flow)

        Args:
            context: The current RunContext
            max_items: Maximum number of messages to retain (default: 10)
        """
        try:
            from livekit.agents import llm

            # Get agent through session (correct pattern for Realtime API)
            agent = context.session.current_agent

            # Get current chat context (read-only)
            current_ctx = agent.chat_ctx

            # Get message items
            items = current_ctx.items if hasattr(current_ctx, 'items') else []
            messages_before = len(items)

            # Truncate to last N messages
            truncated_items = items[-max_items:] if len(items) > max_items else items

            # Create new context with truncated items
            new_ctx = llm.ChatContext.empty()
            for item in truncated_items:
                new_ctx.insert(item)

            # Update agent's chat context (syncs to Realtime API automatically)
            await agent.update_chat_ctx(new_ctx)

            messages_removed = messages_before - len(truncated_items)
            if messages_removed > 0:
                print(f"[CONTEXT] Truncated: removed {messages_removed} messages, kept last {len(truncated_items)}")
            else:
                print(f"[CONTEXT] No truncation needed: {messages_before} messages <= {max_items} limit")

        except Exception as e:
            # Don't fail the conversation if truncation fails
            print(f"[CONTEXT] Warning: Failed to truncate conversation: {e}")
            print(f"[CONTEXT] Continuing without truncation...")

    # ===== CONTEXT SUMMARIZATION METHODS =====

    def _items_to_text(self, items: list) -> str:
        """
        Convert chat items to readable text format for summarization.

        Args:
            items: List of ChatMessage items

        Returns:
            Formatted conversation text
        """
        lines = []
        for item in items:
            role = item.role.upper() if hasattr(item, 'role') else 'UNKNOWN'

            # Extract text content (handle different item structures)
            text = ""
            if hasattr(item, 'content'):
                if isinstance(item.content, str):
                    text = item.content
                elif isinstance(item.content, list):
                    # Handle content array (common in OpenAI format)
                    for content_item in item.content:
                        if isinstance(content_item, dict):
                            text += content_item.get('text', '') or content_item.get('transcript', '')
                        elif hasattr(content_item, 'text'):
                            text += content_item.text or ''
            elif hasattr(item, 'text'):
                text = item.text or ''

            if text.strip():
                lines.append(f"{role}: {text.strip()}")

        return "\n".join(lines)

    def _build_fallback_summary(self) -> str:
        """
        Build a simple summary from agent state if LLM call fails.

        Returns:
            Formatted summary string from collected state
        """
        try:
            # Access existing state/collected data from program creation mode
            mode = self.state.get_mode()

            parts = []

            # Check if we're in program creation mode and have collected data
            if mode == "program_creation":
                # Try to get data from state
                height = self.state.get("program_creation.height_cm")
                weight = self.state.get("program_creation.weight_kg")
                age = self.state.get("program_creation.age")
                sex = self.state.get("program_creation.sex")
                goal = self.state.get("program_creation.goal")
                experience = self.state.get("program_creation.experience_level")
                equipment = self.state.get("program_creation.equipment_access")
                schedule = self.state.get("program_creation.days_per_week")
                injuries = self.state.get("program_creation.injuries_limitations")

                if height or weight:
                    parts.append(f"User is {height}cm tall, weighing {weight}kg" if height and weight else f"Height/weight: {height or weight}")

                if age or sex:
                    parts.append(f"{age} year old {sex}" if age and sex else f"{age or sex}")

                if goal:
                    parts.append(f"Goal: {goal}")

                if experience:
                    parts.append(f"Experience: {experience}")

                if equipment:
                    parts.append(f"Equipment: {equipment}")

                if schedule:
                    parts.append(f"Training {schedule} days per week")

                if injuries:
                    parts.append(f"Injuries/limitations: {injuries}")

            if parts:
                return "Collected data: " + ". ".join(parts) + "."
            else:
                return "Conversation in progress. Some user information has been collected."

        except Exception as e:
            print(f"[SUMMARY] Fallback summary generation failed: {e}")
            return "Fitness consultation in progress."

    async def _generate_conversation_summary(self, items: list) -> str | None:
        """
        Call gpt-4o-mini to generate a 2-3 sentence summary of conversation items.

        Args:
            items: List of ChatMessage items to summarize

        Returns:
            Summary string or None if generation fails
        """
        try:
            # Convert items to text format
            conversation_text = self._items_to_text(items)

            if not conversation_text.strip():
                print("[SUMMARY] No conversation text to summarize")
                return None

            print(f"[SUMMARY] Generating summary for {len(conversation_text)} characters of conversation...")

            # Import OpenAI client
            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            # Call OpenAI API (non-blocking with asyncio.to_thread)
            response = await asyncio.to_thread(
                lambda: client.chat.completions.create(
                    model=SUMMARY_MODEL,
                    temperature=0.3,
                    max_tokens=200,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a summarization assistant for a fitness consultation. "
                                "Summarize the conversation in 2-3 concise sentences. "
                                "Focus on data collected: height, weight, age, sex, fitness goals, "
                                "experience level, equipment access, training schedule, and injuries/limitations. "
                                "Be specific with numbers and measurements. "
                                "Do not include pleasantries, greetings, or filler words."
                            )
                        },
                        {
                            "role": "user",
                            "content": f"Summarize this fitness consultation:\n\n{conversation_text}"
                        }
                    ]
                )
            )

            summary = response.choices[0].message.content.strip()
            print(f"[SUMMARY] Generated summary ({len(summary)} chars): {summary[:100]}...")
            return summary

        except Exception as e:
            print(f"[SUMMARY] LLM summary generation failed: {e}")
            return None

    async def _update_context_with_summary(
        self,
        agent,
        summary_text: str,
        system_items: list,
        recent_items: list,
        old_items: list
    ) -> None:
        """
        Update the agent's chat context with the summary.

        Creates new context: original system prompt + summary (as SYSTEM message) + recent messages.

        Args:
            agent: The current voice agent
            summary_text: Generated summary text
            system_items: Original system prompt items to preserve
            recent_items: Recent conversation items to keep
            old_items: Old items that were summarized (for logging)
        """
        from livekit.agents import llm

        # Create new chat context
        new_ctx = llm.ChatContext.empty()

        # 1. Add original system prompt(s)
        for item in system_items:
            new_ctx.items.append(item)

        # 2. Add summary as SYSTEM message (CRITICAL: use system role, not assistant)
        summary_message = llm.ChatMessage(
            role="system",
            content=f"[CONVERSATION SUMMARY] {summary_text}"
        )
        new_ctx.items.append(summary_message)

        # 3. Add recent conversation items
        for item in recent_items:
            new_ctx.items.append(item)

        # Update agent context
        await agent.update_chat_ctx(new_ctx)

        print(f"[SUMMARY] Context updated: {len(system_items)} system + 1 summary + {len(recent_items)} recent items")
        print(f"[SUMMARY] Removed {len(old_items)} old items")

    async def _summarize_and_prune_context(self) -> None:
        """
        Async summarization: compress old conversation turns into a summary.

        This runs in the background without blocking the main event loop.
        Uses SYSTEM message type to avoid audio/text modality confusion.
        """
        if self._is_summarizing:
            print("[SUMMARY] Summarization already in progress, skipping")
            return

        self._is_summarizing = True
        print(f"[SUMMARY] ⚠️  Token count {self._current_token_count} >= {SUMMARY_TRIGGER_TOKENS}. Starting async summarization...")

        try:
            # Get current agent - we need to access it from the agent itself
            # In LiveKit Realtime API, the agent is 'self' when called from within the agent
            agent = self

            if not agent or not hasattr(agent, 'chat_ctx'):
                print("[SUMMARY] No agent or chat context available for summarization")
                return

            chat_ctx = agent.chat_ctx
            items = list(chat_ctx.items)

            # Need enough items to summarize
            if len(items) <= KEEP_LAST_TURNS + 1:  # +1 for system prompt
                print(f"[SUMMARY] Not enough items to summarize ({len(items)} items)")
                return

            # Split: keep system prompt + last N turns, summarize the rest
            # Note: Some items (like FunctionCall) don't have a 'role' attribute
            system_items = [item for item in items if hasattr(item, 'role') and item.role == "system"]
            non_system_items = [item for item in items if not hasattr(item, 'role') or item.role != "system"]

            if len(non_system_items) <= KEEP_LAST_TURNS:
                print(f"[SUMMARY] Not enough non-system items to summarize ({len(non_system_items)} items)")
                return

            old_items = non_system_items[:-KEEP_LAST_TURNS]
            recent_items = non_system_items[-KEEP_LAST_TURNS:]

            print(f"[SUMMARY] Splitting context: {len(old_items)} old items to summarize, {len(recent_items)} recent items to keep")

            # Generate LLM summary of old items
            summary_text = await self._generate_conversation_summary(old_items)

            if not summary_text:
                print("[SUMMARY] Failed to generate LLM summary, using fallback")
                summary_text = self._build_fallback_summary()

            # Create new context with summary
            await self._update_context_with_summary(
                agent=agent,
                summary_text=summary_text,
                system_items=system_items,
                recent_items=recent_items,
                old_items=old_items
            )

            self._summary_count += 1
            print(f"[SUMMARY] ✅ Summarization complete (summary #{self._summary_count})")

        except Exception as e:
            print(f"[SUMMARY] Summarization failed: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._is_summarizing = False

    async def check_and_summarize_if_needed(self, context: RunContext = None) -> None:
        """
        Check if summarization is needed based on message count and trigger if necessary.

        This is called at strategic points during the conversation to prevent context overflow.
        Uses message count as a proxy for token count (since direct token tracking requires
        accessing response.done events which may not be easily available in the LiveKit SDK).

        Args:
            context: Optional RunContext (not used currently, but kept for compatibility)
        """
        try:
            # Get current chat context
            if not hasattr(self, 'chat_ctx'):
                return

            chat_ctx = self.chat_ctx
            items = list(chat_ctx.items) if hasattr(chat_ctx, 'items') else []

            # Use message count as heuristic: ~15 messages typically means we're approaching limits
            # This is conservative to ensure we summarize before hitting the 28K token limit
            MESSAGE_COUNT_THRESHOLD = 15

            if len(items) > MESSAGE_COUNT_THRESHOLD and not self._is_summarizing:
                print(f"[SUMMARY] Message count ({len(items)}) exceeds threshold ({MESSAGE_COUNT_THRESHOLD})")
                # Trigger async summarization (non-blocking)
                asyncio.create_task(self._summarize_and_prune_context())

        except Exception as e:
            print(f"[SUMMARY] Error checking for summarization: {e}")

    # ===== ONBOARDING TOOLS =====

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
            return None, "Too many retry attempts. Say something like: 'Having trouble with the name. Let's try text input instead - what's your name?' (This should trigger fallback to text mode)"

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

            # Update agent instructions to main_menu mode
            new_instructions = self._get_main_menu_instructions()
            self.update_instructions(new_instructions)
            print("[ONBOARDING] Updated agent instructions to main_menu mode")

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
            return None, "Too many retry attempts. Say something like: 'Having trouble with the email. Let's try text input instead - what's your email?' (This should trigger fallback to text mode)"

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

        from db.database import SessionLocal
        from db.schedule_utils import get_todays_workout
        from core.workout_session import WorkoutSession

        # Get today's workout from schedule
        db = SessionLocal()
        try:
            user = self.state.get_user()
            user_id = user.get("id")
            name = user.get("name", "there")

            workout = get_todays_workout(db, user_id)

            if not workout:
                print("[WORKOUT] No workout scheduled for today")
                return None, f"Tell the user: 'Hey {name}, you don't have a workout scheduled for today. Would you like to check your upcoming schedule or create a new program?' Keep it helpful and supportive."

            # Initialize workout session
            session = WorkoutSession(
                user_id=user_id,
                schedule_id=workout["schedule_id"],
                workout_data=workout
            )

            # Store session in state
            self.state.set("workout.current_session", session.to_dict())
            self.state.switch_mode("workout")
            self.state.save_state()

            # Update agent instructions to workout mode
            new_instructions = self._get_workout_instructions()
            self.update_instructions(new_instructions)
            print("[STATE] Switched to workout mode with loaded workout - main.py will detect and start pose estimation")

            # Get first exercise info
            first_exercise_desc = session.get_current_exercise_description()

            return None, f"Workout started. Today's workout: {workout['workout_name']}. First exercise: {first_exercise_desc}. Inform the user enthusiastically and let them know you're tracking their form and counting reps."

        except Exception as e:
            print(f"[WORKOUT ERROR] Failed to load workout: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Tell the user: 'Hmm, I'm having trouble loading your workout right now. Let's try again in a moment.' Keep it reassuring."
        finally:
            db.close()

    @function_tool
    async def view_schedule(self, days_ahead: int = 7, context: RunContext = None):
        """
        Call this when the user wants to see their upcoming workout schedule.
        This includes requests about when workouts are scheduled, what's coming up,
        viewing the calendar, or planning ahead.

        Args:
            days_ahead: Number of days to look ahead (default 7)
        """
        print(f"[MAIN MENU] User requested schedule (next {days_ahead} days)")

        from db.database import SessionLocal
        from db.schedule_utils import get_upcoming_workouts
        from datetime import datetime

        db = SessionLocal()
        try:
            user = self.state.get_user()
            user_id = user.get("id")
            name = user.get("name", "there")

            workouts = get_upcoming_workouts(db, user_id, days_ahead)

            if not workouts:
                return None, f"The user has no workouts scheduled in the next {days_ahead} days. Suggest creating a new program or offer to help with other options."

            # Build schedule summary
            schedule_list = []
            for w in workouts:
                # Parse date for natural language
                date_obj = datetime.fromisoformat(w['scheduled_date'])
                date_display = date_obj.strftime("%A, %B %d")  # e.g., "Monday, November 4"

                status = "completed" if w['completed'] else "scheduled"
                schedule_list.append(
                    f"{date_display}: {w['workout_name']} ({status})"
                )

            schedule_text = "\n".join(schedule_list)

            return None, f"The user wants to see their schedule. Tell them they have {len(workouts)} workouts in the next {days_ahead} days:\n{schedule_text}\n\nKeep the delivery natural and conversational."

        except Exception as e:
            print(f"[SCHEDULE ERROR] Failed to load schedule: {e}")
            import traceback
            traceback.print_exc()
            return None, "There was an error loading the schedule. Apologize and suggest trying again."
        finally:
            db.close()

    @function_tool
    async def view_workout_exercises(self, context: RunContext, date_text: str = "today"):
        """
        Call this when the user wants to see the exercises in their workout for a specific day.
        This includes requests like "what exercises do I have today", "show me my workout",
        "what's in tomorrow's session", "tell me the exercises for monday", "what's my next workout".

        Args:
            date_text: The day to view. YOU (the LLM) should interpret what the user means:
                      - If they say "today" → pass "today"
                      - If they say "tomorrow" → pass "tomorrow"
                      - If they say "next workout" or similar → use your judgment (probably "tomorrow")
                      - If they say a day name → pass it (e.g., "monday", "friday")
                      Supported formats: "today", "tomorrow", "monday", "next friday", "in 3 days"
        """
        print(f"[MAIN MENU] User requested exercises for: {date_text}")

        from db.database import SessionLocal
        from db.schedule_utils import get_upcoming_workouts
        from datetime import datetime, date, timedelta
        from utils.date_parser import parse_natural_date, DateParseError

        db = SessionLocal()
        try:
            user = self.state.get_user()
            user_id = user.get("id")
            name = user.get("name", "there")

            # Parse the date
            try:
                target_date = parse_natural_date(date_text)
            except DateParseError as e:
                print(f"[WORKOUT VIEW] Date parsing failed: {e}")
                # Ask the LLM to interpret and retry
                return None, f"I had trouble understanding '{date_text}' as a date. Please call this function again with a clearer date like 'today', 'tomorrow', or a day of the week."

            # Get workout for that date
            from db.models import Schedule, Workout, WorkoutExercise, Exercise, Set
            from sqlalchemy import and_
            from sqlalchemy.orm import joinedload

            schedule = db.query(Schedule).options(
                joinedload(Schedule.workout).joinedload(Workout.workout_exercises).joinedload(WorkoutExercise.exercise),
                joinedload(Schedule.workout).joinedload(Workout.workout_exercises).joinedload(WorkoutExercise.sets)
            ).filter(
                and_(
                    Schedule.user_id == user_id,
                    Schedule.scheduled_date == target_date
                )
            ).first()

            if not schedule:
                date_str = target_date.strftime("%A, %B %d")
                return None, f"No workout scheduled for {date_str}. Suggest viewing their schedule or creating a program."

            workout = schedule.workout

            # Build exercise list
            exercise_list = []
            for we in sorted(workout.workout_exercises, key=lambda x: x.order_number):
                ex_name = we.exercise.name if we.exercise else "Unknown Exercise"
                sets_count = len(we.sets)

                # Get rep range from sets
                if we.sets:
                    reps = [s.reps for s in we.sets if s.reps]
                    if reps:
                        if min(reps) == max(reps):
                            rep_info = f"{reps[0]} reps"
                        else:
                            rep_info = f"{min(reps)}-{max(reps)} reps"
                    else:
                        rep_info = "reps not specified"
                else:
                    rep_info = "no sets"

                exercise_info = f"{ex_name}: {sets_count} sets of {rep_info}"

                # Add notes if present
                if we.notes:
                    exercise_info += f" ({we.notes})"

                exercise_list.append(exercise_info)

            exercises_text = "\n".join([f"{i+1}. {ex}" for i, ex in enumerate(exercise_list)])

            date_str = target_date.strftime("%A, %B %d")

            return None, f"Workout for {date_str} - {workout.name}:\n\n{exercises_text}\n\nPresent this information naturally and conversationally."

        except Exception as e:
            print(f"[WORKOUT VIEW ERROR] Failed to load exercises: {e}")
            import traceback
            traceback.print_exc()
            return None, "There was an error loading the workout details. Apologize and suggest trying again."
        finally:
            db.close()

    # ===== SCHEDULE MODIFICATION TOOLS =====

    @function_tool
    async def move_workout_to_date(
        self,
        context: RunContext,
        workout_description: str,
        target_date_text: str
    ):
        """
        Move a specific workout to a new date (NO cascading).

        User examples:
        - "move this week's leg day to tomorrow"
        - "move tuesday's workout to friday"
        - "reschedule today's workout to next monday"

        Args:
            workout_description: Description of workout to move (e.g., "leg day", "tuesday's workout", "today's workout")
            target_date_text: Natural language target date (e.g., "tomorrow", "next friday", "in 3 days")
        """
        from db.database import SessionLocal
        from db.schedule_utils import find_schedule_by_criteria, move_workout
        from utils.date_parser import parse_natural_date, get_date_description, DateParseError
        from datetime import date, timedelta

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        db = SessionLocal()
        try:
            # Parse target date
            try:
                target_date = parse_natural_date(target_date_text)
            except DateParseError as e:
                return None, f"I couldn't understand the date '{target_date_text}'. Could you say it differently? For example: 'tomorrow', 'next Monday', or 'in 3 days'."

            # Find the workout to move
            source_date = None
            workout_name_hint = None

            if "today" in workout_description.lower():
                source_date = date.today()
            elif "tomorrow" in workout_description.lower():
                source_date = date.today() + timedelta(days=1)

            # Check for day names
            for day_name in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                if day_name in workout_description.lower():
                    source_date = parse_natural_date(day_name)
                    break

            # Extract workout type hints
            if "leg" in workout_description.lower():
                workout_name_hint = "leg"
            elif "upper" in workout_description.lower():
                workout_name_hint = "upper"
            elif "push" in workout_description.lower():
                workout_name_hint = "push"
            elif "pull" in workout_description.lower():
                workout_name_hint = "pull"

            # Search for matching workouts
            matches = find_schedule_by_criteria(
                db, user_id,
                target_date=source_date,
                workout_name_fragment=workout_name_hint
            )

            if len(matches) == 0:
                return None, f"I couldn't find a workout matching '{workout_description}'. Could you be more specific?"

            if len(matches) > 1:
                # Multiple matches - ask for clarification
                workout_list = ", ".join([f"{w.workout.name} on {w.scheduled_date}" for w in matches[:3]])
                return None, f"I found multiple workouts: {workout_list}. Which one did you mean?"

            # Single match - move it
            schedule = matches[0]
            success, error_msg = move_workout(db, schedule.id, target_date)

            if not success:
                return None, f"I couldn't move that workout. {error_msg}"

            target_desc = get_date_description(target_date)
            return None, f"Done! I moved '{schedule.workout.name}' to {target_desc}. Your schedule is updated."

        except Exception as e:
            print(f"[ERROR] move_workout_to_date failed: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Sorry {name}, I ran into an issue moving that workout. Let's try again."
        finally:
            db.close()

    @function_tool
    async def swap_two_workouts(
        self,
        context: RunContext,
        workout1_description: str,
        workout2_description: str
    ):
        """
        Swap two individual workouts by exchanging their dates.

        User examples:
        - "swap tuesday and thursday's workout"
        - "swap today's workout with friday's"
        - "swap my leg day and push day"

        Args:
            workout1_description: First workout (e.g., "tuesday's workout", "leg day")
            workout2_description: Second workout (e.g., "thursday's workout", "push day")
        """
        from db.database import SessionLocal
        from db.schedule_utils import find_schedule_by_criteria, swap_workouts
        from utils.date_parser import parse_natural_date
        from datetime import date, timedelta

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        db = SessionLocal()
        try:
            # Helper function to find workout
            def find_workout(description: str):
                source_date = None
                workout_name_hint = None

                # Parse date hints
                if "today" in description.lower():
                    source_date = date.today()
                elif "tomorrow" in description.lower():
                    source_date = date.today() + timedelta(days=1)

                for day_name in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                    if day_name in description.lower():
                        source_date = parse_natural_date(day_name)
                        break

                # Parse workout type hints
                for hint in ['leg', 'upper', 'lower', 'push', 'pull', 'chest', 'back', 'shoulder']:
                    if hint in description.lower():
                        workout_name_hint = hint
                        break

                return find_schedule_by_criteria(db, user_id, target_date=source_date, workout_name_fragment=workout_name_hint)

            # Find both workouts
            matches1 = find_workout(workout1_description)
            matches2 = find_workout(workout2_description)

            if len(matches1) == 0 or len(matches2) == 0:
                return None, f"I couldn't find both workouts. Could you be more specific about which workouts to swap?"

            if len(matches1) > 1 or len(matches2) > 1:
                return None, f"I found multiple matches. Could you specify the exact dates? Like 'swap Tuesday's and Thursday's workout'."

            # Swap them
            success, error_msg = swap_workouts(db, matches1[0].id, matches2[0].id)

            if not success:
                return None, f"I couldn't swap those workouts. {error_msg}"

            return None, f"Done! I swapped '{matches1[0].workout.name}' and '{matches2[0].workout.name}'. Your schedule is updated."

        except Exception as e:
            print(f"[ERROR] swap_two_workouts failed: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Sorry {name}, I ran into an issue swapping those workouts. Let's try again."
        finally:
            db.close()

    @function_tool
    async def swap_entire_weeks(
        self,
        context: RunContext,
        week1_description: str,
        week2_description: str
    ):
        """
        Swap ALL workouts between two weeks.

        User examples:
        - "swap next week and the week after"
        - "swap this week with next week"

        Args:
            week1_description: First week (e.g., "this week", "next week")
            week2_description: Second week (e.g., "the week after", "next week")
        """
        from db.database import SessionLocal
        from db.schedule_utils import swap_weeks
        from utils.date_parser import parse_week_range, DateParseError

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        db = SessionLocal()
        try:
            # Parse week ranges
            try:
                week1_start, week1_end = parse_week_range(week1_description)
                week2_start, week2_end = parse_week_range(week2_description)
            except DateParseError as e:
                return None, f"I couldn't understand those week descriptions. Could you say it like 'this week and next week'?"

            # Swap weeks
            success, error_msg, swapped_pairs = swap_weeks(db, user_id, week1_start, week2_start)

            if not success:
                return None, f"I couldn't swap those weeks. {error_msg}"

            return None, f"Done! I swapped all workouts between {week1_description} and {week2_description}. {len(swapped_pairs)} workouts were moved."

        except Exception as e:
            print(f"[ERROR] swap_entire_weeks failed: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Sorry {name}, I ran into an issue swapping those weeks. Let's try again."
        finally:
            db.close()

    @function_tool
    async def skip_workout_today(
        self,
        context: RunContext,
        reason: str = None
    ):
        """
        Skip a workout (does NOT reschedule automatically).
        Preserves the workout in history for adherence tracking.

        User examples:
        - "I'm tired, skip today's workout"
        - "skip this workout, I need rest"
        - "I can't do today's workout"

        Args:
            reason: Optional reason for skipping (e.g., "tired", "injured", "travel")
        """
        from db.database import SessionLocal
        from db.schedule_utils import get_todays_workout, skip_workout

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        db = SessionLocal()
        try:
            # Get today's workout
            workout = get_todays_workout(db, user_id)

            if not workout:
                return None, f"{name}, you don't have a workout scheduled today. Would you like to see your upcoming schedule?"

            # Skip it
            success, error_msg = skip_workout(db, workout["schedule_id"], reason=reason)

            if not success:
                return None, f"I couldn't skip that workout. {error_msg}"

            return None, f"No problem, {name}. I've marked today's workout as skipped. Rest up and we'll get back to it next time!"

        except Exception as e:
            print(f"[ERROR] skip_workout_today failed: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Sorry {name}, I ran into an issue. Let's try again."
        finally:
            db.close()

    @function_tool
    async def add_rest_day_and_shift(
        self,
        context: RunContext,
        rest_date_text: str
    ):
        """
        Add a rest day and shift future workouts forward.

        User examples:
        - "add a rest day tomorrow"
        - "I need rest on friday, push everything back"

        Args:
            rest_date_text: Natural language date for rest day (e.g., "tomorrow", "friday")
        """
        from db.database import SessionLocal
        from db.schedule_utils import add_rest_day
        from utils.date_parser import parse_natural_date, get_date_description, DateParseError

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        db = SessionLocal()
        try:
            # Parse date
            try:
                rest_date = parse_natural_date(rest_date_text)
            except DateParseError as e:
                return None, f"I couldn't understand '{rest_date_text}'. Could you say it differently?"

            # Add rest day
            success, error_msg, shifted_count = add_rest_day(db, user_id, rest_date, shift_future_workouts=True)

            if not success:
                return None, f"I couldn't add a rest day. {error_msg}"

            rest_desc = get_date_description(rest_date)
            return None, f"Done! I added a rest day on {rest_desc} and pushed {shifted_count} future workouts forward by one day."

        except Exception as e:
            print(f"[ERROR] add_rest_day_and_shift failed: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Sorry {name}, I ran into an issue. Let's try again."
        finally:
            db.close()

    @function_tool
    async def repeat_workout_on_date(
        self,
        context: RunContext,
        workout_description: str,
        repeat_date_text: str
    ):
        """
        Duplicate a workout to another date.

        User examples:
        - "repeat today's workout on friday"
        - "I want to do leg day again next week"

        Args:
            workout_description: Workout to repeat (e.g., "today's workout", "leg day")
            repeat_date_text: Date to repeat on (e.g., "friday", "next monday")
        """
        from db.database import SessionLocal
        from db.schedule_utils import find_schedule_by_criteria, repeat_workout
        from utils.date_parser import parse_natural_date, get_date_description, DateParseError
        from datetime import date

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        db = SessionLocal()
        try:
            # Parse repeat date
            try:
                repeat_date = parse_natural_date(repeat_date_text)
            except DateParseError as e:
                return None, f"I couldn't understand '{repeat_date_text}'. Could you say it differently?"

            # Find workout to repeat
            source_date = None
            workout_name_hint = None

            if "today" in workout_description.lower():
                source_date = date.today()

            for hint in ['leg', 'upper', 'lower', 'push', 'pull']:
                if hint in workout_description.lower():
                    workout_name_hint = hint
                    break

            matches = find_schedule_by_criteria(db, user_id, target_date=source_date, workout_name_fragment=workout_name_hint)

            if len(matches) == 0:
                return None, f"I couldn't find a workout matching '{workout_description}'."

            if len(matches) > 1:
                return None, f"I found multiple matches. Could you be more specific?"

            # Repeat it
            success, error_msg, new_schedule_id = repeat_workout(db, matches[0].id, repeat_date)

            if not success:
                return None, f"I couldn't repeat that workout. {error_msg}"

            repeat_desc = get_date_description(repeat_date)
            return None, f"Done! I added '{matches[0].workout.name}' on {repeat_desc}."

        except Exception as e:
            print(f"[ERROR] repeat_workout_on_date failed: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Sorry {name}, I ran into an issue. Let's try again."
        finally:
            db.close()

    @function_tool
    async def apply_deload_to_week(
        self,
        context: RunContext,
        week_description: str,
        intensity_percentage: int = 70
    ):
        """
        Apply deload to a week (reduce intensity for recovery).

        User examples:
        - "make next week a deload week"
        - "reduce intensity to 60% this week"

        Args:
            week_description: Week to deload (e.g., "this week", "next week")
            intensity_percentage: Target intensity as percentage (default 70%)
        """
        from db.database import SessionLocal
        from db.schedule_utils import apply_deload_week
        from utils.date_parser import parse_week_range, DateParseError

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        db = SessionLocal()
        try:
            # Parse week
            try:
                week_start, week_end = parse_week_range(week_description)
            except DateParseError as e:
                return None, f"I couldn't understand '{week_description}'. Could you say 'this week' or 'next week'?"

            # Validate intensity
            if not (30 <= intensity_percentage <= 100):
                return None, f"Intensity should be between 30% and 100%. Did you mean {intensity_percentage}%?"

            # Apply deload
            intensity_modifier = intensity_percentage / 100.0
            success, error_msg, modified_count = apply_deload_week(db, user_id, week_start, intensity_modifier)

            if not success:
                return None, f"I couldn't apply deload. {error_msg}"

            return None, f"Done! I set {week_description} as a deload week at {intensity_percentage}% intensity. {modified_count} workouts were modified."

        except Exception as e:
            print(f"[ERROR] apply_deload_to_week failed: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Sorry {name}, I ran into an issue. Let's try again."
        finally:
            db.close()

    @function_tool
    async def clear_schedule_for_vacation(
        self,
        context: RunContext,
        start_date_text: str,
        end_date_text: str
    ):
        """
        Clear workouts in a date range (vacation mode).

        User examples:
        - "I'm on vacation from Dec 24th to Jan 2nd, clear my schedule"
        - "remove all workouts next week"

        Args:
            start_date_text: Vacation start date
            end_date_text: Vacation end date
        """
        from db.database import SessionLocal
        from db.schedule_utils import clear_date_range
        from utils.date_parser import parse_natural_date, DateParseError

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        db = SessionLocal()
        try:
            # Parse dates
            try:
                start_date = parse_natural_date(start_date_text)
                end_date = parse_natural_date(end_date_text)
            except DateParseError as e:
                return None, f"I couldn't understand those dates. Could you say them differently?"

            # Clear range
            success, error_msg, cleared_count = clear_date_range(db, user_id, start_date, end_date, preserve_completed=True)

            if not success:
                return None, f"I couldn't clear that range. {error_msg}"

            return None, f"Done! I cleared {cleared_count} workouts from {start_date} to {end_date}. Enjoy your break, {name}!"

        except Exception as e:
            print(f"[ERROR] clear_schedule_for_vacation failed: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Sorry {name}, I ran into an issue. Let's try again."
        finally:
            db.close()

    @function_tool
    async def push_remaining_week_forward(
        self,
        context: RunContext,
        days: int = 1
    ):
        """
        Push remaining workouts this week forward by N days.

        User examples:
        - "push the rest of this week forward by 2 days"
        - "I need extra recovery, shift this week's remaining workouts"

        Args:
            days: Number of days to shift forward (default: 1)
        """
        from db.database import SessionLocal
        from db.schedule_utils import reschedule_remaining_week

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        db = SessionLocal()
        try:
            # Validate days
            if not (1 <= days <= 7):
                return None, f"I can only shift workouts by 1-7 days. Did you mean {days} days?"

            # Reschedule
            success, error_msg, rescheduled_count = reschedule_remaining_week(db, user_id, days_offset=days)

            if not success:
                return None, f"I couldn't reschedule those workouts. {error_msg}"

            return None, f"Done! I pushed {rescheduled_count} remaining workouts forward by {days} day{'s' if days > 1 else ''}."

        except Exception as e:
            print(f"[ERROR] push_remaining_week_forward failed: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Sorry {name}, I ran into an issue. Let's try again."
        finally:
            db.close()

    @function_tool
    async def undo_last_schedule_change(
        self,
        context: RunContext
    ):
        """
        Undo the last schedule change made by the user.

        User examples:
        - "undo that"
        - "nevermind"
        - "go back"
        - "undo the last change"

        Returns user-friendly confirmation or error message.
        """
        from db.database import SessionLocal
        from db.schedule_history import undo_last_change

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        db = SessionLocal()
        try:
            success, error_msg = undo_last_change(db, user_id)

            if not success:
                return None, f"{error_msg}"

            return None, f"Done! I've undone your last change."

        except Exception as e:
            print(f"[ERROR] undo_last_schedule_change failed: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Sorry {name}, I ran into an issue undoing that change. Let's try again."
        finally:
            db.close()

    @function_tool
    async def view_schedule_change_history(
        self,
        context: RunContext,
        limit: int = 5
    ):
        """
        View recent schedule changes made by the user.

        User examples:
        - "what did I change recently?"
        - "show me my recent changes"
        - "what changes have I made?"

        Args:
            limit: Number of recent changes to show (default: 5, max: 10)

        Returns formatted list of recent changes.
        """
        from db.database import SessionLocal
        from db.schedule_history import get_recent_changes, format_change_for_display

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        db = SessionLocal()
        try:
            # Validate limit
            if not (1 <= limit <= 10):
                limit = 5

            changes = get_recent_changes(db, user_id, limit=limit)

            if not changes:
                return None, "You haven't made any schedule changes yet."

            # Format changes for display
            response = f"Here are your {len(changes)} most recent schedule changes:\n\n"
            for i, change in enumerate(changes, 1):
                formatted = format_change_for_display(change)
                response += f"{i}. {formatted}\n"

            return None, response.strip()

        except Exception as e:
            print(f"[ERROR] view_schedule_change_history failed: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Sorry {name}, I ran into an issue retrieving your change history."
        finally:
            db.close()

    @function_tool
    async def analyze_schedule_for_recovery(
        self,
        context: RunContext
    ):
        """
        Analyze the user's schedule for recovery issues and suggest rest days.

        User examples:
        - "analyze my schedule"
        - "suggest rest days"
        - "check if I need rest"
        - "is my schedule good for recovery?"

        Provides quality score and specific rest day recommendations.
        """
        from db.database import SessionLocal
        from db.recovery_analysis import analyze_schedule_recovery, format_recommendation_for_display

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        db = SessionLocal()
        try:
            # Analyze schedule
            analysis = analyze_schedule_recovery(db, user_id)

            # Build response
            response = f"{analysis['analysis_summary']}\n\n"

            if analysis["recommendations"]:
                response += f"I found {len(analysis['recommendations'])} recovery concerns:\n\n"
                for i, rec in enumerate(analysis["recommendations"][:3], 1):  # Show top 3
                    formatted = format_recommendation_for_display(rec)
                    response += f"{i}. {formatted}\n\n"

                response += "Would you like me to add these rest days to your schedule?"
            else:
                response += "No rest day recommendations - keep up the great work!"

            return None, response.strip()

        except Exception as e:
            print(f"[ERROR] analyze_schedule_for_recovery failed: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Sorry {name}, I ran into an issue analyzing your schedule."
        finally:
            db.close()

    @function_tool
    async def apply_recommended_rest_days(
        self,
        context: RunContext,
        shift_future_workouts: bool = True
    ):
        """
        Apply the recommended rest days from schedule analysis.

        User examples:
        - "yes, add those rest days"
        - "apply the recommendations"
        - "add the suggested rest days"

        Args:
            shift_future_workouts: Whether to push future workouts forward (default: True)
        """
        from db.database import SessionLocal
        from db.recovery_analysis import apply_all_recommended_rest_days

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        db = SessionLocal()
        try:
            success, error, added_count = apply_all_recommended_rest_days(
                db, user_id, max_rest_days=3, shift_future_workouts=shift_future_workouts
            )

            if not success:
                return None, f"{error}"

            shift_msg = " and shifted future workouts" if shift_future_workouts else ""
            return None, f"Done! I added {added_count} rest day{'s' if added_count != 1 else ''}{shift_msg}. Your recovery should be much better now!"

        except Exception as e:
            print(f"[ERROR] apply_recommended_rest_days failed: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Sorry {name}, I ran into an issue adding those rest days."
        finally:
            db.close()

    @function_tool
    async def check_if_deload_needed(
        self,
        context: RunContext
    ):
        """
        Check if the user needs a deload week based on training load analysis.

        User examples:
        - "do I need a deload week?"
        - "check my training load"
        - "should I deload?"
        - "am I overtrained?"

        Analyzes fatigue score, velocity decline, RPE trends, and time since last deload.
        """
        from db.database import SessionLocal
        from db.training_load import check_deload_recommendation

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        db = SessionLocal()
        try:
            needs_deload, recommendation, reason = check_deload_recommendation(db, user_id)

            if not needs_deload:
                return None, f"Good news! You don't need a deload right now. {reason}"

            # Build response
            response = "Based on your training load, I recommend a deload week:\n\n"
            response += f"📊 Fatigue Score: {recommendation.get('fatigue_score', 'N/A')}/100\n"
            response += f"📅 Recommended Week: {recommendation['week_start'].strftime('%b %d')} - {recommendation['week_end'].strftime('%b %d')}\n"
            response += f"💪 Intensity: {int(recommendation['intensity_modifier'] * 100)}% of normal\n\n"
            response += "Reasons:\n"
            for r in recommendation['trigger_reasons']:
                response += f"  • {r}\n"

            response += "\nWould you like me to apply this deload week to your schedule?"

            return None, response.strip()

        except Exception as e:
            print(f"[ERROR] check_if_deload_needed failed: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Sorry {name}, I ran into an issue checking your training load."
        finally:
            db.close()

    @function_tool
    async def apply_deload_week_recommendation(
        self,
        context: RunContext
    ):
        """
        Apply the recommended deload week from training load analysis.

        User examples:
        - "yes, apply the deload"
        - "add that deload week"
        - "yes please"
        """
        from db.database import SessionLocal
        from db.training_load import check_deload_recommendation, apply_deload_recommendation

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        db = SessionLocal()
        try:
            # Get recommendation
            needs_deload, recommendation, reason = check_deload_recommendation(db, user_id)

            if not needs_deload:
                return None, f"There's no deload recommendation right now. {reason}"

            # Apply it
            success, error = apply_deload_recommendation(db, user_id, recommendation)

            if not success:
                return None, f"I couldn't apply the deload week. {error}"

            intensity_pct = int(recommendation['intensity_modifier'] * 100)
            week_str = recommendation['week_start'].strftime('%b %d')

            return None, f"Done! I've applied a {intensity_pct}% deload week starting {week_str}. Focus on recovery and lighter training this week!"

        except Exception as e:
            print(f"[ERROR] apply_deload_week_recommendation failed: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Sorry {name}, I ran into an issue applying the deload week."
        finally:
            db.close()

    @function_tool
    async def view_training_load_history(
        self,
        context: RunContext,
        weeks: int = 4
    ):
        """
        View recent training load metrics and fatigue trends.

        User examples:
        - "show me my training load"
        - "what's my fatigue score?"
        - "view my training history"

        Args:
            weeks: Number of weeks to show (default: 4)
        """
        from db.database import SessionLocal
        from db.models import TrainingLoadMetrics
        from sqlalchemy import desc

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        db = SessionLocal()
        try:
            # Validate weeks
            if not (1 <= weeks <= 12):
                weeks = 4

            # Get recent metrics
            metrics = db.query(TrainingLoadMetrics).filter(
                TrainingLoadMetrics.user_id == user_id
            ).order_by(desc(TrainingLoadMetrics.week_start_date)).limit(weeks).all()

            if not metrics:
                return None, "I don't have any training load data for you yet. Complete some workouts and I'll start tracking!"

            response = f"Here's your training load for the past {len(metrics)} weeks:\n\n"

            for m in metrics:
                week_str = m.week_start_date.strftime('%b %d')
                response += f"📅 Week of {week_str}:\n"
                response += f"  • Workouts: {m.workouts_completed}\n"
                response += f"  • Total Sets: {m.total_sets}\n"
                response += f"  • Volume: {float(m.total_volume_kg):.0f} kg\n"
                if m.avg_rpe:
                    response += f"  • Avg RPE: {float(m.avg_rpe):.1f}/10\n"
                if m.fatigue_score:
                    response += f"  • Fatigue Score: {float(m.fatigue_score):.1f}/100\n"
                if m.velocity_decline_percent:
                    response += f"  • Velocity Decline: {float(m.velocity_decline_percent):.1f}%\n"
                response += "\n"

            return None, response.strip()

        except Exception as e:
            print(f"[ERROR] view_training_load_history failed: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Sorry {name}, I ran into an issue retrieving your training load."
        finally:
            db.close()

    @function_tool
    async def view_progress(self, context: RunContext):
        """
        Call this when the user wants to view their progress, stats, or history.
        This includes requests about performance trends, personal records, or past workouts.
        """
        print("[MAIN MENU] User requested to view progress")

        # TODO: Fetch actual progress data from database
        user = self.state.get_user()
        name = user.get("name", "there")

        # For now, placeholder response
        return None, f"The user wants to see their progress. Acknowledge their request and let them know this feature is coming soon - they'll be able to see workout history, personal records, and progress charts. Keep it encouraging."

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
        return None, f"The user wants to update their profile. Say something like: '{name}, profile updates are coming soon! For now, you can ask me to change specific things and I'll note them down.' Keep it helpful."

    def _extract_program_params_from_request(self, user_request: str) -> dict:
        """
        Extract program parameters from natural language request using intelligent parsing.

        Args:
            user_request: The user's full request (e.g., "build me a 6 week program to get my butt bigger")

        Returns:
            dict with extracted params (only high-confidence extractions)
        """
        import re
        from datetime import datetime, timedelta

        extracted = {}
        request_lower = user_request.lower()

        # Extract GOAL/CATEGORY
        hypertrophy_keywords = ['muscle', 'bigger', 'size', 'mass', 'hypertrophy', 'bulk', 'grow', 'butt', 'glutes', 'chest', 'arms', 'legs', 'aesthetic', 'look good', 'shredded', 'toned']
        strength_keywords = ['stronger', 'strength', 'powerlifting', 'max', '1rm', 'heavy', 'strong']
        power_keywords = ['explosive', 'power', 'jump', 'vertical', 'sprint', 'athletics', 'speed', 'fast', 'quick']

        hypertrophy_score = sum(1 for kw in hypertrophy_keywords if kw in request_lower)
        strength_score = sum(1 for kw in strength_keywords if kw in request_lower)
        power_score = sum(1 for kw in power_keywords if kw in request_lower)

        if max(hypertrophy_score, strength_score, power_score) > 0:
            if hypertrophy_score > strength_score and hypertrophy_score > power_score:
                extracted['goal'] = 'hypertrophy'
            elif strength_score > hypertrophy_score and strength_score > power_score:
                extracted['goal'] = 'strength'
            elif power_score > hypertrophy_score and power_score > strength_score:
                extracted['goal'] = 'power'

        # Extract DURATION (weeks)
        # Pattern: "X weeks", "X week", "X months", "X month"
        week_match = re.search(r'(\d+)\s*(?:weeks?|wks?)', request_lower)
        if week_match:
            extracted['duration'] = int(week_match.group(1))
        else:
            # Check for months
            month_match = re.search(r'(\d+)\s*months?', request_lower)
            if month_match:
                extracted['duration'] = int(month_match.group(1)) * 4  # Convert to weeks

        # Pattern: "by [date/event]" - calculate weeks from now
        # E.g., "before christmas", "by the time season starts in 2 months"
        if 'christmas' in request_lower and 'duration' not in extracted:
            # Calculate weeks until Dec 25
            today = datetime.now()
            christmas = datetime(today.year if today.month < 12 else today.year + 1, 12, 25)
            weeks_until = max(1, int((christmas - today).days / 7))
            if weeks_until <= 52:  # Reasonable range
                extracted['duration'] = weeks_until

        # Extract TRAINING FREQUENCY
        # Pattern: "X days a week", "X days per week", "Xx per week", "X times a week"
        freq_match = re.search(r'(\d+)\s*(?:days?|times?|x)\s*(?:a|per)?\s*week', request_lower)
        if freq_match:
            extracted['frequency'] = int(freq_match.group(1))

        # Extract USER NOTES (specific preferences)
        notes_parts = []

        # Muscle group emphasis
        if 'glute' in request_lower or 'butt' in request_lower:
            notes_parts.append("glute emphasis")
        if 'chest' in request_lower:
            notes_parts.append("chest emphasis")
        if 'leg' in request_lower:
            notes_parts.append("leg emphasis")
        if 'arm' in request_lower:
            notes_parts.append("arm emphasis")
        if 'back' in request_lower:
            notes_parts.append("back emphasis")

        # Athletic goals
        if 'vertical' in request_lower and 'jump' in request_lower:
            notes_parts.append("vertical jump focus")
        if 'sprint' in request_lower:
            notes_parts.append("sprint speed focus")

        if notes_parts:
            extracted['notes'] = ", ".join(notes_parts)

        # Extract SPORT
        sports = ['basketball', 'football', 'soccer', 'volleyball', 'track', 'baseball', 'powerlifting', 'weightlifting', 'crossfit']
        for sport in sports:
            if sport in request_lower:
                extracted['sport'] = sport
                break

        # Extract INJURIES
        injury_keywords = ['injury', 'injured', 'hurt', 'pain', 'bad knee', 'bad shoulder', 'back pain']
        for kw in injury_keywords:
            if kw in request_lower:
                # Try to extract what's injured
                if 'knee' in request_lower:
                    extracted['injuries'] = "knee issues mentioned"
                elif 'shoulder' in request_lower:
                    extracted['injuries'] = "shoulder issues mentioned"
                elif 'back' in request_lower:
                    extracted['injuries'] = "back issues mentioned"
                else:
                    extracted['injuries'] = "injury mentioned - needs clarification"
                break

        # Extract SESSION DURATION
        # Pattern: "X minute workouts", "X min sessions", "X hour workouts"
        duration_match = re.search(r'(\d+)\s*(?:minute|min)\s*(?:workout|session)', request_lower)
        if duration_match:
            extracted['session_duration'] = int(duration_match.group(1))
        else:
            hour_match = re.search(r'(\d+)\s*hour\s*(?:workout|session)', request_lower)
            if hour_match:
                extracted['session_duration'] = int(hour_match.group(1)) * 60

        return extracted

    @function_tool
    async def create_program(self, context: RunContext, user_request: str = ""):
        """
        Call this IMMEDIATELY when the user wants to create a program.

        User phrases that trigger this function:
        - "create a program"
        - "make a program"
        - "build a program"
        - "create a workout plan"
        - "make a new program"
        - "I want to create a program"
        - "new program"
        - "make me a program"

        IMPORTANT: Pass the user's FULL original message as user_request to enable intelligent parameter extraction.
        Example: user_request="build me a 6 week program to get my butt as big as possible before christmas"

        This will start the program creation flow and guide the user through collecting their information.

        Args:
            user_request: The user's full original request (enables smart parameter extraction)
        """
        print("\n" + "="*80)
        print("[MAIN MENU] create_program() CALLED")
        print(f"[MAIN MENU] User request: {user_request}")
        print("="*80)

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        print(f"[PROGRAM] User: {name} (ID: {user_id})")

        # Extract program parameters from user request
        extracted_params = {}
        if user_request:
            extracted_params = self._extract_program_params_from_request(user_request)
            if extracted_params:
                print(f"[PROGRAM] Extracted parameters: {extracted_params}")

        # Check if user has any existing programs
        db = SessionLocal()
        try:
            has_programs = has_any_programs(db, user_id)
            print(f"[PROGRAM] User has programs: {has_programs}")

            if not has_programs:
                # No programs - switch to program_creation mode
                print("[PROGRAM] User has no programs - switching to program_creation mode")

                # Query and cache user's existing data ONCE before switching modes
                from db.models import User
                db_user = db.query(User).filter(User.id == user_id).first()
                existing_data = {}
                if db_user:
                    # Convert Decimal to float for JSON serialization
                    existing_data = {
                        "height_cm": float(db_user.height_cm) if db_user.height_cm else None,
                        "weight_kg": float(db_user.weight_kg) if db_user.weight_kg else None,
                        "age": int(db_user.age) if db_user.age else None,
                        "sex": db_user.sex
                    }
                    print(f"[PROGRAM] Cached existing user data: height={existing_data.get('height_cm')}, weight={existing_data.get('weight_kg')}, age={existing_data.get('age')}, sex={existing_data.get('sex')}")

                # Store in state to avoid re-querying
                self.state.set("program_creation.existing_data", existing_data)

                # Store extracted parameters with precaptured_ prefix
                if 'goal' in extracted_params:
                    self.state.set("program_creation.precaptured_goal", extracted_params['goal'])
                    self.state.set("program_creation.precaptured_goal_raw", user_request)
                    print(f"[PROGRAM] Pre-captured goal: {extracted_params['goal']}")
                if 'duration' in extracted_params:
                    self.state.set("program_creation.precaptured_duration", extracted_params['duration'])
                    print(f"[PROGRAM] Pre-captured duration: {extracted_params['duration']} weeks")
                if 'frequency' in extracted_params:
                    self.state.set("program_creation.precaptured_frequency", extracted_params['frequency'])
                    print(f"[PROGRAM] Pre-captured frequency: {extracted_params['frequency']} days/week")
                if 'notes' in extracted_params:
                    self.state.set("program_creation.precaptured_notes", extracted_params['notes'])
                    print(f"[PROGRAM] Pre-captured notes: {extracted_params['notes']}")
                if 'sport' in extracted_params:
                    self.state.set("program_creation.precaptured_sport", extracted_params['sport'])
                    print(f"[PROGRAM] Pre-captured sport: {extracted_params['sport']}")
                if 'injuries' in extracted_params:
                    self.state.set("program_creation.precaptured_injuries", extracted_params['injuries'])
                    print(f"[PROGRAM] Pre-captured injuries: {extracted_params['injuries']}")
                if 'session_duration' in extracted_params:
                    self.state.set("program_creation.precaptured_session_duration", extracted_params['session_duration'])
                    print(f"[PROGRAM] Pre-captured session duration: {extracted_params['session_duration']} min")

                self.state.switch_mode("program_creation")
                self.state.save_state()

                # Update agent instructions to program_creation mode
                new_instructions = self._get_program_creation_instructions()
                await self.update_instructions(new_instructions)
                print("[PROGRAM] Updated agent instructions to program_creation mode")

                # Start the program creation flow DIRECTLY - no need for create_program()
                return None, f"Program creation started. You are now in program_creation mode. The 'PARAMETER COLLECTION ORDER' section at the top of your instructions shows the EXACT order to ask questions. Say: 'Oh! Let's create your first program, {name}! I'll ask you a few quick questions.' Then IMMEDIATELY ask Question 1 based on your instructions. Keep it encouraging and conversational."
            else:
                # Has programs - but user said "create", so they likely want to create a NEW one
                # Skip the confirmation and go straight to creating a new program
                print("[PROGRAM] User has existing programs but requested creation - proceeding to create new program")

                # Query and cache user's existing data ONCE before switching modes
                from db.models import User
                db_user = db.query(User).filter(User.id == user_id).first()
                existing_data = {}
                if db_user:
                    # Convert Decimal to float for JSON serialization
                    existing_data = {
                        "height_cm": float(db_user.height_cm) if db_user.height_cm else None,
                        "weight_kg": float(db_user.weight_kg) if db_user.weight_kg else None,
                        "age": int(db_user.age) if db_user.age else None,
                        "sex": db_user.sex
                    }
                    print(f"[PROGRAM] Cached existing user data: height={existing_data.get('height_cm')}, weight={existing_data.get('weight_kg')}, age={existing_data.get('age')}, sex={existing_data.get('sex')}")

                # Store in state to avoid re-querying
                self.state.set("program_creation.existing_data", existing_data)

                # Store extracted parameters with precaptured_ prefix
                if 'goal' in extracted_params:
                    self.state.set("program_creation.precaptured_goal", extracted_params['goal'])
                    self.state.set("program_creation.precaptured_goal_raw", user_request)
                    print(f"[PROGRAM] Pre-captured goal: {extracted_params['goal']}")
                if 'duration' in extracted_params:
                    self.state.set("program_creation.precaptured_duration", extracted_params['duration'])
                    print(f"[PROGRAM] Pre-captured duration: {extracted_params['duration']} weeks")
                if 'frequency' in extracted_params:
                    self.state.set("program_creation.precaptured_frequency", extracted_params['frequency'])
                    print(f"[PROGRAM] Pre-captured frequency: {extracted_params['frequency']} days/week")
                if 'notes' in extracted_params:
                    self.state.set("program_creation.precaptured_notes", extracted_params['notes'])
                    print(f"[PROGRAM] Pre-captured notes: {extracted_params['notes']}")
                if 'sport' in extracted_params:
                    self.state.set("program_creation.precaptured_sport", extracted_params['sport'])
                    print(f"[PROGRAM] Pre-captured sport: {extracted_params['sport']}")
                if 'injuries' in extracted_params:
                    self.state.set("program_creation.precaptured_injuries", extracted_params['injuries'])
                    print(f"[PROGRAM] Pre-captured injuries: {extracted_params['injuries']}")
                if 'session_duration' in extracted_params:
                    self.state.set("program_creation.precaptured_session_duration", extracted_params['session_duration'])
                    print(f"[PROGRAM] Pre-captured session duration: {extracted_params['session_duration']} min")

                # Switch to program_creation mode
                self.state.switch_mode("program_creation")
                self.state.save_state()

                # Update agent instructions to program_creation mode
                new_instructions = self._get_program_creation_instructions()
                await self.update_instructions(new_instructions)
                print("[PROGRAM] Updated agent instructions to program_creation mode")

                # Start the program creation flow
                return None, f"Program creation started. You are now in program_creation mode. The 'PARAMETER COLLECTION ORDER' section at the top of your instructions shows the EXACT order to ask questions. Say: 'I see you already have some programs. Let's create a new one for you, {name}! I'll ask you a few quick questions.' Then IMMEDIATELY start with Question 1 based on your instructions. Keep it encouraging and conversational."

        except Exception as e:
            print(f"[ERROR] Failed to check user programs: {e}")
            return None, f"There was an error checking your programs. Say something like: '{name}, I'm having trouble accessing your programs right now. Let's try again in a moment.' Keep it apologetic."
        finally:
            db.close()

    @function_tool
    async def update_program(self, context: RunContext):
        """
        Call this when the user wants to update or modify an existing program.

        User phrases that trigger this function:
        - "update my program"
        - "modify my program"
        - "change my program"
        - "edit my program"
        - "update program"

        This starts the program update flow where the agent will:
        1. Check if user has programs
        2. Ask which program to update (if multiple)
        3. Ask what they want to change
        4. Generate the update using AI
        """
        print("[MAIN MENU] User requested to update program")

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        # Check if user has any programs
        db = SessionLocal()
        try:
            from db.program_utils import get_program_summary_list

            programs = get_program_summary_list(db, user_id)

            if len(programs) == 0:
                # No programs
                return None, f"Say something like: '{name}, you don't have any programs yet. Would you like to create your first program?' Keep it encouraging."
            elif len(programs) == 1:
                # Exactly one program - proceed with it
                program = programs[0]
                self.state.set("program_update.selected_program_id", program["id"])
                self.state.set("program_update.selected_program_name", program["name"])

                print(f"[PROGRAM UPDATE] User has 1 program: {program['name']} (ID: {program['id']})")

                return None, f"Say something like: 'Sure! I can update your {program['name']} program. What would you like to change about it?' Keep it conversational."
            else:
                # Multiple programs - ask which one
                program_list = ", ".join([f"'{p['name']}'" for p in programs[:3]])  # List first 3
                if len(programs) > 3:
                    program_list += f", and {len(programs) - 3} more"

                # Store programs in state for selection
                self.state.set("program_update.available_programs", programs)

                print(f"[PROGRAM UPDATE] User has {len(programs)} programs")

                return None, f"Say something like: '{name}, you have {len(programs)} programs: {program_list}. Which one would you like to update?' Keep it friendly."

        except Exception as e:
            print(f"[ERROR] Failed to list programs: {e}")
            return None, f"Say something like: '{name}, I'm having trouble accessing your programs right now. Let's try again in a moment.' Keep it apologetic."
        finally:
            db.close()

    @function_tool
    async def select_program_for_update(self, context: RunContext, program_name: str):
        """
        Call this when the user selects which program they want to update (when they have multiple programs).

        Args:
            program_name: The name of the program the user wants to update
        """
        user = self.state.get_user()
        name = user.get("name", "there")

        # Get available programs from state
        programs = self.state.get("program_update.available_programs", [])

        if not programs:
            return None, f"Error: No programs available for selection. Try calling update_program() first."

        # Find matching program (fuzzy match on name)
        selected_program = None
        program_name_lower = program_name.lower()

        for program in programs:
            if program_name_lower in program["name"].lower():
                selected_program = program
                break

        if not selected_program:
            # No match found - list options again
            program_list = ", ".join([f"'{p['name']}'" for p in programs])
            return None, f"I didn't find a program called '{program_name}'. Your programs are: {program_list}. Which one would you like to update?"

        # Store selected program
        self.state.set("program_update.selected_program_id", selected_program["id"])
        self.state.set("program_update.selected_program_name", selected_program["name"])

        print(f"[PROGRAM UPDATE] Selected program: {selected_program['name']} (ID: {selected_program['id']})")

        return None, f"Great! I'll update your {selected_program['name']} program. What would you like to change about it? For example, you could change the training frequency, duration, exercises, or intensity."

    @function_tool
    async def capture_program_change_request(self, context: RunContext, change_request: str):
        """
        Call this when the user describes what they want to change about their program.

        Args:
            change_request: The user's description of what they want to change
        """
        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        # Get selected program
        program_id = self.state.get("program_update.selected_program_id")
        program_name = self.state.get("program_update.selected_program_name")

        if not program_id:
            return None, f"Error: No program selected for update. Call update_program() first."

        # Store change request
        self.state.set("program_update.change_request", change_request)

        print(f"[PROGRAM UPDATE] Change request: {change_request}")

        # Check if this is a safe simple change (title/description only)
        db = SessionLocal()
        try:
            from api.services.simple_program_updates import detect_simple_update, handle_simple_update

            update_type, params = detect_simple_update(change_request)

            if update_type != "requires_llm":
                # Safe simple update - apply immediately
                print(f"[PROGRAM UPDATE] Detected safe simple update: {update_type}")
                success, message = handle_simple_update(db, program_id, change_request)

                if success:
                    # Clear update state
                    self.state.set("program_update", None)
                    return None, f"Say something like: 'Done! {message}. Your {program_name} program has been updated.' Keep it quick and positive."
                else:
                    # Simple update failed
                    print(f"[PROGRAM UPDATE] Simple update failed: {message}")
                    return None, f"Say something like: 'I had trouble updating that. {message}' Keep it apologetic."

            # Training-related change - need LLM validation
            print(f"[PROGRAM UPDATE] Training change detected, validating with LLM...")

            from db.models import User
            db_user = db.query(User).filter(User.id == user_id).first()

            if not db_user:
                return None, f"Error: User not found in database."

            # Validate required user data
            if not db_user.age or not db_user.sex or not db_user.height_cm or not db_user.weight_kg:
                return None, f"Say something like: '{name}, I need some more information about you first. Let me ask you a few quick questions.' Then ask for missing: age, sex, height, weight."

            # Build user profile
            user_profile = {
                "age": int(db_user.age),
                "sex": db_user.sex,
                "height_cm": float(db_user.height_cm),
                "weight_kg": float(db_user.weight_kg),
                "fitness_level": "intermediate"  # Default
            }

            # Get current program for validation
            from api.services.program_updater import _get_current_program_as_json, validate_program_change_with_llm
            current_program = _get_current_program_as_json(db, program_id)
            if not current_program:
                return None, f"Error: Could not load program for validation."

            # Run validation
            validation_result = await validate_program_change_with_llm(
                current_program=current_program,
                change_request=change_request,
                user_profile=user_profile
            )

            is_risky = validation_result.get("is_risky", False)

            if not is_risky:
                # Safe change - proceed directly to update
                print(f"[PROGRAM UPDATE] ✅ Validation passed, proceeding with update")

                # Store user profile for update job
                self.state.set("program_update.user_profile", user_profile)

                return None, f"Got it! I'll update your {program_name} program: '{change_request}'. Now call start_program_update_job() to begin."

            else:
                # Risky change - present warning and alternative
                warning = validation_result.get("warning", "This change may not be ideal for your goals.")
                alternative = validation_result.get("alternative", "")

                print(f"[PROGRAM UPDATE] ⚠️  Risky change detected")
                print(f"[PROGRAM UPDATE]    Warning: {warning}")
                print(f"[PROGRAM UPDATE]    Alternative: {alternative}")

                # Store validation result and user profile
                self.state.set("program_update.validation_result", validation_result)
                self.state.set("program_update.user_profile", user_profile)
                self.state.set("program_update.awaiting_choice", True)

                # Present options to user conversationally
                if alternative:
                    return None, f"Say something like: 'I noticed something about this change. {warning} {alternative} Would you prefer that alternative, or do you still want to go with your original request?' Keep it conversational and helpful."
                else:
                    return None, f"Say something like: 'I need to mention something. {warning} Are you sure you want to make this change?' Keep it concerned but supportive."

        except Exception as e:
            print(f"[ERROR] Failed to process change request: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Error processing change request. Try again."
        finally:
            db.close()

    @function_tool
    async def start_program_update_job(self, context: RunContext, user_response: str = ""):
        """
        Call this to start the program update job after the user has described what they want to change.
        This sends the request to the FastAPI backend for processing.

        Args:
            user_response: Optional - user's response if they were presented with validation choices
        """
        import httpx

        user = self.state.get_user()
        name = user.get("name", "there")

        # Get all required data from state
        program_id = self.state.get("program_update.selected_program_id")
        program_name = self.state.get("program_update.selected_program_name")
        change_request = self.state.get("program_update.change_request")
        user_profile = self.state.get("program_update.user_profile")
        awaiting_choice = self.state.get("program_update.awaiting_choice", False)
        validation_result = self.state.get("program_update.validation_result")

        if not program_id or not change_request or not user_profile:
            return None, f"Error: Missing required data. Ensure capture_program_change_request() was called first."

        # Handle validation choice if pending
        if awaiting_choice and validation_result:
            print(f"[PROGRAM UPDATE] Processing user choice: {user_response}")

            alternative = validation_result.get("alternative", "")
            user_response_lower = user_response.lower()

            # Parse user's choice conversationally
            wants_alternative = any(phrase in user_response_lower for phrase in [
                "alternative", "better", "that sounds good", "yes", "yeah", "sure",
                "front squat", "safety bar", "2 days", "3 days"  # Specific alternatives
            ])

            wants_original = any(phrase in user_response_lower for phrase in [
                "original", "no", "still want", "barbell curl", "1 day", "stick with"
            ])

            cancel = any(phrase in user_response_lower for phrase in [
                "cancel", "never mind", "forget it", "don't"
            ])

            if cancel:
                # User cancelled
                self.state.set("program_update", None)
                return None, f"Say something like: 'No problem! Let me know if you want to make any other changes.' Keep it friendly."

            elif wants_alternative and alternative:
                # Use the LLM's suggested alternative
                print(f"[PROGRAM UPDATE] User chose alternative: {alternative}")
                change_request = alternative  # Override with alternative
            elif wants_original:
                # User insists on original (respect autonomy)
                print(f"[PROGRAM UPDATE] User insists on original request")
                # Keep change_request as is
            else:
                # Ambiguous response - default to alternative if available, otherwise original
                if alternative:
                    print(f"[PROGRAM UPDATE] Ambiguous response, defaulting to alternative")
                    change_request = alternative
                else:
                    print(f"[PROGRAM UPDATE] Ambiguous response, proceeding with original")

            # Clear validation state
            self.state.set("program_update.awaiting_choice", False)
            self.state.set("program_update.validation_result", None)

        print(f"[PROGRAM UPDATE] Starting update job for program {program_id}")
        print(f"[PROGRAM UPDATE] Change: {change_request}")

        try:
            # Call FastAPI endpoint
            fastapi_url = os.getenv("FASTAPI_URL", "http://localhost:8000")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{fastapi_url}/api/programs/{program_id}/update",
                    json={
                        "change_request": change_request,
                        "age": user_profile["age"],
                        "sex": user_profile["sex"],
                        "height_cm": user_profile["height_cm"],
                        "weight_kg": user_profile["weight_kg"],
                        "fitness_level": user_profile["fitness_level"]
                    },
                    timeout=10.0
                )
                data = response.json()
                job_id = data["job_id"]

            # Store job_id in state
            self.state.set("program_update.job_id", job_id)
            print(f"[PROGRAM UPDATE] ✅ Started update job: {job_id}")

            return None, f"Say something like: 'Perfect! I'm updating your {program_name} program now. This will take about a minute. Hang tight!' Wait 45 seconds, then call check_program_update_status()."

        except Exception as e:
            print(f"[PROGRAM UPDATE] ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Error starting update. Say something like: '{name}, I had trouble starting the update. Let me try again.'"

    @function_tool
    async def check_program_update_status(self, context: RunContext):
        """
        Check if the program update is complete.
        Call this after start_program_update_job() to poll for completion.
        """
        import httpx

        user = self.state.get_user()
        name = user.get("name", "there")

        job_id = self.state.get("program_update.job_id")
        program_name = self.state.get("program_update.selected_program_name")

        if not job_id:
            return None, f"No update job found. Call start_program_update_job() first."

        try:
            # Check status via FastAPI
            fastapi_url = os.getenv("FASTAPI_URL", "http://localhost:8000")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{fastapi_url}/api/programs/update-status/{job_id}",
                    timeout=5.0
                )
                data = response.json()

            status = data["status"]
            progress = data.get("progress", 0)

            if status == "completed":
                # Get diff
                diff = data.get("diff") or []

                if diff:
                    diff_summary = "\n".join([f"- {change}" for change in diff])
                    print(f"[PROGRAM UPDATE] ✅ Update complete!")
                    print(f"[PROGRAM UPDATE] Changes:\n{diff_summary}")
                    changes_text = f"Here's what changed:\n{diff_summary}\n"
                else:
                    print(f"[PROGRAM UPDATE] ✅ Update complete!")
                    changes_text = ""

                # Clear update state
                self.state.set("program_update", None)

                return None, f"Say something like: 'Awesome! Your {program_name} program has been updated successfully. {changes_text}Your updated program is ready to go!' Keep it enthusiastic."

            elif status == "failed":
                error = data.get("error_message", "Unknown error")
                print(f"[PROGRAM UPDATE] ❌ Update failed: {error}")
                return None, f"Update failed. Say something like: '{name}, I had trouble updating your program. Let's try again.'"

            else:
                # Still in progress
                print(f"[PROGRAM UPDATE] Update in progress: {progress}%")
                return None, f"Update is {progress}% complete. Wait 15 more seconds, then call check_program_update_status() again. Don't say anything, just wait."

        except Exception as e:
            print(f"[PROGRAM UPDATE] Error checking status: {e}")
            return None, f"Error checking status. Wait 10 seconds and call check_program_update_status() again."

    # ===== PROGRAM CREATION HELPER TOOLS =====

    @function_tool
    async def capture_height_weight(self, context: RunContext, height_value: str = None, weight_value: str = None):
        """
        Call this when the user provides both height and weight together.
        Can also be called without arguments to use existing DB values.
        This is the preferred method for collecting physical stats.

        Args:
            height_value: The height as spoken by the user (e.g., "5'10\"", "175 cm"), or None to use DB value
            weight_value: The weight as spoken by the user (e.g., "185 pounds", "80 kg"), or None to use DB value
        """
        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        # Check database for existing values if not provided
        db = SessionLocal()
        try:
            from db.models import User
            db_user = db.query(User).filter(User.id == user_id).first()

            # If no new values provided, try to use existing DB values
            if height_value is None and weight_value is None and db_user:
                if db_user.height_cm and db_user.weight_kg:
                    print(f"[PROGRAM] Using existing DB values: height={db_user.height_cm} cm, weight={db_user.weight_kg} kg")
                    self.state.set("program_creation.height_cm", float(db_user.height_cm))
                    self.state.set("program_creation.weight_kg", float(db_user.weight_kg))
                    # When loading from DB, we're confirming stats - need to also call capture_age_sex()
                    return None, "Height and weight loaded. Now call capture_age_sex() with no arguments, then ask about their fitness goal."
                else:
                    # DB data incomplete - need to ask for it
                    print(f"[PROGRAM] No complete height/weight data in DB - need to ask user")
                    return None, "No height and weight on file. Ask: 'What's your height and weight?'"

            # Parse new values if provided
            if height_value:
                print(f"[PROGRAM] Capturing new height and weight: {height_value}, {weight_value}")

                height_cm = self._normalize_height_to_cm(height_value)
                if height_cm is None or height_cm < 50 or height_cm > 300:
                    return None, f"That height doesn't seem right. Say: 'Hmm, that height doesn't sound quite right. Can you tell me your height again? For example, five foot nine, or 175 centimeters.' Keep it friendly."

                weight_kg = self._normalize_weight_to_kg(weight_value)
                if weight_kg is None or weight_kg < 30 or weight_kg > 300:
                    return None, f"That weight doesn't seem right. Say: 'Hmm, that weight doesn't sound quite right. Can you tell me your weight again? For example, 185 pounds or 80 kilograms.' Keep it friendly."

                # Save to database
                if db_user:
                    db_user.height_cm = height_cm
                    db_user.weight_kg = weight_kg
                    db.commit()
                    print(f"[PROGRAM] Saved to database: height={height_cm} cm, weight={weight_kg} kg")

                # Save to state
                self.state.set("program_creation.height_cm", height_cm)
                self.state.set("program_creation.weight_kg", weight_kg)

                print(f"[PROGRAM] Height: {height_cm} cm, Weight: {weight_kg} kg")

                return None, "Captured. Immediately ask the next question."

        except Exception as e:
            print(f"[ERROR] Failed to handle height/weight: {e}")
            db.rollback()
        finally:
            db.close()

        return None, f"Error: Could not capture height and weight. Please provide them again."

    @function_tool
    async def capture_age_sex(self, context: RunContext, age: int = None, sex: str = None):
        """
        Call this when the user provides both age and sex together.
        Can also be called without arguments to use existing DB values.
        This is the preferred method for collecting demographics.

        Args:
            age: User's age in years, or None to use DB value
            sex: "male", "female", "M", "F", etc., or None to use DB value
        """
        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        # Check database for existing values if not provided
        db = SessionLocal()
        try:
            from db.models import User
            db_user = db.query(User).filter(User.id == user_id).first()

            # If no new values provided, try to use existing DB values
            if age is None and sex is None and db_user:
                if db_user.age and db_user.sex:
                    print(f"[PROGRAM] Using existing DB values: age={db_user.age}, sex={db_user.sex}")
                    self.state.set("program_creation.age", int(db_user.age))
                    self.state.set("program_creation.sex", db_user.sex)
                    # When loading from DB, stats confirmation is complete - ask about goal
                    return None, "Age and sex loaded. Stats confirmation complete. Immediately ask about their fitness goal."
                else:
                    # DB data incomplete - need to ask for it
                    print(f"[PROGRAM] No complete age/sex data in DB - need to ask user")
                    return None, "No age and sex on file. Ask: 'How old are you, and are you male or female?'"

            # Validate and normalize new values if provided
            if age is not None:
                print(f"[PROGRAM] Capturing new age and sex: {age}, {sex}")

                if age < 13 or age > 100:
                    return None, f"That age seems unusual. Say: 'Hmm, that age doesn't seem right. How old are you?' Keep it friendly."

                # Normalize sex
                sex_normalized = sex.lower().strip()
                if sex_normalized in ["m", "male", "man", "boy"]:
                    sex_normalized = "male"
                elif sex_normalized in ["f", "female", "woman", "girl"]:
                    sex_normalized = "female"
                else:
                    return None, f"I didn't catch the sex. Say: 'Sorry, are you male or female?' Keep it simple."

                # Save to database
                if db_user:
                    db_user.age = age
                    db_user.sex = sex_normalized
                    db.commit()
                    print(f"[PROGRAM] Saved to database: age={age}, sex={sex_normalized}")

                # Save to state
                self.state.set("program_creation.age", age)
                self.state.set("program_creation.sex", sex_normalized)

                print(f"[PROGRAM] Age: {age}, Sex: {sex_normalized}")

                # Check and summarize conversation after basic stats collected (Milestone 1)
                # This prevents context buildup from lengthy stat confirmations
                await self.check_and_summarize_if_needed(context)

                return None, "Captured. Immediately ask the next question."

        except Exception as e:
            print(f"[ERROR] Failed to handle age/sex: {e}")
            db.rollback()
        finally:
            db.close()

        return None, f"Error: Could not capture age and sex. Please provide them again."

    def _normalize_height_to_cm(self, height_str: str) -> float:
        """Convert various height formats to centimeters"""
        import re

        height_str = height_str.lower().strip()

        # Pattern: X cm or X centimeters
        cm_match = re.search(r'(\d+\.?\d*)\s*(cm|centimeter)', height_str)
        if cm_match:
            return float(cm_match.group(1))

        # Pattern: X.XX m or X.XX meters
        m_match = re.search(r'(\d+\.?\d*)\s*(m|meter)', height_str)
        if m_match:
            return float(m_match.group(1)) * 100

        # Pattern: X feet Y inches OR X foot Y inches OR X'Y"
        feet_inches_match = re.search(r"(\d+)\s*(?:feet|foot|ft|')\s*(\d+)\s*(?:inches?|in|\")?", height_str)
        if feet_inches_match:
            feet = int(feet_inches_match.group(1))
            inches = int(feet_inches_match.group(2))
            total_inches = (feet * 12) + inches
            return total_inches * 2.54

        # Pattern: Just feet (e.g., "6 feet" or "5 foot")
        feet_only_match = re.search(r'(\d+)\s*(?:feet|foot|ft)', height_str)
        if feet_only_match:
            feet = int(feet_only_match.group(1))
            return feet * 12 * 2.54

        # Pattern: Just inches
        inches_match = re.search(r'(\d+)\s*(?:inches?|in)', height_str)
        if inches_match:
            inches = int(inches_match.group(1))
            return inches * 2.54

        # Pattern: Just a number - try to infer
        number_match = re.search(r'(\d+\.?\d*)', height_str)
        if number_match:
            num = float(number_match.group(1))
            # If < 10, likely meters (e.g., 1.75)
            if num < 10:
                return num * 100
            # If between 50-300, likely cm
            elif 50 <= num <= 300:
                return num
            # If > 300, likely inches
            elif num > 300:
                return num * 2.54

        return None

    def _normalize_weight_to_kg(self, weight_str: str) -> float:
        """Convert various weight formats to kilograms"""
        import re

        weight_str = weight_str.lower().strip()

        # Pattern: X kg or X kilograms
        kg_match = re.search(r'(\d+\.?\d*)\s*(?:kg|kilogram)', weight_str)
        if kg_match:
            return float(kg_match.group(1))

        # Pattern: X lbs or X pounds
        lbs_match = re.search(r'(\d+\.?\d*)\s*(?:lbs?|pounds?)', weight_str)
        if lbs_match:
            return float(lbs_match.group(1)) * 0.453592

        # Pattern: Just a number - try to infer
        number_match = re.search(r'(\d+\.?\d*)', weight_str)
        if number_match:
            num = float(number_match.group(1))
            # If < 200, likely kg (most people)
            # If >= 200, likely lbs
            if num >= 200:
                return num * 0.453592
            else:
                # Could be either - default to kg for safety
                # Most adult weights in kg are 40-150
                return num

        return None

    @function_tool
    async def capture_goal(self, context: RunContext, goal_description: str):
        """
        Call this when the user describes their fitness goal.
        Accepts free-form input and categorizes it into power, strength, or hypertrophy focus.

        Args:
            goal_description: The user's goal as they described it (e.g., "I want to look good for summer", "get stronger", "improve my vertical jump")
        """
        print(f"[PROGRAM] Capturing goal: {goal_description}")

        # VALIDATION: Check if prerequisites were collected (height, weight, age, sex)
        # HOWEVER: If user has existing data in DB, we allow goals to be asked first
        height_cm = self.state.get("program_creation.height_cm")
        weight_kg = self.state.get("program_creation.weight_kg")
        age = self.state.get("program_creation.age")
        sex = self.state.get("program_creation.sex")

        # Check if user has existing data in their profile
        existing_data = self.state.get("program_creation.existing_data", {})
        has_existing_stats = (existing_data.get("height_cm") and existing_data.get("weight_kg") and
                             existing_data.get("age") and existing_data.get("sex"))

        if not (height_cm and weight_kg and age and sex) and not has_existing_stats:
            print(f"[ERROR] Goal asked before prerequisites! height={height_cm}, weight={weight_kg}, age={age}, sex={sex}, existing_data={has_existing_stats}")
            return None, f"ERROR: You MUST ask for height/weight (Question 1) and age/sex (Question 2) BEFORE asking about goals (Question 3). Go back and ask Questions 1 and 2 first!"

        user = self.state.get_user()
        name = user.get("name", "there")

        # Categorize the goal
        goal_category = self._categorize_goal(goal_description)

        # Store raw description and category in state
        self.state.set("program_creation.goal_raw", goal_description)
        self.state.set("program_creation.goal_category", goal_category)

        print(f"[PROGRAM] Goal categorized as: {goal_category}")

        # Create confirmation message based on category
        if goal_category == "power":
            confirmation = "explosiveness and athletic performance"
        elif goal_category == "strength":
            confirmation = "building maximum strength"
        else:  # hypertrophy
            confirmation = "building muscle and aesthetics"

        # Store for prompt to use
        self.state.set("program_creation.goal_confirmation", confirmation)
        self.state.set("program_creation.recommended_duration", self._get_recommended_duration(goal_category))

        return None, "Goal captured. Immediately ask the next question based on what's missing in state."

    def _categorize_goal(self, goal_text: str) -> str:
        """Categorize user's goal into power, strength, or hypertrophy"""
        goal_lower = goal_text.lower()

        # Power keywords
        power_keywords = [
            "explosive", "power", "athletic", "speed", "jump", "vertical",
            "sprint", "agility", "quick", "fast", "sport", "performance"
        ]

        # Strength keywords
        strength_keywords = [
            "strong", "strength", "lift heavy", "max", "powerlifting",
            "deadlift", "squat", "bench", "1rm", "pr", "personal record"
        ]

        # Hypertrophy keywords
        hypertrophy_keywords = [
            "muscle", "size", "big", "aesthetic", "look good", "beach",
            "summer", "bodybuilding", "bulk", "mass", "tone", "definition",
            "shredded", "ripped", "physique", "gains"
        ]

        # Count keyword matches
        power_score = sum(1 for kw in power_keywords if kw in goal_lower)
        strength_score = sum(1 for kw in strength_keywords if kw in goal_lower)
        hypertrophy_score = sum(1 for kw in hypertrophy_keywords if kw in goal_lower)

        # Return category with highest score
        if power_score > strength_score and power_score > hypertrophy_score:
            return "power"
        elif strength_score > hypertrophy_score:
            return "strength"
        else:
            # Default to hypertrophy if unclear or tied
            return "hypertrophy"

    def _get_recommended_duration(self, goal_category: str) -> int:
        """Get recommended program duration based on goal"""
        if goal_category == "power":
            return 6
        elif goal_category == "strength":
            return 10
        else:  # hypertrophy
            return 12

    @function_tool
    async def capture_program_duration(self, context: RunContext, duration_weeks: int):
        """
        Call this when the user specifies how long they want their program to be.

        Args:
            duration_weeks: Number of weeks for the program (e.g., 8, 12, 16)
        """
        print(f"[PROGRAM] Capturing program duration: {duration_weeks} weeks")

        user = self.state.get_user()
        name = user.get("name", "there")

        # Validate duration
        if duration_weeks < 2 or duration_weeks > 52:
            return None, f"Invalid duration. Say something like: 'Hmm, {duration_weeks} weeks seems a bit off. Most programs work best between 4 and 16 weeks. How long would you like your program to be?' Keep it helpful."

        # Store in state
        self.state.set("program_creation.duration_weeks", duration_weeks)

        print(f"[PROGRAM] Duration set to: {duration_weeks} weeks")

        return None, "Captured. Immediately ask the next question."

    @function_tool
    async def capture_training_frequency(self, context: RunContext, days_per_week: int):
        """
        Call this when the user specifies how many days per week they can train.

        Args:
            days_per_week: Number of training days per week (e.g., 3, 4, 5)
        """
        print(f"[PROGRAM] Capturing training frequency: {days_per_week} days/week")

        user = self.state.get_user()
        name = user.get("name", "there")

        # Validate frequency
        if days_per_week < 1 or days_per_week > 7:
            return None, f"Invalid frequency. Say something like: 'That doesn't sound quite right. How many days per week can you realistically train? Something between 2 and 6 days works best for most people.' Keep it supportive."

        # Store in state
        self.state.set("program_creation.days_per_week", days_per_week)

        print(f"[PROGRAM] Frequency set to: {days_per_week} days/week")

        # Check and summarize conversation after main parameters collected (Milestone 2)
        # Core program structure is now defined, can clear early conversation
        await self.check_and_summarize_if_needed(context)

        return None, "Training frequency captured. Immediately ask the next question."

    @function_tool
    async def capture_session_duration(self, context: RunContext, duration_minutes: int):
        """
        Call this when the user specifies session duration.
        Optional parameter - defaults to 60 minutes if not provided.

        Args:
            duration_minutes: Session duration in minutes (e.g., 60, 90, 45)
        """
        print(f"[PROGRAM] Capturing session duration: {duration_minutes} minutes")

        user = self.state.get_user()
        name = user.get("name", "there")

        # Validate (reasonable range)
        if duration_minutes < 20 or duration_minutes > 180:
            return None, f"That seems unusual. Say: 'Hmm, {duration_minutes} minutes seems a bit off. Most sessions are between 30 and 120 minutes. How much time do you realistically have?' Keep it supportive."

        # Store in state
        self.state.set("program_creation.session_duration", duration_minutes)
        print(f"[PROGRAM] Session duration set to: {duration_minutes} minutes")

        return None, "Captured. Immediately ask the next question."

    @function_tool
    async def capture_injury_history(self, context: RunContext, injury_description: str):
        """
        Call this when the user describes injury history.
        Optional parameter - use "none" if they have no injuries.

        Args:
            injury_description: Description of injuries or "none"
        """
        print(f"[PROGRAM] Capturing injury history: {injury_description}")

        # Store in state
        self.state.set("program_creation.injury_history", injury_description)
        print(f"[PROGRAM] Injury history saved")

        return None, "Captured. Immediately ask the next question."

    @function_tool
    async def capture_specific_sport(self, context: RunContext, sport_name: str):
        """
        Call this when the user specifies a sport they're training for.
        Optional parameter - use "none" for general fitness.

        Args:
            sport_name: Name of sport (e.g., "basketball", "powerlifting") or "none"
        """
        print(f"[PROGRAM] Capturing specific sport: {sport_name}")

        # Normalize to lowercase for consistency
        sport_normalized = sport_name.lower().strip()
        if sport_normalized in ["no", "nothing", "general", "general fitness", "just fitness"]:
            sport_normalized = "none"

        # Store in state
        self.state.set("program_creation.specific_sport", sport_normalized)
        print(f"[PROGRAM] Specific sport set to: {sport_normalized}")

        return None, "Captured. Immediately ask the next question."

    @function_tool
    async def capture_user_notes(self, context: RunContext, notes: str):
        """
        Call this when the user provides additional notes or preferences.
        Optional parameter - can be empty or "none".

        Args:
            notes: User's additional notes/preferences or "none"
        """
        print(f"[PROGRAM] Capturing user notes: {notes}")

        # Store in state
        self.state.set("program_creation.user_notes", notes)
        print(f"[PROGRAM] User notes saved")

        # Check and summarize conversation after all optional parameters collected (Milestone 3)
        # Almost done with collection, keep context lean for final steps
        await self.check_and_summarize_if_needed(context)

        return None, "Captured. Immediately ask the next question."

    @function_tool
    async def capture_age(self, context: RunContext, age: int):
        """
        Call this when the user provides their age.

        Args:
            age: User's age in years
        """
        print(f"[PROGRAM] Capturing age: {age}")

        # Validate age
        if age < 13 or age > 100:
            user = self.state.get_user()
            name = user.get("name", "there")
            return None, f"That age seems unusual. Say: 'Hmm, that doesn't seem right. How old are you?' Keep it friendly."

        # Store in state
        self.state.set("program_creation.age", age)
        print(f"[PROGRAM] Age set to: {age}")

        return None, "Captured. Immediately ask the next question."

    @function_tool
    async def capture_sex(self, context: RunContext, sex: str):
        """
        Call this when the user provides their biological sex.

        Args:
            sex: "male", "female", "M", "F", etc.
        """
        print(f"[PROGRAM] Capturing sex: {sex}")

        # Normalize
        sex_normalized = sex.lower().strip()
        if sex_normalized in ["m", "male", "man", "boy"]:
            sex_normalized = "male"
        elif sex_normalized in ["f", "female", "woman", "girl"]:
            sex_normalized = "female"
        else:
            user = self.state.get_user()
            name = user.get("name", "there")
            return None, f"I didn't catch that. Say: 'Sorry, are you male or female?' Keep it simple."

        # Store in state
        self.state.set("program_creation.sex", sex_normalized)
        print(f"[PROGRAM] Sex set to: {sex_normalized}")

        return None, "Captured. Immediately ask the next question."

    @function_tool
    async def set_vbt_capability(self, context: RunContext, enabled: bool):
        """
        Automatically enable or disable VBT based on training parameters.
        DO NOT call this manually - it's automatically called after capture_fitness_level().

        VBT is enabled when:
        - Fitness level is intermediate or advanced (required)
        - AND one of:
          - Goal is power or athletic_performance
          - Goal is strength AND fitness level is advanced
          - Sport involves explosiveness (sprinting, Olympic lifting, powerlifting, etc.)

        VBT is disabled for:
        - Beginners (always)
        - Hypertrophy-only goals
        - General fitness with no power component

        Args:
            enabled: True to enable VBT programming, False to disable
        """
        print(f"[PROGRAM] Setting VBT capability: {enabled}")

        # Store in state
        self.state.set("program_creation.has_vbt_capability", enabled)

        # Log the decision for debugging
        if enabled:
            print("[PROGRAM] ✅ VBT ENABLED - Program will include velocity-based training")
        else:
            print("[PROGRAM] ❌ VBT DISABLED - Program will use traditional percentage-based loading")

        # Return continuation signal
        return None, "Captured. Immediately ask the next question."

    @function_tool
    async def capture_fitness_level(self, context: RunContext, fitness_level: str):
        """
        Call this when the user describes their fitness level.
        Normalize to beginner, intermediate, or advanced.

        Args:
            fitness_level: The user's fitness level (e.g., "beginner", "intermediate", "I've been lifting for 2 years")
        """
        print(f"[PROGRAM] Capturing fitness level: {fitness_level}")
        print(f"[DEBUG] Step 1: Getting user from state...")

        user = self.state.get_user()
        print(f"[DEBUG] Step 2: User retrieved: {user}")

        name = user.get("name", "there")
        print(f"[DEBUG] Step 3: Name is: {name}")

        # Normalize fitness level
        print(f"[DEBUG] Step 4: Normalizing fitness level...")
        normalized_level = self._normalize_fitness_level(fitness_level)
        print(f"[DEBUG] Step 5: Normalized to: {normalized_level}")

        # Store in state
        print(f"[DEBUG] Step 6: Storing in state...")
        self.state.set("program_creation.fitness_level", normalized_level)
        print(f"[DEBUG] Step 7: Stored successfully")

        print(f"[PROGRAM] Fitness level normalized to: {normalized_level}")

        # Get all collected data
        height_cm = self.state.get("program_creation.height_cm")
        weight_kg = self.state.get("program_creation.weight_kg")
        goal_category = self.state.get("program_creation.goal_category")
        goal_raw = self.state.get("program_creation.goal_raw")
        duration_weeks = self.state.get("program_creation.duration_weeks")
        days_per_week = self.state.get("program_creation.days_per_week")

        # Print summary to console
        print("\n" + "="*60)
        print("[PROGRAM CREATION] All parameters collected:")
        print(f"  User: {name} (ID: {user.get('id')})")
        print(f"  Height: {height_cm} cm")
        print(f"  Weight: {weight_kg} kg")
        print(f"  Goal Category: {goal_category}")
        print(f"  Goal Description: \"{goal_raw}\"")
        print(f"  Duration: {duration_weeks} weeks")
        print(f"  Training Frequency: {days_per_week} days/week")
        print(f"  Fitness Level: {normalized_level}")
        print("="*60 + "\n")

        # Automatically determine VBT capability based on collected parameters
        print(f"[PROGRAM] Determining VBT capability...")
        print(f"[PROGRAM] Fitness Level: {normalized_level}")
        print(f"[PROGRAM] Goal Category: {goal_category}")
        print(f"[PROGRAM] Sport: {self.state.get('program_creation.specific_sport', 'none')}")

        should_enable_vbt = self._should_enable_vbt(
            fitness_level=normalized_level,
            goal_category=goal_category,
            specific_sport=self.state.get("program_creation.specific_sport", "none")
        )

        print(f"[PROGRAM] VBT Decision: {'ENABLED' if should_enable_vbt else 'DISABLED'}")

        # Store VBT decision and completion flag in state for prompt to use
        self.state.set("program_creation.vbt_enabled", should_enable_vbt)
        self.state.set("program_creation.all_params_collected", True)

        return None, "All parameters collected. Summarize their program, call set_vbt_capability, then generate_workout_program."

    def _should_enable_vbt(self, fitness_level: str, goal_category: str, specific_sport: str) -> bool:
        """
        Determine if VBT should be enabled based on training parameters.

        VBT is enabled when:
        1. Fitness level is intermediate or advanced (required)
        2. AND one of:
           - Goal is power or athletic_performance
           - Goal is strength AND fitness level is advanced
           - Sport involves explosiveness

        Args:
            fitness_level: beginner, intermediate, or advanced
            goal_category: power, strength, hypertrophy, or athletic_performance
            specific_sport: sport name or "none"

        Returns:
            True if VBT should be enabled, False otherwise
        """
        # Rule 1: Beginners NEVER get VBT
        if fitness_level == "beginner":
            print("[VBT] Disabled: beginner level (form mastery priority)")
            return False

        # Rule 2: Hypertrophy-only goals don't use VBT
        if goal_category == "hypertrophy" and specific_sport == "none":
            print("[VBT] Disabled: hypertrophy goal without sport context")
            return False

        # Rule 3: Power goals (intermediate or advanced) use VBT
        if goal_category in ["power", "athletic_performance"]:
            print(f"[VBT] Enabled: {goal_category} goal with {fitness_level} level")
            return True

        # Rule 4: Advanced strength athletes use VBT
        if goal_category == "strength" and fitness_level == "advanced":
            print(f"[VBT] Enabled: advanced strength training")
            return True

        # Rule 5: Check if sport involves explosiveness
        explosive_sports = [
            "sprinting", "track and field", "olympic weightlifting", "powerlifting",
            "basketball", "football", "volleyball", "jumping", "throwing",
            "baseball", "softball", "rugby", "hockey", "soccer", "lacrosse"
        ]

        sport_lower = specific_sport.lower() if specific_sport else ""
        if any(sport in sport_lower for sport in explosive_sports):
            print(f"[VBT] Enabled: explosive sport ({specific_sport}) with {fitness_level} level")
            return True

        # Default: No VBT
        print(f"[VBT] Disabled: {fitness_level} + {goal_category} + {specific_sport} doesn't warrant VBT")
        return False

    def _normalize_fitness_level(self, level_str: str) -> str:
        """Normalize fitness level to beginner, intermediate, or advanced"""
        level_lower = level_str.lower()

        # Beginner indicators
        beginner_keywords = ["beginner", "new", "just starting", "never", "first time", "noob"]

        # Advanced indicators
        advanced_keywords = ["advanced", "experienced", "years", "competitive", "athlete", "expert"]

        # Check for matches
        if any(kw in level_lower for kw in beginner_keywords):
            return "beginner"
        elif any(kw in level_lower for kw in advanced_keywords):
            return "advanced"
        else:
            # Default to intermediate
            return "intermediate"

    @function_tool
    async def generate_workout_program(self, context: RunContext):
        """
        Call this to START generating a complete workout program via FastAPI backend.
        Returns immediately - generation happens in the background.

        The program will be generated based on:
        - User's height and weight
        - Goal (power/strength/hypertrophy)
        - Program duration
        - Training frequency
        - Fitness level
        """
        import httpx

        print("\n" + "="*80)
        print("[PROGRAM] ⚡ generate_workout_program() CALLED (FastAPI mode)")
        print("="*80)

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        print(f"[PROGRAM] User: {name} (ID: {user_id})")

        # Check if already generated
        saved_program_id = self.state.get("program_creation.saved_program_id")
        if saved_program_id:
            print("[PROGRAM] ⚠️  Program already generated - skipping duplicate call")
            return None, f"Program already generated. Now call finish_program_creation() to complete."

        # Check if job already started
        existing_job_id = self.state.get("program_creation.job_id")
        if existing_job_id:
            print(f"[PROGRAM] ⚠️  Generation job already started: {existing_job_id}")
            return None, f"Generation already started. Now call check_program_status() to see if it's done."

        # Get all parameters from state
        print("[PROGRAM] Retrieving parameters from state...")
        height_cm = self.state.get("program_creation.height_cm")
        weight_kg = self.state.get("program_creation.weight_kg")
        age = self.state.get("program_creation.age")
        sex = self.state.get("program_creation.sex")
        goal_category = self.state.get("program_creation.goal_category")
        goal_raw = self.state.get("program_creation.goal_raw")
        duration_weeks = self.state.get("program_creation.duration_weeks")
        days_per_week = self.state.get("program_creation.days_per_week")
        session_duration = self.state.get("program_creation.session_duration", 60)
        injury_history = self.state.get("program_creation.injury_history", "none")
        specific_sport = self.state.get("program_creation.specific_sport", "none")
        user_notes = self.state.get("program_creation.user_notes")
        fitness_level = self.state.get("program_creation.fitness_level")
        has_vbt_capability = self.state.get("program_creation.has_vbt_capability", False)

        # Validate we have all REQUIRED parameters
        missing = []
        if not height_cm: missing.append("height_cm")
        if not weight_kg: missing.append("weight_kg")
        if not age: missing.append("age")
        if not sex: missing.append("sex")
        if not goal_category: missing.append("goal_category")
        if not goal_raw: missing.append("goal_raw")
        if not duration_weeks: missing.append("duration_weeks")
        if not days_per_week: missing.append("days_per_week")
        if not fitness_level: missing.append("fitness_level")

        if missing:
            print(f"[PROGRAM] ❌ ERROR: Missing required parameters: {', '.join(missing)}")
            print(f"[PROGRAM] Current state: height={height_cm}, weight={weight_kg}, age={age}, sex={sex}, goal={goal_category}, duration={duration_weeks}, days={days_per_week}, fitness={fitness_level}")
            return None, f"ERROR: Cannot generate program - missing required parameters: {', '.join(missing)}. You MUST collect all parameters in order before calling generate_workout_program(). Go back and ask the missing questions."

        print("[PROGRAM] ✅ All parameters validated successfully")

        try:
            print("[PROGRAM] 🌐 Calling FastAPI to start generation...")

            # Prepare request payload with all new parameters
            params = {
                "user_id": user_id,
                "height_cm": height_cm,
                "weight_kg": weight_kg,
                "age": age,
                "sex": sex,
                "goal_category": goal_category,
                "goal_raw": goal_raw,
                "duration_weeks": duration_weeks,
                "days_per_week": days_per_week,
                "session_duration": session_duration,
                "injury_history": injury_history,
                "specific_sport": specific_sport,
                "user_notes": user_notes,
                "fitness_level": fitness_level,
                "has_vbt_capability": has_vbt_capability
            }

            print(f"[PROGRAM] 🎯 VBT Status: {'ENABLED' if has_vbt_capability else 'DISABLED'}")

            # Call FastAPI endpoint to start generation
            fastapi_url = os.getenv("FASTAPI_URL", "http://localhost:8000")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{fastapi_url}/api/programs/generate",
                    json=params,
                    timeout=10.0
                )
                data = response.json()
                job_id = data["job_id"]

            # Store job_id in state
            self.state.set("program_creation.job_id", job_id)
            print(f"[PROGRAM] ✅ Started generation job: {job_id}")
            print("="*80 + "\n")

            # Tell agent to wait and check status
            return None, f"Program generation started! Wait 45 seconds, then call check_program_status() to see if it's done. Don't say anything yet, just wait and call check_program_status() after 45 seconds."

        except Exception as e:
            print(f"\n[PROGRAM] ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            print("="*80 + "\n")
            return None, f"Error starting generation. Say something like: '{name}, I had trouble starting your program. Let me try again.' Keep it apologetic."

    @function_tool
    async def check_program_status(self, context: RunContext):
        """
        Check if program generation is complete.
        Call this after generate_workout_program() to poll for completion.
        """
        import httpx

        user = self.state.get_user()
        name = user.get("name", "there")

        job_id = self.state.get("program_creation.job_id")
        if not job_id:
            return None, f"No generation job found. Call generate_workout_program() first."

        try:
            # Check status via FastAPI
            fastapi_url = os.getenv("FASTAPI_URL", "http://localhost:8000")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{fastapi_url}/api/programs/status/{job_id}",
                    timeout=5.0
                )
                data = response.json()

            status = data["status"]
            progress = data.get("progress", 0)

            if status == "completed":
                # Get the program ID
                program_id = data["program_id"]

                # Store in state
                self.state.set("program_creation.saved_program_id", program_id)

                print(f"[PROGRAM] ✅ Program generation complete! ID: {program_id}")

                return None, f"Program is ready! Say something like: 'Great news! Your custom program is ready. I've saved it to your account.' Then call finish_program_creation(). Be enthusiastic!"

            elif status == "failed":
                error = data.get("error_message", "Unknown error")
                print(f"[PROGRAM] ❌ Generation failed: {error}")
                return None, f"Generation failed. Say something like: 'Hmmm, seems like I had trouble creating your program. Let me try again.' Keep it apologetic."

            else:
                # Still in progress
                print(f"[PROGRAM] Generation in progress: {progress}%")
                return None, f"Program is {progress}% complete. Wait 15 more seconds, then call check_program_status() again. Don't say anything, just wait."

        except Exception as e:
            print(f"[PROGRAM] Error checking status: {e}")
            return None, f"Error checking status. Wait 10 seconds and call check_program_status() again."


    def _get_program_generation_system_prompt(self) -> str:
        """Get the system prompt for GPT-5 program generation with CAG knowledge base"""

        # Base coaching expertise and guidelines
        base_prompt = """You are an elite strength and conditioning coach specializing in barbell training and evidence-based program design.

Your expertise includes:
- Exercise physiology and biomechanics
- Progressive overload and periodization strategies
- Volume landmarks for hypertrophy, strength, and power development
- Proper exercise selection and sequencing
- Recovery and fatigue management

**Volume Guidelines (sets per muscle group per week):**

Hypertrophy Focus:
- Chest: 12-20 sets/week
- Back: 14-22 sets/week
- Quads: 12-18 sets/week
- Hamstrings: 10-16 sets/week
- Shoulders: 12-18 sets/week
- Arms: 8-14 sets/week

Strength Focus:
- Main Lifts (Squat, Bench, Deadlift, OHP): 6-12 sets/week each
- Accessory work: 50-70% of main lift volume

Power Focus:
- Main Power Movements: 4-8 sets/week
- Accessory Strength: 6-10 sets/week

**Rep Ranges:**
- Hypertrophy: 6-12 reps (can use 5-20 range)
- Strength: 1-6 reps (80-95% 1RM)
- Power: 1-5 reps with explosive intent (50-85% 1RM)

**Rest Periods:**
- Strength/Power: 3-5 minutes
- Hypertrophy: 1.5-3 minutes
- Accessory: 1-2 minutes

**RIR (Reps in Reserve):**
- Beginner: 2-4 RIR (focus on technique)
- Intermediate: 1-3 RIR
- Advanced: 0-2 RIR (can approach failure on appropriate exercises)

**Barbell Exercise Library:**
- Lower: Back squat, front squat, deadlift (conventional/sumo), RDL, Bulgarian split squat, hip thrust
- Upper Push: Bench press (flat/incline), overhead press, push press, close-grip bench
- Upper Pull: Barbell row (bent-over/pendlay), pull-ups (weighted)
- Olympic: Clean, snatch, push jerk (for power focus)

**Progression Strategies:**
- Linear Progression: Add weight each week (beginner)
- Double Progression: Increase reps, then weight (all levels)
- Wave Loading: Vary intensity across weeks (intermediate+)
- Block Periodization: Phase-based training (advanced)

**Program Structure by Frequency:**
- If the user plans to workout 2-3 days a week: Full body each session
- If the user plans to workout 4 days a week: Upper/Lower split
- If the user plans to workout 5-6 days a week: Push/Pull/Legs or Upper/Lower/Upper/Lower

**Key Principles:**
1. Start conservative, progress steadily
2. Balance muscle groups across the week
3. Place hardest work first in each session
4. Include deload weeks every 4-8 weeks
5. Prioritize compound movements
6. Scale volume to recovery capacity

Generate programs that are challenging but achievable, progressive, and scientifically sound. Always return valid JSON in the exact format specified."""

        # Load CAG periodization knowledge base from external file
        try:
            cag_knowledge_path = Path(__file__).parent.parent / "knowledge" / "cag_periodization.txt"
            with open(cag_knowledge_path, 'r', encoding='utf-8') as f:
                cag_knowledge = f.read()

            print(f"[PROGRAM] Loaded CAG knowledge base ({len(cag_knowledge)} characters)")

            # Combine base prompt with CAG knowledge
            full_prompt = base_prompt + "\n\n" + "="*80 + "\n" + cag_knowledge
            return full_prompt

        except FileNotFoundError:
            print("[PROGRAM] ⚠️  WARNING: CAG knowledge base file not found, using base prompt only")
            return base_prompt
        except Exception as e:
            print(f"[PROGRAM] ⚠️  WARNING: Error loading CAG knowledge base: {e}")
            return base_prompt


    @function_tool
    async def finish_program_creation(self, context: RunContext):
        """
        Call this to complete the program creation process and return to main menu.
        """
        print("[PROGRAM] Finishing program creation, returning to main menu...")

        user = self.state.get_user()
        name = user.get("name", "there")

        # Clear program creation state
        self.state.set("program_creation", None)

        # Switch back to main menu
        self.state.switch_mode("main_menu")
        self.state.save_state()

        # Update agent instructions to main_menu mode
        new_instructions = self._get_main_menu_instructions()
        self.update_instructions(new_instructions)
        print("[STATE] Returned to main_menu mode and updated instructions")

        return None, f"Program creation complete. Say something like: 'All set! Your program is ready to go. You can start your first workout whenever you're ready, or explore the other options. What would you like to do?' Keep it motivating."

    # ===== WORKOUT TOOLS =====

    @function_tool
    async def end_workout(self, context: RunContext):
        """
        Call this when the user wants to end/stop their workout.
        User might say: "stop workout", "I'm done", "end session", "finish"
        """
        print("[WORKOUT] User requested to end workout")

        from db.database import SessionLocal
        from db.schedule_utils import mark_workout_completed
        from db.progress_utils import log_completed_set
        from core.workout_session import WorkoutSession

        # Get current session from state
        session_data = self.state.get("workout.current_session")

        if session_data:
            try:
                # Deserialize session
                session = WorkoutSession.from_dict(session_data)
                session.end_session()

                # Log all completed sets to database
                db = SessionLocal()
                try:
                    for set_data in session.get_completed_sets_for_logging():
                        # Only log if reps were actually performed
                        if set_data["performed_reps"] > 0:
                            log_completed_set(
                                db=db,
                                user_id=session.user_id,
                                set_id=set_data["set_id"],
                                performed_reps=set_data["performed_reps"],
                                performed_weight=set_data.get("performed_weight"),
                                rpe=set_data.get("rpe"),
                                measured_velocity=set_data.get("measured_velocity")
                            )
                            print(f"[WORKOUT] Logged set {set_data['set_id']}")

                    # Mark workout as completed in schedule
                    mark_workout_completed(db, session.schedule_id)
                    print(f"[WORKOUT] Marked schedule {session.schedule_id} as completed")

                    # Get progress summary
                    summary = session.get_progress_summary()

                except Exception as e:
                    print(f"[WORKOUT ERROR] Failed to save workout data: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    db.close()

            except Exception as e:
                print(f"[WORKOUT ERROR] Failed to process session: {e}")
                import traceback
                traceback.print_exc()

        # Clear workout session from state
        self.state.set("workout.current_session", None)

        # Switch back to main menu mode (main.py monitors state file)
        self.state.switch_mode("main_menu")
        self.state.set("workout.active", False)
        self.state.save_state()

        # Update agent instructions to main_menu mode
        new_instructions = self._get_main_menu_instructions()
        self.update_instructions(new_instructions)
        print("[STATE] Switched to main_menu mode and updated instructions - main.py will detect and stop pose estimation")

        user = self.state.get_user()
        name = user.get("name", "there")

        return None, f"The user wants to end the workout. Say something like: 'Great work today, {name}! You crushed it. All your progress has been saved. Returning to the main menu.' Keep it celebratory and proud."

    @function_tool
    async def complete_set(
        self,
        reps: int,
        weight: Optional[float] = None,
        rpe: Optional[float] = None,
        context: RunContext = None
    ):
        """
        Call this when the user completes a set.
        User might say: "done", "finished", "complete", or you count the reps and they confirm.

        Args:
            reps: Number of reps completed
            weight: Weight used (optional, kg or lbs)
            rpe: Rate of perceived exertion 1-10 (optional)
        """
        print(f"[WORKOUT] User completed set: {reps} reps, weight={weight}, rpe={rpe}")

        from core.workout_session import WorkoutSession

        # Get current session from state
        session_data = self.state.get("workout.current_session")
        if not session_data:
            print("[WORKOUT ERROR] No active session")
            return None, "Tell the user: 'Hmm, I don't have an active workout session. Let's start a workout first!' Keep it helpful."

        try:
            # Deserialize session
            session = WorkoutSession.from_dict(session_data)

            # Get current set info before marking complete
            current_set = session.get_current_set()
            if not current_set:
                return None, "Tell the user: 'Great work! Looks like you've finished all the sets. Ready to move on or end the workout?' Keep it encouraging."

            # Mark set complete
            session.mark_set_complete(
                performed_reps=reps,
                performed_weight=weight,
                rpe=rpe
            )

            # Advance to next set
            has_next = session.advance_to_next_set()

            # Save updated session
            self.state.set("workout.current_session", session.to_dict())
            self.state.save_state()

            user = self.state.get_user()
            name = user.get("name", "there")

            if has_next:
                # Get next set info
                next_desc = session.get_current_exercise_description()
                rest_time = current_set.rest_seconds

                rest_min = rest_time // 60
                rest_sec = rest_time % 60
                rest_display = f"{rest_min}:{rest_sec:02d}" if rest_min > 0 else f"{rest_sec} seconds"

                return None, f"Tell the user: 'Awesome set, {name}! That's {reps} reps at {weight}kg.' Then say: 'Rest for {rest_display}. Next up: {next_desc}' Keep it energetic and clear."
            else:
                # Workout complete
                summary = session.get_progress_summary()
                return None, f"Tell the user: 'YES! That's the last one, {name}! You completed {summary['completed_sets']} total sets today. Amazing work! Ready to wrap up?' Keep it celebratory."

        except Exception as e:
            print(f"[WORKOUT ERROR] Failed to complete set: {e}")
            import traceback
            traceback.print_exc()
            return None, "Tell the user: 'Good set! Let me know when you're ready for the next one.' Keep it simple."

    @function_tool
    async def skip_exercise(self, reason: Optional[str] = None, context: RunContext = None):
        """
        Call this when the user wants to skip the current exercise.
        User might say: "skip this", "I can't do this one", "next exercise", "equipment not available"

        Args:
            reason: Optional reason for skipping (e.g., "injury", "no equipment")
        """
        print(f"[WORKOUT] User wants to skip exercise. Reason: {reason}")

        from core.workout_session import WorkoutSession

        # Get current session from state
        session_data = self.state.get("workout.current_session")
        if not session_data:
            return None, "Tell the user: 'No active workout to skip. Let's start a workout first!' Keep it helpful."

        try:
            # Deserialize session
            session = WorkoutSession.from_dict(session_data)

            current_exercise = session.get_current_exercise()
            if not current_exercise:
                return None, "Tell the user: 'You're all done with the workout! No more exercises to skip.' Keep it positive."

            exercise_name = current_exercise.exercise_name

            # Skip the exercise
            session.skip_current_exercise(reason=reason)

            # Save updated session
            self.state.set("workout.current_session", session.to_dict())
            self.state.save_state()

            next_exercise = session.get_current_exercise()
            if next_exercise:
                next_desc = session.get_current_exercise_description()
                return None, f"Tell the user: 'No problem, skipping {exercise_name}. Moving on to {next_desc}' Keep it supportive and matter-of-fact."
            else:
                return None, f"Tell the user: 'Alright, skipped {exercise_name}. That was the last exercise! Great work on what you did today. Ready to wrap up?' Keep it encouraging."

        except Exception as e:
            print(f"[WORKOUT ERROR] Failed to skip exercise: {e}")
            import traceback
            traceback.print_exc()
            return None, "Tell the user: 'Okay, let's move on to the next exercise.' Keep it simple."

    @function_tool
    async def get_next_exercise(self, context: RunContext = None):
        """
        Call this when the user asks what's next or wants to preview upcoming exercises.
        User might say: "what's next", "what exercise is coming up", "show me next"
        """
        print("[WORKOUT] User wants to see next exercise")

        from core.workout_session import WorkoutSession

        # Get current session from state
        session_data = self.state.get("workout.current_session")
        if not session_data:
            return None, "Tell the user: 'No active workout. Start a workout to see your exercises!' Keep it helpful."

        try:
            # Deserialize session
            session = WorkoutSession.from_dict(session_data)

            next_exercise = session.get_next_exercise()

            if next_exercise:
                set_count = len(next_exercise.sets)
                return None, f"Tell the user: 'Coming up next: {next_exercise.exercise_name}, {set_count} sets. But let's finish this exercise first!' Keep it focused and motivating."
            else:
                current = session.get_current_exercise()
                if current:
                    return None, f"Tell the user: '{current.exercise_name} is the last exercise! Finish strong!' Keep it motivating."
                else:
                    return None, "Tell the user: 'You're done! That was the last exercise. Great job!' Keep it celebratory."

        except Exception as e:
            print(f"[WORKOUT ERROR] Failed to get next exercise: {e}")
            import traceback
            traceback.print_exc()
            return None, "Tell the user: 'Let's focus on this exercise first!' Keep it simple."

    @function_tool
    async def get_workout_progress(self, context: RunContext = None):
        """
        Call this when the user asks about their progress or where they are in the workout.
        User might say: "how much left", "where am I", "progress", "how many sets left"
        """
        print("[WORKOUT] User wants to see workout progress")

        from core.workout_session import WorkoutSession

        # Get current session from state
        session_data = self.state.get("workout.current_session")
        if not session_data:
            return None, "Tell the user: 'No active workout. Start a workout to track your progress!' Keep it helpful."

        try:
            # Deserialize session
            session = WorkoutSession.from_dict(session_data)

            summary = session.get_progress_summary()

            user = self.state.get_user()
            name = user.get("name", "there")

            return None, f"Tell the user: 'You're crushing it, {name}! You've completed {summary['completed_sets']} out of {summary['total_sets']} sets. That's {summary['percent_complete']}% done. Currently on {summary['current_exercise_name']}.' Keep it motivating and clear."

        except Exception as e:
            print(f"[WORKOUT ERROR] Failed to get progress: {e}")
            import traceback
            traceback.print_exc()
            return None, "Tell the user: 'Keep pushing! You're doing great.' Keep it simple and encouraging."


async def entrypoint(ctx: agents.JobContext):
    """Main entry point for Nova voice agent"""

    print("[NOVA] Entrypoint function called")

    # Initialize state management
    # Check if user_id is provided in room metadata (for returning users)
    print("[NOVA] Checking for user_id in room metadata...")
    user_id = ctx.room.metadata.get('user_id') if ctx.room.metadata else None
    print(f"[NOVA] user_id from metadata: {user_id}")

    # If no user_id from metadata, try to find the most recent state file
    # (for console mode where metadata isn't available)
    if not user_id:
        import glob
        print("[NOVA] Searching for state files...")
        state_files = glob.glob('.agent_state_*.json')
        print(f"[NOVA] Found {len(state_files)} state files")
        if state_files:
            # Get most recently modified state file
            latest_state = max(state_files, key=os.path.getmtime)
            # Extract user_id from filename
            user_id = latest_state.replace('.agent_state_', '').replace('.json', '')
            print(f"[NOVA] Found recent state file for user: {user_id}")

    print(f"[NOVA] Creating AgentState with user_id: {user_id}...")
    state = AgentState(user_id=user_id)
    print(f"[NOVA] AgentState created successfully")

    print(f"[NOVA] Starting with mode: {state.get_mode()}")
    if user_id:
        print(f"[NOVA] Loaded existing user: {user_id}")

    # IPC is not needed - state file is used for communication with main.py
    ipc_client = None

    # Initialize OpenAI Realtime API model
    # Replaces separate STT (Deepgram) + LLM (OpenAI) + TTS (Inworld)
    print("[NOVA] Initializing OpenAI Realtime model...")
    realtime_model = openai.realtime.RealtimeModel(
        voice=os.getenv("REALTIME_VOICE", "alloy"),
        temperature=float(os.getenv("REALTIME_TEMPERATURE", "0.8")),
        turn_detection={
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 300,
        },
        modalities=["audio", "text"],
    )
    print("[NOVA] Realtime model initialized")

    # Initialize agent session with Realtime model
    print("[NOVA] Creating agent session...")
    session = AgentSession(
        llm=realtime_model,
        preemptive_generation=True,
        # Note: LiveKit doesn't have a direct tool_timeout parameter
        # Long-running tools (like GPT-5 program generation) should handle their own timeouts
        # Our generate_workout_program() has a 300s timeout configured
    )
    print("[NOVA] Agent session created")

    # Create agent with state management and IPC - tools are automatically registered via @function_tool decorators
    print("[NOVA] Creating NovaVoiceAgent instance...")
    agent = NovaVoiceAgent(state=state, ipc_client=ipc_client)
    print("[NOVA] NovaVoiceAgent created")

    print("[NOVA] Starting session (connecting to room)...")
    print("[NOVA] This may require microphone permissions on macOS")
    await session.start(
        room=ctx.room,
        agent=agent,
    )
    print("[NOVA] Session started successfully!")

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