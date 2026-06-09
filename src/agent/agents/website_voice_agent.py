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
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

load_dotenv()

from livekit import agents
from livekit.agents import AgentSession, Agent, RunContext, TurnHandlingOptions
from livekit.agents.llm import function_tool
from livekit.agents.voice.room_io import RoomInputOptions
from livekit.plugins import deepgram, openai, silero, elevenlabs, noise_cancellation
from livekit.plugins.turn_detector.english import EnglishModel

# Imports
from agent.agents.prompts.website_step_prompts import (
    ConversationStep, get_step_prompt, get_first_step, get_next_step, get_first_missing_step
)
from agent.agents.shared.unit_conversion import normalize_height_to_cm, normalize_weight_to_kg, categorize_goal
from agent.agents.website_voice_agent_v2 import WebsiteVoiceAgentV2
from auth.security import hash_password
from db.database import SessionLocal
from db.models import User
import httpx

logger = logging.getLogger(__name__)


def _service_headers() -> dict:
    """Headers for authenticated service-to-service API calls."""
    return {"X-Service-Key": os.getenv("SERVICE_API_KEY", "")}


class WebsiteVoiceAgent(Agent):
    """Streamlined voice agent for website visitors creating programs"""

    # Only 5 methods carry @function_tool (the batched 5-step flow).
    # Legacy per-field helpers (capture_age_sex, capture_height_weight, …)
    # are kept as plain methods for programmatic / fallback use but are NOT
    # decorated, so the LLM never sees them.

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

        # Step-scoped prompt system
        self._current_step = get_first_step(state)
        self._step_retries = 0
        self._finalize_fired = False
        instructions = get_step_prompt(self._current_step, state)

        super().__init__(instructions=instructions)

        logger.info(
            f"[WEBSITE AGENT] Registered {len(self._tools)} tools: "
            f"{[t.info.name for t in self._tools]}"
        )
        logger.info(
            f"[WEBSITE AGENT] Initialized with email: {state.get('email')}, "
            f"first step: {self._current_step.value}, "
            f"known fields: {list(state.get('existing_profile', {}).keys())}"
        )

    async def _advance_to(self, step: ConversationStep):
        """Swap the system prompt to the next conversation step."""
        self._current_step = step
        self._step_retries = 0
        await self.update_instructions(get_step_prompt(step, self.state))
        logger.info(f"[STEP] -> {step.value}")

    async def on_enter(self):
        """Entry point - speak initial greeting when agent enters conversation"""
        name = self.state.get("name")
        if name:
            await self.session.generate_reply(
                instructions=(
                    "An existing user has just logged back in. Give the user a warm welcome and move on."
                    "Example: Hey! Welcome back buddy! Let's get you a new program set up."
                )
            )
        else:
            await self.session.generate_reply(
                instructions="""
                A new user just joined us! Give them a warm welcome and move on to the next step.
                Example: 'Hey there! Nice to meet you, I'm Nova, your AI fitness coach!
                We'll be able to do a lot more once the Nova One squat rack is released,
                but for now they've put me on duty helping y'all generate programs...
                So, what's your first name?' """
            )

    def _log_function_call(self, function_name: str, parameters: dict, result: any):
        """Helper method to log function tool calls"""
        logger.info(f"[TOOL] {function_name}() completed")

    # =========================================================================
    # NEW TOOLS - Website-Specific
    # =========================================================================

    @function_tool
    async def capture_name(self, context: RunContext, first_name: str):
        """
        Call this AS SOON AS the user tells you their first name.
        Do not wait -- call immediately once you hear a name.

        Args:
            first_name: User's first name (just the name, no filler words)
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

            # Reject placeholder/example values that LLMs sometimes generate
            placeholder_names = {
                "example_value", "example", "string", "first_name", "name",
                "user", "test", "placeholder", "null", "none", "undefined",
                "value", "sample", "default", "your_name", "your name",
                "user_name", "username",
            }
            if first_name.lower().replace(" ", "_") in placeholder_names:
                logger.warning(f"[WEBSITE AGENT] Rejected placeholder name: {first_name}")
                result = None, "That doesn't sound like a real name. Please ask the user for their actual first name again."
                self._log_function_call(function_name, parameters, result)
                return result

            # Store in state
            self.state["name"] = first_name
            logger.info(f"[WEBSITE AGENT] Name captured: {first_name}")

            next_step = get_next_step(ConversationStep.NAME_CAPTURE, self.state)
            await self._advance_to(next_step)
            result = None, "Name captured. Follow your current instructions."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture name: {e}")
            result = None, "Error capturing name. Ask for name again."
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def correct_previous_answer(self, context: RunContext, field: str, new_value: str):
        """
        Call this when the user wants to CHANGE a previously captured value.
        For example: "actually make it a strength program", "I'm 26 not 25",
        "change my weight to 200 pounds".

        Args:
            field: Which field to update. One of: "name", "age", "sex", "height",
                   "weight", "goal", "fitness_level", "days_per_week",
                   "session_duration", "injury_history", "specific_sport",
                   "training_season", "games_per_week"
            new_value: The corrected value as spoken by the user
        """
        function_name = "correct_previous_answer"
        parameters = {"field": field, "new_value": new_value}

        try:
            field_lower = field.lower().strip()
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            pc = self.state["program_creation"]

            if field_lower == "name":
                name = new_value.strip()
                if not name or len(name) > 50:
                    result = None, "Invalid name. Ask the user to repeat it."
                    self._log_function_call(function_name, parameters, result)
                    return result
                self.state["name"] = name
                logger.info(f"[CORRECTION] Name -> {name}")
                result = None, f"Updated name to {name}. Continue with your current step."

            elif field_lower == "age":
                try:
                    age = int(re.search(r'\d+', new_value).group())
                except (AttributeError, ValueError):
                    result = None, "Could not parse age. Ask the user to say their age as a number."
                    self._log_function_call(function_name, parameters, result)
                    return result
                if age < 13 or age > 100:
                    result = None, "Age out of range (13-100). Ask the user to confirm their age."
                    self._log_function_call(function_name, parameters, result)
                    return result
                pc["age"] = age
                logger.info(f"[CORRECTION] Age -> {age}")
                result = None, f"Updated age to {age}. Continue with your current step."

            elif field_lower == "sex":
                sex_lower = new_value.lower().strip()
                if sex_lower in ("m", "male", "man", "boy"):
                    pc["sex"] = "male"
                elif sex_lower in ("f", "female", "woman", "girl"):
                    pc["sex"] = "female"
                else:
                    result = None, "Could not determine sex. Ask the user: male or female?"
                    self._log_function_call(function_name, parameters, result)
                    return result
                logger.info("[CORRECTION] Sex updated")
                result = None, f"Updated sex to {pc['sex']}. Continue with your current step."

            elif field_lower == "height":
                height_cm = normalize_height_to_cm(new_value)
                if height_cm is None or height_cm < 50 or height_cm > 300:
                    result = None, "Could not parse height. Ask the user to say it like 'five foot ten' or '175 cm'."
                    self._log_function_call(function_name, parameters, result)
                    return result
                pc["height_cm"] = height_cm
                logger.info(f"[CORRECTION] Height -> {height_cm:.0f}cm")
                result = None, f"Updated height to {height_cm:.0f} cm. Continue with your current step."

            elif field_lower == "weight":
                weight_kg = normalize_weight_to_kg(new_value)
                if weight_kg is None or weight_kg < 30 or weight_kg > 300:
                    result = None, "Could not parse weight. Ask the user to say it like '185 pounds' or '80 kg'."
                    self._log_function_call(function_name, parameters, result)
                    return result
                pc["weight_kg"] = weight_kg
                logger.info(f"[CORRECTION] Weight -> {weight_kg:.0f}kg")
                result = None, f"Updated weight to {weight_kg:.0f} kg. Continue with your current step."

            elif field_lower == "goal":
                if not new_value.strip():
                    result = None, "Goal description is empty. Ask the user to describe their goal."
                    self._log_function_call(function_name, parameters, result)
                    return result
                pc["goal_raw"] = new_value.strip()
                pc["goal_category"] = categorize_goal(new_value)
                logger.info(f"[CORRECTION] Goal -> {pc['goal_category']} ({new_value.strip()[:60]})")
                result = None, f"Updated goal to {pc['goal_category']}. Continue with your current step."

            elif field_lower == "fitness_level":
                level = new_value.lower().strip()
                if "beginner" in level or "new" in level or "start" in level:
                    level = "beginner"
                elif "advanced" in level or "expert" in level or "experienced" in level:
                    level = "advanced"
                else:
                    level = "intermediate"
                pc["fitness_level"] = level
                logger.info(f"[CORRECTION] Fitness level -> {level}")
                result = None, f"Updated fitness level to {level}. Continue with your current step."

            elif field_lower == "days_per_week":
                try:
                    days = int(re.search(r'\d+', new_value).group())
                except (AttributeError, ValueError):
                    result = None, "Could not parse days per week. Ask the user for a number between 1 and 7."
                    self._log_function_call(function_name, parameters, result)
                    return result
                pc["days_per_week"] = max(1, min(7, days))
                logger.info(f"[CORRECTION] Days/week -> {pc['days_per_week']}")
                result = None, f"Updated to {pc['days_per_week']} days per week. Continue with your current step."

            elif field_lower == "session_duration":
                try:
                    mins = int(re.search(r'\d+', new_value).group())
                except (AttributeError, ValueError):
                    result = None, "Could not parse session duration. Ask for minutes (30-180)."
                    self._log_function_call(function_name, parameters, result)
                    return result
                pc["session_duration"] = max(30, min(180, mins))
                logger.info(f"[CORRECTION] Session duration -> {pc['session_duration']}min")
                result = None, f"Updated session duration to {pc['session_duration']} minutes. Continue with your current step."

            elif field_lower == "injury_history":
                pc["injury_history"] = new_value.strip() if new_value.strip() else "none"
                logger.info(f"[CORRECTION] Injuries -> {pc['injury_history'][:60]}")
                result = None, f"Updated injury info. Continue with your current step."

            elif field_lower == "specific_sport":
                pc["specific_sport"] = new_value.strip() if new_value.strip() else "none"
                logger.info(f"[CORRECTION] Sport -> {pc['specific_sport']}")
                result = None, f"Updated sport to {pc['specific_sport']}. Continue with your current step."

            elif field_lower == "training_season":
                season = new_value.lower().strip().replace(" ", "_").replace("-", "_")
                if season in ("off_season", "pre_season", "in_season", "post_season"):
                    pc["training_season"] = season
                else:
                    result = None, "Invalid season. Ask the user: off-season, pre-season, in-season, or post-season?"
                    self._log_function_call(function_name, parameters, result)
                    return result
                logger.info(f"[CORRECTION] Season -> {season}")
                result = None, f"Updated training season to {season}. Continue with your current step."

            elif field_lower == "games_per_week":
                try:
                    games = int(re.search(r'\d+', new_value).group())
                except (AttributeError, ValueError):
                    result = None, "Could not parse games per week. Ask for a number between 0 and 7."
                    self._log_function_call(function_name, parameters, result)
                    return result
                pc["games_per_week"] = max(0, min(7, games))
                logger.info(f"[CORRECTION] Games/week -> {pc['games_per_week']}")
                result = None, f"Updated to {pc['games_per_week']} games per week. Continue with your current step."

            else:
                result = None, f"Unknown field '{field}'. Continue with your current step."
                self._log_function_call(function_name, parameters, result)
                return result

            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to correct field '{field}': {e}")
            result = None, "Error updating that value. Acknowledge the user's request and continue with the current step."
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def capture_personal_info(
        self,
        context: RunContext,
        age: int,
        sex: str,
        height_value: str,
        weight_value: str,
        extra_info: str = "none",
    ):
        """
        Call this IMMEDIATELY once the user has provided all four: age, sex, height, and weight.
        If they also shared extra context (training history, goals, life context), include it.

        Args:
            age: User's age in years (13-100)
            sex: "male", "female", "M", "F", etc.
            height_value: Height as spoken (e.g., "5'10", "175 cm", "six foot")
            weight_value: Weight as spoken (e.g., "185 pounds", "80 kg")
            extra_info: Any extra info the user shared beyond the four required fields, or "none"
        """
        function_name = "capture_personal_info"
        parameters = {
            "age": age,
            "sex": sex,
            "height_value": height_value,
            "weight_value": weight_value,
            "extra_info": extra_info,
        }

        try:
            invalid_fields = []

            # Validate age
            age_valid = isinstance(age, int) and 13 <= age <= 100
            if not age_valid:
                invalid_fields.append("age")

            # Normalize sex
            sex_normalized = None
            if sex:
                sex_lower = sex.lower().strip()
                if sex_lower in ("m", "male", "man", "boy"):
                    sex_normalized = "male"
                elif sex_lower in ("f", "female", "woman", "girl"):
                    sex_normalized = "female"
            if sex_normalized is None:
                invalid_fields.append("biological sex")

            # Parse height
            height_cm = normalize_height_to_cm(height_value) if height_value else None
            if height_cm is None or height_cm < 50 or height_cm > 300:
                invalid_fields.append("height")
                height_cm = None

            # Parse weight
            weight_kg = normalize_weight_to_kg(weight_value) if weight_value else None
            if weight_kg is None or weight_kg < 30 or weight_kg > 300:
                invalid_fields.append("weight")
                weight_kg = None

            if invalid_fields:
                self._step_retries += 1
                # Build a list of what we DID get so Nova doesn't re-ask for it.
                got = []
                if age_valid:
                    got.append(f"age {age}")
                if sex_normalized:
                    got.append(f"sex {sex_normalized}")
                if height_cm is not None:
                    got.append(f"height {height_cm:.0f}cm")
                if weight_kg is not None:
                    got.append(f"weight {weight_kg:.0f}kg")

                got_note = f"Already got: {', '.join(got)}. " if got else ""
                need_note = f"Still need: {', '.join(invalid_fields)}."

                if self._step_retries >= 3:
                    msg = (
                        f"{got_note}{need_note} Ask the user very clearly for only the missing values "
                        "with concrete examples -- for example 'five foot nine' or 'one seventy-five centimeters' "
                        "for height, 'one eighty pounds' or 'eighty kilograms' for weight."
                    )
                else:
                    msg = (
                        f"{got_note}{need_note} Ask the user ONLY for the missing values. "
                        "Do NOT re-ask for values you already have. Do NOT advance."
                    )
                result = None, msg
                self._log_function_call(function_name, parameters, result)
                return result

            # All four valid -- store everything.
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["age"] = age
            self.state["program_creation"]["sex"] = sex_normalized
            self.state["program_creation"]["height_cm"] = height_cm
            self.state["program_creation"]["weight_kg"] = weight_kg

            # Stash extra info for later DB persistence.
            if extra_info and extra_info.strip().lower() not in ("none", ""):
                self.state["extra_info"] = extra_info.strip()
                logger.info("[PROGRAM] Extra info captured")

            logger.info("[PROGRAM] Personal info captured (age, sex, height, weight)")

            next_step = get_next_step(ConversationStep.PERSONAL_INFO, self.state)
            await self._advance_to(next_step)
            result = None, "Captured. Follow your current instructions."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture personal info: {e}")
            result = None, "Error capturing personal info. Ask the user for their age, sex, height, and weight again."
            self._log_function_call(function_name, parameters, result)
            return result


    # =========================================================================
    # PROGRAM CREATION TOOLS - Copied from voice_agent.py
    # =========================================================================

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
                self._step_retries += 1
                if self._step_retries >= 3:
                    result = None, "That still didn't work. Try saying something like five foot nine, or one seventy-five centimeters."
                else:
                    result = None, "Height invalid. Ask for height again with examples like five foot nine or one seventy-five centimeters."
                self._log_function_call(function_name, parameters, result)
                return result

            # Parse and validate weight
            weight_kg = normalize_weight_to_kg(weight_value)
            if weight_kg is None or weight_kg < 30 or weight_kg > 300:
                self._step_retries += 1
                if self._step_retries >= 3:
                    result = None, "That still didn't work. Try saying something like one eighty-five pounds, or eighty kilograms."
                else:
                    result = None, "Weight invalid. Ask for weight again with examples like one eighty-five pounds or eighty kilograms."
                self._log_function_call(function_name, parameters, result)
                return result

            # Save to state (will update DB at the end)
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["height_cm"] = height_cm
            self.state["program_creation"]["weight_kg"] = weight_kg

            logger.info(f"[PROGRAM] Height: {height_cm} cm, Weight: {weight_kg} kg")

            next_step = get_next_step(ConversationStep.HEIGHT_WEIGHT, self.state)
            await self._advance_to(next_step)
            result = None, "Captured. Follow your current instructions."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture height/weight: {e}")
            result = None, "Error capturing height and weight. Please provide them again."
            self._log_function_call(function_name, parameters, result)
            return result

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
                self._step_retries += 1
                result = None, "Age out of range. Ask for age again -- must be between thirteen and one hundred."
                self._log_function_call(function_name, parameters, result)
                return result

            # Normalize sex
            sex_normalized = sex.lower().strip()
            if sex_normalized in ["m", "male", "man", "boy"]:
                sex_normalized = "male"
            elif sex_normalized in ["f", "female", "woman", "girl"]:
                sex_normalized = "female"
            else:
                self._step_retries += 1
                result = None, "Sex unclear. Ask if male or female."
                self._log_function_call(function_name, parameters, result)
                return result

            # Save to state (will update DB at the end)
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["age"] = age
            self.state["program_creation"]["sex"] = sex_normalized

            logger.info("[PROGRAM] Age and sex captured")

            next_step = get_next_step(ConversationStep.AGE_SEX, self.state)
            await self._advance_to(next_step)
            result = None, "Captured. Follow your current instructions."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture age/sex: {e}")
            result = None, "Error capturing age and sex. Please provide them again."
            self._log_function_call(function_name, parameters, result)
            return result

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

            next_step = get_next_step(ConversationStep.GOAL, self.state)
            await self._advance_to(next_step)
            result = None, "Captured. Follow your current instructions."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture goal: {e}")
            result = None, "Error capturing goal. Please describe your goal again."
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def capture_goal_and_details(
        self,
        context: RunContext,
        goal_description: str,
        duration_weeks: Optional[int] = None,
        days_per_week: Optional[int] = None,
        session_duration: Optional[int] = None,
        injury_history: Optional[str] = None,
        specific_sport: Optional[str] = None,
        training_season: Optional[str] = None,
        games_per_week: Optional[int] = None,
    ):
        """
        Call this IMMEDIATELY when the user describes their fitness goal.
        Only goal_description is required. Include any optional details they
        happened to mention; omit anything they did not mention.

        Args:
            goal_description: User's full description of their fitness goal
            duration_weeks: Program length in weeks (2-52), only if mentioned
            days_per_week: Training frequency (1-7), only if mentioned
            session_duration: Minutes per session (30-180), only if mentioned
            injury_history: Injuries or limitations, only if mentioned
            specific_sport: Sport name, only if mentioned
            training_season: "off_season", "pre_season", "in_season", "post_season", only if mentioned
            games_per_week: Games per week (0-7), only if mentioned
        """
        function_name = "capture_goal_and_details"
        parameters = {
            "goal_description": goal_description,
            "duration_weeks": duration_weeks,
            "days_per_week": days_per_week,
            "session_duration": session_duration,
            "injury_history": injury_history,
            "specific_sport": specific_sport,
            "training_season": training_season,
            "games_per_week": games_per_week,
        }

        try:
            if not goal_description or not goal_description.strip():
                result = None, "Goal description is empty. Ask the user to describe their main fitness goal."
                self._log_function_call(function_name, parameters, result)
                return result

            # Categorize goal
            goal_category = categorize_goal(goal_description)

            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            pc = self.state["program_creation"]

            pc["goal_raw"] = goal_description
            pc["goal_category"] = goal_category

            # Optional params -- only store if provided and valid.
            if duration_weeks is not None:
                pc["duration_weeks"] = max(2, min(52, int(duration_weeks)))
            if days_per_week is not None:
                pc["days_per_week"] = max(1, min(7, int(days_per_week)))
            if session_duration is not None:
                pc["session_duration"] = max(30, min(180, int(session_duration)))
            if injury_history is not None and injury_history.strip():
                pc["injury_history"] = injury_history.strip()
            if specific_sport is not None and specific_sport.strip():
                pc["specific_sport"] = specific_sport.strip()
            if training_season is not None and training_season.strip():
                season = training_season.lower().strip().replace(" ", "_").replace("-", "_")
                if season in ("off_season", "pre_season", "in_season", "post_season"):
                    pc["training_season"] = season
            if games_per_week is not None:
                pc["games_per_week"] = max(0, min(7, int(games_per_week)))

            logger.info(
                f"[PROGRAM] Goal: {goal_description} -> {goal_category}. "
                f"Optional details captured: "
                f"duration={pc.get('duration_weeks')}, days={pc.get('days_per_week')}, "
                f"session={pc.get('session_duration')}, injuries={pc.get('injury_history')}, "
                f"sport={pc.get('specific_sport')}, season={pc.get('training_season')}, "
                f"games={pc.get('games_per_week')}"
            )

            next_step = get_next_step(ConversationStep.GOAL, self.state)
            await self._advance_to(next_step)
            result = None, "Captured. Follow your current instructions."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture goal and details: {e}")
            result = None, "Error capturing goal. Please describe your goal again."
            self._log_function_call(function_name, parameters, result)
            return result

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
                self._step_retries += 1
                result = None, "Duration out of range. Ask again -- must be between two and fifty-two weeks."
                self._log_function_call(function_name, parameters, result)
                return result

            # Save to state
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["duration_weeks"] = duration_weeks

            logger.info(f"[PROGRAM] Duration: {duration_weeks} weeks")

            next_step = get_next_step(ConversationStep.DURATION, self.state)
            await self._advance_to(next_step)
            result = None, "Captured. Follow your current instructions."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture program duration: {e}")
            result = None, "Error capturing duration. Please specify the number of weeks again."
            self._log_function_call(function_name, parameters, result)
            return result

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
                self._step_retries += 1
                result = None, "Frequency out of range. Ask again -- must be between one and seven days per week."
                self._log_function_call(function_name, parameters, result)
                return result

            # Save to state
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["days_per_week"] = days_per_week

            logger.info(f"[PROGRAM] Frequency: {days_per_week} days/week")

            next_step = get_next_step(ConversationStep.FREQUENCY, self.state)
            await self._advance_to(next_step)
            result = None, "Captured. Follow your current instructions."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture training frequency: {e}")
            result = None, "Error capturing frequency. Please specify the number of days again."
            self._log_function_call(function_name, parameters, result)
            return result

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
                self._step_retries += 1
                if self._step_retries >= 3:
                    # Optional field -- skip with default
                    duration_minutes = 60
                    logger.warning("[RETRY] Max retries for session_duration, defaulting to 60 min")
                else:
                    result = None, "Duration out of range. Ask again -- between thirty and one hundred eighty minutes."
                    self._log_function_call(function_name, parameters, result)
                    return result

            # Save to state
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["session_duration"] = duration_minutes

            logger.info(f"[PROGRAM] Session duration: {duration_minutes} minutes")

            next_step = get_next_step(ConversationStep.SESSION_DURATION, self.state)
            await self._advance_to(next_step)
            result = None, "Captured. Follow your current instructions."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture session duration: {e}")
            result = None, "Error capturing session duration. Please specify the duration again."
            self._log_function_call(function_name, parameters, result)
            return result

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

            next_step = get_next_step(ConversationStep.INJURIES, self.state)
            await self._advance_to(next_step)
            result = None, "Captured. Follow your current instructions."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture injury history: {e}")
            result = None, "Error capturing injury history. Please describe any injuries again."
            self._log_function_call(function_name, parameters, result)
            return result

    async def capture_specific_sport(self, context: RunContext, sport_name: str):
        """
        Call this when the user mentions a specific sport they're training for.

        Args:
            sport_name: Name of the sport or "none"
        """
        function_name = "capture_specific_sport"
        parameters = {"sport_name": sport_name}

        try:
            # Save to state BEFORE calling get_next_step (skip logic depends on sport value)
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["specific_sport"] = sport_name

            logger.info(f"[PROGRAM] Specific sport: {sport_name}")

            next_step = get_next_step(ConversationStep.SPORT, self.state)
            await self._advance_to(next_step)
            result = None, "Captured. Follow your current instructions."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture specific sport: {e}")
            result = None, "Error capturing sport. Please tell me the sport again."
            self._log_function_call(function_name, parameters, result)
            return result

    async def capture_training_season(self, context: RunContext, training_season: str):
        """
        Call this when the user specifies their current training season.
        Only ask this if the user plays a sport — skip for general fitness.

        Args:
            training_season: "off_season", "pre_season", "in_season", or "post_season"
        """
        function_name = "capture_training_season"
        parameters = {"training_season": training_season}

        try:
            season = training_season.lower().strip().replace(" ", "_").replace("-", "_")
            valid_seasons = {"off_season", "pre_season", "in_season", "post_season"}
            if season not in valid_seasons:
                season = "off_season"

            # Save to state BEFORE calling get_next_step (skip logic depends on season value)
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["training_season"] = season

            logger.info(f"[PROGRAM] Training season: {season}")

            next_step = get_next_step(ConversationStep.TRAINING_SEASON, self.state)
            await self._advance_to(next_step)
            result = None, "Captured. Follow your current instructions."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture training season: {e}")
            result = None, "Error capturing training season. Please tell me your season again."
            self._log_function_call(function_name, parameters, result)
            return result

    async def capture_games_per_week(self, context: RunContext, games_per_week: int):
        """
        Call this when the user specifies how many games or competitions they have per week.
        Only ask this if the user is in-season. Skip otherwise.

        Args:
            games_per_week: Number of games/competitions per week (0-7)
        """
        function_name = "capture_games_per_week"
        parameters = {"games_per_week": games_per_week}

        try:
            games = max(0, min(7, games_per_week))

            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["games_per_week"] = games

            logger.info(f"[PROGRAM] Games per week: {games}")

            next_step = get_next_step(ConversationStep.GAMES_PER_WEEK, self.state)
            await self._advance_to(next_step)
            result = None, "Captured. Follow your current instructions."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture games per week: {e}")
            result = None, "Error capturing games per week. Please tell me the number again."
            self._log_function_call(function_name, parameters, result)
            return result

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

            next_step = get_next_step(ConversationStep.NOTES, self.state)
            await self._advance_to(next_step)
            result = None, "Captured. Follow your current instructions."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture user notes: {e}")
            result = None, "Error capturing notes. Please tell me your preferences again."
            self._log_function_call(function_name, parameters, result)
            return result

    async def capture_equipment_tier(self, context: RunContext, equipment_tier: int):
        """
        Call this when the user describes their gym equipment access.
        Tier 1 = barbell, rack, bench, pull-up bar, floor space
        Tier 2 = Tier 1 + dumbbells
        Tier 3 = Tier 2 + bands

        Args:
            equipment_tier: 1, 2, or 3
        """
        function_name = "capture_equipment_tier"
        parameters = {"equipment_tier": equipment_tier}

        try:
            tier = max(1, min(3, equipment_tier))

            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            self.state["program_creation"]["equipment_tier"] = tier

            logger.info(f"[PROGRAM] Equipment tier: {tier}")

            next_step = get_next_step(ConversationStep.EQUIPMENT, self.state)
            await self._advance_to(next_step)
            result = None, "Captured. Follow your current instructions."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture equipment tier: {e}")
            result = None, "Error capturing equipment tier. Please tell me again."
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def capture_fitness_level(self, context: RunContext, fitness_level: str):
        """
        Call this IMMEDIATELY when the user states their fitness level.

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

            next_step = get_next_step(ConversationStep.FITNESS_LEVEL, self.state)
            await self._advance_to(next_step)
            result = None, "Captured. Follow your current instructions."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to capture fitness level: {e}")
            result = None, "Error capturing fitness level. Please tell me your level again."
            self._log_function_call(function_name, parameters, result)
            return result

    @function_tool
    async def apply_defaults(
        self,
        context: RunContext,
        use_defaults: bool,
        days_per_week: Optional[int] = None,
        session_duration: Optional[int] = None,
        injury_history: Optional[str] = None,
        specific_sport: Optional[str] = None,
        training_season: Optional[str] = None,
        games_per_week: Optional[int] = None,
    ):
        """
        Call this IMMEDIATELY when the user responds to "defaults or customize?".
        This is the LAST tool call before goodbye.

        - User says "defaults" / "sounds good" / "go for it" / any agreement
          -> call with use_defaults=true
        - User gives specific customizations (e.g. "four days a week")
          -> call with use_defaults=false and pass their values

        Do NOT ask about equipment. Do NOT ask follow-up questions before calling this.

        Args:
            use_defaults: true = pure defaults, false = apply the optional params below first
            days_per_week: Custom training frequency (1-7), only if user specified
            session_duration: Custom session length in minutes (30-180), only if user specified
            injury_history: Injuries description, only if user specified
            specific_sport: Sport name, only if user specified
            training_season: "off_season"/"pre_season"/"in_season"/"post_season", only if user specified
            games_per_week: Games per week (0-7), only if user specified
        """
        function_name = "apply_defaults"
        parameters = {
            "use_defaults": use_defaults,
            "days_per_week": days_per_week,
            "session_duration": session_duration,
            "injury_history": injury_history,
            "specific_sport": specific_sport,
            "training_season": training_season,
            "games_per_week": games_per_week,
        }

        try:
            if "program_creation" not in self.state:
                self.state["program_creation"] = {}
            pc = self.state["program_creation"]

            # Apply user customizations first (only when not pure-defaults).
            if not use_defaults:
                if days_per_week is not None:
                    pc["days_per_week"] = max(1, min(7, int(days_per_week)))
                if session_duration is not None:
                    pc["session_duration"] = max(30, min(180, int(session_duration)))
                if injury_history is not None and injury_history.strip():
                    pc["injury_history"] = injury_history.strip()
                if specific_sport is not None and specific_sport.strip():
                    pc["specific_sport"] = specific_sport.strip()
                if training_season is not None and training_season.strip():
                    season = training_season.lower().strip().replace(" ", "_").replace("-", "_")
                    if season in ("off_season", "pre_season", "in_season", "post_season"):
                        pc["training_season"] = season
                if games_per_week is not None:
                    pc["games_per_week"] = max(0, min(7, int(games_per_week)))

            # Fill remaining gaps with defaults.
            # Hardcoded always:
            pc["duration_weeks"] = 12
            pc["equipment_tier"] = 3
            pc["has_vbt_capability"] = False

            # Days-per-week default derived from fitness level.
            if pc.get("days_per_week") is None:
                fitness_level = pc.get("fitness_level", "intermediate")
                pc["days_per_week"] = {"beginner": 3, "intermediate": 4, "advanced": 5}.get(
                    fitness_level, 4
                )

            # Simple scalar defaults.
            if pc.get("session_duration") is None:
                pc["session_duration"] = 60
            if pc.get("injury_history") is None:
                pc["injury_history"] = "none"
            if pc.get("specific_sport") is None:
                pc["specific_sport"] = "none"
            if pc.get("games_per_week") is None:
                pc["games_per_week"] = 0
            # training_season stays None if not set.

            logger.info(
                f"[PROGRAM] Defaults applied (use_defaults={use_defaults}). Final params: "
                f"duration={pc['duration_weeks']}, days={pc['days_per_week']}, "
                f"session={pc['session_duration']}, injuries={pc['injury_history']}, "
                f"sport={pc['specific_sport']}, season={pc.get('training_season')}, "
                f"games={pc['games_per_week']}, equipment_tier={pc['equipment_tier']}"
            )

            # Advance to GOODBYE prompt -- LLM will generate the farewell speech
            await self._advance_to(ConversationStep.GOODBYE)

            # Register callback to fire finalize chain after goodbye speech plays out.
            # Same pattern as LiveKit's EndCallTool (agents/beta/tools/end_call.py).
            def _on_goodbye_done(_):
                if not self._finalize_fired:
                    self._finalize_fired = True
                    asyncio.create_task(self._finalize_and_disconnect())

            context.speech_handle.add_done_callback(_on_goodbye_done)

            # Timeout fallback: if speech callback never fires, finalize anyway.
            async def _finalize_timeout():
                await asyncio.sleep(30)
                if not self._finalize_fired:
                    logger.warning("[FINALIZE] Timeout -- speech callback never fired, finalizing anyway")
                    self._finalize_fired = True
                    await self._finalize_and_disconnect()

            asyncio.create_task(_finalize_timeout())

            result = None, "All parameters collected. Say goodbye following your current instructions."
            self._log_function_call(function_name, parameters, result)
            return result

        except Exception as e:
            logger.error(f"[ERROR] Failed to apply defaults: {e}")
            result = None, "Error applying defaults. Try finalizing with defaults again."
            self._log_function_call(function_name, parameters, result)
            return result

    # =========================================================================
    # PROGRAMMATIC FINALIZE CHAIN (no LLM round-trip)
    # =========================================================================

    async def _update_user_profile_direct(self):
        """Update user profile in DB. Extracted from the function_tool for programmatic use."""
        user_id = self.state.get("user_id")
        if not user_id:
            logger.error("[FINALIZE] No user ID. Cannot update profile.")
            return

        name = self.state.get("name")
        program_params = self.state.get("program_creation", {})

        extra_info = self.state.get("extra_info")

        db = SessionLocal()
        try:
            db_user = db.query(User).filter(User.id == user_id).first()
            if db_user:
                if name:
                    db_user.name = name
                if "height_cm" in program_params:
                    db_user.height_cm = program_params["height_cm"]
                if "weight_kg" in program_params:
                    db_user.weight_kg = program_params["weight_kg"]
                if "age" in program_params:
                    db_user.age = program_params["age"]
                if "sex" in program_params:
                    db_user.sex = program_params["sex"]
                if extra_info:
                    db_user.extra_info = extra_info
                db.commit()
                logger.info(f"[FINALIZE] Updated user profile for {self.state.get('email')}")
            else:
                logger.error("[FINALIZE] User not found in database.")
        except Exception as e:
            logger.error(f"[FINALIZE] Failed to update user profile: {e}")
            db.rollback()
        finally:
            db.close()

    async def _generate_program_direct(self):
        """Trigger program generation via FastAPI. Extracted for programmatic use."""
        user_id = self.state.get("user_id")
        user_email = self.state.get("email")

        if not user_id:
            logger.error("[FINALIZE] No user ID. Cannot generate program.")
            return

        program_params = self.state.get("program_creation", {})

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
            "send_email": True,
            "training_season": program_params.get("training_season"),
            "games_per_week": program_params.get("games_per_week", 0),
            "equipment_tier": program_params.get("equipment_tier", 3),
        }

        fastapi_url = os.getenv("FASTAPI_URL", "http://localhost:8000")
        url = f"{fastapi_url}/api/programs/generate"
        logger.info(f"[FINALIZE] Calling program generation API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=_service_headers())

                if response.status_code == 202:
                    data = response.json()
                    job_id = data.get("job_id")
                    self.state["program_creation"]["job_id"] = job_id
                    logger.info(f"[FINALIZE] Program generation started. Job ID: {job_id}")

                    # Send data message to frontend
                    try:
                        await self.session.room_io.room.local_participant.publish_data(
                            json.dumps({
                                "type": "program_generating",
                                "job_id": job_id,
                                "email": user_email
                            }).encode(),
                            reliable=True
                        )
                        logger.info("[FINALIZE] Sent 'program_generating' data message to frontend")
                    except Exception as e:
                        logger.error(f"[FINALIZE] Failed to send data message: {e}")
                else:
                    logger.error(f"[FINALIZE] API error: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"[FINALIZE] Failed to generate program: {e}")

    async def _finalize_and_disconnect(self):
        """Run the post-goodbye chain: save profile, generate program, disconnect."""
        try:
            # Check for missing required data
            required = [
                "height_cm", "weight_kg", "age", "sex",
                "goal_category", "goal_raw", "duration_weeks",
                "days_per_week", "fitness_level"
            ]
            program = self.state.get("program_creation", {})
            missing = [p for p in required if p not in program]
            if missing:
                logger.error(f"[FINALIZE] Missing required params: {missing}")
                first_missing = get_first_missing_step(missing)
                if first_missing:
                    await self._advance_to(first_missing)
                    return  # Don't finalize -- conversation continues

            # 1. Update user profile in DB
            await self._update_user_profile_direct()

            # 2. Trigger program generation via API
            await self._generate_program_direct()

            # 3. Disconnect from room (try room disconnect first, fall back to session close)
            try:
                await self.session.room_io.room.disconnect()
                logger.info("[FINALIZE] Complete. Disconnected via room.")
            except Exception as e:
                logger.warning(f"[FINALIZE] Room disconnect failed ({e}), closing session directly")
                try:
                    await self.session.aclose()
                    logger.info("[FINALIZE] Complete. Session closed.")
                except Exception as e2:
                    logger.error(f"[FINALIZE] Session close also failed: {e2}")

        except Exception as e:
            logger.error(f"[FINALIZE] Error in finalize chain: {e}")

    # =========================================================================
    # FUNCTION TOOLS (kept for backward compat / direct LLM invocation fallback)
    # =========================================================================

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

                    result = None, "Profile updated successfully. Now immediately call generate_workout_program()."
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
                "send_email": True,  # Website users always get email
                # V6 fields
                "training_season": program_params.get("training_season"),
                "games_per_week": program_params.get("games_per_week", 0),
                "equipment_tier": program_params.get("equipment_tier", 3),
            }

            # Call FastAPI endpoint
            fastapi_url = os.getenv("FASTAPI_URL", "http://localhost:8000")
            url = f"{fastapi_url}/api/programs/generate"

            logger.info(f"[PROGRAM] Calling program generation API: {url}")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=_service_headers())

                if response.status_code == 202:
                    # Success - generation started
                    data = response.json()
                    job_id = data.get("job_id")

                    # Save job_id to state
                    self.state["program_creation"]["job_id"] = job_id

                    logger.info(f"[PROGRAM] Program generation started. Job ID: {job_id}")

                    # Send data message to frontend to trigger completion UI
                    try:
                        await context.session.room_io.room.local_participant.publish_data(
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
                    result = None, f"Program generation started successfully. You have already said goodbye to the user. Now immediately call end_conversation()."
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
                await context.session.room_io.room.disconnect()
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

    # In console mode, use a test email since there are no real participants
    is_console = ctx.room.name == "console"
    if is_console:
        email = os.getenv("TEST_EMAIL", "ambakalgr@gmail.com")
        logger.info(f"[WEBSITE AGENT] Console mode — using test email: {email}")

    # Check already-connected participants first
    if not email:
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
        existing_profile = {}
        if existing_user:
            user_id = existing_user.id
            username = existing_user.username
            # Read existing profile data for returning users
            if existing_user.name and existing_user.name.strip():
                existing_profile["name"] = existing_user.name.strip()
            if existing_user.height_cm is not None:
                existing_profile["height_cm"] = float(existing_user.height_cm)
            if existing_user.weight_kg is not None:
                existing_profile["weight_kg"] = float(existing_user.weight_kg)
            if existing_user.age is not None:
                existing_profile["age"] = existing_user.age
            if existing_user.sex is not None:
                existing_profile["sex"] = existing_user.sex
            logger.info(f"[WEBSITE AGENT] Existing user found: {email}, ID: {user_id}, profile: {list(existing_profile.keys())}")
        else:
            # Generate username from email
            email_prefix = email.split('@')[0]
            email_prefix = re.sub(r'[^\w\.]', '', email_prefix)
            random_suffix = secrets.randbelow(10000)
            username = f"{email_prefix}_{random_suffix:04d}"

            # Generate random password (bcrypt-hashed)
            password_hash = hash_password(secrets.token_urlsafe(32))

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
    # Pre-populate program_creation with known profile values so
    # generate_workout_program validation passes without calling skipped capture tools
    prepopulated = {}
    for key in ("height_cm", "weight_kg", "age", "sex"):
        if key in existing_profile:
            prepopulated[key] = existing_profile[key]

    state = {
        "email": email,
        "name": existing_profile.get("name"),
        "user_id": user_id,
        "username": username,
        "existing_profile": existing_profile,
        "program_creation": prepopulated,
    }

    # Initialize cascade pipeline components (STT + LLM + TTS)
    stt = deepgram.STT(
        model="nova-3",
        language="en",
        endpointing_ms=50,
        smart_format=True,
        filler_words=True,
        keyterm=["Nowva", "Nova"],
    )

    # Select agent variant: v1 (multi-step) or v2 (single-prompt).
    agent_variant = os.getenv("WEBSITE_AGENT_VARIANT", "v1").lower()

    # V2 can run on its own model (defaults to gpt-5.4-nano); V1 keeps its own knob.
    if agent_variant == "v2":
        llm = openai.LLM(
            model=os.getenv("WEBSITE_V2_LLM_MODEL", "gpt-5.4-nano"),
            reasoning_effort=os.getenv("WEBSITE_V2_LLM_REASONING_EFFORT", "low"),
        )
    else:
        llm = openai.LLM(
            model=os.getenv("WEBSITE_LLM_MODEL", "gpt-5.4-mini"),
            reasoning_effort=os.getenv("WEBSITE_LLM_REASONING_EFFORT", "low"),
        )

    tts = elevenlabs.TTS(
        api_key=os.getenv("ELEVEN_API_KEY"),
        voice_id=os.getenv("ELEVENLABS_VOICE_ID"),
        model="eleven_multilingual_v2",
        encoding="pcm_24000",
        voice_settings=elevenlabs.VoiceSettings(
            stability=0.30,
            similarity_boost=0.5,
        ),
        chunk_length_schedule=[40, 120, 200, 260],
    )

    if agent_variant == "v2":
        agent = WebsiteVoiceAgentV2(state=state)
        logger.info("[WEBSITE AGENT] Using V2 (single-prompt) agent variant")
    else:
        agent = WebsiteVoiceAgent(state=state)

    # Retrieve prewarmed VAD or load fresh as fallback
    vad = ctx.proc.userdata.get("vad")
    if vad is None:
        logger.warning("[WEBSITE AGENT] No prewarmed VAD found, loading fresh...")
        vad = silero.VAD.load()
    else:
        logger.info("[WEBSITE AGENT] Using prewarmed Silero VAD")

    # Create session with cascade pipeline
    session = AgentSession(
        stt=stt,
        llm=llm,
        tts=tts,
        vad=vad,
        turn_handling=TurnHandlingOptions(
            turn_detection=EnglishModel(),
            preemptive_generation={"enabled": True},
        ),
    )

    # Store session reference in agent so it can disconnect later
    agent._session_ref = session

    # --- Session event tracking ---
    # TODO(v2.0): migrate to ChatMessage.metrics for per-turn latency
    _lk_logger = logging.getLogger("livekit.agents.voice.agent_session")
    _prev_level = _lk_logger.level
    _lk_logger.setLevel(logging.ERROR)

    @session.on("metrics_collected")
    def _on_metrics(ev):
        m = ev.metrics
        if hasattr(m, "ttft"):
            logger.info(
                f"[METRICS] {m.type} — ttft={m.ttft:.3f}s, duration={m.duration:.3f}s, "
                f"cancelled={m.cancelled}, input_tokens={getattr(m, 'input_tokens', 'N/A')}, "
                f"output_tokens={getattr(m, 'output_tokens', 'N/A')}, "
                f"tps={getattr(m, 'tokens_per_second', 'N/A')}"
            )
        elif hasattr(m, "audio_duration"):
            logger.info(
                f"[METRICS] {m.type} — duration={m.duration:.3f}s, "
                f"audio_duration={m.audio_duration:.3f}s"
            )
        else:
            logger.info(f"[METRICS] {m.type}")

    _lk_logger.setLevel(_prev_level)

    @session.on("error")
    def _on_error(ev):
        logger.error(f"[SESSION] Error from {ev.source}: {ev.error}")

    # Start session — on_enter() will handle the initial greeting automatically
    logger.info("[WEBSITE AGENT] Starting session...")
    await session.start(
        room=ctx.room,
        agent=agent,
        record=True,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
            pre_connect_audio=True,
            pre_connect_audio_timeout=5.0,
        ),
    )

    logger.info("[WEBSITE AGENT] Session ended.")


def prewarm(proc: agents.JobProcess):
    """Pre-load heavy resources before any room connection.

    Silero VAD model is loaded here so entrypoint() starts instantly.
    MultilingualModel turn detector requires a job context and is
    created inside entrypoint() instead.
    """
    import time

    logger.info("[PREWARM] Pre-loading Silero VAD...")
    start = time.monotonic()

    try:
        proc.userdata["vad"] = silero.VAD.load()
        logger.info("[PREWARM] Silero VAD pre-loaded")
    except Exception as e:
        logger.warning(f"[PREWARM] VAD pre-load failed (will load in entrypoint): {e}")

    elapsed = time.monotonic() - start
    logger.info(f"[PREWARM] Pre-load complete in {elapsed:.3f}s")


if __name__ == "__main__":
    try:
        agents.cli.run_app(
            agents.WorkerOptions(
                entrypoint_fnc=entrypoint,
                prewarm_fnc=prewarm,
                initialize_process_timeout=120,
                num_idle_processes=2,
            )
        )
    except KeyboardInterrupt:
        logger.info("\n[SHUTDOWN] Agent stopped by user")
    except Exception as e:
        if "termios" not in str(e).lower():
            logger.error(f"[ERROR] {e}")
