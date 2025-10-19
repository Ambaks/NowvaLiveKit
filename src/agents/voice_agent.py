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
                instructions=f"Welcome {name} back to the main menu. Say: 'Hey {name}, welcome back! You can start a workout, create or update a program, check your progress, or update your profile. What would you like to do?' Keep it friendly and conversational."
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

    @function_tool
    async def create_or_update_program(self, context: RunContext):
        """
        Call this when the user wants to create a new program or update an existing one.
        User might say: "create a program", "make a workout plan", "build a program", "update my program"
        """
        print("[MAIN MENU] User requested to create or update program")

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        # Check if user has any existing programs
        db = SessionLocal()
        try:
            has_programs = has_any_programs(db, user_id)

            if not has_programs:
                # No programs - inform user and proceed to creation
                print("[PROGRAM] User has no programs - proceeding to creation")
                return None, f"The user has no programs yet. Say: '{name}, looks like you don't have any programs yet. Let's create your first one! I'll ask you a few questions to build a custom program just for you.' Then call create_program() to start the creation process. Keep it encouraging."
            else:
                # Has programs - ask if they want to create new or update existing
                print("[PROGRAM] User has existing programs")
                return None, f"The user has existing programs. Say: '{name}, you already have some programs. Would you like to create a new one or update an existing program?' Keep it helpful and wait for their response."

        except Exception as e:
            print(f"[ERROR] Failed to check user programs: {e}")
            return None, f"There was an error checking your programs. Say: '{name}, I'm having trouble accessing your programs right now. Let's try again in a moment.' Keep it apologetic."
        finally:
            db.close()

    @function_tool
    async def create_program(self, context: RunContext):
        """
        Call this to start the program creation process.
        Checks if user has height and weight in database, and asks for missing values.
        """
        print("[PROGRAM] Starting program creation")

        user = self.state.get_user()
        user_id = user.get("id")
        name = user.get("name", "there")

        # Query database to check if user has height and weight
        db = SessionLocal()
        try:
            from db.models import User
            db_user = db.query(User).filter(User.id == user_id).first()

            if not db_user:
                return None, f"Error: Could not find user in database. Say: '{name}, I'm having trouble accessing your profile. Let's try again in a moment.'"

            has_height = db_user.height_cm is not None
            has_weight = db_user.weight_kg is not None

            # Store in state temporarily for this session
            self.state.set("program_creation.height_cm", float(db_user.height_cm) if has_height else None)
            self.state.set("program_creation.weight_kg", float(db_user.weight_kg) if has_weight else None)

            if not has_height and not has_weight:
                # Need both
                print("[PROGRAM] User missing both height and weight - asking for height first")
                return None, f"The user needs to provide height and weight. Say: '{name}, to create the best program for you, I need a couple of quick details. First, what's your height? You can tell me in feet and inches, or centimeters.' Keep it conversational."

            elif not has_height:
                # Need only height
                print("[PROGRAM] User missing height - asking for it")
                return None, f"The user has weight but needs height. Say: '{name}, I have your weight on file, but I need your height to create your program. What's your height? You can tell me in feet and inches, or centimeters.' Keep it friendly."

            elif not has_weight:
                # Need only weight
                print("[PROGRAM] User missing weight - asking for it")
                return None, f"The user has height but needs weight. Say: '{name}, I have your height on file, but I need your current weight. What's your weight? You can tell me in pounds or kilograms.' Keep it supportive."

            else:
                # Have both - proceed to goal collection
                print(f"[PROGRAM] User has height ({db_user.height_cm} cm) and weight ({db_user.weight_kg} kg) - proceeding to goal")
                return None, f"The user has all required info. Say: '{name}, perfect! I have your stats. Now let's talk about your goals. What are you looking to achieve with this program?' Keep it engaging and wait for their response, then call capture_goal()."

        except Exception as e:
            print(f"[ERROR] Failed to check user stats: {e}")
            return None, f"Database error. Say: '{name}, I'm having trouble accessing your profile right now. Let's try again in a moment.' Keep it apologetic."
        finally:
            db.close()

    # ===== PROGRAM CREATION HELPER TOOLS =====

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
                return None, f"That height doesn't seem right. Say: 'Hmm, that doesn't sound quite right. Can you tell me your height again? For example, you could say five foot nine, or 175 centimeters.' Keep it friendly."

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
                        return None, f"Height captured successfully ({height_cm} cm). Say: 'Got it, {name}! Now, what's your current weight? You can tell me in pounds or kilograms.' Keep it supportive."
                    else:
                        # Have both now - proceed to goal collection
                        self.state.set("program_creation.weight_kg", float(db_user.weight_kg))
                        return None, f"Height captured ({height_cm} cm). User has all stats. Say: 'Perfect! I've got your stats. Now let's talk about your goals. What are you looking to achieve with this program?' Keep it engaging and wait for their response, then call capture_goal()."

            finally:
                db.close()

        except Exception as e:
            print(f"[ERROR] Failed to capture height: {e}")
            return None, f"Error capturing height. Say: '{name}, I had trouble understanding that. Can you tell me your height again? For example, five foot nine, or 175 centimeters.' Keep it patient."

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
                return None, f"That weight doesn't seem right. Say: 'Hmm, that doesn't sound quite right. Can you tell me your weight again? For example, you could say 150 pounds, or 68 kilograms.' Keep it supportive."

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
                        return None, f"Weight captured successfully ({weight_kg} kg). Say: 'Great! Now I need your height. What's your height? You can tell me in feet and inches, or centimeters.' Keep it friendly."
                    else:
                        # Have both now - proceed to goal collection
                        self.state.set("program_creation.height_cm", float(db_user.height_cm))
                        return None, f"Weight captured ({weight_kg} kg). User has all stats. Say: 'Awesome, {name}! I've got everything I need. Now let's talk about your goals. What are you looking to achieve with this program?' Keep it engaging and wait for their response, then call capture_goal()."

            finally:
                db.close()

        except Exception as e:
            print(f"[ERROR] Failed to capture weight: {e}")
            return None, f"Error capturing weight. Say: '{name}, I had trouble understanding that. Can you tell me your weight again? For example, 150 pounds, or 68 kilograms.' Keep it patient."

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

        user = self.state.get_user()
        user_id = user.get("id")
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

        return None, f"Goal captured: '{goal_description}' → {goal_category}. Say: 'Got it! So it sounds like you're focused on {confirmation}. Now, how long would you like this program to run? I'd recommend {self._get_recommended_duration(goal_category)} weeks for {confirmation}, but you can choose what works best for you.' Keep it conversational."

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
            return None, f"Invalid duration. Say: 'Hmm, {duration_weeks} weeks seems a bit off. Most programs work best between 4 and 16 weeks. How long would you like your program to be?' Keep it helpful."

        # Store in state
        self.state.set("program_creation.duration_weeks", duration_weeks)

        print(f"[PROGRAM] Duration set to: {duration_weeks} weeks")

        return None, f"Duration captured: {duration_weeks} weeks. Say: 'Perfect! A {duration_weeks}-week program is a great choice. Now, how many days per week can you train? Most people see great results with 3 to 5 days per week.' Keep it encouraging."

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
            return None, f"Invalid frequency. Say: 'That doesn't sound quite right. How many days per week can you realistically train? Something between 2 and 6 days works best for most people.' Keep it supportive."

        # Store in state
        self.state.set("program_creation.days_per_week", days_per_week)

        print(f"[PROGRAM] Frequency set to: {days_per_week} days/week")

        return None, f"Frequency captured: {days_per_week} days/week. Say: 'Awesome! {days_per_week} days per week is solid. Last question: how would you describe your fitness level? Are you a beginner, intermediate, or advanced?' Keep it non-judgmental."

    @function_tool
    async def capture_fitness_level(self, context: RunContext, fitness_level: str):
        """
        Call this when the user describes their fitness level.
        Normalize to beginner, intermediate, or advanced.

        Args:
            fitness_level: The user's fitness level (e.g., "beginner", "intermediate", "I've been lifting for 2 years")
        """
        print(f"[PROGRAM] Capturing fitness level: {fitness_level}")

        user = self.state.get_user()
        name = user.get("name", "there")

        # Normalize fitness level
        normalized_level = self._normalize_fitness_level(fitness_level)

        # Store in state
        self.state.set("program_creation.fitness_level", normalized_level)

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

        return None, f"All parameters collected! Say: 'Perfect, {name}! I'm going to create a {duration_weeks}-week {goal_category} program with {days_per_week} training days per week, tailored for your {normalized_level} level. This is going to be awesome!' Keep it enthusiastic."

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