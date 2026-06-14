"""
CollectExerciseInfoTask - Collects quick-exercise parameters then hands off to calibration or workout.
"""

import asyncio
import logging

from livekit.agents import function_tool, AgentTask

from agent.agents.shared.helpers import check_calibration, start_calibration_mode

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
                Collect the amount of sets, reps, rest and weight
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
            instructions="Let the user know you only need a few things from them."
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
        from agent.agents.calibration_agent import CalibrationAgent
        from agent.agents.workout_agent import WorkoutAgent
        from agent.core.workout_session import WorkoutSession, ExerciseProgress, SetProgress

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

        set_list = [
            SetProgress(
                set_id=None,
                set_number=i + 1,
                target_reps=reps,
                target_weight=weight,
                intensity_percent=None,
                rpe_target=None,
                rest_seconds=rest_seconds,
                velocity_threshold=None,
            )
            for i in range(sets)
        ]

        exercise = ExerciseProgress(
            workout_exercise_id=None,
            exercise_id=None,
            exercise_name=exercise_name,
            muscle_group=None,
            category="Strength",
            order_number=1,
            notes=None,
            sets=set_list,
        )

        session = WorkoutSession(
            user_id=self.user_id,
            schedule_id=None,
            workout_data={
                "workout_id": None,
                "workout_name": f"Quick {exercise_name}",
                "description": f"Ad-hoc {exercise_name} session",
                "exercises": [],
            },
            is_quick_exercise=True,
        )
        session.exercises = [exercise]

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



