"""
TeachingAgent — Phase-gated state machine that walks a beginner through
their first reps of a squat before handing off to WorkoutAgent.

Flow:
  INTRO        → speak greeting + setup checklist (LLM)
  AWAITING_STANCE → watch frame_data; once stance_width_ratio sustains
                    above target, greenlight + give descent cues (LLM)
  DESCENDING / ASCENDING → realtime cached cues for live faults; record
                           all faults for end-of-rep evaluation
  REP_COMPLETE → either positive cue + advance or LLM fix feedback
  HANDOFF      → transition speech, swap to WorkoutAgent

Real-time speech is cached cues only. LLM is used for the setup checklist,
greenlight + descent cues, per-rep fault feedback, and handoff.
"""

import asyncio
import logging
import random
from typing import Optional

from agents.shared.base_agent import BaseNovaAgent
from agents.teaching_phases import TeachingPhase
from services.teaching_cues import SQUAT_TEACHING_CUES, CLEAN_REP_CUE_KEYS

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Tunables
# ----------------------------------------------------------------------

STANCE_TARGET_RATIO = 1.5      # ankle/shoulder ratio to greenlight descent
STANCE_WIDE_THRESHOLD = 1.9    # above = "very wide" → suggest more toe-out
TOE_OUT_LOW_DEG = 8.0          # below = "toes parallel"
TOE_OUT_HIGH_DEG = 20.0        # above = "toes pointed out a lot"
STANCE_DEBOUNCE_FRAMES = 5     # frames in a row above target before advancing
TARGET_CLEAN_REPS = 2          # consecutive clean reps required before handoff


# Persona prefix for all teaching LLM instructions.
_TEACHING_PERSONA = (
    "You are Nova, an energetic, world-class fitness coach on the Nowva smart squat rack. "
    "You are currently teaching a beginner how to perform the exercise correctly. "
    "Be warm, direct, and encouraging — like a real coach, not a manual. "
    "SHORT responses only — follow the word limits given. No emojis."
)


def _get_teaching_prompt(exercise: str) -> str:
    return (
        f"You are Nova, an AI strength coach on the Nowva smart squat rack. "
        f"You are teaching a beginner the basics of the {exercise}. "
        f"Be brief, warm, and clear. Sound like a real coach, not a chatbot."
    )


def _trunk_flexion_fix(stance: float, toe_out: float) -> str:
    """Pick the right cue for a forward-lean fault based on the user's
    current stance ratio and average toe-out angle."""
    narrow = stance < STANCE_TARGET_RATIO
    wide = stance >= STANCE_WIDE_THRESHOLD
    toes_in = toe_out < TOE_OUT_LOW_DEG
    toes_out = toe_out >= TOE_OUT_HIGH_DEG

    if narrow and toes_in:
        return "widen your stance and turn your toes out a touch"
    if narrow and toes_out:
        return "your toes are already pointed out — try widening your stance instead"
    if wide and toes_in:
        return "you have plenty of width — try turning your toes out a bit more"
    if wide and toes_out:
        return (
            "stance and toe-out look fine — focus on driving knees out and "
            "bracing harder before going down"
        )
    # Middle ground.
    return (
        "try widening your stance a touch"
        if stance < 1.7
        else "try turning your toes out slightly more"
    )


class TeachingAgent(BaseNovaAgent):
    """Walks a beginner through their first reps of a squat, then hands off
    to WorkoutAgent once they nail TARGET_CLEAN_REPS in a row."""

    def __init__(self, state, userdata, exercise: str = "squat") -> None:
        self.exercise = exercise
        self.phase: TeachingPhase = TeachingPhase.INTRO
        self._consecutive_correct_reps: int = 0
        self._current_rep_faults: list[str] = []

        # Live frame_data cache (populated by on_biomechanics_event).
        self._last_stance_ratio: float = 0.0
        self._last_toe_out_avg: float = 0.0
        self._stance_ok_streak: int = 0

        # Optional: per-user calibration (loaded on enter; informational only for v1).
        self._calibration: Optional[dict] = None

        # Lock to prevent concurrent rep_complete handlers stepping on each other.
        self._rep_lock = asyncio.Lock()

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
        # Cache movement cues for instant playback.
        audio_svc = self.userdata.audio_cue_service
        if audio_svc:
            await audio_svc.cache_cues(SQUAT_TEACHING_CUES)

        # Load calibration if available (v1: informational).
        self._load_calibration()

        # Spin up a teaching-mode CoachingService that forwards biomechanics
        # IPC events to this agent's on_biomechanics_event.
        await self._start_teaching_coaching_service()

        # Intro line (LLM).
        await self._say(
            "Say something natural and brief — like you're about to walk the user "
            "through the basics of the squat. Think \"alright, let's go through "
            "the basic squat checklist\" energy. One sentence, no filler, no emojis."
        )

        # Setup checklist (LLM). After this, transition to AWAITING_STANCE.
        await self._run_setup_checklist()

    def _load_calibration(self) -> None:
        try:
            from db.database import SessionLocal
            from db.calibration_utils import get_user_calibration_full
            user_id = self.state.get("user.id")
            if user_id is None:
                return
            db = SessionLocal()
            try:
                self._calibration = get_user_calibration_full(db, user_id, "squat")
                if self._calibration:
                    logger.info(
                        f"[TEACHING] Loaded calibration for user={user_id}: "
                        f"reps={self._calibration.get('calibration_reps')}"
                    )
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[TEACHING] Calibration load failed (non-fatal): {e}")

    async def _start_teaching_coaching_service(self) -> None:
        from services.coaching_service import CoachingService
        coaching = CoachingService(
            session=self.session,
            state=self.state,
            room=getattr(self.userdata, "room", None),
            audio_cue_service=self.userdata.audio_cue_service,
            mode="teaching",
            teaching_agent=self,
        )
        await coaching.start()
        self.userdata.coaching_service = coaching

    # ------------------------------------------------------------------
    # SETUP — checklist + stance gate
    # ------------------------------------------------------------------

    async def _run_setup_checklist(self):
        """Speak the setup checklist (LLM), then enter AWAITING_STANCE."""
        instruction = (
            f"[CONTEXT] exercise={self.exercise}\n\n"
            "Walk the user through the starting position for the squat. Cover "
            "in this order, naturally: "
            "(1) Feet slightly wider than shoulder width, toes pointed out slightly. "
            "Tell them to find what feels comfortable. "
            "(2) Keep gaze forward throughout. "
            "(3) Take a big breath, brace the core. "
            "End by telling them to settle into their stance — say you'll "
            "greenlight them when their feet are in a good spot. Sound like a "
            "real coach, not a manual. Do NOT number the points. Do NOT say "
            "'step one'. Flow as natural speech. At most 4 sentences."
        )
        await self._say(instruction)
        self.phase = TeachingPhase.AWAITING_STANCE
        self._stance_ok_streak = 0
        logger.info("[TEACHING] Setup checklist delivered — phase → AWAITING_STANCE")

    async def _greenlight_descent(self):
        """Acknowledge stance and give descent + ascent cues (LLM)."""
        instruction = (
            f"[CONTEXT] stance_ratio_observed={round(self._last_stance_ratio, 2)}, "
            f"exercise={self.exercise}\n\n"
            "The user just settled into a good stance. Acknowledge it briefly, "
            "then give them the descent and ascent cues: squat straight down "
            "with hands in front of the chest; maintain as straight a back as "
            "possible; think about going straight down and sitting between the "
            "legs; control the descent, brief pause at the bottom, stand back "
            "up to finish; whenever they're ready, go. Brief and warm. No "
            "numbered list. At most 3 sentences total."
        )
        await self._say(instruction)
        self.phase = TeachingPhase.DESCENDING
        self._current_rep_faults = []
        logger.info("[TEACHING] Stance OK — phase → DESCENDING")

    # ------------------------------------------------------------------
    # Biomechanics event dispatch
    # ------------------------------------------------------------------

    async def on_biomechanics_event(self, event: dict):
        """Main entry point for every biomechanics IPC message routed to us
        by the teaching-mode CoachingService."""
        msg_type = event.get("type", "")

        if msg_type == "frame_data":
            await self._on_frame_data(event)
        elif msg_type == "fault":
            await self._on_fault(event)
        elif msg_type == "rep_complete":
            await self._on_rep_complete(event)
        # All other types (set_complete, rest_*, calibration_*) ignored.

    async def _on_frame_data(self, event: dict):
        ja = event.get("joint_angles") or {}
        self._last_stance_ratio = float(ja.get("stance_width_ratio", 0.0) or 0.0)
        toe_l = float(ja.get("toe_out_angle_l", 0.0) or 0.0)
        toe_r = float(ja.get("toe_out_angle_r", 0.0) or 0.0)
        self._last_toe_out_avg = (toe_l + toe_r) / 2.0

        if self.phase != TeachingPhase.AWAITING_STANCE:
            return

        if self._last_stance_ratio >= STANCE_TARGET_RATIO:
            self._stance_ok_streak += 1
        else:
            self._stance_ok_streak = 0

        if self._stance_ok_streak >= STANCE_DEBOUNCE_FRAMES:
            # Move to a transitional phase before awaiting LLM playout to
            # avoid double-firing if more frames stream in during speech.
            self.phase = TeachingPhase.REP_COMPLETE  # placeholder; gets overwritten
            await self._greenlight_descent()

    async def _on_fault(self, event: dict):
        if self.phase not in (TeachingPhase.DESCENDING, TeachingPhase.ASCENDING):
            return

        fault_type = event.get("fault_type", "")
        if not fault_type or fault_type in self._current_rep_faults:
            return

        self._current_rep_faults.append(fault_type)
        logger.info(f"[TEACHING] Fault recorded: {fault_type}")

        # Realtime cached cues only for the two cues we have audio for.
        if fault_type == "knee_valgus":
            await self._play_teaching_cue("knees_out")
        elif fault_type == "forward_lean":
            await self._play_teaching_cue("chest_up")
        # tempo_*, heel_rise, bilateral_asymmetry → silent until rep close.

    async def _on_rep_complete(self, event: dict):
        # Lock to keep evaluation atomic; multiple events may arrive close
        # together if the pipeline is bursty.
        async with self._rep_lock:
            await self._complete_rep(event)

    # ------------------------------------------------------------------
    # Rep evaluation
    # ------------------------------------------------------------------

    async def _complete_rep(self, event: dict):
        """Evaluate the rep, give feedback, loop or hand off."""
        # Merge realtime fault tags with the authoritative server-side list.
        server_faults = list(event.get("faults_in_rep", []) or [])
        seen = set()
        faults: list[str] = []
        for f in self._current_rep_faults + server_faults:
            if f and f not in seen:
                seen.add(f)
                faults.append(f)

        is_clean = bool(event.get("is_clean", False)) and not faults
        self._current_rep_faults = []

        if is_clean:
            self._consecutive_correct_reps += 1
            logger.info(
                f"[TEACHING] Clean rep — streak "
                f"{self._consecutive_correct_reps}/{TARGET_CLEAN_REPS}"
            )
            if self._consecutive_correct_reps >= TARGET_CLEAN_REPS:
                await self._handoff()
                return
            await self._play_teaching_cue(random.choice(CLEAN_REP_CUE_KEYS))
        else:
            self._consecutive_correct_reps = 0
            logger.info(f"[TEACHING] Fault rep — faults: {faults}")
            await self._speak_fault_feedback(faults, event)

        # Re-open descent only after speech has resolved.
        self.phase = TeachingPhase.DESCENDING

    async def _speak_fault_feedback(self, faults: list[str], event: dict):
        """LLM delivers per-fault fix from a precomputed mapping."""
        stance = round(self._last_stance_ratio, 2)
        toe_out = round(self._last_toe_out_avg, 1)
        peak_d = int(round(event.get("peak_descent_velocity_cm_s", 0.0) or 0.0))
        peak_a = int(round(event.get("peak_ascent_velocity_cm_s", 0.0) or 0.0))

        forward_lean_fix = _trunk_flexion_fix(stance, toe_out)

        instruction = (
            "[CONTEXT]\n"
            f"exercise={self.exercise}\n"
            f"faults={faults}\n"
            f"stance_ratio={stance}\n"
            f"toe_out_avg_deg={toe_out}\n"
            f"peak_descent_velocity_cm_s={peak_d}\n"
            f"peak_ascent_velocity_cm_s={peak_a}\n\n"
            "[FIX MAPPING — deliver each applicable line conversationally; "
            "skip lines whose fault is not in the faults list]\n"
            f"- forward_lean: {forward_lean_fix}\n"
            "- knee_valgus: your knees should track right over your toes — "
            "push them out as you go down\n"
            "- tempo_uncontrolled: control the way down — slow the descent\n"
            "- tempo_stalled: don't pause too long at the bottom — drive up sooner\n"
            "- tempo_grind: drive up faster out of the bottom — full intent on the way up\n"
            "- heel_rise: keep your heels planted the whole way down\n"
            "- bilateral_asymmetry: try to load both legs evenly — push through "
            "both feet equally\n\n"
            "End with: \"take a breath, and try that one again.\" Do NOT repeat "
            "the realtime cues (knees out, chest up — those already fired during "
            "the rep). One sentence per fault max. At most 3 sentences total. "
            "No emojis. No numbered list."
        )
        await self._say(instruction)

    # ------------------------------------------------------------------
    # Handoff
    # ------------------------------------------------------------------

    async def _handoff(self):
        """Congratulate the user and hot-swap to WorkoutAgent."""
        self.phase = TeachingPhase.HANDOFF
        logger.info("[TEACHING] Target reached — handing off to WorkoutAgent")

        instruction = (
            f"[CONTEXT] exercise={self.exercise}, "
            f"clean_reps_completed={self._consecutive_correct_reps}\n\n"
            f"The user has just completed {TARGET_CLEAN_REPS} clean squat reps "
            "in a row. Tell them they've got the movement pattern down. Keep "
            "it genuine and brief — like a coach who's actually pleased, not a "
            "chatbot congratulating them. Naturally transition them into their "
            "workout. At most 2 sentences."
        )
        await self._say(instruction)

        # Stop the teaching CoachingService so WorkoutAgent.on_enter can spin
        # up its own workout-mode service cleanly.
        coaching = self.userdata.coaching_service
        if coaching is not None:
            try:
                await coaching.stop()
            except Exception as e:
                logger.warning(f"[TEACHING] CoachingService.stop failed: {e}")
            self.userdata.coaching_service = None

        await self._truncate_context_for_handoff()
        from agents.workout_agent import WorkoutAgent
        new_agent = WorkoutAgent(state=self.state, userdata=self.userdata)
        self.session.update_agent(new_agent)

    # ------------------------------------------------------------------
    # Audio helpers
    # ------------------------------------------------------------------

    async def _play_teaching_cue(self, cue_key: str):
        audio_svc = self.userdata.audio_cue_service
        if audio_svc:
            await audio_svc.play_cue(cue_key)
        else:
            logger.warning(f"[TEACHING] No audio_cue_service — cannot play: {cue_key}")
