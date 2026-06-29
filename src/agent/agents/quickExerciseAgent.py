"""
CollectExerciseInfoTask - Collects quick-exercise parameters then hands off to calibration or workout.
"""

import asyncio
import logging

from livekit.agents import function_tool, AgentTask

from agent.agents.shared.helpers import check_calibration, start_calibration_mode
from agent.agents.calibration_agent import CalibrationAgent
from agent.agents.workout_agent import WorkoutAgent
from agent.core.workout_session import WorkoutSession


logger = logging.getLogger(__name__)


class CollectExerciseInfoTask(AgentTask):
    def __init__(
        self,
        exercise_name: str,
        user_id: str,
        state,
        userdata,
        chat_ctx=None,
    ):
        super().__init__(
            instructions=("""
                Conversationally collect the amount of sets, reps, rest and weight
                the user wants to use for their quick exercise. 
                Once that is done, call the start_workout tool.
                """
            ),
            chat_ctx=chat_ctx,
        )

        self.user_id = user_id
        self.state = state
        self.userdata = userdata
        self.exercise_name = exercise_name

        self.calibration_task = asyncio.create_task(
            check_calibration(user_id, exercise_name)
        )

    async def on_enter(self):
        await self.session.generate_reply(
            instructions="You are transitionning smoothly from the main menu into collecting the required information for the quick exercise."
        )

    @function_tool
    async def start_workout(
        self,
        sets: int,
        reps: int,
        weight: float = 0.0,
        rest_seconds: int = 120,
    ):
        """
        Call this once the user has provided sets, reps, weight, and rest time.

        Args:
            sets: Number of sets to perform
            reps: Target reps per set
            weight: Weight in lbs. Use 0 for bodyweight exercises.
            rest_seconds: Rest between sets in seconds (default 120)
        """
        exercise_name = self.exercise_name
        logger.info(
            f"[QUICK EXERCISE] Collected: {sets}x{reps}, "
            f"weight={weight}, rest={rest_seconds}s, exercise={exercise_name}"
        )

        calibration_profile = await self.calibration_task

        if calibration_profile:
            self.state.set("workout.calibration_profile", calibration_profile)
            logger.info(f"[CALIBRATION] Found existing calibration for {exercise_name}")
        else:
            start_calibration_mode(self.state, exercise_name, {
                "type": "quick_exercise",
            })
            logger.info(f"[CALIBRATION] No calibration for {exercise_name} — entering calibration mode")

        session = WorkoutSession.create_quick_session(
            user_id=self.user_id,
            exercise_name=exercise_name,
            sets=sets,
            reps=reps,
            weight=weight,
            rest_seconds=rest_seconds,
        )

        self.state.set("workout.current_session", session.to_dict())
        self.state.set("workout.exercise_name", exercise_name)
        self.state.set("workout.active", True)
        self.state.switch_mode("workout")
        self.state.save_state()

        logger.info("[STATE] Switched to workout mode — main.py will detect and start pose estimation")

        if calibration_profile:
            return WorkoutAgent(state=self.state, userdata=self.userdata)
        else:
            return CalibrationAgent(state=self.state, userdata=self.userdata)



