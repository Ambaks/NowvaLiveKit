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

# Persona prefix prepended to all coaching LLM instructions.
_COACHING_PERSONA = (
    "You are Nova, an energetic, world-class fitness coach on the Nowva smart squat rack. "
    "HIGH energy, motivating, supportive. SHORT responses only — follow the word limits given. "
    "Sound like a real coach in the gym — keep it human."
)


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
        room=None,        # rtc.Room — for publishing separate audio tracks
        on_workout_complete: Optional[Callable] = None,
        on_calibration_complete: Optional[Callable] = None,
        audio_cue_service=None,  # Prewarmed AudioCueService (optional)
    ):
        self._session = session
        self._state = state
        self._room = room
        self._on_workout_complete_callback = on_workout_complete
        self._on_calibration_complete_callback = on_calibration_complete

        # Owned components
        self._coaching_ipc = None
        self._coaching_orchestrator = None
        self._audio_cue_service = audio_cue_service

        # Internal state
        self._listener_running = False
        self._event_loop = None
        self._started = False

        # Flag for wake word system to detect active coaching speech
        self.is_coaching_speaking: bool = False

    # ------------------------------------------------------------------
    # Lifecycle API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start all coaching subsystems."""
        if self._started:
            return

        self._event_loop = asyncio.get_running_loop()
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
        """Connect to the coaching IPC server and listen for biomechanics messages.

        Uses exponential backoff reconnection (3 attempts: 1s, 2s, 4s).
        If the connection drops mid-session, the listener thread will
        automatically attempt to reconnect.
        """
        if self._listener_running:
            logger.info("[COACHING SERVICE] Listener already running")
            return

        from core.ipc_communication import IPCClient

        max_retries = 3
        base_delay = 1.0  # seconds

        def _connect_with_retry() -> bool:
            """Attempt IPC connection with exponential backoff."""
            for attempt in range(1, max_retries + 1):
                self._coaching_ipc = IPCClient(socket_path="/tmp/nowva_coaching.sock")
                if self._coaching_ipc.connect(timeout=15):
                    logger.info(f"[COACHING SERVICE] Connected to coaching IPC server (attempt {attempt})")
                    return True
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    f"[COACHING SERVICE] IPC connection attempt {attempt}/{max_retries} failed, "
                    f"retrying in {delay}s..."
                )
                import time as _time
                _time.sleep(delay)
            logger.error(
                f"[COACHING SERVICE] Failed to connect to coaching IPC server "
                f"after {max_retries} attempts — coaching data will be unavailable"
            )
            return False

        def _listen_thread():
            try:
                if not _connect_with_retry():
                    return
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
                # Attempt reconnection on unexpected disconnect
                if self._started:
                    logger.info("[COACHING SERVICE] Attempting reconnection after disconnect...")
                    try:
                        if _connect_with_retry():
                            self._listener_running = True

                            def on_message_retry(message: dict):
                                if self._event_loop and self._event_loop.is_running():
                                    asyncio.run_coroutine_threadsafe(
                                        self._handle_message(message),
                                        self._event_loop,
                                    )

                            self._coaching_ipc.listen(message_callback=on_message_retry)
                    except Exception as e2:
                        logger.error(f"[COACHING SERVICE] Reconnection failed: {e2}")
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
            elif msg_type == "diagnosis_complete":
                diagnosis = message.get("diagnosis", {})
                scoring = message.get("scoring", {})
                logger.info(
                    f"[COACHING SERVICE] DIAGNOSIS COMPLETE: "
                    f"confidence={diagnosis.get('confidence', 0):.2f} "
                    f"score={scoring.get('mean_score', 0):.3f}"
                )
                if self._coaching_orchestrator:
                    self._coaching_orchestrator.set_diagnosis_data(diagnosis, scoring)
                else:
                    logger.warning("[COACHING SERVICE] No orchestrator — diagnosis_complete dropped")
            elif msg_type == "set_complete":
                logger.info("[COACHING SERVICE] set_complete from pipeline (ignored — orchestrator handles via rep count)")
            elif msg_type == "rest_complete":
                logger.info("[COACHING SERVICE] REST COMPLETE — firing LLM prompt for next set")

                # Get set numbers from workout session
                completed_set, next_set, total_sets = self._get_set_numbers()

                instructions = (
                    f"[REST COMPLETE] Rest is over. "
                    f"Set {completed_set} of {total_sets} is done. Set {next_set} of {total_sets} starts now. "
                    f"Announce it — be energetic and brief (1 sentence max). "
                    f"Do NOT ask if they are ready. Do NOT wait for confirmation. "
                    f"Just announce it. Example: 'Set {completed_set} done, set {next_set} — let's go!'"
                )
                logger.info("[COACHING SERVICE] → Calling coaching LLM for rest_complete")
                await self._coaching_llm_reply(instructions)
                logger.info("[COACHING SERVICE] ✓ Coaching LLM returned for rest_complete")

                # Resume rep/fault processing AFTER the announcement finishes.
                # Keeping _resting=True during speech prevents the orchestrator
                # from dispatching cached cues that collide with the announcement.
                if self._coaching_orchestrator:
                    self._coaching_orchestrator.on_rest_complete()
            elif msg_type == "assessment_rep":
                rep = message.get("rep_number", 0)
                total = message.get("total_required", 2)
                round_num = message.get("round", 1)
                logger.info(f"[COACHING SERVICE] ASSESSMENT REP {rep}/{total} (round {round_num})")
                cue_key = f"rep_{rep}"
                await self._play_cached_cue_audio(cue_key)
            elif msg_type == "assessment_result":
                passed = message.get("passed", False)
                round_num = message.get("round", 1)
                logger.info(
                    f"[COACHING SERVICE] ASSESSMENT RESULT: passed={passed} round={round_num}"
                )
                await self._on_assessment_result(message)
            elif msg_type == "calibration_rep":
                rep = message.get("rep_number", 0)
                total = message.get("total_required", 5)
                depth = message.get("depth_angle", 0)
                logger.info(f"[COACHING SERVICE] CALIBRATION REP {rep}/{total} depth={depth}°")
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
            if self._room:
                await self._audio_cue_service.setup_rep_track(self._room)
        else:
            # Prewarmed service — attach live session and rep track on first use
            if self._audio_cue_service._session is None:
                self._audio_cue_service.attach_session(self._session)
                logger.info("[COACHING SERVICE] Attached session to prewarmed AudioCueService")
            if self._room and not self._audio_cue_service._rep_track_ready:
                await self._audio_cue_service.setup_rep_track(self._room)

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

    async def _on_assessment_result(self, message: dict) -> None:
        """Handle assessment result — speak feedback via LLM."""
        passed = message.get("passed", False)
        round_num = message.get("round", 1)
        diagnosis = message.get("diagnosis", {})
        scoring = message.get("scoring", {})

        if not passed:
            instructions = self._build_assessment_correction_prompt(
                diagnosis, scoring, round_num,
            )
        else:
            instructions = self._build_assessment_pass_prompt(
                diagnosis, scoring, round_num,
            )

        logger.info(f"[ASSESSMENT] LLM prompt: {instructions[:150]}...")
        await self._coaching_llm_reply(instructions)

    def _build_assessment_correction_prompt(
        self, diagnosis: dict, scoring: dict, round_num: int,
    ) -> str:
        immediate = diagnosis.get("immediate_causes", [])
        top_issue = immediate[0] if immediate else {}

        context_parts = []
        context_parts.append(f"Assessment round {round_num}: 2 bodyweight squats analyzed.")

        mean_pct = round(scoring.get("mean_score", 0) * 100)
        context_parts.append(f"Form score: {mean_pct}/100.")

        if top_issue:
            context_parts.append(
                f"Main issue: {top_issue.get('explanation', 'form issue detected')}."
            )
            delta = top_issue.get("parameter_delta")
            if delta:
                delta_str = ", ".join(f"{k}: {v}" for k, v in delta.items())
                context_parts.append(f"Recommended adjustment: {delta_str}.")

        if len(immediate) > 1:
            other = immediate[1]
            context_parts.append(
                f"Secondary issue: {other.get('explanation', '')}."
            )

        context_str = " ".join(context_parts)

        return (
            f"[PRE-WORKOUT ASSESSMENT] You are assessing the user's squat form before their workout. "
            f"This is a form check — NOT a workout set. "
            f"{context_str} "
            f"Tell the user the specific issue you found and what to adjust. "
            f"Be specific and actionable (e.g., 'widen your stance a bit' or 'push your knees out more'). "
            f"Then tell them to try 2 more reps with that adjustment. "
            f"Keep it encouraging and brief (2-3 sentences). "
            f"Do NOT say 'assessment' — say something like 'Let me see that again with [adjustment].'"
        )

    def _build_assessment_pass_prompt(
        self, diagnosis: dict, scoring: dict, round_num: int,
    ) -> str:
        session_causes = diagnosis.get("session_causes", [])
        contextual = diagnosis.get("contextual_notes", [])
        mean_pct = round(scoring.get("mean_score", 0) * 100)

        context_parts = []
        context_parts.append(
            f"Assessment complete after {round_num} round(s). Form score: {mean_pct}/100."
        )

        other_notes = []
        for cause in session_causes:
            explanation = cause.get("explanation", "")
            if explanation:
                other_notes.append(explanation)
        for note in contextual:
            explanation = note.get("explanation", "")
            if explanation:
                other_notes.append(explanation)

        if other_notes:
            context_parts.append(
                f"Things that may show up during heavier sets: {'; '.join(other_notes[:2])}."
            )

        context_str = " ".join(context_parts)

        if other_notes:
            return (
                f"[PRE-WORKOUT ASSESSMENT PASSED] The user's squat form looks good — no immediate fixes needed. "
                f"{context_str} "
                f"Praise their form briefly, then mention 1-2 things they might notice during heavier sets "
                f"(these are informational, not something to fix right now). "
                f"Then transition to calibration: tell them you need 5 deep bodyweight squats "
                f"to learn their movement pattern so you can coach them during the workout. "
                f"Keep it natural and brief (3-4 sentences max)."
            )
        else:
            return (
                f"[PRE-WORKOUT ASSESSMENT PASSED] The user's squat form looks great — no issues at all! "
                f"{context_str} "
                f"Praise their form enthusiastically. "
                f"Then transition to calibration: tell them you need 5 deep bodyweight squats "
                f"to fine-tune your understanding of how they move. "
                f"Keep it brief and hype (2-3 sentences)."
            )

    async def _on_calibration_complete(self, message: dict):
        """Handle calibration_complete IPC message — save to DB and notify user."""
        from db.database import SessionLocal
        from db.calibration_utils import save_user_calibration

        movement_pattern = message.get("movement_pattern", "squat")
        peaks = message.get("peaks", {})
        thresholds = message.get("thresholds", {})
        athlete_params = message.get("athlete_params")
        baseline = message.get("baseline")

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
                    athlete_params=athlete_params,
                    baseline=baseline,
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
        instructions = (
            "[CALIBRATION COMPLETE] Calibration is done. "
            "The user's custom movement thresholds are now set. "
            "Say something like: 'Alright, we're all dialed in! Let's get into your workout.' "
            "Keep it brief and hype."
        )
        await self._coaching_llm_reply(instructions)

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
            prune_context_fn=self._prune_conversation_context,
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

                return None

        except Exception:
            logger.exception("[COACHING SERVICE] Failed to advance workout set")
            return None

    async def force_end_current_set(self, reps: int) -> dict:
        """Force-end the current set early (called by workout agent when user verbally stops).

        Puts the orchestrator into rest mode, overrides the rep count,
        advances the WorkoutSession, and resets for the next set if any.
        """
        from core.workout_session import WorkoutSession

        session_data = self._state.get("workout.current_session")
        if not session_data:
            return {"status": "no_session"}

        session = WorkoutSession.from_dict(session_data)
        completed_set = session.get_current_set()
        rest_seconds = completed_set.rest_seconds if completed_set else 60

        if self._coaching_orchestrator:
            self._coaching_orchestrator._resting = True
            self._coaching_orchestrator._set_rep_count = reps

        new_target = await self._advance_workout_set()

        if new_target is not None:
            # There is a next set — reset orchestrator
            if self._coaching_orchestrator:
                self._coaching_orchestrator.reset_set(target_reps=new_target)

            session_data = self._state.get("workout.current_session")
            next_desc = ""
            if session_data:
                s = WorkoutSession.from_dict(session_data)
                next_desc = s.get_current_exercise_description()

            return {
                "status": "advanced",
                "rest_seconds": rest_seconds,
                "next_set_description": next_desc,
            }
        else:
            return {"status": "workout_complete"}

    async def _on_workout_complete(self):
        """Called by orchestrator after exercise recap is spoken."""
        logger.info("[COACHING SERVICE] Workout complete — notifying voice agent")
        if self._on_workout_complete_callback:
            await self._on_workout_complete_callback({"workout_complete": True})

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

    async def _prune_conversation_context(self, max_items: int = 20):
        """Prune old conversation items, injecting compaction summary.

        If a CompactionService is active, injects its pre-built summary
        so historical context is preserved. Falls back to simple truncation.
        """
        try:
            agent = self._session.current_agent
            if agent is None:
                return
            ctx = agent.chat_ctx
            if len(ctx.items) <= max_items:
                return

            old_count = len(ctx.items)

            # Try to get compaction summary via agent's userdata
            summary_text = ""
            userdata = getattr(agent, 'userdata', None)
            if userdata:
                compaction = getattr(userdata, 'compaction_service', None)
                if compaction:
                    summary_text = compaction.get_summary()

            if not summary_text:
                # Fallback: simple truncation (original behavior)
                new_ctx = ctx.copy()
                new_ctx.truncate(max_items=max_items)
                await agent.update_chat_ctx(new_ctx)
                logger.info(
                    f"[COACHING SERVICE] Pruned context: "
                    f"{old_count} → {len(new_ctx.items)} items (no summary)"
                )
                return

            # Summary-aware pruning: system items + summary + recent items
            from livekit.agents import llm

            items = list(ctx.items)
            system_items = [i for i in items if hasattr(i, 'role') and i.role in ("system", "developer")]
            non_system = [i for i in items if not (hasattr(i, 'role') and i.role in ("system", "developer"))]
            recent_items = non_system[-max_items:] if len(non_system) > max_items else non_system

            new_ctx = llm.ChatContext.empty()
            for item in system_items:
                new_ctx.items.append(item)

            summary_message = llm.ChatMessage(
                role="system",
                content=[f"[CONVERSATION SUMMARY]\n{summary_text}"],
            )
            new_ctx.items.append(summary_message)

            for item in recent_items:
                new_ctx.items.append(item)

            await agent.update_chat_ctx(new_ctx)
            logger.info(
                f"[COACHING SERVICE] Pruned context with summary: "
                f"{old_count} → {len(new_ctx.items)} items "
                f"({len(system_items)} system + 1 summary + {len(recent_items)} recent)"
            )
            logger.info("[COMPACTION:SWAP] Summary injected into context on prune")
        except Exception as e:
            logger.warning(f"[COACHING SERVICE] Context pruning failed: {e}")

    async def _coaching_llm_reply(self, instructions: str):
        """Generate coaching speech via generate_reply with SpeechHandle tracking.

        Sends the coaching persona as system instructions and the coaching
        task as user_input so the LLM has a clear user-role message to
        respond to (Llama models may generate near-empty responses when
        only system instructions are provided with no user turn).
        """
        logger.info(f"[COACHING SERVICE] → Coaching LLM | instructions[:80]={instructions[:80]}...")
        self.is_coaching_speaking = True
        try:
            handle = self._session.generate_reply(
                instructions=_COACHING_PERSONA,
                user_input=instructions,
                tool_choice="none",
                allow_interruptions=False,
            )
            await handle.wait_for_playout()
            logger.info("[COACHING SERVICE] ✓ Coaching LLM playout complete")
            return handle
        except Exception as e:
            logger.error(f"[COACHING SERVICE] Coaching LLM reply failed: {e}", exc_info=True)
            return None
        finally:
            self.is_coaching_speaking = False

    async def _duck_llm_audio(self):
        """No-op: session.say() handles audio transitions on the WebRTC track."""
        pass

    async def _unduck_llm_audio(self):
        """No-op: session.say() handles audio transitions on the WebRTC track."""
        pass
