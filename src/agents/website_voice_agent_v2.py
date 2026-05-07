"""
Website Voice Agent V2 -- Single-Prompt Variant

Same purpose as ``website_voice_agent.py`` (collect program parameters from
website visitors) but uses a single system prompt and one ``capture_fields``
tool instead of the multi-step prompt-swapping flow.

Swap in via ``WEBSITE_AGENT_VARIANT=v2`` (see entrypoint in
``website_voice_agent.py``).
"""

import asyncio
import json
import logging
import os
import re
from typing import Optional, Dict, Any

from livekit.agents import Agent, RunContext
from livekit.agents.llm import function_tool

from agents.prompts.website_single_prompt import get_single_prompt
from agents.shared.unit_conversion import (
    normalize_height_to_cm,
    normalize_weight_to_kg,
    categorize_goal,
)
from db.database import SessionLocal
from db.models import User
import httpx

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {
    "name", "age", "sex", "height_cm", "weight_kg",
    "goal_raw", "goal_category", "fitness_level",
}


def _service_headers() -> dict:
    return {"X-Service-Key": os.getenv("SERVICE_API_KEY", "")}


class WebsiteVoiceAgentV2(Agent):
    """Single-prompt voice agent for website visitors creating programs."""

    def __init__(self, state: Dict[str, Any]) -> None:
        self.state = state
        self._session_ref = None
        self._finalize_fired = False

        instructions = get_single_prompt(state)
        super().__init__(instructions=instructions)

        logger.info(
            f"[V2 AGENT] Registered {len(self._tools)} tools: "
            f"{[t.info.name for t in self._tools]}"
        )
        logger.info(
            f"[V2 AGENT] Initialized with email: {state.get('email')}, "
            f"known fields: {list(state.get('existing_profile', {}).keys())}"
        )

    # ------------------------------------------------------------------
    # Greeting
    # ------------------------------------------------------------------

    async def on_enter(self):
        name = self.state.get("name")
        if name:
            await self.session.generate_reply(
                instructions=(
                    "An existing user has just logged back in. "
                    "Give the user a warm welcome and move on. "
                    "Example: Hey! Welcome back buddy! Let's get you a new program set up."
                )
            )
        else:
            await self.session.generate_reply(
                instructions=(
                    "A new user just joined us! Give them a warm welcome and move on "
                    "to the next step. "
                    "Example: 'Hey there! Nice to meet you, I'm Nova, your AI fitness coach! "
                    "We'll be able to do a lot more once the Nova One squat rack is released, "
                    "but for now they've put me on duty helping y'all generate programs... "
                    "So, what's your first name?'"
                )
            )

    # ------------------------------------------------------------------
    # The single tool
    # ------------------------------------------------------------------

    @function_tool
    async def capture_fields(
        self,
        context: RunContext,
        name: Optional[str] = None,
        age: Optional[int] = None,
        sex: Optional[str] = None,
        height_value: Optional[str] = None,
        weight_value: Optional[str] = None,
        goal_description: Optional[str] = None,
        fitness_level: Optional[str] = None,
        extra_info: Optional[str] = None,
        days_per_week: Optional[int] = None,
        session_duration: Optional[int] = None,
        injury_history: Optional[str] = None,
        specific_sport: Optional[str] = None,
        training_season: Optional[str] = None,
        games_per_week: Optional[int] = None,
    ):
        """
        Save one or more user fields. Call every time the user provides new
        information.  Only pass the fields the user just mentioned -- omit
        everything else.

        Args:
            name: First name
            age: Age in years (13-100)
            sex: "male", "female", "M", "F", etc.
            height_value: Height as spoken (e.g. "5'10", "175 cm", "six foot")
            weight_value: Weight as spoken (e.g. "185 pounds", "80 kg")
            goal_description: What the user wants to achieve
            fitness_level: "beginner", "intermediate", or "advanced"
            extra_info: Any extra context the user shared (training history, etc.)
            days_per_week: Training frequency 1-7, only if user specified
            session_duration: Minutes per session 30-180, only if user specified
            injury_history: Injuries or limitations, only if user specified
            specific_sport: Sport name, only if user specified
            training_season: "off_season", "pre_season", "in_season", "post_season"
            games_per_week: Games per week 0-7, only if user specified
        """
        params = {k: v for k, v in dict(
            name=name, age=age, sex=sex,
            height_value=height_value, weight_value=weight_value,
            goal_description=goal_description, fitness_level=fitness_level,
            extra_info=extra_info, days_per_week=days_per_week,
            session_duration=session_duration, injury_history=injury_history,
            specific_sport=specific_sport, training_season=training_season,
            games_per_week=games_per_week,
        ).items() if v is not None}

        logger.info(f"[V2 TOOL] capture_fields({list(params.keys())})")

        if "program_creation" not in self.state:
            self.state["program_creation"] = {}
        pc = self.state["program_creation"]

        captured: list[str] = []
        errors: list[str] = []

        # -- name --
        if name is not None:
            n = name.strip()
            placeholders = {
                "example_value", "example", "string", "first_name", "name",
                "user", "test", "placeholder", "null", "none", "undefined",
            }
            if not n or len(n) > 50 or n.lower().replace(" ", "_") in placeholders:
                errors.append("name invalid -- ask for their real first name")
            else:
                self.state["name"] = n
                captured.append(f"name={n}")

        # -- age --
        if age is not None:
            if isinstance(age, int) and 13 <= age <= 100:
                pc["age"] = age
                captured.append(f"age={age}")
            else:
                errors.append("age out of range (13-100)")

        # -- sex --
        if sex is not None:
            s = sex.lower().strip()
            if s in ("m", "male", "man", "boy"):
                pc["sex"] = "male"
                captured.append("sex=male")
            elif s in ("f", "female", "woman", "girl"):
                pc["sex"] = "female"
                captured.append("sex=female")
            else:
                errors.append("sex unclear -- ask male or female")

        # -- height --
        if height_value is not None:
            h = normalize_height_to_cm(height_value)
            if h is not None and 50 <= h <= 300:
                pc["height_cm"] = h
                captured.append(f"height={h:.0f}cm")
            else:
                errors.append(
                    "could not parse height -- ask them to say it like "
                    "'five foot ten' or '175 cm'"
                )

        # -- weight --
        if weight_value is not None:
            w = normalize_weight_to_kg(weight_value)
            if w is not None and 30 <= w <= 300:
                pc["weight_kg"] = w
                captured.append(f"weight={w:.0f}kg")
            else:
                errors.append(
                    "could not parse weight -- ask them to say it like "
                    "'185 pounds' or '80 kg'"
                )

        # -- goal --
        if goal_description is not None:
            g = goal_description.strip()
            if g:
                pc["goal_raw"] = g
                pc["goal_category"] = categorize_goal(g)
                captured.append(f"goal={pc['goal_category']}")
            else:
                errors.append("goal description is empty")

        # -- fitness_level --
        if fitness_level is not None:
            fl = fitness_level.lower().strip()
            if "beginner" in fl or "new" in fl or "start" in fl:
                fl = "beginner"
            elif "advanced" in fl or "expert" in fl or "experienced" in fl:
                fl = "advanced"
            else:
                fl = "intermediate"
            pc["fitness_level"] = fl
            captured.append(f"fitness_level={fl}")

        # -- extra_info --
        if extra_info is not None and extra_info.strip().lower() not in ("none", ""):
            self.state["extra_info"] = extra_info.strip()

        # -- optional program params --
        if days_per_week is not None:
            pc["days_per_week"] = max(1, min(7, int(days_per_week)))
            captured.append(f"days_per_week={pc['days_per_week']}")
        if session_duration is not None:
            pc["session_duration"] = max(30, min(180, int(session_duration)))
            captured.append(f"session_duration={pc['session_duration']}")
        if injury_history is not None and injury_history.strip():
            pc["injury_history"] = injury_history.strip()
            captured.append("injury_history=set")
        if specific_sport is not None and specific_sport.strip():
            pc["specific_sport"] = specific_sport.strip()
            captured.append(f"sport={pc['specific_sport']}")
        if training_season is not None and training_season.strip():
            season = training_season.lower().strip().replace(" ", "_").replace("-", "_")
            if season in ("off_season", "pre_season", "in_season", "post_season"):
                pc["training_season"] = season
                captured.append(f"season={season}")
        if games_per_week is not None:
            pc["games_per_week"] = max(0, min(7, int(games_per_week)))
            captured.append(f"games_per_week={pc['games_per_week']}")

        # -- build status response --
        missing = self._get_missing_required()

        parts: list[str] = []
        if captured:
            parts.append(f"Saved: {', '.join(captured)}.")
        if errors:
            parts.append(f"Errors: {'; '.join(errors)}.")

        if not missing:
            self._apply_defaults()
            parts.append(
                "ALL REQUIRED FIELDS CAPTURED. "
                "Say goodbye: thank the user, tell them they will get their program "
                "via email within five minutes (check inbox and spam). "
                "Do NOT ask any more questions."
            )

            def _on_goodbye_done(_):
                if not self._finalize_fired:
                    self._finalize_fired = True
                    asyncio.create_task(self._finalize_and_disconnect())

            context.speech_handle.add_done_callback(_on_goodbye_done)

            async def _finalize_timeout():
                await asyncio.sleep(30)
                if not self._finalize_fired:
                    logger.warning("[V2 FINALIZE] Timeout -- forcing finalize")
                    self._finalize_fired = True
                    await self._finalize_and_disconnect()

            asyncio.create_task(_finalize_timeout())
        else:
            parts.append(f"Still missing: {', '.join(missing)}. Ask for these next.")

        msg = " ".join(parts)
        logger.info(f"[V2 TOOL] -> {msg}")
        return None, msg

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_missing_required(self) -> list[str]:
        """Return human-readable list of missing required fields."""
        pc = self.state.get("program_creation", {})
        missing = []
        if not self.state.get("name"):
            missing.append("name")
        for field, label in [
            ("age", "age"),
            ("sex", "sex"),
            ("height_cm", "height"),
            ("weight_kg", "weight"),
            ("goal_raw", "goal"),
            ("goal_category", "goal"),
            ("fitness_level", "fitness_level"),
        ]:
            if field not in pc and label not in missing:
                missing.append(label)
        return missing

    def _apply_defaults(self):
        """Fill optional fields with sensible defaults."""
        pc = self.state.get("program_creation", {})
        pc["duration_weeks"] = 12
        pc["equipment_tier"] = 3
        pc["has_vbt_capability"] = False

        if pc.get("days_per_week") is None:
            fl = pc.get("fitness_level", "intermediate")
            pc["days_per_week"] = {"beginner": 3, "intermediate": 4, "advanced": 5}.get(fl, 4)
        if pc.get("session_duration") is None:
            pc["session_duration"] = 60
        if pc.get("injury_history") is None:
            pc["injury_history"] = "none"
        if pc.get("specific_sport") is None:
            pc["specific_sport"] = "none"
        if pc.get("games_per_week") is None:
            pc["games_per_week"] = 0

        logger.info(f"[V2 AGENT] Defaults applied: {pc}")

    # ------------------------------------------------------------------
    # Finalize chain (mirrors V1)
    # ------------------------------------------------------------------

    async def _update_user_profile_direct(self):
        user_id = self.state.get("user_id")
        if not user_id:
            logger.error("[V2 FINALIZE] No user ID. Cannot update profile.")
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
                logger.info(f"[V2 FINALIZE] Updated user profile for {self.state.get('email')}")
            else:
                logger.error("[V2 FINALIZE] User not found in database.")
        except Exception as e:
            logger.error(f"[V2 FINALIZE] Failed to update user profile: {e}")
            db.rollback()
        finally:
            db.close()

    async def _generate_program_direct(self):
        user_id = self.state.get("user_id")
        user_email = self.state.get("email")
        if not user_id:
            logger.error("[V2 FINALIZE] No user ID. Cannot generate program.")
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
        logger.info(f"[V2 FINALIZE] Calling program generation API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=_service_headers())
                if response.status_code == 202:
                    data = response.json()
                    job_id = data.get("job_id")
                    self.state["program_creation"]["job_id"] = job_id
                    logger.info(f"[V2 FINALIZE] Program generation started. Job ID: {job_id}")
                    try:
                        await self.session.room_io.room.local_participant.publish_data(
                            json.dumps({
                                "type": "program_generating",
                                "job_id": job_id,
                                "email": user_email,
                            }).encode(),
                            reliable=True,
                        )
                        logger.info("[V2 FINALIZE] Sent 'program_generating' data message")
                    except Exception as e:
                        logger.error(f"[V2 FINALIZE] Failed to send data message: {e}")
                else:
                    logger.error(f"[V2 FINALIZE] API error: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"[V2 FINALIZE] Failed to generate program: {e}")

    async def _finalize_and_disconnect(self):
        try:
            required = [
                "height_cm", "weight_kg", "age", "sex",
                "goal_category", "goal_raw", "duration_weeks",
                "days_per_week", "fitness_level",
            ]
            program = self.state.get("program_creation", {})
            missing = [p for p in required if p not in program]
            if missing:
                logger.error(f"[V2 FINALIZE] Missing required params: {missing} -- cannot finalize")
                return

            await self._update_user_profile_direct()
            await self._generate_program_direct()

            try:
                await self.session.room_io.room.disconnect()
                logger.info("[V2 FINALIZE] Complete. Disconnected via room.")
            except Exception as e:
                logger.warning(f"[V2 FINALIZE] Room disconnect failed ({e}), closing session")
                try:
                    await self.session.aclose()
                    logger.info("[V2 FINALIZE] Complete. Session closed.")
                except Exception as e2:
                    logger.error(f"[V2 FINALIZE] Session close also failed: {e2}")
        except Exception as e:
            logger.error(f"[V2 FINALIZE] Error in finalize chain: {e}")
