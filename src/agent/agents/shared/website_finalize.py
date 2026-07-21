"""
Shared post-goodbye finalize chain for the website voice agents:
persist the user profile, trigger program generation via FastAPI,
then disconnect from the room.
"""

from __future__ import annotations

import json
import logging
import os

import httpx

from agent.agents.shared.helpers import build_program_generation_payload, service_headers
from db.database import SessionLocal
from db.models import User

logger = logging.getLogger(__name__)

REQUIRED_PROGRAM_PARAMS = [
    "height_cm", "weight_kg", "age", "sex",
    "goal_category", "goal_raw", "duration_weeks",
    "days_per_week", "fitness_level",
]


class WebsiteFinalizeMixin:
    """Finalize chain shared by WebsiteVoiceAgent (V1) and WebsiteVoiceAgentV2.

    Expects the host agent to provide ``self.state`` (plain dict) and
    ``self.session`` (LiveKit AgentSession).
    """

    async def _recover_missing_params(self, missing: list[str]) -> bool:
        """Return True if the conversation was re-routed to collect missing params
        (finalize aborts). Default: cannot recover, abort finalize."""
        return True

    async def _update_user_profile_direct(self):
        """Update user profile in DB from collected program params."""
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
        """Trigger program generation via FastAPI."""
        user_id = self.state.get("user_id")
        user_email = self.state.get("email")
        if not user_id:
            logger.error("[FINALIZE] No user ID. Cannot generate program.")
            return

        program_params = self.state.get("program_creation", {})
        payload = build_program_generation_payload(
            program_params,
            user_id=str(user_id),
            name=self.state.get("name"),
            email=user_email,
            send_email=True,
        )

        fastapi_url = os.getenv("FASTAPI_URL", "http://localhost:8000")
        url = f"{fastapi_url}/api/programs/generate"
        logger.info(f"[FINALIZE] Calling program generation API: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=service_headers())
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
                                "email": user_email,
                            }).encode(),
                            reliable=True,
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
            program = self.state.get("program_creation", {})
            missing = [p for p in REQUIRED_PROGRAM_PARAMS if p not in program]
            if missing:
                logger.error(f"[FINALIZE] Missing required params: {missing}")
                if await self._recover_missing_params(missing):
                    return  # Don't finalize -- conversation continues

            await self._update_user_profile_direct()
            await self._generate_program_direct()

            # Disconnect from room (try room disconnect first, fall back to session close)
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
