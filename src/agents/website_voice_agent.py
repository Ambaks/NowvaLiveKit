"""
Website Voice Agent - Streamlined for New Visitors
Handles program creation for website users without authentication
"""

import asyncio
import json
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
from livekit.agents.voice.room_io import RoomInputOptions
from livekit.plugins import openai
from openai.types.beta.realtime.session import TurnDetection

# Imports
from agents.prompts.website_agent_prompt import get_website_agent_prompt
from agents.shared.unit_conversion import normalize_height_to_cm, normalize_weight_to_kg, categorize_goal
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
        self._session_ref = None

        # Get prompt
        instructions = get_website_agent_prompt()

        super().__init__(instructions=instructions)

        logger.info(f"[WEBSITE AGENT] Initialized with email: {state.get('email')}")

    async def on_enter(self):
        """Entry point - generate initial greeting when agent enters conversation"""
        await self.session.generate_reply(
            instructions="Greet the user warmly and ask for their first name. Follow the STEP 1 instructions exactly."
        )

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
            Instruction to start collecting program parameters
        """
        function_name = "capture_name"
        parameters = {"first_name": first_name}

        try:
            # Validate name
            first_name = first_name.strip()
            if not first_name or len(first_name) < 1:
                result = None, "Name is too short. Ask for first name again."
                self._log_function_call(function_name, parameters, result)
                return result

            if len(first_name) > 50:
                result = None, "Name is too long. Ask for just first name."
                self._log_function_call(function_name, parameters, result)
                return result

            # Store in state
            self.state["name"] = first_name
            logger.info(f"[WEBSITE AGENT] Name captured: {first_name}")

            result = None, f"Name captured. Now start collecting program parameters with Question 1 (height and weight)."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture name: {e}")
            result = None, "Error capturing name. Ask for name again."
            self._log_function_call(function_name, parameters, result)
            return result


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
            # Parse and validate height
            height_cm = normalize_height_to_cm(height_value)
            if height_cm is None or height_cm < 50 or height_cm > 300:
                result = None, "Height invalid. Ask for height again with examples (e.g., 5'9\" or 175cm)."
                self._log_function_call(function_name, parameters, result)
                return result

            # Parse and validate weight
            weight_kg = normalize_weight_to_kg(weight_value)
            if weight_kg is None or weight_kg < 30 or weight_kg > 300:
                result = None, "Weight invalid. Ask for weight again with examples (e.g., 185lbs or 80kg)."
                self._log_function_call(function_name, parameters, result)
                return result

            # Save to state (will update DB at the end)
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
            # Validate age
            if age < 13 or age > 100:
                result = None, "Age out of range (13-100). Ask for age again."
                self._log_function_call(function_name, parameters, result)
                return result

            # Normalize sex
            sex_normalized = sex.lower().strip()
            if sex_normalized in ["m", "male", "man", "boy"]:
                sex_normalized = "male"
            elif sex_normalized in ["f", "female", "woman", "girl"]:
                sex_normalized = "female"
            else:
                result = None, "Sex unclear. Ask if male or female."
                self._log_function_call(function_name, parameters, result)
                return result

            # Save to state (will update DB at the end)
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
            goal_category = categorize_goal(goal_description)

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
                result = None, "Duration out of range (2-52 weeks). Ask for duration again."
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
                result = None, "Frequency out of range (1-7 days/week). Ask for frequency again."
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
                result = None, "Duration out of range (30-180 minutes). Ask for session duration again."
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
        This is the LAST question - after this, update the user in DB and generate program.

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

            # Set VBT to false by default for website users
            self.state["program_creation"]["has_vbt_capability"] = False

            result = None, "All parameters collected! Now immediately call update_user_profile() to save their info to the database, then generate the program."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture fitness level: {e}")
            result = None, "Error capturing fitness level. Please tell me your level again."
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def update_user_profile(self, context: RunContext):
        """
        Update user profile in database with all collected information.
        Called after all questions are answered, before generating the program.

        Returns:
            Instruction to generate the workout program
        """
        function_name = "update_user_profile"
        parameters = {}

        try:
            user_id = self.state.get("user_id")
            if not user_id:
                result = None, "Error: No user ID. Cannot update profile."
                self._log_function_call(function_name, parameters, result)
                return result

            name = self.state.get("name")
            program_params = self.state.get("program_creation", {})

            # Update user in database
            db = SessionLocal()
            try:
                db_user = db.query(User).filter(User.id == user_id).first()
                if db_user:
                    # Update name
                    if name:
                        db_user.name = name

                    # Update physical stats
                    if "height_cm" in program_params:
                        db_user.height_cm = program_params["height_cm"]
                    if "weight_kg" in program_params:
                        db_user.weight_kg = program_params["weight_kg"]
                    if "age" in program_params:
                        db_user.age = program_params["age"]
                    if "sex" in program_params:
                        db_user.sex = program_params["sex"]

                    db.commit()
                    logger.info(f"[WEBSITE AGENT] Updated user profile for {self.state.get('email')}")

                    result = None, "Profile updated successfully. Tell user you're submitting for generation, then immediately call generate_workout_program()."
                    self._log_function_call(function_name, parameters, result)
                    return result
                else:
                    result = None, "Error: User not found in database."
                    self._log_function_call(function_name, parameters, result)
                    return result

            except Exception as e:
                logger.error(f"[ERROR] Failed to update user profile: {e}")
                db.rollback()
                result = None, "Error updating profile. Continuing to program generation anyway. Call generate_workout_program()."
                self._log_function_call(function_name, parameters, result)
                return result
            finally:
                db.close()

        except Exception as e:
            logger.error(f"[ERROR] Failed to update user profile: {e}")
            result = None, "Error updating profile. Continuing to program generation anyway. Call generate_workout_program()."
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
                "name": self.state.get("name"),
                "email": user_email,
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

                    # Send data message to frontend to trigger completion UI
                    try:
                        await context.room.local_participant.publish_data(
                            json.dumps({
                                "type": "program_generating",
                                "job_id": job_id,
                                "email": user_email
                            }).encode(),
                            reliable=True
                        )
                        logger.info("[PROGRAM] Sent 'program_generating' data message to frontend")
                    except Exception as e:
                        logger.error(f"[PROGRAM] Failed to send data message: {e}")

                    # Tell user they'll receive email and call end_conversation()
                    result = None, f"Program generation started successfully. Inform user their program is being created and will arrive at {user_email} within 10 minutes. Mention checking spam folder. Then immediately call end_conversation()."
                    self._log_function_call(function_name, parameters, result)
                    return result
                else:
                    # Error
                    logger.error(f"[PROGRAM] API error: {response.status_code} - {response.text}")
                    result = None, f"Error starting program generation. Tell user there's an issue and team will contact them at {user_email}."
                    self._log_function_call(function_name, parameters, result)
                    return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to generate program: {e}")
            result = None, f"Error generating program. Tell user there's an issue and team will contact them at {self.state.get('email')}."
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def end_conversation(self, context: RunContext):
        """
        End the conversation gracefully.
        Call this AFTER telling the user their program is being generated.
        """
        function_name = "end_conversation"
        parameters = {}

        try:
            logger.info("[WEBSITE AGENT] Gracefully ending conversation...")

            # Disconnect from the room to free up resources
            try:
                await context.room.disconnect()
                logger.info("[WEBSITE AGENT] Disconnected from room successfully")
            except Exception as disconnect_error:
                logger.warning(f"[WEBSITE AGENT] Error disconnecting from room: {disconnect_error}")

            result = None, "Conversation ended successfully. Session will close."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to end conversation: {e}")
            result = None, f"Error disconnecting: {e}"
            self._log_function_call(function_name, parameters, result)
            return result


# =========================================================================
# ENTRY POINT
# =========================================================================

async def entrypoint(ctx: agents.JobContext):
    """Entry point for website voice agent"""

    logger.info("[WEBSITE AGENT] Starting...")

    # Connect to the room first
    await ctx.connect()
    logger.info(f"[WEBSITE AGENT] Connected to room: {ctx.room.name}")

    # Get email from participant metadata using event-based waiting
    email = None
    participant_event = asyncio.Event()
    found_participant = {}

    def on_participant_connected(participant):
        if participant.metadata:
            try:
                metadata_dict = json.loads(participant.metadata)
                found_participant['email'] = metadata_dict.get('email')
                found_participant['ref'] = participant
                participant_event.set()
            except json.JSONDecodeError as e:
                logger.error(f"[ERROR] Failed to parse participant metadata: {participant.metadata}, error: {e}")

    # Check already-connected participants first
    for participant in ctx.room.remote_participants.values():
        if participant.metadata:
            try:
                metadata_dict = json.loads(participant.metadata)
                email = metadata_dict.get('email')
                if email:
                    logger.info(f"[WEBSITE AGENT] Email from existing participant: {email}")
                    break
            except json.JSONDecodeError:
                pass

    # If no email found yet, wait for participant connection event
    if not email:
        ctx.room.on("participant_connected", on_participant_connected)
        try:
            await asyncio.wait_for(participant_event.wait(), timeout=10.0)
            email = found_participant.get('email')
        except asyncio.TimeoutError:
            logger.error("[ERROR] No participant connected within 10 seconds")
            return

    if not email:
        logger.error("[ERROR] No email provided in participant metadata")
        return

    logger.info(f"[WEBSITE AGENT] Using email: {email}")

    # Create user account immediately (before conversation starts)
    db = SessionLocal()
    user_id = None
    username = None
    try:
        # Check if user exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            user_id = existing_user.id
            username = existing_user.username
            logger.info(f"[WEBSITE AGENT] Existing user found: {email}, ID: {user_id}")
        else:
            # Generate username from email
            email_prefix = email.split('@')[0]
            email_prefix = re.sub(r'[^\w\.]', '', email_prefix)
            random_suffix = secrets.randbelow(10000)
            username = f"{email_prefix}_{random_suffix:04d}"

            # Generate random password hash
            password_hash = secrets.token_urlsafe(32)

            # Create new user (name will be updated later)
            new_user = User(
                id=uuid.uuid4(),
                username=username,
                name="",  # Will be updated after asking
                email=email,
                password_hash=password_hash
            )
            db.add(new_user)
            db.commit()
            user_id = new_user.id
            logger.info(f"[WEBSITE AGENT] Created new user: {email}, ID: {user_id}")
    except Exception as e:
        logger.error(f"[ERROR] Failed to create user: {e}")
        db.rollback()
        return
    finally:
        db.close()

    # Initialize ephemeral state (simple dict)
    state = {
        "email": email,
        "name": None,
        "user_id": user_id,
        "username": username,
        "program_creation": {}
    }

    # Initialize OpenAI Realtime Model
    realtime_model = openai.realtime.RealtimeModel(
        voice=os.getenv("REALTIME_VOICE", "marin"),
        turn_detection=TurnDetection(
            type="semantic_vad",
            eagerness="low",           # Patient — let users finish thinking before responding
            create_response=True,
            interrupt_response=True,
            silence_duration_ms=1000,   # Require 1s of silence before treating as end-of-turn
        ),
        input_audio_noise_reduction="far_field",  # Users may be at varying distances
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
    agent._session_ref = session

    # Start session — on_enter() will handle the initial greeting automatically
    logger.info("[WEBSITE AGENT] Starting session...")
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            pre_connect_audio=True,
            pre_connect_audio_timeout=5.0,
        ),
    )

    logger.info("[WEBSITE AGENT] Session ended.")


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
