"""
TeachingAgent — Phase-gated state machine that walks a beginner through
their first reps of a given exercise before handing off to WorkoutAgent.

Currently supports: barbell back squat.

Flow:
  SETUP -> DESCENDING <-> ASCENDING -> REP_COMPLETE -> (loop or HANDOFF)

All speech during active movement phases uses pre-cached audio cues only.
LLM-generated speech is used for setup instructions, fault feedback between
reps, and the handoff transition.
"""

import logging
import random
from typing import Optional

from agents.shared.base_agent import BaseNovaAgent
from agents.teaching_phases import TeachingPhase
from biomechanics.utils.types import RepPhase
from services.teaching_cues import SQUAT_TEACHING_CUES, CLEAN_REP_CUE_KEYS

logger = logging.getLogger(__name__)

# Persona prefix for all teaching LLM instructions.
_TEACHING_PERSONA = (
    "You are Nova, an energetic, world-class fitness coach on the Nowva smart squat rack. "
    "You are currently teaching a beginner how to perform the exercise correctly. "
    "Be warm, direct, and encouraging — like a real coach, not a manual. "
    "SHORT responses only — follow the word limits given. No emojis."
)

# Height threshold (cm) for wider stance suggestion.
_TALL_THRESHOLD_CM = 185


def _get_teaching_prompt(exercise: str) -> str:
    """Return the base system prompt for the teaching agent."""
    return (
        f"You are Nova, an AI strength coach on the Nowva smart squat rack. "
        f"You are teaching a beginner the basics of the {exercise}. "
        f"Be brief, warm, and clear. Sound like a real coach, not a chatbot."
    )


class TeachingAgent(BaseNovaAgent):
    """Walks a beginner through their first reps of an exercise, then
    hands off to WorkoutAgent once they demonstrate the movement pattern."""

    def __init__(self, state, userdata, exercise: str = "squat") -> None:
        self.exercise = exercise
        self.phase = TeachingPhase.SETUP
        self.consecutive_correct_reps = 0
        self.target_reps = 4
        self.current_rep_faults: list[str] = []

        # Determine height from user profile in state.
        user = state.get_user() or {}
        height = user.get("height_cm")
        self.user_is_tall: bool = (
            float(height) >= _TALL_THRESHOLD_CM if height is not None else False
        )

        super().__init__(
            state=state,
            userdata=userdata,
            instructions=_get_teaching_prompt(exercise),
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def on_enter(self):
        """Called when AgentSession hot-swaps to TeachingAgent."""
        # Ensure teaching cues are cached for instant playback.
        audio_svc = self.userdata.audio_cue_service
        if audio_svc:
            await audio_svc.cache_cues(SQUAT_TEACHING_CUES)

        # LLM generates a natural intro line.
        await self._say(
            f"You are Nova, an AI strength coach. Say something natural "
            f"and brief — like you're about to walk the user through the "
            f"basics of the {self.exercise}. Think 'alright, let's go "
            f"through the basic squat checklist' energy. One sentence, "
            f"no filler, no emojis."
        )
        await self._run_setup()

    # ------------------------------------------------------------------
    # SETUP phase
    # ------------------------------------------------------------------

    async def _run_setup(self):
        """Deliver foot-position, eyes-forward, and bracing cues as a
        single flowing LLM turn, then open the DESCENDING phase."""
        context_block = (
            f"[CONTEXT] exercise={self.exercise}, is_tall={self.user_is_tall}\n\n"
        )
        instruction = (
            context_block
            + "Walk the user through the starting position for the squat. "
            "Cover in this order, naturally: "
            "(1) Feet shoulder-width apart, toes slightly out. "
            "If is_tall is true, mention they can go a touch wider "
            "if it feels more comfortable — keep this casual, not prescriptive. "
            "(2) Keep gaze forward throughout. "
            "(3) Take a big breath, brace the core, squat down when ready. "
            "Sound like a real coach, not a manual. Brief, warm, clear. "
            "Do not number the points. Do not say 'step one'. "
            "This should flow as natural speech."
        )
        await self._say(instruction)
        self.phase = TeachingPhase.DESCENDING
        logger.info("[TEACHING] Setup complete — phase → DESCENDING")

    # ------------------------------------------------------------------
    # Biomechanics event handling
    # ------------------------------------------------------------------

    async def on_biomechanics_event(self, event: dict):
        """Main event handler called by the coaching bridge on each
        relevant biomechanics message.

        Routes by current phase — only DESCENDING and ASCENDING process
        incoming events; all other phases silently ignore them.

        Expected event keys:
          - squat_phase: str  (one of RepPhase values)
          - knee_fault: bool
          - chest_fault: bool
        """
        if self.phase == TeachingPhase.DESCENDING:
            await self._handle_descent(event)
        elif self.phase == TeachingPhase.ASCENDING:
            await self._handle_ascent(event)
        # All other phases: ignore incoming events.

    # ------------------------------------------------------------------
    # DESCENDING phase
    # ------------------------------------------------------------------

    async def _handle_descent(self, event: dict):
        """Process biomechanics during the eccentric (descent) phase.

        Only pre-cached cues fire here — no LLM during movement.
        """
        knee_fault = event.get("knee_fault", False)
        chest_fault = event.get("chest_fault", False)
        squat_phase = event.get("squat_phase", "")

        if knee_fault and "knee" not in self.current_rep_faults:
            self.current_rep_faults.append("knee")
            await self._play_teaching_cue("knees_out")

        if chest_fault and "chest" not in self.current_rep_faults:
            self.current_rep_faults.append("chest")
            await self._play_teaching_cue("chest_up")

        if squat_phase == RepPhase.BOTTOM or squat_phase == RepPhase.BOTTOM.value:
            self.phase = TeachingPhase.ASCENDING
            await self._play_teaching_cue("up")
            logger.info("[TEACHING] Bottom detected — phase → ASCENDING")

    # ------------------------------------------------------------------
    # ASCENDING phase
    # ------------------------------------------------------------------

    async def _handle_ascent(self, event: dict):
        """Process biomechanics during the concentric (ascent) phase.

        Uses separate fault keys so ascent faults are tracked independently
        from descent faults within the same rep.
        """
        knee_fault = event.get("knee_fault", False)
        chest_fault = event.get("chest_fault", False)
        squat_phase = event.get("squat_phase", "")

        if knee_fault and "knee_ascent" not in self.current_rep_faults:
            self.current_rep_faults.append("knee_ascent")
            await self._play_teaching_cue("knees_out")

        if chest_fault and "chest_ascent" not in self.current_rep_faults:
            self.current_rep_faults.append("chest_ascent")
            await self._play_teaching_cue("chest_up")

        if squat_phase == RepPhase.STANDING or squat_phase == RepPhase.STANDING.value:
            self.phase = TeachingPhase.REP_COMPLETE
            logger.info("[TEACHING] Standing detected — phase → REP_COMPLETE")
            await self._complete_rep()

    # ------------------------------------------------------------------
    # REP_COMPLETE — core branching logic
    # ------------------------------------------------------------------

    async def _complete_rep(self):
        """Evaluate the rep, give feedback, and either loop or hand off.

        IMPORTANT: phase is set back to DESCENDING only AFTER all awaited
        speech resolves, preventing biomechanics events from re-entering
        the descent handler while Nova is still speaking.
        """
        faults = self.current_rep_faults.copy()
        self.current_rep_faults = []

        if not faults:
            # Clean rep
            self.consecutive_correct_reps += 1
            logger.info(
                f"[TEACHING] Clean rep — streak {self.consecutive_correct_reps}/{self.target_reps}"
            )

            if self.consecutive_correct_reps >= self.target_reps:
                await self._handoff()
                return

            await self._play_teaching_cue(random.choice(CLEAN_REP_CUE_KEYS))
        else:
            # Fault rep — reset streak
            self.consecutive_correct_reps = 0
            logger.info(f"[TEACHING] Fault rep — faults: {faults}")

            context_block = (
                f"[CONTEXT] faults={faults}, exercise={self.exercise}\n\n"
            )
            instruction = (
                context_block
                + "The user just completed a squat rep but had form faults. "
                "The faults list contains one or more of: "
                "'knee' (knees caved on descent), "
                "'knee_ascent' (knees caved on ascent), "
                "'chest' (chest dropped on descent), "
                "'chest_ascent' (chest dropped on ascent). "
                "Briefly address what needs fixing. One sentence per fault max. "
                "Be direct but encouraging — like a good coach, not a critic. "
                "End by telling them to take a breath and try again. "
                "Do not repeat the cues that were already fired during the rep "
                "(knees out, chest up were already said in real time). "
                "Give the why or the fix, not just the repeat command."
            )
            await self._say(instruction)

        # Re-open descent only after all speech resolves.
        self.phase = TeachingPhase.DESCENDING
        logger.info("[TEACHING] Phase → DESCENDING (ready for next rep)")

    # ------------------------------------------------------------------
    # HANDOFF to WorkoutAgent
    # ------------------------------------------------------------------

    async def _handoff(self):
        """Congratulate the user and hot-swap to WorkoutAgent."""
        self.phase = TeachingPhase.HANDOFF
        logger.info("[TEACHING] Target reached — handing off to WorkoutAgent")

        context_block = f"[CONTEXT] exercise={self.exercise}\n\n"
        instruction = (
            context_block
            + "The user has just completed 4 clean squat reps in a row. "
            "Tell them they've got the movement pattern down. "
            "Keep it genuine and brief — like a coach who's actually "
            "pleased, not a chatbot congratulating them. "
            "Naturally transition them into their workout. "
            "One or two sentences max."
        )
        await self._say(instruction)

        await self._truncate_context_for_handoff()
        from agents.workout_agent import WorkoutAgent
        new_agent = WorkoutAgent(state=self.state, userdata=self.userdata)
        self.session.update_agent(new_agent)

    # ------------------------------------------------------------------
    # Audio helpers
    # ------------------------------------------------------------------

    async def _play_teaching_cue(self, cue_key: str):
        """Play a pre-cached teaching cue through the AudioCueService."""
        audio_svc = self.userdata.audio_cue_service
        if audio_svc:
            await audio_svc.play_cue(cue_key)
        else:
            logger.warning(
                f"[TEACHING] No audio_cue_service — cannot play: {cue_key}"
            )
