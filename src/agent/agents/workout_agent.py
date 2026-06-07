"""
WorkoutAgent - Handles active workout sessions with wake word system and coaching
"""

import asyncio
import logging
from typing import Optional

from livekit.agents import RunContext
from livekit.agents.llm import function_tool

from agent.agents.prompts import get_workout_prompt
from agent.agents.shared.base_agent import BaseNovaAgent
from db.database import SessionLocal

logger = logging.getLogger(__name__)


class WorkoutAgent(BaseNovaAgent):
    """Handles active workout sessions with wake word detection and coaching integration."""

    def __init__(self, state, userdata) -> None:
        # Wake word system state (agent-local)
        self._wake_word_active: bool = False
        self._wake_word_listening: bool = False
        self._wake_word_timeout_task: Optional[asyncio.Task] = None
        self._wake_word_phrases: list[str] = ["hey nova", "hey, nova", "a nova"]
        self._wake_word_timeout_seconds: float = 5.0

        super().__init__(state=state, userdata=userdata, instructions=get_workout_prompt())

    async def on_enter(self):
        """Start coaching service, generate greeting, then activate wake word system."""
        # Create and start coaching service
        from agent.services.coaching_service import CoachingService
        coaching_service = CoachingService(
            session=self.session,
            state=self.state,
            room=self.userdata.room,
            on_workout_complete=self._on_workout_complete_signal,
            on_calibration_complete=self._on_calibration_complete,
            audio_cue_service=self.userdata.audio_cue_service,
        )
        await coaching_service.start()
        self.userdata.coaching_service = coaching_service

        # Check if calibration is active
        needs_calibration = self.state.get("calibration.active", False)

        # Generate context-aware greeting BEFORE starting wake word system.
        # _say() suppresses turn detection so the greeting can't be interrupted.
        exercise_name = self.state.get("workout.exercise_name", "")

        if needs_calibration:
            # Don't restore turn detection — calibration is conversational
            await self._say(
                f"Tell the user conversationally that you haven't seen them do {exercise_name} before. "
                f"Say something like: 'So, I haven't seen you squat before — before we get into "
                f"your workout, I want to take a quick look at your form. Do 2 bodyweight squats "
                f"for me — hands out in front, go as deep as you can. I'll check your movement "
                f"and let you know if anything needs adjusting. Step into frame whenever you're ready.' "
                f"Keep it natural and encouraging.",
                restore=True,
            )
            # Signal main.py that greeting is done — safe to start pose estimation
            self.state.set("workout.greeting_done", True)
            self.state.save_state()
            logger.info("[WORKOUT] Greeting done — signalled main.py to start pose estimation")
        else:
            # Don't restore — wake word system sets its own turn detection next
            from agent.core.workout_session import WorkoutSession
            session_data = self.state.get("workout.current_session")
            if session_data:
                session = WorkoutSession.from_dict(session_data)
                first_desc = session.get_current_exercise_description()
                is_quick = session.is_quick_exercise
                if is_quick:
                    await self._say(
                        f"Quick exercise started! First up: {first_desc}. "
                        f"Tell the user enthusiastically that you're ready to go — get them going for the first set ",
                        restore=False,
                    )
                else:
                    workout_name = session_data.get("workout_name", "today's workout")
                    await self._say(
                        f"Workout started! Today's workout: {workout_name}. "
                        f"First exercise: {first_desc}. Inform the user enthusiastically "
                        f"and let them know you're tracking their form",
                        restore=False,
                    )
            else:
                await self._say(
                    f"Workout mode is starting. Psych the user up and get them ready to workout!",
                    restore=False,
                )

            # Signal main.py that greeting is done — safe to start pose estimation
            self.state.set("workout.greeting_done", True)
            self.state.save_state()
            logger.info("[WORKOUT] Greeting done — signalled main.py to start pose estimation")

            # Now start wake word system AFTER greeting has fully played out
            await self._start_wake_word_system()

    # ===== COACHING SERVICE CALLBACKS =====

    async def _on_workout_complete_signal(self, data: dict):
        """Called by CoachingService when the entire workout is done."""
        logger.info("[COACHING] Workout complete signal received — scheduling cleanup")
        asyncio.create_task(self._handle_workout_complete())

    async def _on_calibration_complete(self):
        """Called by CoachingService after calibration finishes.
        Activate wake word system so agent suppresses auto-responses during workout.
        """
        logger.info("[CALIBRATION] Calibration complete — starting wake word system")
        await self._start_wake_word_system()

    async def _handle_workout_complete(self):
        """Run cleanup and agent handoff outside the orchestrator's task."""
        await self._cleanup_workout()
        # Brief pause to let the LLM finish processing pending conversation
        # events from the exercise recap before truncation.
        await asyncio.sleep(0.5)
        await self._truncate_context_for_handoff()
        from agent.agents.main_menu_agent import MainMenuAgent
        new_agent = MainMenuAgent(state=self.state, userdata=self.userdata)
        self.session.update_agent(new_agent)

    async def _cleanup_workout(self):
        """Shared cleanup for ending a workout (DB logging, state clearing)."""
        from db.schedule_utils import mark_workout_completed
        from db.progress_utils import log_completed_set
        from agent.core.workout_session import WorkoutSession

        session_data = self.state.get("workout.current_session")
        if session_data:
            try:
                session = WorkoutSession.from_dict(session_data)
                session.end_session()

                if not session.is_quick_exercise:
                    db = SessionLocal()
                    try:
                        for set_data in session.get_completed_sets_for_logging():
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
                                logger.info(f"[WORKOUT] Logged set {set_data['set_id']}")

                        mark_workout_completed(db, session.schedule_id)
                        logger.info(f"[WORKOUT] Marked schedule {session.schedule_id} as completed")
                    except Exception:
                        logger.exception("[WORKOUT ERROR] Failed to save workout data")
                    finally:
                        db.close()
                else:
                    logger.info("[QUICK EXERCISE] Skipping DB logging for ad-hoc session")

            except Exception:
                logger.exception("[WORKOUT ERROR] Failed to process session")

        # Clear workout session, quick exercise, and calibration state
        self.state.set("workout.current_session", None)
        self.state.set("workout.exercise_name", None)
        self.state.set("workout.calibration_profile", None)
        self.state.set("quick_exercise.exercise_name", None)
        self.state.set("quick_exercise.gathering_params", False)
        self.state.set("calibration.active", None)
        self.state.set("calibration.movement_pattern", None)
        self.state.set("calibration.pending_workout", None)
        self.state.set("workout.greeting_done", False)

        await self._stop_wake_word_system()

        if self.userdata.coaching_service:
            await self.userdata.coaching_service.stop()
            self.userdata.coaching_service = None

        self.state.switch_mode("main_menu")
        self.state.set("workout.active", False)
        self.state.save_state()

        logger.info("[STATE] Workout cleanup complete — switched to main_menu")

    # ===== WAKE WORD SYSTEM =====

    def _set_workout_turn_detection(self):
        """Workout mode: disable auto-responses, only respond to wake word."""
        try:
            self.session.input.set_audio_enabled(False)
            logger.info("[WAKE WORD] Turn detection disabled (workout mode)")
        except Exception as e:
            logger.error(f"[WAKE WORD] FAILED to set workout turn detection: {e}", exc_info=True)

    def _set_conversational_turn_detection(self):
        """Restore normal conversational turn detection."""
        try:
            self.session.input.set_audio_enabled(True)
            logger.info("[WAKE WORD] Turn detection restored (conversational mode)")
        except Exception as e:
            logger.error(f"[WAKE WORD] FAILED to set conversational turn detection: {e}", exc_info=True)

    def _set_active_listening_turn_detection(self):
        """Temporarily enable responses after wake word detection."""
        try:
            self.session.input.set_audio_enabled(True)
            logger.info("[WAKE WORD] Turn detection enabled (active listening)")
        except Exception as e:
            logger.error(f"[WAKE WORD] FAILED to set active listening turn detection: {e}", exc_info=True)

    def _on_user_transcription_for_wake_word(self, ev):
        """Handle user transcriptions during workout mode for wake word detection."""
        logger.info(
            f"[WAKE WORD] Transcription event: is_final={ev.is_final} "
            f"active={self._wake_word_active} listening={self._wake_word_listening} "
            f"transcript='{getattr(ev, 'transcript', '')[:50]}'"
        )

        if not self._wake_word_active or self._wake_word_listening:
            logger.info(f"[WAKE WORD] Skipping (active={self._wake_word_active}, listening={self._wake_word_listening})")
            return

        if not ev.is_final:
            return

        transcript = ev.transcript.lower().strip()
        if not transcript:
            return

        wake_word_detected = any(phrase in transcript for phrase in self._wake_word_phrases)

        if wake_word_detected:
            logger.info(f"[WAKE WORD] ★ DETECTED in: '{transcript}'")
            asyncio.create_task(self._activate_listening_mode(transcript))
        else:
            logger.info(f"[WAKE WORD] No wake word in: '{transcript}'")

    def _on_speech_created_for_wake_word(self, ev):
        """Cancel auto-generated responses in workout mode.
        Allows coaching LLM speech and programmatic calls through.
        """
        logger.info(
            f"[WAKE WORD] speech_created event: user_initiated={ev.user_initiated} "
            f"source={getattr(ev, 'source', 'unknown')} "
            f"active={self._wake_word_active} listening={self._wake_word_listening}"
        )

        if not self._wake_word_active or self._wake_word_listening:
            logger.info("[WAKE WORD] Allowing speech (wake word inactive or in listening mode)")
            return

        # Never cancel speech from the coaching service
        coaching = self.userdata.coaching_service
        if coaching and coaching.is_coaching_speaking:
            logger.info("[WAKE WORD] Allowing speech (coaching LLM in progress)")
            return

        if not ev.user_initiated:
            try:
                ev.speech_handle.cancel()
                logger.info("[WAKE WORD] ✗ CANCELLED auto-response (user_initiated=False)")
            except Exception as e:
                logger.error(f"[WAKE WORD] Failed to cancel speech: {e}", exc_info=True)
        else:
            logger.info("[WAKE WORD] Allowing speech through (user_initiated=True — programmatic call)")

    async def _activate_listening_mode(self, trigger_transcript: str):
        """Activate listening mode after wake word detection."""
        coaching = self.userdata.coaching_service
        if coaching and coaching.is_coaching_speaking:
            logger.info("[WAKE WORD] Coaching LLM in progress — deferring wake word response")
            return

        logger.info(f"[WAKE WORD] Activating listening mode (trigger: '{trigger_transcript}')")
        self._wake_word_listening = True
        self._set_active_listening_turn_detection()

        # Extract command after the wake word (if any)
        command_after_wake = ""
        for phrase in self._wake_word_phrases:
            if phrase in trigger_transcript.lower():
                idx = trigger_transcript.lower().index(phrase) + len(phrase)
                command_after_wake = trigger_transcript[idx:].strip(" ,.")
                break

        if command_after_wake and len(command_after_wake) > 3:
            logger.info(f"[WAKE WORD] Command included: '{command_after_wake}'")
            await self.session.generate_reply(
                user_input=command_after_wake,
            )
        else:
            await self.session.generate_reply(
                instructions="The user just said 'Hey Nova' during a workout. Respond very briefly (2-5 words max) like 'Yeah?', 'What's up?', or 'I'm here!' — then wait for their question."
            )

        # Start timeout to revert back to wake word mode
        if self._wake_word_timeout_task:
            self._wake_word_timeout_task.cancel()
        self._wake_word_timeout_task = asyncio.create_task(self._wake_word_timeout())

    async def _deactivate_listening_mode(self):
        """Revert from active listening back to wake word detection mode."""
        logger.info("[WAKE WORD] Deactivating listening mode → back to wake word detection")
        self._wake_word_listening = False
        if self._wake_word_timeout_task:
            self._wake_word_timeout_task.cancel()
            self._wake_word_timeout_task = None
        self._set_workout_turn_detection()
        logger.info("[WAKE WORD] Reverted to wake word mode")

    async def _wake_word_timeout(self):
        """After inactivity, revert back to workout (wake word) mode."""
        try:
            await asyncio.sleep(self._wake_word_timeout_seconds)
            if self._wake_word_active and self._wake_word_listening:
                logger.info("[WAKE WORD] Timeout — reverting to wake word mode")
                await self._deactivate_listening_mode()
        except asyncio.CancelledError:
            pass

    def _on_agent_state_changed_for_wake_word(self, ev):
        """Auto-revert after wake-word-triggered responses complete."""
        if not self._wake_word_active or not self._wake_word_listening:
            return

        if ev.new_state in ("listening", "idle") and ev.old_state == "speaking":
            if self._wake_word_timeout_task:
                self._wake_word_timeout_task.cancel()
            self._wake_word_timeout_task = asyncio.create_task(self._wake_word_timeout())

    async def _start_wake_word_system(self):
        """Activate wake word detection for workout mode."""
        logger.info("[WAKE WORD] === Starting wake word system ===")
        self._wake_word_active = True
        self._wake_word_listening = False

        try:
            self.session.on("user_input_transcribed", self._on_user_transcription_for_wake_word)
            logger.info("[WAKE WORD] Registered user_input_transcribed handler")
        except Exception as e:
            logger.error(f"[WAKE WORD] FAILED to register user_input_transcribed: {e}", exc_info=True)

        try:
            self.session.on("agent_state_changed", self._on_agent_state_changed_for_wake_word)
            logger.info("[WAKE WORD] Registered agent_state_changed handler")
        except Exception as e:
            logger.error(f"[WAKE WORD] FAILED to register agent_state_changed: {e}", exc_info=True)

        try:
            self.session.on("speech_created", self._on_speech_created_for_wake_word)
            logger.info("[WAKE WORD] Registered speech_created handler")
        except Exception as e:
            logger.error(f"[WAKE WORD] FAILED to register speech_created: {e}", exc_info=True)

        # Disable preemptive_generation
        try:
            self.session.options.preemptive_generation = False
            logger.info("[WAKE WORD] Disabled preemptive_generation on AgentSession")
        except Exception as e:
            logger.error(f"[WAKE WORD] Failed to disable preemptive_generation: {e}")

        self._set_workout_turn_detection()
        logger.info("[WAKE WORD] === Wake word system ACTIVE ===")

    async def _stop_wake_word_system(self):
        """Deactivate wake word detection when leaving workout mode."""
        self._wake_word_active = False
        self._wake_word_listening = False

        if self._wake_word_timeout_task:
            self._wake_word_timeout_task.cancel()
            self._wake_word_timeout_task = None

        try:
            self.session.off("user_input_transcribed", self._on_user_transcription_for_wake_word)
            self.session.off("agent_state_changed", self._on_agent_state_changed_for_wake_word)
            self.session.off("speech_created", self._on_speech_created_for_wake_word)
        except Exception:
            pass

        # Re-enable preemptive_generation for conversational mode
        try:
            self.session.options.preemptive_generation = True
            logger.info("[WAKE WORD] Re-enabled preemptive_generation")
        except Exception as e:
            logger.error(f"[WAKE WORD] Failed to re-enable preemptive_generation: {e}")

        self._set_conversational_turn_detection()
        logger.info("[WAKE WORD] System deactivated")

    # ===== WORKOUT FUNCTION TOOLS =====

    @function_tool
    async def end_workout(self, context: RunContext):
        """
        Call this when the user wants to end/stop their workout.
        User might say: "stop workout", "I'm done", "end session", "finish"
        """
        logger.info("[WORKOUT] User requested to end workout")
        await self._cleanup_workout()

        # Handoff to MainMenuAgent
        await self._suppress_turn_detection()
        await self._truncate_context_for_handoff()
        from agent.agents.main_menu_agent import MainMenuAgent
        return MainMenuAgent(state=self.state, userdata=self.userdata)

    @function_tool
    async def end_set_early(self, reps_completed: int, context: RunContext = None):
        """
        Call this when the user wants to stop the current set before the target reps.
        User might say: "I'm done, that was 5", "stop, I got 3", "rack it".
        Do NOT call this when sets complete normally — the coaching system handles that automatically.

        Args:
            reps_completed: Number of reps the user completed before stopping
        """
        logger.info(f"[WORKOUT] User ending set early: {reps_completed} reps")

        coaching = self.userdata.coaching_service
        if not coaching:
            return None, (
                "Tell the user: 'Got it, set logged.' Keep it brief."
            )

        # Check if the orchestrator already auto-completed this set
        if coaching.is_resting:
            return None, (
                "The set was already tracked automatically. "
                "Let the user know their set is recorded and to rest up."
            )

        try:
            result = await coaching.force_end_current_set(reps=reps_completed)

            if result["status"] == "advanced":
                rest_sec = result.get("rest_seconds", 60)
                next_desc = result.get("next_set_description", "the next set")
                rest_display = f"{rest_sec // 60}:{rest_sec % 60:02d}" if rest_sec >= 60 else f"{rest_sec} seconds"
                return None, (
                    f"Tell the user: 'Got it — {reps_completed} reps, set logged. "
                    f"Rest for {rest_display}. Next up: {next_desc}.' "
                    f"Keep it brief and encouraging."
                )
            elif result["status"] == "workout_complete":
                return None, (
                    f"Tell the user: 'That's {reps_completed} reps — and that was your last set! "
                    f"Amazing work today.' Be celebratory. Then call end_workout()."
                )
            else:
                return None, (
                    f"Tell the user: 'Got it, {reps_completed} reps logged.' Keep it brief."
                )

        except Exception as e:
            logger.exception("[WORKOUT ERROR] Failed to end set early")
            return None, (
                "Tell the user: 'Got it, set logged. Rest up!' Keep it simple."
            )

    @function_tool
    async def skip_exercise(self, reason: Optional[str] = None, context: RunContext = None):
        """
        Call this when the user wants to skip the current exercise.
        User might say: "skip this", "I can't do this one", "next exercise", "equipment not available"

        Args:
            reason: Optional reason for skipping (e.g., "injury", "no equipment")
        """
        logger.info(f"[WORKOUT] User wants to skip exercise. Reason: {reason}")

        from agent.core.workout_session import WorkoutSession

        session_data = self.state.get("workout.current_session")
        if not session_data:
            return None, "Tell the user: 'No active workout to skip. Let's start a workout first!' Keep it helpful."

        try:
            session = WorkoutSession.from_dict(session_data)

            current_exercise = session.get_current_exercise()
            if not current_exercise:
                return None, "Tell the user: 'You're all done with the workout! No more exercises to skip.' Keep it positive."

            exercise_name = current_exercise.exercise_name

            session.skip_current_exercise(reason=reason)

            self.state.set("workout.current_session", session.to_dict())
            self.state.save_state()

            next_exercise = session.get_current_exercise()
            if next_exercise:
                next_desc = session.get_current_exercise_description()
                return None, f"Tell the user: 'No problem, skipping {exercise_name}. Moving on to {next_desc}' Keep it supportive and matter-of-fact."
            else:
                return None, f"Tell the user: 'Alright, skipped {exercise_name}. That was the last exercise! Great work on what you did today. Ready to wrap up?' Keep it encouraging."

        except Exception as e:
            logger.exception("[WORKOUT ERROR] Failed to skip exercise")
            return None, "Tell the user: 'Okay, let's move on to the next exercise.' Keep it simple."

    @function_tool
    async def get_next_exercise(self, context: RunContext = None):
        """
        Call this when the user asks what's next or wants to preview upcoming exercises.
        User might say: "what's next", "what exercise is coming up", "show me next"
        """
        logger.info("[WORKOUT] User wants to see next exercise")

        from agent.core.workout_session import WorkoutSession

        session_data = self.state.get("workout.current_session")
        if not session_data:
            return None, "Tell the user: 'No active workout. Start a workout to see your exercises!' Keep it helpful."

        try:
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
            logger.exception("[WORKOUT ERROR] Failed to get next exercise")
            return None, "Tell the user: 'Let's focus on this exercise first!' Keep it simple."

    @function_tool
    async def get_workout_progress(self, context: RunContext = None):
        """
        Call this when the user asks about their progress or where they are in the workout.
        User might say: "how much left", "where am I", "progress", "how many sets left"
        """
        logger.info("[WORKOUT] User wants to see workout progress")

        from agent.core.workout_session import WorkoutSession

        session_data = self.state.get("workout.current_session")
        if not session_data:
            return None, "Tell the user: 'No active workout. Start a workout to track your progress!' Keep it helpful."

        try:
            session = WorkoutSession.from_dict(session_data)

            summary = session.get_progress_summary()

            return None, f"Tell the user: 'You're crushing it! You've completed {summary['completed_sets']} out of {summary['total_sets']} sets. That's {summary['percent_complete']}% done. Currently on {summary['current_exercise_name']}.' Keep it motivating and clear."

        except Exception as e:
            logger.exception("[WORKOUT ERROR] Failed to get progress")
            return None, "Tell the user: 'Keep pushing! You're doing great.' Keep it simple and encouraging."
