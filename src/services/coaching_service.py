"""
Standalone Coaching Service

Handles all real-time biomechanics coaching during workout sets.
Owns: IPC listener, CoachingOrchestrator, AudioCueService.
The voice agent is passive during sets — this service fires
generate_reply() calls directly for all coaching speech.
"""

import asyncio
import logging
import threading
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger(__name__)

# Minimal system prompt for isolated coaching LLM calls.
# This is the ONLY context the model sees (no conversation history).
COACHING_SYSTEM_PROMPT = """You are Nova, an energetic, world-class fitness coach on the Nowva smart squat rack.

Voice & Delivery:
- HIGH energy, motivating, supportive
- SHORT responses only — follow the word limits given
- Sound like a real coach in the gym
— keep it human"""


class CoachingService:
    """
    Standalone coaching service that runs in the same process as the voice agent.
    Holds references to AgentSession and AgentState, handles all IPC,
    orchestration, audio playback, and LLM calls independently.
    """

    def __init__(
        self,
        session,          # AgentSession — for generate_reply, output.audio
        state,            # AgentState — for reading/writing WorkoutSession
        on_set_complete: Optional[Callable] = None,
        on_calibration_complete: Optional[Callable] = None,
    ):
        self._session = session
        self._state = state
        self._on_set_complete_callback = on_set_complete
        self._on_calibration_complete_callback = on_calibration_complete

        # Owned components
        self._coaching_ipc = None
        self._coaching_orchestrator = None
        self._audio_cue_service = None

        # Internal state
        self._listener_running = False
        self._event_loop = None
        self._started = False

        # Lock to prevent context swap from overlapping with wake word responses
        self.context_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start all coaching subsystems."""
        if self._started:
            return

        self._event_loop = asyncio.get_event_loop()
        self._init_orchestrator()
        asyncio.create_task(self._start_ipc_listener())

        self._started = True
        logger.info("[COACHING SERVICE] Started")

    async def stop(self) -> None:
        """Stop all coaching subsystems and clean up."""
        if not self._started:
            return

        if self._coaching_orchestrator:
            self._coaching_orchestrator.stop()
            self._coaching_orchestrator = None

        self._stop_ipc_listener()
        self._audio_cue_service = None
        self._started = False
        logger.info("[COACHING SERVICE] Stopped")

    @property
    def is_resting(self) -> bool:
        """Whether the service is in rest-between-sets mode."""
        if self._coaching_orchestrator:
            return self._coaching_orchestrator._resting
        return False

    # ------------------------------------------------------------------
    # IPC Listener
    # ------------------------------------------------------------------

    async def _start_ipc_listener(self):
        """Connect to the coaching IPC server and listen for biomechanics messages."""
        if self._listener_running:
            logger.info("[COACHING SERVICE] Listener already running")
            return

        from core.ipc_communication import IPCClient

        self._coaching_ipc = IPCClient(socket_path="/tmp/nowva_coaching.sock")

        def _listen_thread():
            try:
                if not self._coaching_ipc.connect(timeout=15):
                    logger.warning("[COACHING SERVICE] Failed to connect to coaching IPC server")
                    return
                logger.info("[COACHING SERVICE] Connected to coaching IPC server")
                self._listener_running = True

                def on_message(message: dict):
                    if self._event_loop and self._event_loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self._handle_message(message),
                            self._event_loop,
                        )

                self._coaching_ipc.listen(message_callback=on_message)
            except Exception as e:
                logger.error(f"[COACHING SERVICE] Listener error: {e}")
            finally:
                self._listener_running = False

        thread = threading.Thread(target=_listen_thread, daemon=True)
        thread.start()
        logger.info("[COACHING SERVICE] Listener thread started")

    def _stop_ipc_listener(self):
        """Disconnect from the coaching IPC server."""
        if self._coaching_ipc:
            self._coaching_ipc.disconnect()
            self._coaching_ipc = None
        self._listener_running = False
        logger.info("[COACHING SERVICE] Listener stopped")

    # ------------------------------------------------------------------
    # Message Dispatch
    # ------------------------------------------------------------------

    async def _handle_message(self, message: dict):
        """Dispatch incoming coaching message through the orchestrator."""
        msg_type = message.get("type")
        logger.info(f"[COACHING SERVICE] ← IPC message received: type={msg_type} | keys={list(message.keys())}")

        try:
            if msg_type == "cache_cues":
                await self._on_cache_cues(message)
            elif msg_type == "fault":
                cue_key = message.get("cue")
                fault_type = message.get("fault_type", "")
                severity = message.get("severity", "")
                fault_msg = message.get("message", "")
                logger.info(f"[COACHING SERVICE] FAULT received: type={fault_type} severity={severity} cue={cue_key} msg='{fault_msg}'")
                if self._coaching_orchestrator:
                    await self._coaching_orchestrator.on_fault(
                        cue_key=cue_key,
                        fault_type=fault_type,
                        severity=severity,
                        message=fault_msg,
                    )
                else:
                    logger.warning("[COACHING SERVICE] No orchestrator — fault dropped")
            elif msg_type == "rep_complete":
                rep = message.get("rep_number")
                depth = message.get("depth_category", "")
                is_clean = message.get("is_clean", False)
                faults = message.get("faults_in_rep", [])
                max_depth_angle = message.get("max_depth_angle", 0.0)
                rep_duration_ms = message.get("rep_duration_ms", 0)
                logger.info(
                    f"[COACHING SERVICE] REP COMPLETE received: rep={rep} depth={depth} "
                    f"is_clean={is_clean} faults={faults}"
                )
                if self._coaching_orchestrator:
                    await self._coaching_orchestrator.on_rep_complete(
                        rep_number=rep or 0,
                        depth=depth,
                        is_clean=is_clean,
                        faults=faults,
                        max_depth_angle=max_depth_angle,
                        rep_duration_ms=rep_duration_ms,
                    )
                else:
                    logger.warning("[COACHING SERVICE] No orchestrator — rep_complete dropped")
            elif msg_type == "frame_data":
                if self._coaching_orchestrator:
                    self._coaching_orchestrator.record_angle_sample(
                        message.get("joint_angles", {})
                    )
            elif msg_type == "set_complete":
                logger.info("[COACHING SERVICE] set_complete from pipeline (ignored — orchestrator handles via rep count)")
            elif msg_type == "rest_complete":
                logger.info("[COACHING SERVICE] REST COMPLETE — firing LLM prompt for next set")
                if self._coaching_orchestrator:
                    self._coaching_orchestrator.on_rest_complete()

                # Get set numbers from workout session
                completed_set, next_set, total_sets = self._get_set_numbers()

                instructions = (
                    f"[REST COMPLETE] Rest is over. "
                    f"Set {completed_set} of {total_sets} is done. Set {next_set} of {total_sets} starts now. "
                    f"Announce it — be energetic and brief (1 sentence max). "
                    f"Do NOT ask if they are ready. Do NOT wait for confirmation. "
                    f"Just announce it. Example: 'Set {completed_set} done, set {next_set} — let's go!'"
                )
                logger.info("[COACHING SERVICE] → Calling isolated LLM for rest_complete")
                await self._isolated_llm_reply(
                    system_prompt=COACHING_SYSTEM_PROMPT,
                    user_message=instructions,
                )
                logger.info("[COACHING SERVICE] ✓ Isolated LLM returned for rest_complete")
            elif msg_type == "calibration_rep":
                rep = message.get("rep_number", 0)
                total = message.get("total_required", 5)
                depth = message.get("depth_angle", 0)
                logger.info(f"[COACHING SERVICE] CALIBRATION REP {rep}/{total} depth={depth}°")
                # Play cached rep count cue (same "rep_N" keys used during workouts)
                cue_key = f"rep_{rep}"
                await self._play_cached_cue_audio(cue_key)
            elif msg_type == "calibration_complete":
                logger.info("[COACHING SERVICE] CALIBRATION COMPLETE — saving to DB")
                await self._on_calibration_complete(message)
            elif msg_type == "play_cue":
                logger.debug("[COACHING SERVICE] play_cue ignored (orchestrator handles dispatch)")
            else:
                logger.warning(f"[COACHING SERVICE] Unknown message type: {msg_type}")
        except Exception as e:
            logger.error(f"[COACHING SERVICE] Error handling {msg_type}: {e}", exc_info=True)

    async def _on_cache_cues(self, message: dict):
        """Pre-generate TTS audio for all cues in the message."""
        from services.audio_cue_service import AudioCueService

        if self._audio_cue_service is None:
            self._audio_cue_service = AudioCueService(session=self._session)

        cues = message.get("cues", {})
        exercise = message.get("exercise_name", "unknown")
        logger.info(f"[COACHING SERVICE] Pre-caching {len(cues)} cues for {exercise}")

        try:
            await self._audio_cue_service.cache_cues(cues)
            if self._coaching_orchestrator:
                from biomechanics.coaching.cue_cache import POSITIVE_CUE_KEYS
                available = [k for k in cues if k in POSITIVE_CUE_KEYS]
                self._coaching_orchestrator._positive_cue_keys = available
        except Exception as e:
            logger.error(f"[COACHING SERVICE] TTS cache generation failed: {e}")

    async def _on_calibration_complete(self, message: dict):
        """Handle calibration_complete IPC message — save to DB and notify user."""
        from db.database import SessionLocal
        from db.calibration_utils import save_user_calibration

        movement_pattern = message.get("movement_pattern", "squat")
        peaks = message.get("peaks", {})
        thresholds = message.get("thresholds", {})

        # Save calibration to database
        user_id = self._state.get("user.id")
        if user_id:
            db = SessionLocal()
            try:
                save_user_calibration(
                    db=db,
                    user_id=user_id,
                    movement_pattern=movement_pattern,
                    peaks=peaks,
                    thresholds=thresholds,
                )
                logger.info(f"[CALIBRATION] Saved calibration to DB for user={user_id} pattern={movement_pattern}")
            except Exception as e:
                logger.error(f"[CALIBRATION] Failed to save to DB: {e}", exc_info=True)
            finally:
                db.close()
        else:
            logger.warning("[CALIBRATION] No user_id in state — cannot save calibration to DB")

        # Store profile in state for future use
        self._state.set("workout.calibration_profile", thresholds)
        self._state.set("calibration.active", None)
        self._state.set("calibration.movement_pattern", None)
        self._state.save_state()

        # Announce calibration completion via LLM
        name = self._state.get("user.name", "there")
        instructions = (
            f"[CALIBRATION COMPLETE] Calibration is done for {name}. "
            f"Their custom movement thresholds are now set. "
            f"Say something like: 'Alright, we're all dialed in! Let's get into your workout.' "
            f"Keep it brief and hype."
        )
        await self._isolated_llm_reply(
            system_prompt=COACHING_SYSTEM_PROMPT,
            user_message=instructions,
        )

        # Reset orchestrator for the actual workout sets
        if self._coaching_orchestrator:
            target_reps = self._get_current_target_reps()
            total_sets = self._get_total_sets()
            self._coaching_orchestrator.reset_set(target_reps=target_reps, total_sets=total_sets)
            logger.info("[CALIBRATION] Orchestrator reset for workout phase")

        # Notify voice agent so it can start the wake word system now that
        # calibration speech is finished and the user is ready to work out.
        if self._on_calibration_complete_callback:
            try:
                ret = self._on_calibration_complete_callback()
                if asyncio.iscoroutine(ret):
                    await ret
            except Exception as e:
                logger.error(f"[CALIBRATION] on_calibration_complete callback error: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Orchestrator Setup
    # ------------------------------------------------------------------

    def _init_orchestrator(self):
        """Initialize the coaching orchestrator with internal callbacks."""
        from services.coaching_orchestrator import CoachingOrchestrator

        self._coaching_orchestrator = CoachingOrchestrator(
            play_cached_audio_fn=self._play_cached_cue_audio,
            generate_llm_reply_fn=self._coaching_llm_reply,
            duck_llm_fn=self._duck_llm_audio,
            unduck_llm_fn=self._unduck_llm_audio,
            get_cue_audio_fn=self._get_cached_audio,
            advance_set_fn=self._advance_workout_set,
            on_workout_complete_fn=self._on_workout_complete,
        )

        target_reps = self._get_current_target_reps()
        total_sets = self._get_total_sets()
        self._coaching_orchestrator.reset_set(target_reps=target_reps, total_sets=total_sets)
        self._coaching_orchestrator.start()

    def _get_current_target_reps(self) -> Optional[int]:
        """Get target reps for the current set from WorkoutSession."""
        session_data = self._state.get("workout.current_session")
        if session_data:
            from core.workout_session import WorkoutSession
            try:
                session = WorkoutSession.from_dict(session_data)
                current_set = session.get_current_set()
                if current_set:
                    return current_set.target_reps
            except Exception:
                pass
        return None

    def _get_total_sets(self) -> Optional[int]:
        """Get total number of sets for the current exercise."""
        session_data = self._state.get("workout.current_session")
        if session_data:
            from core.workout_session import WorkoutSession
            try:
                session = WorkoutSession.from_dict(session_data)
                exercise = session.get_current_exercise()
                if exercise:
                    return len(exercise.sets)
            except Exception:
                pass
        return None

    def _get_set_numbers(self) -> tuple:
        """Get (completed_set, next_set, total_sets) from WorkoutSession."""
        session_data = self._state.get("workout.current_session")
        if session_data:
            from core.workout_session import WorkoutSession
            try:
                session = WorkoutSession.from_dict(session_data)
                exercise = session.get_current_exercise()
                if exercise:
                    # current_set_index points to the set about to start
                    next_set = exercise.current_set_index + 1
                    completed_set = next_set - 1
                    total_sets = len(exercise.sets)
                    return completed_set, next_set, total_sets
            except Exception:
                pass
        return 1, 2, 3  # Safe fallback

    # ------------------------------------------------------------------
    # Set Management
    # ------------------------------------------------------------------

    async def _advance_workout_set(self) -> Optional[int]:
        """Advance WorkoutSession to the next set. Returns new target_reps or None."""
        from core.workout_session import WorkoutSession

        session_data = self._state.get("workout.current_session")
        if not session_data:
            logger.warning("[COACHING SERVICE] No active session to advance")
            return None

        try:
            session = WorkoutSession.from_dict(session_data)

            completed_set = session.get_current_set()
            rest_seconds = completed_set.rest_seconds if completed_set else 30
            if self._coaching_orchestrator:
                self._coaching_orchestrator._rest_seconds = rest_seconds

            rep_count = (
                self._coaching_orchestrator._set_rep_count
                if self._coaching_orchestrator
                else 0
            )
            session.mark_set_complete(performed_reps=rep_count)

            has_next = session.advance_to_next_set()

            self._state.set("workout.current_session", session.to_dict())
            self._state.save_state()

            if has_next:
                next_set = session.get_current_set()
                new_target = next_set.target_reps if next_set else None
                logger.info(f"[COACHING SERVICE] Advanced to next set — target_reps={new_target}")

                if self._coaching_ipc and rest_seconds > 0:
                    try:
                        self._coaching_ipc.send_message({
                            "type": "rest_start",
                            "rest_seconds": rest_seconds,
                        })
                        logger.info(f"[COACHING SERVICE] Sent rest_start ({rest_seconds}s)")
                    except Exception as e:
                        logger.error(f"[COACHING SERVICE] Failed to send rest_start: {e}")

                # Notify voice agent of set completion
                if self._on_set_complete_callback:
                    set_summary = {
                        "set_number": self._coaching_orchestrator._set_number if self._coaching_orchestrator else 0,
                        "total_reps": rep_count,
                        "clean_reps": self._coaching_orchestrator._set_clean_count if self._coaching_orchestrator else 0,
                        "has_next_set": True,
                        "new_target_reps": new_target,
                    }
                    await self._on_set_complete_callback(set_summary)

                return new_target
            else:
                logger.info("[COACHING SERVICE] Workout complete — no more sets")

                # Signal pipeline to stop counting reps
                if self._coaching_ipc:
                    try:
                        self._coaching_ipc.send_message({"type": "workout_complete"})
                        logger.info("[COACHING SERVICE] Sent workout_complete to pipeline")
                    except Exception as e:
                        logger.error(f"[COACHING SERVICE] Failed to send workout_complete: {e}")

                if self._on_set_complete_callback:
                    set_summary = {
                        "set_number": self._coaching_orchestrator._set_number if self._coaching_orchestrator else 0,
                        "total_reps": rep_count,
                        "clean_reps": self._coaching_orchestrator._set_clean_count if self._coaching_orchestrator else 0,
                        "has_next_set": False,
                        "new_target_reps": None,
                    }
                    await self._on_set_complete_callback(set_summary)

                return None

        except Exception:
            logger.exception("[COACHING SERVICE] Failed to advance workout set")
            return None

    async def _on_workout_complete(self):
        """Called by orchestrator after exercise recap is spoken."""
        logger.info("[COACHING SERVICE] Workout complete — notifying voice agent")
        if self._on_set_complete_callback:
            await self._on_set_complete_callback({
                "workout_complete": True,
                "set_number": self._coaching_orchestrator._set_number if self._coaching_orchestrator else 0,
            })

    # ------------------------------------------------------------------
    # Audio Playback
    # ------------------------------------------------------------------

    async def _play_cached_cue_audio(self, cue_key: str):
        """Play a cached cue through LiveKit's session.say()."""
        logger.info(f"[COACHING SERVICE] → Playing cached cue: {cue_key}")
        if self._audio_cue_service:
            await self._audio_cue_service.play_cue(cue_key)
            logger.info(f"[COACHING SERVICE] ✓ Cached cue played: {cue_key}")
        else:
            logger.warning(f"[COACHING SERVICE] No audio_cue_service — cannot play: {cue_key}")

    def _get_cached_audio(self, cue_key: str) -> bool:
        """Check if cached audio exists for a cue key."""
        if self._audio_cue_service:
            return self._audio_cue_service.has_cue(cue_key)
        return False

    # ------------------------------------------------------------------
    # LLM & Audio Ducking
    # ------------------------------------------------------------------

    async def _coaching_llm_reply(self, instructions: str):
        """Generate a coaching LLM reply with isolated context."""
        logger.info(f"[COACHING SERVICE] → Isolated LLM call | instructions[:80]={instructions[:80]}...")
        await self._isolated_llm_reply(
            system_prompt=COACHING_SYSTEM_PROMPT,
            user_message=instructions,
        )
        logger.info("[COACHING SERVICE] ✓ Isolated LLM call returned")

    async def _isolated_llm_reply(self, system_prompt: str, user_message: str):
        """Generate an LLM reply with isolated context (no conversation history).

        Swaps the agent's chat context to a minimal system+user pair,
        generates the reply, then restores the original context.
        Uses an asyncio.Lock to prevent overlap with wake word responses.
        """
        from livekit.agents import llm

        agent = self._session.current_agent
        if not agent or not hasattr(agent, 'chat_ctx'):
            logger.warning("[COACHING SERVICE] No agent for isolated reply — falling back")
            await self._session.generate_reply(instructions=user_message, tool_choice="none")
            return

        async with self.context_lock:
            # 1. Snapshot current context
            original_ctx = agent.chat_ctx

            # 2. Build minimal context: system prompt + coaching data
            isolated_ctx = llm.ChatContext.empty()
            isolated_ctx.items.append(llm.ChatMessage(role="system", content=[system_prompt]))
            isolated_ctx.items.append(llm.ChatMessage(role="user", content=[user_message]))

            # 3. Swap in isolated context
            await agent.update_chat_ctx(isolated_ctx)

            try:
                # 4. Generate reply (model only sees system + user message)
                await self._session.generate_reply(tool_choice="none")
            finally:
                # 5. Restore original context (always, even on error)
                await agent.update_chat_ctx(original_ctx)

    async def _duck_llm_audio(self):
        """No-op: session.say() handles audio transitions on the WebRTC track."""
        pass

    async def _unduck_llm_audio(self):
        """No-op: session.say() handles audio transitions on the WebRTC track."""
        pass
