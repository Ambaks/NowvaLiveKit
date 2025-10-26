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
from agents.prompts import ONBOARDING_PROMPT, get_main_menu_prompt, get_workout_prompt, get_program_creation_prompt

# Database imports
from db.database import SessionLocal
from db.program_utils import has_any_programs


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

        return get_program_creation_prompt(name, existing_data)

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

        # Switch to workout mode (main.py monitors state file)
        self.state.switch_mode("workout")
        self.state.save_state()

        # Update agent instructions to workout mode
        new_instructions = self._get_workout_instructions()
        self.update_instructions(new_instructions)
        print("[STATE] Switched to workout mode and updated instructions - main.py will detect and start pose estimation")

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
        return None, f"The user wants to see their progress. Say something like: '{name}, you're doing great! This feature is coming soon - I'll be able to show you your workout history, personal records, and progress charts.' Keep it encouraging."

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

    @function_tool
    async def create_program(self, context: RunContext):
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

        This will start the program creation flow and guide the user through collecting their information.
        """
        print("\n" + "="*80)
        print("[MAIN MENU] create_program() CALLED")
        print("="*80)

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        print(f"[PROGRAM] User: {name} (ID: {user_id})")

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

                self.state.switch_mode("program_creation")
                self.state.save_state()

                # Update agent instructions to program_creation mode
                new_instructions = self._get_program_creation_instructions()
                self.update_instructions(new_instructions)
                print("[PROGRAM] Updated agent instructions to program_creation mode")

                # Start the program creation flow DIRECTLY - no need for create_program()
                return None, f"Program creation started. You are now in program_creation mode. The 'PARAMETER COLLECTION ORDER' section at the top of your instructions shows the EXACT order to ask questions. Say: 'Oh! Let's create your first program, {name}! I'll ask you a few quick questions.' Then IMMEDIATELY ask Question 1: 'First, what's your height and weight?' Keep it encouraging and conversational."
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

                # Switch to program_creation mode
                self.state.switch_mode("program_creation")
                self.state.save_state()

                # Update agent instructions to program_creation mode
                new_instructions = self._get_program_creation_instructions()
                self.update_instructions(new_instructions)
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

        This is a placeholder for future functionality.
        """
        print("[MAIN MENU] User requested to update program")

        user = self.state.get_user()
        name = user.get("name", "there")

        # TODO: Implement program update functionality
        # For now, inform user this feature is coming soon
        return None, f"Say something like: '{name}, updating existing programs is coming soon! For now, you can create a new program if you'd like to try something different.' Keep it encouraging."

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
                    return None, f"Using existing stats from database. Immediately ask: 'Perfect! And how old are you, and are you male or female?' Keep it conversational and brief."

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

                return None, f"Height and weight captured: {height_cm} cm, {weight_kg} kg. Immediately ask: 'Perfect! And how old are you, and are you male or female?' Keep it conversational and brief."

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
                    return None, f"Using existing demographics from database. Immediately ask: 'Great! Now, what's your main fitness goal? Are you looking to build muscle, get stronger, improve athleticism, or something else?' Keep it engaging and conversational."

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

                return None, f"Age and sex captured: {age}, {sex_normalized}. Immediately ask: 'Great! Now, what's your main fitness goal? Are you looking to build muscle, get stronger, improve athleticism, or something else?' Keep it engaging and conversational."

        except Exception as e:
            print(f"[ERROR] Failed to handle age/sex: {e}")
            db.rollback()
        finally:
            db.close()

        return None, f"Error: Could not capture age and sex. Please provide them again."

    @function_tool
    async def capture_height(self, context: RunContext, height_value: str):
        """
        Call this when the user provides their height.
        Accepts various formats: "5 feet 9 inches", "5'9\"", "175 cm", "1.75 m", "5 foot 9", etc.
        Normalizes to centimeters and saves to database.

        Args:
            height_value: The height as spoken by the user (e.g., "five nine", "175", "5 feet 9 inches")
        """
        print(f"[PROGRAM] Capturing height: {height_value}")

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        try:
            # Normalize the height to centimeters
            height_cm = self._normalize_height_to_cm(height_value)

            if height_cm is None or height_cm < 50 or height_cm > 300:
                # Invalid height
                return None, f"That height doesn't seem right. Say something like: 'Hmm, that doesn't sound quite right. Can you tell me your height again? For example, you could say five foot nine, or 175 centimeters.' Keep it friendly."

            # Save to database
            db = SessionLocal()
            try:
                from db.models import User
                db_user = db.query(User).filter(User.id == user_id).first()
                if db_user:
                    db_user.height_cm = height_cm
                    db.commit()
                    print(f"[PROGRAM] Saved height: {height_cm} cm")

                    # Store in state
                    self.state.set("program_creation.height_cm", height_cm)

                    # Check if we also need weight
                    if db_user.weight_kg is None:
                        return None, f"Height captured successfully ({height_cm} cm). Say something like: 'Got it, {name}! Now, what's your current weight? You can tell me in pounds or kilograms.' Keep it supportive."
                    else:
                        # Have both now - proceed
                        self.state.set("program_creation.weight_kg", float(db_user.weight_kg))
                        return None, f"Height captured ({height_cm} cm). User has all stats. Say something like: 'Perfect! I've got your stats. Now let's talk about your goals. What are you looking to achieve with this program?' Keep it engaging."

            finally:
                db.close()

        except Exception as e:
            print(f"[ERROR] Failed to capture height: {e}")
            return None, f"Error capturing height. Say something like: '{name}, I had trouble understanding that. Can you tell me your height again? For example, five foot nine, or 175 centimeters.' Keep it patient."

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

    @function_tool
    async def capture_weight(self, context: RunContext, weight_value: str):
        """
        Call this when the user provides their weight.
        Accepts various formats: "150 lbs", "68 kg", "150 pounds", "68 kilograms", etc.
        Normalizes to kilograms and saves to database.

        Args:
            weight_value: The weight as spoken by the user (e.g., "150", "68 kg", "150 pounds")
        """
        print(f"[PROGRAM] Capturing weight: {weight_value}")

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        try:
            # Normalize the weight to kilograms
            weight_kg = self._normalize_weight_to_kg(weight_value)

            if weight_kg is None or weight_kg < 20 or weight_kg > 300:
                # Invalid weight
                return None, f"That weight doesn't seem right. Say something like: 'Hmm, that doesn't sound quite right. Can you tell me your weight again? For example, you could say 150 pounds, or 68 kilograms.' Keep it supportive."

            # Save to database
            db = SessionLocal()
            try:
                from db.models import User
                db_user = db.query(User).filter(User.id == user_id).first()
                if db_user:
                    db_user.weight_kg = weight_kg
                    db.commit()
                    print(f"[PROGRAM] Saved weight: {weight_kg} kg")

                    # Store in state
                    self.state.set("program_creation.weight_kg", weight_kg)

                    # Check if we also need height
                    if db_user.height_cm is None:
                        return None, f"Weight captured successfully ({weight_kg} kg). Say something like: 'Great! Now I need your height. What's your height? You can tell me in feet and inches, or centimeters.' Keep it friendly."
                    else:
                        # Have both now - proceed
                        self.state.set("program_creation.height_cm", float(db_user.height_cm))
                        return None, f"Weight captured ({weight_kg} kg). User has all stats. Say something like: 'Awesome, {name}! I've got everything I need. Now let's talk about your goals. What are you looking to achieve with this program?' Keep it engaging."

            finally:
                db.close()

        except Exception as e:
            print(f"[ERROR] Failed to capture weight: {e}")
            return None, f"Error capturing weight. Say something like: '{name}, I had trouble understanding that. Can you tell me your weight again? For example, 150 pounds, or 68 kilograms.' Keep it patient."

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
        height_cm = self.state.get("program_creation.height_cm")
        weight_kg = self.state.get("program_creation.weight_kg")
        age = self.state.get("program_creation.age")
        sex = self.state.get("program_creation.sex")

        if not (height_cm and weight_kg and age and sex):
            print(f"[ERROR] Goal asked before prerequisites! height={height_cm}, weight={weight_kg}, age={age}, sex={sex}")
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

        return None, f"Goal captured: '{goal_description}' → {goal_category}. Immediately say something like: 'Got it! So it sounds like you're focused on {confirmation}. How long would you like this program to run? I'd recommend {self._get_recommended_duration(goal_category)} weeks.' Keep it brief and conversational. Don't wait for acknowledgment."

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

        return None, f"Duration captured: {duration_weeks} weeks. Immediately say something like: 'Perfect! {duration_weeks} weeks is great. How many days per week can you train?' Keep it brief. Don't wait."

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

        return None, f"Frequency captured: {days_per_week} days/week. Immediately ask: 'Great! How much time do you have per session? Most people do about an hour.' Keep it brief and conversational."

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

        return None, f"Session duration captured: {duration_minutes} minutes. Ask: 'Perfect! Any current or past injuries I should know about? If not, just say no.' Keep it brief."

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

        user = self.state.get_user()
        name = user.get("name", "there")

        return None, f"Injury history captured. Ask: 'Got it! Are you training for a specific sport, or just general fitness?' Keep it conversational."

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

        user = self.state.get_user()
        name = user.get("name", "there")

        return None, f"Sport captured: {sport_normalized}. Ask: 'Cool! Anything else I should know? Like exercise preferences or equipment you have access to? If not, just say no.' Keep it friendly."

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

        user = self.state.get_user()
        name = user.get("name", "there")

        return None, f"Notes captured. Ask: 'Perfect! Last question: would you say you're a beginner, intermediate, or advanced lifter?' This is the final parameter needed."

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

        return None, f"Age captured: {age}. Continue with the next question in the program creation flow."

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

        return None, f"Sex captured: {sex_normalized}. Continue with the next question in the program creation flow."

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

        # Return nothing - this is a silent internal operation
        return None, None

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

        # Acknowledge the fitness level and inform user that generation is starting
        # The agent should speak THEN call the functions (not both simultaneously)
        return None, f"All parameters collected! First, say to {name}: 'Perfect! I've got everything I need. You're an {normalized_level} lifter looking to focus on {goal_category} for {duration_weeks} weeks, training {days_per_week} days a week. Let me generate your custom program now. This will take about a minute, so hang tight!' After you finish speaking, call set_vbt_capability({'true' if should_enable_vbt else 'false'}), then call generate_workout_program() and wait for it to finish before doing anything else."

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
- 2-3 days: Full body each session
- 4 days: Upper/Lower split
- 5-6 days: Push/Pull/Legs or Upper/Lower/Upper/Lower

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

        return None, f"The user wants to end the workout. Say something like: 'Great work today, {name}! You crushed it. Returning to the main menu.' Keep it celebratory."


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
            "silence_duration_ms": 500,
        },
        modalities=["audio", "text"],
    )
    print("[NOVA] Realtime model initialized")

    # Initialize agent session with Realtime model
    print("[NOVA] Creating agent session...")
    session = AgentSession(
        llm=realtime_model,
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