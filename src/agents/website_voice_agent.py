"""
Website Voice Agent - Streamlined for New Visitors
Handles program creation for website users without authentication
"""

import asyncio
import os
import re
import sys
import uuid
import secrets
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Add parent directory (src/) to path when running as subprocess
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()

from livekit import agents
from livekit.agents import AgentSession, Agent, RunContext
from livekit.agents.llm import function_tool
from livekit.plugins import openai

# Imports
from agents.prompts.website_agent_prompt import get_website_agent_prompt
from db.database import SessionLocal
from db.models import User
import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class WebsiteVoiceAgent(Agent):
    """Streamlined voice agent for website visitors creating programs"""

    def __init__(self, state: Dict[str, Any]) -> None:
        """
        Initialize website voice agent with ephemeral state

        Args:
            state: Dictionary containing email from room metadata
        """
        # Ephemeral state (not persisted to file)
        self.state = state

        # Store reference to session (will be set later)
        self.session = None

        # Get prompt
        instructions = get_website_agent_prompt()

        super().__init__(instructions=instructions)

        logger.info(f"[WEBSITE AGENT] Initialized with email: {state.get('email')}")

    def _log_function_call(self, function_name: str, parameters: dict, result: any):
        """Helper method to log function tool calls"""
        logger.info(f"[TOOL] {function_name}({parameters}) -> {result}")

    # =========================================================================
    # NEW TOOLS - Website-Specific
    # =========================================================================

    @function_tool
    async def capture_name(self, context: RunContext, first_name: str):
        """
        Capture user's first name for personalization.

        Args:
            first_name: User's first name

        Returns:
            Instruction to immediately call create_user_account()
        """
        function_name = "capture_name"
        parameters = {"first_name": first_name}

        try:
            # Validate name
            first_name = first_name.strip()
            if not first_name or len(first_name) < 1:
                result = None, "Name is too short. Say: 'Sorry, I didn't catch that. What's your first name?'"
                self._log_function_call(function_name, parameters, result)
                return result

            if len(first_name) > 50:
                result = None, "Name is too long. Say: 'That's a long name! Can you tell me just your first name?'"
                self._log_function_call(function_name, parameters, result)
                return result

            # Store in state
            self.state["name"] = first_name
            logger.info(f"[WEBSITE AGENT] Name captured: {first_name}")

            result = None, f"Name captured. Now immediately call create_user_account() to set up their profile."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture name: {e}")
            result = None, "Error capturing name. Say: 'Sorry, can you tell me your name again?'"
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def create_user_account(self, context: RunContext):
        """
        Create User account in database with email and name from state.
        Generates username and password automatically.

        Returns:
            Instruction to start collecting program parameters
        """
        function_name = "create_user_account"
        parameters = {}

        try:
            email = self.state.get("email")
            name = self.state.get("name")

            if not email:
                result = None, "Error: No email in state. User should restart from website."
                self._log_function_call(function_name, parameters, result)
                return result

            if not name:
                result = None, "Error: No name captured. Call capture_name() first."
                self._log_function_call(function_name, parameters, result)
                return result

            # Generate username from email
            username = self._generate_username_from_email(email)

            # Generate random password hash
            password_hash = self._generate_password_hash()

            # Create user in database
            db = SessionLocal()
            try:
                # Check if user with this email already exists
                existing_user = db.query(User).filter(User.email == email).first()
                if existing_user:
                    # User exists - use their ID
                    user_id = existing_user.id
                    logger.info(f"[WEBSITE AGENT] Existing user found: {email}, using ID: {user_id}")

                    # Update their name if changed
                    if existing_user.name != name:
                        existing_user.name = name
                        db.commit()
                        logger.info(f"[WEBSITE AGENT] Updated name to: {name}")
                else:
                    # Create new user
                    new_user = User(
                        id=uuid.uuid4(),
                        username=username,
                        name=name,
                        email=email,
                        password_hash=password_hash
                    )
                    db.add(new_user)
                    db.commit()
                    user_id = new_user.id
                    logger.info(f"[WEBSITE AGENT] Created new user: {email}, ID: {user_id}")

                # Store user_id and username in state
                self.state["user_id"] = user_id
                self.state["username"] = username

                result = None, "Account created! Now start collecting program parameters with Question 1 (height and weight)."
                self._log_function_call(function_name, parameters, result)
                return result

            except Exception as e:
                logger.error(f"[ERROR] Database error creating user: {e}")
                db.rollback()
                result = None, "Error creating account. Say: 'I'm having trouble setting up your account. Let's try again.'"
                self._log_function_call(function_name, parameters, result)
                return result
            finally:
                db.close()

        except Exception as e:
            logger.error(f"[ERROR] Failed to create user account: {e}")
            result = None, "Error creating account. Say: 'I'm having trouble setting up your account. Let's try again.'"
            self._log_function_call(function_name, parameters, result)
            return result

    def _generate_username_from_email(self, email: str) -> str:
        """
        Generate unique username from email address.

        Args:
            email: Email address

        Returns:
            Generated username (e.g., john.doe_4829)
        """
        # Get email prefix (before @)
        email_prefix = email.split('@')[0]

        # Remove special characters except dots and underscores
        email_prefix = re.sub(r'[^\w\.]', '', email_prefix)

        # Add random 4-digit suffix for uniqueness
        random_suffix = secrets.randbelow(10000)

        username = f"{email_prefix}_{random_suffix:04d}"

        return username

    def _generate_password_hash(self) -> str:
        """
        Generate random password hash for user account.
        Since website users don't log in, we just need a valid hash.

        Returns:
            Random password hash
        """
        # Generate random password
        random_password = secrets.token_urlsafe(32)

        # For now, just store the random string
        # In production, you'd use bcrypt or similar:
        # import bcrypt
        # password_hash = bcrypt.hashpw(random_password.encode(), bcrypt.gensalt())
        # return password_hash.decode()

        return random_password

    # =========================================================================
    # PROGRAM CREATION TOOLS - Copied from voice_agent.py
    # =========================================================================

    @function_tool
    async def capture_height_weight(self, context: RunContext, height_value: str = None, weight_value: str = None):
        """
        Call this when the user provides both height and weight together.

        Args:
            height_value: The height as spoken by the user (e.g., "5'10\"", "175 cm")
            weight_value: The weight as spoken by the user (e.g., "185 pounds", "80 kg")
        """
        function_name = "capture_height_weight"
        parameters = {"height_value": height_value, "weight_value": weight_value}

        try:
            user_id = self.state.get("user_id")
            if not user_id:
                result = None, "Error: No user account. Call create_user_account() first."
                self._log_function_call(function_name, parameters, result)
                return result

            # Parse and validate height
            height_cm = self._normalize_height_to_cm(height_value)
            if height_cm is None or height_cm < 50 or height_cm > 300:
                result = None, "That height doesn't seem right. Say: 'Hmm, that height doesn't sound quite right. Can you tell me your height again? For example, five foot nine, or 175 centimeters.' Keep it friendly."
                self._log_function_call(function_name, parameters, result)
                return result

            # Parse and validate weight
            weight_kg = self._normalize_weight_to_kg(weight_value)
            if weight_kg is None or weight_kg < 30 or weight_kg > 300:
                result = None, "That weight doesn't seem right. Say: 'Hmm, that weight doesn't sound quite right. Can you tell me your weight again? For example, 185 pounds or 80 kilograms.' Keep it friendly."
                self._log_function_call(function_name, parameters, result)
                return result

            # Save to database
            db = SessionLocal()
            try:
                db_user = db.query(User).filter(User.id == user_id).first()
                if db_user:
                    db_user.height_cm = height_cm
                    db_user.weight_kg = weight_kg
                    db.commit()
                    logger.info(f"[PROGRAM] Saved to database: height={height_cm} cm, weight={weight_kg} kg")
            except Exception as e:
                logger.error(f"[ERROR] Failed to save height/weight to database: {e}")
                db.rollback()
            finally:
                db.close()

            # Save to state
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["height_cm"] = height_cm
            self.state["program_creation"]["weight_kg"] = weight_kg

            logger.info(f"[PROGRAM] Height: {height_cm} cm, Weight: {weight_kg} kg")

            result = None, "Captured. Now immediately ask Question 2 about age and sex."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture height/weight: {e}")
            result = None, "Error capturing height and weight. Please provide them again."
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def capture_age_sex(self, context: RunContext, age: int, sex: str):
        """
        Call this when the user provides both age and sex together.

        Args:
            age: User's age in years
            sex: "male", "female", "M", "F", etc.
        """
        function_name = "capture_age_sex"
        parameters = {"age": age, "sex": sex}

        try:
            user_id = self.state.get("user_id")
            if not user_id:
                result = None, "Error: No user account. Call create_user_account() first."
                self._log_function_call(function_name, parameters, result)
                return result

            # Validate age
            if age < 13 or age > 100:
                result = None, "That age seems unusual. Say: 'Hmm, that age doesn't seem right. How old are you?' Keep it friendly."
                self._log_function_call(function_name, parameters, result)
                return result

            # Normalize sex
            sex_normalized = sex.lower().strip()
            if sex_normalized in ["m", "male", "man", "boy"]:
                sex_normalized = "male"
            elif sex_normalized in ["f", "female", "woman", "girl"]:
                sex_normalized = "female"
            else:
                result = None, "I didn't catch the sex. Say: 'Sorry, are you male or female?' Keep it simple."
                self._log_function_call(function_name, parameters, result)
                return result

            # Save to database
            db = SessionLocal()
            try:
                db_user = db.query(User).filter(User.id == user_id).first()
                if db_user:
                    db_user.age = age
                    db_user.sex = sex_normalized
                    db.commit()
                    logger.info(f"[PROGRAM] Saved to database: age={age}, sex={sex_normalized}")
            except Exception as e:
                logger.error(f"[ERROR] Failed to save age/sex to database: {e}")
                db.rollback()
            finally:
                db.close()

            # Save to state
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["age"] = age
            self.state["program_creation"]["sex"] = sex_normalized

            logger.info(f"[PROGRAM] Age: {age}, Sex: {sex_normalized}")

            result = None, "Captured. Now immediately ask Question 3 about fitness goal."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture age/sex: {e}")
            result = None, "Error capturing age and sex. Please provide them again."
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def capture_goal(self, context: RunContext, goal_description: str):
        """
        Call this when the user describes their fitness goal.

        Args:
            goal_description: User's description of their fitness goal
        """
        function_name = "capture_goal"
        parameters = {"goal_description": goal_description}

        try:
            # Categorize goal
            goal_category = self._categorize_goal(goal_description)

            # Recommended duration based on goal
            duration_recommendations = {
                "power": 8,
                "strength": 12,
                "hypertrophy": 12
            }
            recommended_duration = duration_recommendations.get(goal_category, 12)

            # Save to state
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["goal_raw"] = goal_description
            self.state["program_creation"]["goal_category"] = goal_category
            self.state["program_creation"]["recommended_duration"] = recommended_duration

            logger.info(f"[PROGRAM] Goal: {goal_description} -> Category: {goal_category}")

            result = None, f"Captured and categorized as '{goal_category}'. Now immediately ask Question 4 about program duration (recommend {recommended_duration} weeks)."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture goal: {e}")
            result = None, "Error capturing goal. Please describe your goal again."
            self._log_function_call(function_name, parameters, result)
            return result

    def _categorize_goal(self, goal_text: str) -> str:
        """Categorize user's goal into power, strength, or hypertrophy"""
        goal_lower = goal_text.lower()

        # Power/explosive keywords
        power_keywords = [
            "explosive", "power", "athletic", "speed", "jump", "sprint",
            "vertical", "fast", "quick", "agility", "reactive", "plyometric",
            "burst", "acceleration"
        ]

        # Strength keywords
        strength_keywords = [
            "strong", "strength", "lift heavy", "max", "1rm", "powerlifting",
            "squat", "deadlift", "bench", "press", "force"
        ]

        # Hypertrophy keywords
        hypertrophy_keywords = [
            "muscle", "size", "big", "mass", "bulk", "bodybuilding",
            "aesthetic", "look good", "physique", "gain weight", "grow"
        ]

        # Count matches
        power_score = sum(1 for kw in power_keywords if kw in goal_lower)
        strength_score = sum(1 for kw in strength_keywords if kw in goal_lower)
        hypertrophy_score = sum(1 for kw in hypertrophy_keywords if kw in goal_lower)

        # Determine category
        if power_score > strength_score and power_score > hypertrophy_score:
            return "power"
        elif strength_score > hypertrophy_score:
            return "strength"
        else:
            return "hypertrophy"

    @function_tool
    async def capture_program_duration(self, context: RunContext, duration_weeks: int):
        """
        Call this when the user specifies how many weeks they want their program to be.

        Args:
            duration_weeks: Number of weeks (2-52)
        """
        function_name = "capture_program_duration"
        parameters = {"duration_weeks": duration_weeks}

        try:
            # Validate duration
            if duration_weeks < 2 or duration_weeks > 52:
                result = None, "That duration is out of range. Say: 'Program duration should be between 2 and 52 weeks. How many weeks would you like?'"
                self._log_function_call(function_name, parameters, result)
                return result

            # Save to state
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["duration_weeks"] = duration_weeks

            logger.info(f"[PROGRAM] Duration: {duration_weeks} weeks")

            result = None, "Captured. Now immediately ask Question 5 about training frequency (days per week)."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture program duration: {e}")
            result = None, "Error capturing duration. Please specify the number of weeks again."
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def capture_training_frequency(self, context: RunContext, days_per_week: int):
        """
        Call this when the user specifies how many days per week they can train.

        Args:
            days_per_week: Number of training days per week (1-7)
        """
        function_name = "capture_training_frequency"
        parameters = {"days_per_week": days_per_week}

        try:
            # Validate frequency
            if days_per_week < 1 or days_per_week > 7:
                result = None, "That frequency is out of range. Say: 'Training frequency should be between 1 and 7 days per week. How many days can you train?'"
                self._log_function_call(function_name, parameters, result)
                return result

            # Save to state
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["days_per_week"] = days_per_week

            logger.info(f"[PROGRAM] Frequency: {days_per_week} days/week")

            result = None, "Captured. Now immediately ask Question 6 about session duration (optional)."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture training frequency: {e}")
            result = None, "Error capturing frequency. Please specify the number of days again."
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def capture_session_duration(self, context: RunContext, duration_minutes: int):
        """
        Call this when the user specifies how long each training session will be.

        Args:
            duration_minutes: Session duration in minutes (30-180)
        """
        function_name = "capture_session_duration"
        parameters = {"duration_minutes": duration_minutes}

        try:
            # Validate duration
            if duration_minutes < 30 or duration_minutes > 180:
                result = None, "That duration is out of range. Say: 'Session duration should be between 30 and 180 minutes. How long can you train per session?'"
                self._log_function_call(function_name, parameters, result)
                return result

            # Save to state
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["session_duration"] = duration_minutes

            logger.info(f"[PROGRAM] Session duration: {duration_minutes} minutes")

            result = None, "Captured. Now immediately ask Question 7 about injuries (optional)."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture session duration: {e}")
            result = None, "Error capturing session duration. Please specify the duration again."
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def capture_injury_history(self, context: RunContext, injury_description: str):
        """
        Call this when the user describes any injuries or limitations.

        Args:
            injury_description: Description of injuries or "none"
        """
        function_name = "capture_injury_history"
        parameters = {"injury_description": injury_description}

        try:
            # Save to state
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["injury_history"] = injury_description

            logger.info(f"[PROGRAM] Injury history: {injury_description}")

            result = None, "Captured. Now immediately ask Question 8 about specific sport (optional)."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture injury history: {e}")
            result = None, "Error capturing injury history. Please describe any injuries again."
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def capture_specific_sport(self, context: RunContext, sport_name: str):
        """
        Call this when the user mentions a specific sport they're training for.

        Args:
            sport_name: Name of the sport or "none"
        """
        function_name = "capture_specific_sport"
        parameters = {"sport_name": sport_name}

        try:
            # Save to state
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["specific_sport"] = sport_name

            logger.info(f"[PROGRAM] Specific sport: {sport_name}")

            result = None, "Captured. Now immediately ask Question 9 about additional notes (optional)."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture specific sport: {e}")
            result = None, "Error capturing sport. Please tell me the sport again."
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def capture_user_notes(self, context: RunContext, notes: str):
        """
        Call this when the user provides additional preferences or requirements.

        Args:
            notes: Additional notes or preferences
        """
        function_name = "capture_user_notes"
        parameters = {"notes": notes}

        try:
            # Save to state
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["user_notes"] = notes

            logger.info(f"[PROGRAM] User notes: {notes}")

            result = None, "Captured. Now immediately ask Question 10 about fitness level (LAST QUESTION)."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture user notes: {e}")
            result = None, "Error capturing notes. Please tell me your preferences again."
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def capture_fitness_level(self, context: RunContext, fitness_level: str):
        """
        Call this when the user describes their fitness level.

        Args:
            fitness_level: "beginner", "intermediate", or "advanced"
        """
        function_name = "capture_fitness_level"
        parameters = {"fitness_level": fitness_level}

        try:
            # Normalize fitness level
            level_normalized = fitness_level.lower().strip()
            if "beginner" in level_normalized or "new" in level_normalized or "start" in level_normalized:
                level_normalized = "beginner"
            elif "advanced" in level_normalized or "expert" in level_normalized or "experienced" in level_normalized:
                level_normalized = "advanced"
            else:
                level_normalized = "intermediate"

            # Save to state
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["fitness_level"] = level_normalized

            logger.info(f"[PROGRAM] Fitness level: {level_normalized}")

            result = None, "Captured. Now immediately ask Question 11 about VBT equipment."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture fitness level: {e}")
            result = None, "Error capturing fitness level. Please tell me your level again."
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def capture_vbt_equipment(self, context: RunContext, has_equipment: bool):
        """
        Call this when the user responds about VBT equipment availability.

        Args:
            has_equipment: True if user has VBT equipment, False otherwise
        """
        function_name = "capture_vbt_equipment"
        parameters = {"has_equipment": has_equipment}

        try:
            # Save to state
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["has_vbt_capability"] = has_equipment

            logger.info(f"[PROGRAM] VBT equipment: {has_equipment}")

            result = None, "Captured. All parameters collected! Say: 'Perfect! I have everything I need. Your program is on its way...' Then immediately call generate_workout_program()."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture VBT equipment: {e}")
            result = None, "Error capturing VBT equipment. Say: 'Sorry, do you have VBT equipment? Just yes or no.'"
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def set_vbt_capability(self, context: RunContext, enabled: bool):
        """
        Set velocity-based training (VBT) capability.
        Called automatically after fitness level is captured.

        Args:
            enabled: True to enable VBT, False to disable
        """
        function_name = "set_vbt_capability"
        parameters = {"enabled": enabled}

        try:
            # Save to state
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["has_vbt_capability"] = enabled

            logger.info(f"[PROGRAM] VBT capability: {enabled}")

            result = None, "VBT decision made. All parameters ready. Now immediately call generate_workout_program()."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to set VBT capability: {e}")
            result = None, "Error setting VBT. Continuing anyway, call generate_workout_program()."
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def generate_workout_program(self, context: RunContext):
        """
        Generate the workout program by calling FastAPI backend.
        This triggers async program generation (takes 3-6 minutes).
        After submitting, tell user they'll receive email and call end_conversation().
        """
        function_name = "generate_workout_program"
        parameters = {}

        try:
            user_id = self.state.get("user_id")
            user_email = self.state.get("email")

            if not user_id:
                result = None, "Error: No user account created. Cannot generate program."
                self._log_function_call(function_name, parameters, result)
                return result

            program_params = self.state.get("program_creation", {})

            # Validate all required parameters
            required_params = [
                "height_cm", "weight_kg", "age", "sex",
                "goal_category", "goal_raw", "duration_weeks",
                "days_per_week", "fitness_level"
            ]

            missing = [p for p in required_params if p not in program_params]
            if missing:
                result = None, f"Error: Missing required parameters: {missing}. Cannot generate program."
                self._log_function_call(function_name, parameters, result)
                return result

            # Prepare request payload (include send_email flag for website users)
            payload = {
                "user_id": str(user_id),
                "height_cm": program_params["height_cm"],
                "weight_kg": program_params["weight_kg"],
                "age": program_params["age"],
                "sex": program_params["sex"],
                "goal_category": program_params["goal_category"],
                "goal_raw": program_params["goal_raw"],
                "duration_weeks": program_params["duration_weeks"],
                "days_per_week": program_params["days_per_week"],
                "session_duration": program_params.get("session_duration", 60),
                "injury_history": program_params.get("injury_history", "none"),
                "specific_sport": program_params.get("specific_sport", "none"),
                "user_notes": program_params.get("user_notes", None),
                "fitness_level": program_params["fitness_level"],
                "has_vbt_capability": program_params.get("has_vbt_capability", False),
                "send_email": True  # Website users always get email
            }

            # Call FastAPI endpoint
            fastapi_url = os.getenv("FASTAPI_URL", "http://localhost:8000")
            url = f"{fastapi_url}/api/programs/generate"

            logger.info(f"[PROGRAM] Calling program generation API: {url}")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)

                if response.status_code == 202:
                    # Success - generation started
                    data = response.json()
                    job_id = data.get("job_id")

                    # Save job_id to state
                    self.state["program_creation"]["job_id"] = job_id

                    logger.info(f"[PROGRAM] Program generation started. Job ID: {job_id}")

                    # Tell user they'll receive email and call end_conversation()
                    result = None, f"Program generation started! Tell user: 'Perfect! Your personalized program is being created now. You'll receive it at {user_email} within the next 10 minutes. Be sure to check your spam folder if you don't see it! The program includes your full workout schedule, exercise details, and progression plan. Can't wait for you to get started!' Then immediately call end_conversation() to gracefully disconnect."
                    self._log_function_call(function_name, parameters, result)
                    return result
                else:
                    # Error
                    logger.error(f"[PROGRAM] API error: {response.status_code} - {response.text}")
                    result = None, f"Error starting program generation. Say: 'I'm having trouble generating your program. Our team will reach out to you at {user_email}.'"
                    self._log_function_call(function_name, parameters, result)
                    return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to generate program: {e}")
            result = None, f"Error generating program. Say: 'I'm having trouble generating your program. Our team will reach out to you at {self.state.get('email')}.'"
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def end_conversation(self, context: RunContext):
        """
        End the conversation gracefully by disconnecting from the LiveKit room.
        Call this AFTER telling the user their program is being generated.
        """
        function_name = "end_conversation"
        parameters = {}

        try:
            if self.session is None:
                logger.error("[WEBSITE AGENT] Cannot disconnect - no session reference")
                result = None, "Error: No session available to disconnect."
                self._log_function_call(function_name, parameters, result)
                return result

            logger.info("[WEBSITE AGENT] Gracefully ending conversation and disconnecting...")

            # Disconnect the session gracefully
            await self.session.shutdown(drain=True)

            logger.info("[WEBSITE AGENT] ✅ Session disconnected successfully")

            result = None, "Conversation ended successfully."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to end conversation: {e}")
            result = None, f"Error disconnecting: {e}"
            self._log_function_call(function_name, parameters, result)
            return result

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _normalize_height_to_cm(self, height_str: str) -> Optional[float]:
        """Convert various height formats to centimeters"""
        if not height_str:
            return None

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

        # Pattern: Just feet
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
            if num < 10:  # Likely meters
                return num * 100
            elif 50 <= num <= 300:  # Likely cm
                return num
            elif num > 300:  # Likely inches
                return num * 2.54

        return None

    def _normalize_weight_to_kg(self, weight_str: str) -> Optional[float]:
        """Convert various weight formats to kilograms"""
        if not weight_str:
            return None

        weight_str = weight_str.lower().strip()

        # Pattern: X kg or X kilograms
        kg_match = re.search(r'(\d+\.?\d*)\s*(kg|kilogram)', weight_str)
        if kg_match:
            return float(kg_match.group(1))

        # Pattern: X lbs or X pounds
        lbs_match = re.search(r'(\d+\.?\d*)\s*(lbs?|pounds?)', weight_str)
        if lbs_match:
            return float(lbs_match.group(1)) * 0.453592

        # Pattern: Just a number - assume pounds if < 500, kg if >= 500
        number_match = re.search(r'(\d+\.?\d*)', weight_str)
        if number_match:
            num = float(number_match.group(1))
            if num < 500:  # Likely pounds
                return num * 0.453592
            else:  # Likely kg
                return num

        return None


# =========================================================================
# ENTRY POINT
# =========================================================================

async def entrypoint(ctx: agents.JobContext):
    """Entry point for website voice agent"""

    logger.info("[WEBSITE AGENT] Starting...")

    # Connect to the room first
    await ctx.connect()
    logger.info(f"[WEBSITE AGENT] Connected to room: {ctx.room.name}")

    # Get email from participant metadata (set in the token)
    email = None
    import json

    # Wait for a participant to join (max 10 seconds)
    for i in range(20):
        await asyncio.sleep(0.5)

        participants = list(ctx.room.remote_participants.values())
        logger.info(f"[WEBSITE AGENT] Checking for participants... Found: {len(participants)}")

        if participants:
            participant = participants[0]
            logger.info(f"[WEBSITE AGENT] Participant identity: {participant.identity}, metadata: {participant.metadata}")

            if participant.metadata:
                try:
                    metadata_dict = json.loads(participant.metadata)
                    email = metadata_dict.get('email')
                    logger.info(f"[WEBSITE AGENT] Email from participant metadata: {email}")
                    break
                except json.JSONDecodeError as e:
                    logger.error(f"[ERROR] Failed to parse participant metadata: {participant.metadata}, error: {e}")

    if not email:
        logger.error("[ERROR] No email provided in participant metadata after waiting")
        return

    logger.info(f"[WEBSITE AGENT] Using email: {email}")

    # Initialize ephemeral state (simple dict)
    state = {
        "email": email,
        "name": None,
        "user_id": None,
        "username": None,
        "program_creation": {}
    }

    # Initialize OpenAI Realtime Model
    realtime_model = openai.realtime.RealtimeModel(
        voice=os.getenv("REALTIME_VOICE", "marin"),
        temperature=0.8,
        turn_detection={
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 300,
        },
        modalities=["audio", "text"],
    )

    # Create agent with state
    agent = WebsiteVoiceAgent(state=state)

    # Create session
    session = AgentSession(
        llm=realtime_model,
        preemptive_generation=True
    )

    # Store session reference in agent so it can disconnect later
    agent.session = session

    # Start session and make agent speak first
    await session.start(room=ctx.room, agent=agent)

    # Send initial greeting so agent speaks first (don't wait for user)
    await asyncio.sleep(1.5)  # Brief delay to ensure connection is fully established

    # Send initial greeting message
    initial_greeting = "Hi there! I'm Nova, your AI fitness coach. I'm excited to help you create a personalized workout program. What's your first name?"

    logger.info(f"[WEBSITE AGENT] Sending initial greeting: {initial_greeting}")
    await session.say(initial_greeting)


if __name__ == "__main__":
    import signal

    shutting_down = False

    def signal_handler(signum, frame):
        global shutting_down
        if not shutting_down:
            shutting_down = True
            logger.info("\n[SHUTDOWN] Gracefully shutting down website agent...")
            sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the agent using LiveKit's CLI
    # The agent will automatically join any room created on this LiveKit server
    try:
        agents.cli.run_app(
            agents.WorkerOptions(
                entrypoint_fnc=entrypoint,
            )
        )
    except KeyboardInterrupt:
        logger.info("\n[SHUTDOWN] Agent stopped by user")
        sys.exit(0)
    except Exception as e:
        if "termios" not in str(e).lower():
            logger.error(f"[ERROR] {e}")
        sys.exit(0)
