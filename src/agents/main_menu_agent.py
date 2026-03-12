"""
MainMenuAgent - Primary interaction hub with schedule management, workout start, and program creation
"""

import logging
import os
import re
from typing import Optional

from livekit.agents import RunContext
from livekit.agents.llm import function_tool

from agents.prompts import get_main_menu_prompt
from agents.shared.base_agent import BaseNovaAgent
from agents.shared.helpers import normalize_exercise_name, check_calibration, start_calibration_mode
from db.database import SessionLocal
from db.program_utils import has_any_programs

logger = logging.getLogger(__name__)


class MainMenuAgent(BaseNovaAgent):
    """Primary interaction hub: schedule management, workout start, program creation."""

    def __init__(self, state, userdata) -> None:
        name = state.get_user().get("name", "there")
        super().__init__(state=state, userdata=userdata, instructions=get_main_menu_prompt(name))

    async def on_enter(self):
        """Generate main menu greeting."""
        name = self.user_name

        # Check if this is the first time arriving at main menu (from onboarding)
        if self.state.is_first_time_main_menu():
            self.state.mark_main_menu_visited()
            self.state.save_state()
            await self._say(
                f"Welcome {name} to the main menu for the first time! "
                f"Tell them about their options: start a workout, create or update a program, "
                f"check their progress, or update their profile. Keep it friendly and conversational."
            )
        else:
            await self._say(
                f"The user, {name}, is back at the main menu. Welcome them back and tell them "
                f"about their options which are to start a workout, create or update a program, "
                f"check their progress, or update their profile. Keep it friendly and conversational."
            )

    # ===== WORKOUT START TOOLS =====

    @function_tool
    async def start_workout(self, context: RunContext):
        """
        Call this when the user wants to start a workout.
        User might say: "start workout", "let's train", "I'm ready", "begin workout"
        """
        logger.info("[MAIN MENU] User requested to start workout")

        from db.schedule_utils import get_todays_workout
        from core.workout_session import WorkoutSession

        db = SessionLocal()
        try:
            user_id = self.user_id
            name = self.user_name

            workout = get_todays_workout(db, user_id)

            if not workout:
                logger.info("[WORKOUT] No workout scheduled for today")
                return None, f"Tell the user: 'Hey {name}, you don't have a workout scheduled for today. Would you like to check your upcoming schedule or create a new program?' Keep it helpful and supportive."

            # Initialize workout session
            session = WorkoutSession(
                user_id=user_id,
                schedule_id=workout["schedule_id"],
                workout_data=workout
            )

            # Store session in state
            self.state.set("workout.current_session", session.to_dict())

            # Set exercise name for main.py to pass to pose estimation
            first_exercise = session.get_current_exercise()
            exercise_name = first_exercise.exercise_name if first_exercise else "Barbell Back Squat"
            self.state.set("workout.exercise_name", exercise_name)

            # Check calibration for the first exercise
            calibration_profile = await check_calibration(user_id, exercise_name)
            needs_calibration = calibration_profile is None

            if calibration_profile:
                self.state.set("workout.calibration_profile", calibration_profile)
                logger.info(f"[CALIBRATION] Found existing calibration for {exercise_name}")
            else:
                start_calibration_mode(self.state, exercise_name, {
                    "type": "scheduled_workout",
                })
                logger.info(f"[CALIBRATION] No calibration found for {exercise_name} — entering calibration mode")

            self.state.switch_mode("workout")
            self.state.set("workout.active", True)
            self.state.save_state()

            logger.info("[STATE] Switched to workout mode - main.py will detect and start pose estimation")

            self._log_function_call("start_workout", {}, "handoff to WorkoutAgent")

            # Handoff to WorkoutAgent
            self._suppress_turn_detection()
            from agents.workout_agent import WorkoutAgent
            return WorkoutAgent(state=self.state, userdata=self.userdata)

        except Exception as e:
            logger.exception("[WORKOUT ERROR] Failed to load workout")
            result = (None, f"Tell the user: 'Hmm, I'm having trouble loading your workout right now. Let's try again in a moment.' Keep it reassuring.")
            self._log_function_call("start_workout", {}, result)
            return result
        finally:
            db.close()

    @function_tool
    async def start_quick_exercise(self, exercise_name: str, context: RunContext):
        """
        Call this when the user wants to do a single exercise without a scheduled workout.
        User might say: "I want to squat", "let me do some bench press",
        "I just want to deadlift", "can I just do squats?"

        Args:
            exercise_name: The exercise the user wants to do (e.g., "squat", "bench press", "deadlift")
        """
        logger.info(f"[MAIN MENU] User wants quick exercise: {exercise_name}")

        normalized = normalize_exercise_name(exercise_name)

        if not normalized:
            result = (None, (
                "Tell the user: 'I can't track that exercise with form feedback just yet. "
                "Right now I can track squats, deadlifts, bench press, and overhead press. "
                "Would you like to do one of those?' Keep it helpful and casual."
            ))
            self._log_function_call("start_quick_exercise", {"exercise_name": exercise_name}, result)
            return result

        self.state.set("quick_exercise.exercise_name", normalized)
        self.state.set("quick_exercise.gathering_params", True)
        self.state.save_state()

        name = self.user_name

        result = (None, (
            f"The user wants to do {normalized} as a quick exercise (not part of a scheduled workout). "
            f"Now ask {name} conversationally about their plan. Ask how many sets they're thinking, "
            f"how many reps per set, what weight they want to use, and how long they want to rest between sets. "
            f"Once you have all the details, call confirm_quick_exercise() with the parameters. "
            f"Keep it natural and conversational — like a coach checking in. "
            f"If they're unsure about anything, suggest reasonable defaults "
            f"(3-5 sets, 5-10 reps, 90-120 seconds rest)."
        ))
        self._log_function_call("start_quick_exercise", {"exercise_name": exercise_name}, result)
        return result

    @function_tool
    async def confirm_quick_exercise(
        self,
        sets: int,
        reps: int,
        weight: float = 0.0,
        rest_seconds: int = 120,
        context: RunContext = None
    ):
        """
        Call this after gathering all parameters for a quick exercise session.
        This starts workout mode for the single exercise.

        Args:
            sets: Number of sets to perform
            reps: Target reps per set
            weight: Weight in lbs. Use 0 for bodyweight exercises.
            rest_seconds: Rest between sets in seconds (default 120)
        """
        logger.info(f"[QUICK EXERCISE] Confirming: {sets} sets x {reps} reps, "
                    f"weight={weight}, rest={rest_seconds}s")

        exercise_name = self.state.get("quick_exercise.exercise_name")

        if not exercise_name:
            return None, ("Tell the user: 'Hmm, I lost track of which exercise we were setting up. "
                          "Can you tell me again what you'd like to do?' Keep it casual.")

        from core.workout_session import WorkoutSession, ExerciseProgress, SetProgress

        # Check calibration
        calibration_profile = await check_calibration(self.user_id, exercise_name)
        needs_calibration = calibration_profile is None

        if calibration_profile:
            self.state.set("workout.calibration_profile", calibration_profile)
            logger.info(f"[CALIBRATION] Found existing calibration for {exercise_name}")
        else:
            start_calibration_mode(self.state, exercise_name, {
                "type": "quick_exercise",
                "sets": sets, "reps": reps, "weight": weight,
                "rest_seconds": rest_seconds, "exercise_name": exercise_name,
            })
            logger.info(f"[CALIBRATION] No calibration found for {exercise_name} — entering calibration mode")

        # Build synthetic sets
        set_list = []
        for i in range(sets):
            set_list.append(SetProgress(
                set_id=None,
                set_number=i + 1,
                target_reps=reps,
                target_weight=weight,
                intensity_percent=None,
                rpe_target=None,
                rest_seconds=rest_seconds,
                velocity_threshold=None,
            ))

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

        workout_data = {
            "workout_id": None,
            "workout_name": f"Quick {exercise_name}",
            "description": f"Ad-hoc {exercise_name} session",
            "exercises": []
        }

        session = WorkoutSession(
            user_id=self.user_id,
            schedule_id=None,
            workout_data=workout_data,
            is_quick_exercise=True,
        )
        session.exercises = [exercise]

        # Store in state and switch to workout mode
        self.state.set("workout.current_session", session.to_dict())
        self.state.set("quick_exercise.gathering_params", False)
        self.state.set("workout.exercise_name", exercise_name)
        self.state.set("workout.active", True)

        self.state.switch_mode("workout")
        self.state.save_state()

        logger.info("[STATE] Switched to workout mode with quick exercise - main.py will detect and start pose estimation")

        self._log_function_call("confirm_quick_exercise", {
            "sets": sets, "reps": reps, "weight": weight, "rest_seconds": rest_seconds
        }, "handoff to WorkoutAgent")

        # Handoff to WorkoutAgent
        self._suppress_turn_detection()
        from agents.workout_agent import WorkoutAgent
        return WorkoutAgent(state=self.state, userdata=self.userdata)

    # ===== PROGRAM TOOLS =====

    def _extract_program_params_from_request(self, user_request: str) -> dict:
        """Extract program parameters from natural language request."""
        from datetime import datetime

        extracted = {}
        request_lower = user_request.lower()

        # Extract GOAL/CATEGORY
        hypertrophy_keywords = ['muscle', 'bigger', 'size', 'mass', 'hypertrophy', 'bulk', 'grow', 'butt', 'glutes', 'chest', 'arms', 'legs', 'aesthetic', 'look good', 'shredded', 'toned']
        strength_keywords = ['stronger', 'strength', 'powerlifting', 'max', '1rm', 'heavy', 'strong']
        power_keywords = ['explosive', 'power', 'jump', 'vertical', 'sprint', 'athletics', 'athleticism', 'athlete', 'speed', 'fast', 'quick']

        hypertrophy_score = sum(1 for kw in hypertrophy_keywords if kw in request_lower)
        strength_score = sum(1 for kw in strength_keywords if kw in request_lower)
        power_score = sum(1 for kw in power_keywords if kw in request_lower)

        if max(hypertrophy_score, strength_score, power_score) > 0:
            if hypertrophy_score > strength_score and hypertrophy_score > power_score:
                extracted['goal'] = 'hypertrophy'
            elif strength_score > hypertrophy_score and strength_score > power_score:
                extracted['goal'] = 'strength'
            elif power_score > hypertrophy_score and power_score > strength_score:
                extracted['goal'] = 'power'

        # Extract DURATION (weeks)
        week_match = re.search(r'(\d+)\s*(?:weeks?|wks?)', request_lower)
        if week_match:
            extracted['duration'] = int(week_match.group(1))
        else:
            month_match = re.search(r'(\d+)\s*months?', request_lower)
            if month_match:
                extracted['duration'] = int(month_match.group(1)) * 4

        if 'christmas' in request_lower and 'duration' not in extracted:
            today = datetime.now()
            christmas = datetime(today.year if today.month < 12 else today.year + 1, 12, 25)
            weeks_until = max(1, int((christmas - today).days / 7))
            if weeks_until <= 52:
                extracted['duration'] = weeks_until

        # Extract TRAINING FREQUENCY
        freq_match = re.search(r'(\d+)\s*(?:days?|times?|x)\s*(?:a|per)?\s*week', request_lower)
        if freq_match:
            extracted['frequency'] = int(freq_match.group(1))

        # Extract USER NOTES (specific preferences)
        notes_parts = []
        if 'glute' in request_lower or 'butt' in request_lower:
            notes_parts.append("glute emphasis")
        if 'chest' in request_lower:
            notes_parts.append("chest emphasis")
        if 'leg' in request_lower:
            notes_parts.append("leg emphasis")
        if 'arm' in request_lower:
            notes_parts.append("arm emphasis")
        if 'back' in request_lower:
            notes_parts.append("back emphasis")
        if 'vertical' in request_lower and 'jump' in request_lower:
            notes_parts.append("vertical jump focus")
        if 'sprint' in request_lower:
            notes_parts.append("sprint speed focus")
        if notes_parts:
            extracted['notes'] = ", ".join(notes_parts)

        # Extract SPORT
        sports = ['basketball', 'football', 'soccer', 'volleyball', 'track', 'baseball', 'powerlifting', 'weightlifting', 'crossfit']
        for sport in sports:
            if sport in request_lower:
                extracted['sport'] = sport
                break

        # Extract INJURIES
        injury_keywords = ['injury', 'injured', 'hurt', 'pain', 'bad knee', 'bad shoulder', 'back pain']
        for kw in injury_keywords:
            if kw in request_lower:
                if 'knee' in request_lower:
                    extracted['injuries'] = "knee issues mentioned"
                elif 'shoulder' in request_lower:
                    extracted['injuries'] = "shoulder issues mentioned"
                elif 'back' in request_lower:
                    extracted['injuries'] = "back issues mentioned"
                else:
                    extracted['injuries'] = "injury mentioned - needs clarification"
                break

        # Extract SESSION DURATION
        duration_match = re.search(r'(\d+)\s*(?:minute|min)\s*(?:workout|session)', request_lower)
        if duration_match:
            extracted['session_duration'] = int(duration_match.group(1))
        else:
            hour_match = re.search(r'(\d+)\s*hour\s*(?:workout|session)', request_lower)
            if hour_match:
                extracted['session_duration'] = int(hour_match.group(1)) * 60

        return extracted

    async def _enter_program_creation_mode(self, db, user_id: str, name: str, extracted_params: dict, user_request: str = "") -> str:
        """Shared logic for entering program creation mode."""
        from db.models import User

        db_user = db.query(User).filter(User.id == user_id).first()
        existing_data = {}
        if db_user:
            existing_data = {
                "height_cm": float(db_user.height_cm) if db_user.height_cm else None,
                "weight_kg": float(db_user.weight_kg) if db_user.weight_kg else None,
                "age": int(db_user.age) if db_user.age else None,
                "sex": db_user.sex
            }
            logger.info(f"[PROGRAM] Cached existing user data: {existing_data}")

        self.state.set("program_creation.existing_data", existing_data)

        # Store extracted parameters with precaptured_ prefix
        param_mappings = {
            'goal': 'precaptured_goal',
            'duration': 'precaptured_duration',
            'frequency': 'precaptured_frequency',
            'notes': 'precaptured_notes',
            'sport': 'precaptured_sport',
            'injuries': 'precaptured_injuries',
            'session_duration': 'precaptured_session_duration',
        }

        for key, state_key in param_mappings.items():
            if key in extracted_params:
                self.state.set(f"program_creation.{state_key}", extracted_params[key])
                logger.info(f"[PROGRAM] Pre-captured {key}: {extracted_params[key]}")

        if 'goal' in extracted_params and user_request:
            self.state.set("program_creation.precaptured_goal_raw", user_request)

        self.state.switch_mode("program_creation")
        self.state.save_state()

        logger.info("[PROGRAM] Entering program creation mode")

    @function_tool
    async def create_program(self, context: RunContext, user_request: str = ""):
        """
        Call this IMMEDIATELY when the user wants to create a program.

        IMPORTANT: Pass the user's FULL original message as user_request to enable intelligent parameter extraction.

        Args:
            user_request: The user's full original request (enables smart parameter extraction)
        """
        logger.info("="*80)
        logger.info("[MAIN MENU] create_program() CALLED")
        logger.info(f"[MAIN MENU] User request: {user_request}")
        logger.info("="*80)

        user_id = self.user_id
        name = self.user_name

        # Extract program parameters from user request
        extracted_params = {}
        if user_request:
            extracted_params = self._extract_program_params_from_request(user_request)
            if extracted_params:
                logger.info(f"[PROGRAM] Extracted parameters: {extracted_params}")

        db = SessionLocal()
        try:
            # Enter program creation mode (caches user data, stores params, switches mode)
            await self._enter_program_creation_mode(db, user_id, name, extracted_params, user_request)

            # Handoff to ProgramCreationAgent
            self._suppress_turn_detection()
            from agents.program_creation_agent import ProgramCreationAgent
            return ProgramCreationAgent(state=self.state, userdata=self.userdata)

        except Exception as e:
            logger.error(f"[ERROR] Failed to enter program creation: {e}")
            return None, f"There was an error starting program creation. Say something like: '{name}, I'm having trouble. Let's try again.' Keep it apologetic."
        finally:
            db.close()

    @function_tool
    async def update_program(self, context: RunContext):
        """
        Call this when the user wants to update or modify an existing program.
        User might say: "update my program", "modify my program", "change my program"
        """
        logger.info("[MAIN MENU] User requested to update program")

        user_id = self.user_id
        name = self.user_name

        db = SessionLocal()
        try:
            from db.program_utils import get_program_summary_list

            programs = get_program_summary_list(db, user_id)

            if len(programs) == 0:
                return None, f"Say something like: '{name}, you don't have any programs yet. Would you like to create your first program?' Keep it encouraging."
            elif len(programs) == 1:
                program = programs[0]
                self.state.set("program_update.selected_program_id", program["id"])
                self.state.set("program_update.selected_program_name", program["name"])
                self.state.save_state()

                logger.info(f"[PROGRAM UPDATE] User has 1 program: {program['name']} (ID: {program['id']})")

                # Handoff to ProgramCreationAgent (which handles updates too)
                self._suppress_turn_detection()
                from agents.program_creation_agent import ProgramCreationAgent
                return ProgramCreationAgent(state=self.state, userdata=self.userdata)
            else:
                # Multiple programs - store list and handoff to let ProgramCreationAgent handle selection
                self.state.set("program_update.available_programs", programs)
                self.state.save_state()

                logger.info(f"[PROGRAM UPDATE] User has {len(programs)} programs")

                self._suppress_turn_detection()
                from agents.program_creation_agent import ProgramCreationAgent
                return ProgramCreationAgent(state=self.state, userdata=self.userdata)

        except Exception as e:
            logger.error(f"[ERROR] Failed to list programs: {e}")
            return None, f"Say something like: '{name}, I'm having trouble accessing your programs right now. Let's try again in a moment.' Keep it apologetic."
        finally:
            db.close()

    # ===== SCHEDULE & INFO TOOLS =====

    @function_tool
    async def view_schedule(self, days_ahead: int = 7, context: RunContext = None):
        """
        Call this when the user wants to see their upcoming workout schedule.

        Args:
            days_ahead: Number of days to look ahead (default 7)
        """
        logger.info(f"[MAIN MENU] User requested schedule (next {days_ahead} days)")

        from db.schedule_utils import get_upcoming_workouts
        from datetime import datetime

        db = SessionLocal()
        try:
            user_id = self.user_id
            name = self.user_name

            workouts = get_upcoming_workouts(db, user_id, days_ahead)

            if not workouts:
                return None, f"The user has no workouts scheduled in the next {days_ahead} days. Suggest creating a new program or offer to help with other options."

            schedule_list = []
            for w in workouts:
                date_obj = datetime.fromisoformat(w['scheduled_date'])
                date_display = date_obj.strftime("%A, %B %d")
                status = "completed" if w['completed'] else "scheduled"
                schedule_list.append(f"{date_display}: {w['workout_name']} ({status})")

            schedule_text = "\n".join(schedule_list)

            return None, f"The user wants to see their schedule. Tell them they have {len(workouts)} workouts in the next {days_ahead} days:\n{schedule_text}\n\nKeep the delivery natural and conversational."

        except Exception as e:
            logger.exception("[SCHEDULE ERROR] Failed to load schedule")
            return None, "There was an error loading the schedule. Apologize and suggest trying again."
        finally:
            db.close()

    @function_tool
    async def view_workout_exercises(self, context: RunContext, date_text: str = "today"):
        """
        Call this when the user wants to see the exercises in their workout for a specific day.

        Args:
            date_text: The day to view (e.g., "today", "tomorrow", "monday", "next friday")
        """
        logger.info(f"[MAIN MENU] User requested exercises for: {date_text}")

        from db.schedule_utils import get_upcoming_workouts
        from datetime import datetime, date, timedelta
        from utils.date_parser import parse_natural_date, DateParseError

        db = SessionLocal()
        try:
            user_id = self.user_id
            name = self.user_name

            try:
                target_date = parse_natural_date(date_text)
            except DateParseError as e:
                return None, f"I had trouble understanding '{date_text}' as a date. Please call this function again with a clearer date like 'today', 'tomorrow', or a day of the week."

            from db.models import Schedule, Workout, WorkoutExercise, Exercise, Set
            from sqlalchemy import and_
            from sqlalchemy.orm import joinedload

            schedule = db.query(Schedule).options(
                joinedload(Schedule.workout).joinedload(Workout.workout_exercises).joinedload(WorkoutExercise.exercise),
                joinedload(Schedule.workout).joinedload(Workout.workout_exercises).joinedload(WorkoutExercise.sets)
            ).filter(
                and_(
                    Schedule.user_id == user_id,
                    Schedule.scheduled_date == target_date
                )
            ).first()

            if not schedule:
                date_str = target_date.strftime("%A, %B %d")
                return None, f"No workout scheduled for {date_str}. Suggest viewing their schedule or creating a program."

            workout = schedule.workout

            exercise_list = []
            for we in sorted(workout.workout_exercises, key=lambda x: x.order_number):
                ex_name = we.exercise.name if we.exercise else "Unknown Exercise"
                sets_count = len(we.sets)

                if we.sets:
                    reps = [s.reps for s in we.sets if s.reps]
                    if reps:
                        if min(reps) == max(reps):
                            rep_info = f"{reps[0]} reps"
                        else:
                            rep_info = f"{min(reps)}-{max(reps)} reps"
                    else:
                        rep_info = "reps not specified"
                else:
                    rep_info = "no sets"

                exercise_info = f"{ex_name}: {sets_count} sets of {rep_info}"
                if we.notes:
                    exercise_info += f" ({we.notes})"
                exercise_list.append(exercise_info)

            exercises_text = "\n".join([f"{i+1}. {ex}" for i, ex in enumerate(exercise_list)])
            date_str = target_date.strftime("%A, %B %d")

            return None, f"Workout for {date_str} - {workout.name}:\n\n{exercises_text}\n\nPresent this information naturally and conversationally."

        except Exception as e:
            logger.exception("[WORKOUT VIEW ERROR] Failed to load exercises")
            return None, "There was an error loading the workout details. Apologize and suggest trying again."
        finally:
            db.close()

    # ===== SCHEDULE MODIFICATION TOOLS =====

    @function_tool
    async def move_workout_to_date(self, context: RunContext, workout_description: str, target_date_text: str):
        """
        Move a specific workout to a new date (NO cascading).

        Args:
            workout_description: Description of workout to move (e.g., "leg day", "tuesday's workout")
            target_date_text: Natural language target date (e.g., "tomorrow", "next friday")
        """
        from db.schedule_utils import find_schedule_by_criteria, move_workout
        from utils.date_parser import parse_natural_date, get_date_description, DateParseError
        from datetime import date, timedelta

        user_id = self.user_id
        name = self.user_name

        db = SessionLocal()
        try:
            try:
                target_date = parse_natural_date(target_date_text)
            except DateParseError:
                return None, f"I couldn't understand the date '{target_date_text}'. Could you say it differently?"

            source_date = None
            workout_name_hint = None

            if "today" in workout_description.lower():
                source_date = date.today()
            elif "tomorrow" in workout_description.lower():
                source_date = date.today() + timedelta(days=1)

            for day_name in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                if day_name in workout_description.lower():
                    source_date = parse_natural_date(day_name)
                    break

            for hint in ['leg', 'upper', 'lower', 'push', 'pull', 'chest', 'back', 'shoulder']:
                if hint in workout_description.lower():
                    workout_name_hint = hint
                    break

            matches = find_schedule_by_criteria(db, user_id, target_date=source_date, workout_name_fragment=workout_name_hint)

            if len(matches) == 0:
                return None, f"I couldn't find a workout matching '{workout_description}'. Could you be more specific?"
            if len(matches) > 1:
                workout_list = ", ".join([f"{w.workout.name} on {w.scheduled_date}" for w in matches[:3]])
                return None, f"I found multiple workouts: {workout_list}. Which one did you mean?"

            schedule = matches[0]
            success, error_msg = move_workout(db, schedule.id, target_date)

            if not success:
                return None, f"I couldn't move that workout. {error_msg}"

            target_desc = get_date_description(target_date)
            return None, f"Done! I moved '{schedule.workout.name}' to {target_desc}. Your schedule is updated."

        except Exception as e:
            logger.exception("[ERROR] move_workout_to_date failed")
            return None, f"Sorry {name}, I ran into an issue moving that workout. Let's try again."
        finally:
            db.close()

    @function_tool
    async def swap_two_workouts(self, context: RunContext, workout1_description: str, workout2_description: str):
        """
        Swap two individual workouts by exchanging their dates.

        Args:
            workout1_description: First workout (e.g., "tuesday's workout", "leg day")
            workout2_description: Second workout (e.g., "thursday's workout", "push day")
        """
        from db.schedule_utils import find_schedule_by_criteria, swap_workouts
        from utils.date_parser import parse_natural_date
        from datetime import date, timedelta

        user_id = self.user_id
        name = self.user_name

        db = SessionLocal()
        try:
            def find_workout(description: str):
                source_date = None
                workout_name_hint = None

                if "today" in description.lower():
                    source_date = date.today()
                elif "tomorrow" in description.lower():
                    source_date = date.today() + timedelta(days=1)

                for day_name in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                    if day_name in description.lower():
                        source_date = parse_natural_date(day_name)
                        break

                for hint in ['leg', 'upper', 'lower', 'push', 'pull', 'chest', 'back', 'shoulder']:
                    if hint in description.lower():
                        workout_name_hint = hint
                        break

                return find_schedule_by_criteria(db, user_id, target_date=source_date, workout_name_fragment=workout_name_hint)

            matches1 = find_workout(workout1_description)
            matches2 = find_workout(workout2_description)

            if len(matches1) == 0 or len(matches2) == 0:
                return None, f"I couldn't find both workouts. Could you be more specific about which workouts to swap?"

            if len(matches1) > 1 or len(matches2) > 1:
                return None, f"I found multiple matches. Could you specify the exact dates?"

            success, error_msg = swap_workouts(db, matches1[0].id, matches2[0].id)

            if not success:
                return None, f"I couldn't swap those workouts. {error_msg}"

            return None, f"Done! I swapped '{matches1[0].workout.name}' and '{matches2[0].workout.name}'. Your schedule is updated."

        except Exception as e:
            logger.exception("[ERROR] swap_two_workouts failed")
            return None, f"Sorry {name}, I ran into an issue swapping those workouts. Let's try again."
        finally:
            db.close()

    @function_tool
    async def swap_entire_weeks(self, context: RunContext, week1_description: str, week2_description: str):
        """
        Swap ALL workouts between two weeks.

        Args:
            week1_description: First week (e.g., "this week", "next week")
            week2_description: Second week (e.g., "the week after", "next week")
        """
        from db.schedule_utils import swap_weeks
        from utils.date_parser import parse_week_range, DateParseError

        user_id = self.user_id
        name = self.user_name

        db = SessionLocal()
        try:
            try:
                week1_start, week1_end = parse_week_range(week1_description)
                week2_start, week2_end = parse_week_range(week2_description)
            except DateParseError:
                return None, f"I couldn't understand those week descriptions. Could you say it like 'this week and next week'?"

            success, error_msg, swapped_pairs = swap_weeks(db, user_id, week1_start, week2_start)

            if not success:
                return None, f"I couldn't swap those weeks. {error_msg}"

            return None, f"Done! I swapped all workouts between {week1_description} and {week2_description}. {len(swapped_pairs)} workouts were moved."

        except Exception as e:
            logger.exception("[ERROR] swap_entire_weeks failed")
            return None, f"Sorry {name}, I ran into an issue swapping those weeks. Let's try again."
        finally:
            db.close()

    @function_tool
    async def skip_workout_today(self, context: RunContext, reason: str = None):
        """
        Skip today's workout (does NOT reschedule automatically).

        Args:
            reason: Optional reason for skipping (e.g., "tired", "injured", "travel")
        """
        from db.schedule_utils import get_todays_workout, skip_workout

        user_id = self.user_id
        name = self.user_name

        db = SessionLocal()
        try:
            workout = get_todays_workout(db, user_id)

            if not workout:
                return None, f"{name}, you don't have a workout scheduled today. Would you like to see your upcoming schedule?"

            success, error_msg = skip_workout(db, workout["schedule_id"], reason=reason)

            if not success:
                return None, f"I couldn't skip that workout. {error_msg}"

            return None, f"No problem, {name}. I've marked today's workout as skipped. Rest up and we'll get back to it next time!"

        except Exception as e:
            logger.exception("[ERROR] skip_workout_today failed")
            return None, f"Sorry {name}, I ran into an issue. Let's try again."
        finally:
            db.close()

    @function_tool
    async def add_rest_day_and_shift(self, context: RunContext, rest_date_text: str):
        """
        Add a rest day and shift future workouts forward.

        Args:
            rest_date_text: Natural language date for rest day (e.g., "tomorrow", "friday")
        """
        from db.schedule_utils import add_rest_day
        from utils.date_parser import parse_natural_date, get_date_description, DateParseError

        user_id = self.user_id
        name = self.user_name

        db = SessionLocal()
        try:
            try:
                rest_date = parse_natural_date(rest_date_text)
            except DateParseError:
                return None, f"I couldn't understand '{rest_date_text}'. Could you say it differently?"

            success, error_msg, shifted_count = add_rest_day(db, user_id, rest_date, shift_future_workouts=True)

            if not success:
                return None, f"I couldn't add a rest day. {error_msg}"

            rest_desc = get_date_description(rest_date)
            return None, f"Done! I added a rest day on {rest_desc} and pushed {shifted_count} future workouts forward by one day."

        except Exception as e:
            logger.exception("[ERROR] add_rest_day_and_shift failed")
            return None, f"Sorry {name}, I ran into an issue. Let's try again."
        finally:
            db.close()

    @function_tool
    async def repeat_workout_on_date(self, context: RunContext, workout_description: str, repeat_date_text: str):
        """
        Duplicate a workout to another date.

        Args:
            workout_description: Workout to repeat (e.g., "today's workout", "leg day")
            repeat_date_text: Date to repeat on (e.g., "friday", "next monday")
        """
        from db.schedule_utils import find_schedule_by_criteria, repeat_workout
        from utils.date_parser import parse_natural_date, get_date_description, DateParseError
        from datetime import date

        user_id = self.user_id
        name = self.user_name

        db = SessionLocal()
        try:
            try:
                repeat_date = parse_natural_date(repeat_date_text)
            except DateParseError:
                return None, f"I couldn't understand '{repeat_date_text}'. Could you say it differently?"

            source_date = None
            workout_name_hint = None

            if "today" in workout_description.lower():
                source_date = date.today()

            for hint in ['leg', 'upper', 'lower', 'push', 'pull']:
                if hint in workout_description.lower():
                    workout_name_hint = hint
                    break

            matches = find_schedule_by_criteria(db, user_id, target_date=source_date, workout_name_fragment=workout_name_hint)

            if len(matches) == 0:
                return None, f"I couldn't find a workout matching '{workout_description}'."
            if len(matches) > 1:
                return None, f"I found multiple matches. Could you be more specific?"

            success, error_msg, new_schedule_id = repeat_workout(db, matches[0].id, repeat_date)

            if not success:
                return None, f"I couldn't repeat that workout. {error_msg}"

            repeat_desc = get_date_description(repeat_date)
            return None, f"Done! I added '{matches[0].workout.name}' on {repeat_desc}."

        except Exception as e:
            logger.exception("[ERROR] repeat_workout_on_date failed")
            return None, f"Sorry {name}, I ran into an issue. Let's try again."
        finally:
            db.close()

    @function_tool
    async def apply_deload_to_week(self, context: RunContext, week_description: str, intensity_percentage: int = 70):
        """
        Apply deload to a week (reduce intensity for recovery).

        Args:
            week_description: Week to deload (e.g., "this week", "next week")
            intensity_percentage: Target intensity as percentage (default 70%)
        """
        from db.schedule_utils import apply_deload_week
        from utils.date_parser import parse_week_range, DateParseError

        user_id = self.user_id
        name = self.user_name

        db = SessionLocal()
        try:
            try:
                week_start, week_end = parse_week_range(week_description)
            except DateParseError:
                return None, f"I couldn't understand '{week_description}'. Could you say 'this week' or 'next week'?"

            if not (30 <= intensity_percentage <= 100):
                return None, f"Intensity should be between 30% and 100%. Did you mean {intensity_percentage}%?"

            intensity_modifier = intensity_percentage / 100.0
            success, error_msg, modified_count = apply_deload_week(db, user_id, week_start, intensity_modifier)

            if not success:
                return None, f"I couldn't apply deload. {error_msg}"

            return None, f"Done! I set {week_description} as a deload week at {intensity_percentage}% intensity. {modified_count} workouts were modified."

        except Exception as e:
            logger.exception("[ERROR] apply_deload_to_week failed")
            return None, f"Sorry {name}, I ran into an issue. Let's try again."
        finally:
            db.close()

    @function_tool
    async def clear_schedule_for_vacation(self, context: RunContext, start_date_text: str, end_date_text: str):
        """
        Clear workouts in a date range (vacation mode).

        Args:
            start_date_text: Vacation start date
            end_date_text: Vacation end date
        """
        from db.schedule_utils import clear_date_range
        from utils.date_parser import parse_natural_date, DateParseError

        user_id = self.user_id
        name = self.user_name

        db = SessionLocal()
        try:
            try:
                start_date = parse_natural_date(start_date_text)
                end_date = parse_natural_date(end_date_text)
            except DateParseError:
                return None, f"I couldn't understand those dates. Could you say them differently?"

            success, error_msg, cleared_count = clear_date_range(db, user_id, start_date, end_date, preserve_completed=True)

            if not success:
                return None, f"I couldn't clear that range. {error_msg}"

            return None, f"Done! I cleared {cleared_count} workouts from {start_date} to {end_date}. Enjoy your break, {name}!"

        except Exception as e:
            logger.exception("[ERROR] clear_schedule_for_vacation failed")
            return None, f"Sorry {name}, I ran into an issue. Let's try again."
        finally:
            db.close()

    @function_tool
    async def push_remaining_week_forward(self, context: RunContext, days: int = 1):
        """
        Push remaining workouts this week forward by N days.

        Args:
            days: Number of days to shift forward (default: 1)
        """
        from db.schedule_utils import reschedule_remaining_week

        user_id = self.user_id
        name = self.user_name

        db = SessionLocal()
        try:
            if not (1 <= days <= 7):
                return None, f"I can only shift workouts by 1-7 days. Did you mean {days} days?"

            success, error_msg, rescheduled_count = reschedule_remaining_week(db, user_id, days_offset=days)

            if not success:
                return None, f"I couldn't reschedule those workouts. {error_msg}"

            return None, f"Done! I pushed {rescheduled_count} remaining workouts forward by {days} day{'s' if days > 1 else ''}."

        except Exception as e:
            logger.exception("[ERROR] push_remaining_week_forward failed")
            return None, f"Sorry {name}, I ran into an issue. Let's try again."
        finally:
            db.close()

    @function_tool
    async def undo_last_schedule_change(self, context: RunContext):
        """
        Undo the last schedule change made by the user.
        """
        from db.schedule_history import undo_last_change

        user_id = self.user_id
        name = self.user_name

        db = SessionLocal()
        try:
            success, error_msg = undo_last_change(db, user_id)

            if not success:
                return None, f"{error_msg}"

            return None, f"Done! I've undone your last change."

        except Exception as e:
            logger.exception("[ERROR] undo_last_schedule_change failed")
            return None, f"Sorry {name}, I ran into an issue undoing that change. Let's try again."
        finally:
            db.close()

    @function_tool
    async def view_schedule_change_history(self, context: RunContext, limit: int = 5):
        """
        View recent schedule changes.

        Args:
            limit: Number of recent changes to show (default: 5, max: 10)
        """
        from db.schedule_history import get_recent_changes, format_change_for_display

        user_id = self.user_id
        name = self.user_name

        db = SessionLocal()
        try:
            if not (1 <= limit <= 10):
                limit = 5

            changes = get_recent_changes(db, user_id, limit=limit)

            if not changes:
                return None, "You haven't made any schedule changes yet."

            response = f"Here are your {len(changes)} most recent schedule changes:\n\n"
            for i, change in enumerate(changes, 1):
                formatted = format_change_for_display(change)
                response += f"{i}. {formatted}\n"

            return None, response.strip()

        except Exception as e:
            logger.exception("[ERROR] view_schedule_change_history failed")
            return None, f"Sorry {name}, I ran into an issue retrieving your change history."
        finally:
            db.close()

    @function_tool
    async def analyze_schedule_for_recovery(self, context: RunContext):
        """
        Analyze the user's schedule for recovery issues and suggest rest days.
        """
        from db.recovery_analysis import analyze_schedule_recovery, format_recommendation_for_display

        user_id = self.user_id
        name = self.user_name

        db = SessionLocal()
        try:
            analysis = analyze_schedule_recovery(db, user_id)

            response = f"{analysis['analysis_summary']}\n\n"

            if analysis["recommendations"]:
                response += f"I found {len(analysis['recommendations'])} recovery concerns:\n\n"
                for i, rec in enumerate(analysis["recommendations"][:3], 1):
                    formatted = format_recommendation_for_display(rec)
                    response += f"{i}. {formatted}\n\n"
                response += "Would you like me to add these rest days to your schedule?"
            else:
                response += "No rest day recommendations - keep up the great work!"

            return None, response.strip()

        except Exception as e:
            logger.exception("[ERROR] analyze_schedule_for_recovery failed")
            return None, f"Sorry {name}, I ran into an issue analyzing your schedule."
        finally:
            db.close()

    @function_tool
    async def apply_recommended_rest_days(self, context: RunContext, shift_future_workouts: bool = True):
        """
        Apply the recommended rest days from schedule analysis.

        Args:
            shift_future_workouts: Whether to push future workouts forward (default: True)
        """
        from db.recovery_analysis import apply_all_recommended_rest_days

        user_id = self.user_id
        name = self.user_name

        db = SessionLocal()
        try:
            success, error, added_count = apply_all_recommended_rest_days(
                db, user_id, max_rest_days=3, shift_future_workouts=shift_future_workouts
            )

            if not success:
                return None, f"{error}"

            shift_msg = " and shifted future workouts" if shift_future_workouts else ""
            return None, f"Done! I added {added_count} rest day{'s' if added_count != 1 else ''}{shift_msg}. Your recovery should be much better now!"

        except Exception as e:
            logger.exception("[ERROR] apply_recommended_rest_days failed")
            return None, f"Sorry {name}, I ran into an issue adding those rest days."
        finally:
            db.close()

    @function_tool
    async def check_if_deload_needed(self, context: RunContext):
        """
        Check if the user needs a deload week based on training load analysis.
        """
        from db.training_load import check_deload_recommendation

        user_id = self.user_id
        name = self.user_name

        db = SessionLocal()
        try:
            needs_deload, recommendation, reason = check_deload_recommendation(db, user_id)

            if not needs_deload:
                return None, f"Good news! You don't need a deload right now. {reason}"

            response = "Based on your training load, I recommend a deload week:\n\n"
            response += f"Fatigue Score: {recommendation.get('fatigue_score', 'N/A')}/100\n"
            response += f"Recommended Week: {recommendation['week_start'].strftime('%b %d')} - {recommendation['week_end'].strftime('%b %d')}\n"
            response += f"Intensity: {int(recommendation['intensity_modifier'] * 100)}% of normal\n\n"
            response += "Reasons:\n"
            for r in recommendation['trigger_reasons']:
                response += f"  - {r}\n"
            response += "\nWould you like me to apply this deload week to your schedule?"

            return None, response.strip()

        except Exception as e:
            logger.exception("[ERROR] check_if_deload_needed failed")
            return None, f"Sorry {name}, I ran into an issue checking your training load."
        finally:
            db.close()

    @function_tool
    async def apply_deload_week_recommendation(self, context: RunContext):
        """
        Apply the recommended deload week from training load analysis.
        """
        from db.training_load import check_deload_recommendation, apply_deload_recommendation

        user_id = self.user_id
        name = self.user_name

        db = SessionLocal()
        try:
            needs_deload, recommendation, reason = check_deload_recommendation(db, user_id)

            if not needs_deload:
                return None, f"There's no deload recommendation right now. {reason}"

            success, error = apply_deload_recommendation(db, user_id, recommendation)

            if not success:
                return None, f"I couldn't apply the deload week. {error}"

            intensity_pct = int(recommendation['intensity_modifier'] * 100)
            week_str = recommendation['week_start'].strftime('%b %d')

            return None, f"Done! I've applied a {intensity_pct}% deload week starting {week_str}. Focus on recovery and lighter training this week!"

        except Exception as e:
            logger.exception("[ERROR] apply_deload_week_recommendation failed")
            return None, f"Sorry {name}, I ran into an issue applying the deload week."
        finally:
            db.close()

    @function_tool
    async def view_training_load_history(self, context: RunContext, weeks: int = 4):
        """
        View recent training load metrics and fatigue trends.

        Args:
            weeks: Number of weeks to show (default: 4)
        """
        from db.models import TrainingLoadMetrics
        from sqlalchemy import desc

        user_id = self.user_id
        name = self.user_name

        db = SessionLocal()
        try:
            if not (1 <= weeks <= 12):
                weeks = 4

            metrics = db.query(TrainingLoadMetrics).filter(
                TrainingLoadMetrics.user_id == user_id
            ).order_by(desc(TrainingLoadMetrics.week_start_date)).limit(weeks).all()

            if not metrics:
                return None, "I don't have any training load data for you yet. Complete some workouts and I'll start tracking!"

            response = f"Here's your training load for the past {len(metrics)} weeks:\n\n"

            for m in metrics:
                week_str = m.week_start_date.strftime('%b %d')
                response += f"Week of {week_str}:\n"
                response += f"  - Workouts: {m.workouts_completed}\n"
                response += f"  - Total Sets: {m.total_sets}\n"
                response += f"  - Volume: {float(m.total_volume_kg):.0f} kg\n"
                if m.avg_rpe:
                    response += f"  - Avg RPE: {float(m.avg_rpe):.1f}/10\n"
                if m.fatigue_score:
                    response += f"  - Fatigue Score: {float(m.fatigue_score):.1f}/100\n"
                if m.velocity_decline_percent:
                    response += f"  - Velocity Decline: {float(m.velocity_decline_percent):.1f}%\n"
                response += "\n"

            return None, response.strip()

        except Exception as e:
            logger.exception("[ERROR] view_training_load_history failed")
            return None, f"Sorry {name}, I ran into an issue retrieving your training load."
        finally:
            db.close()

    @function_tool
    async def view_progress(self, context: RunContext):
        """
        Call this when the user wants to view their progress, stats, or history.
        """
        logger.info("[MAIN MENU] User requested to view progress")
        name = self.user_name
        return None, f"The user wants to see their progress. Acknowledge their request and let them know this feature is coming soon - they'll be able to see workout history, personal records, and progress charts. Keep it encouraging."

    @function_tool
    async def update_profile(self, context: RunContext):
        """
        Call this when the user wants to update their profile or settings.
        """
        logger.info("[MAIN MENU] User requested to update profile")
        name = self.user_name
        return None, f"The user wants to update their profile. Say something like: '{name}, profile updates are coming soon! For now, you can ask me to change specific things and I'll note them down.' Keep it helpful."

    @function_tool
    async def shutdown(self, context: RunContext):
        """
        Call this when the user wants to shut down, exit, turn off, or say goodbye.
        User might say: "shut down", "turn off", "exit", "goodbye", "I'm done",
        "quit", "close", "power off", "see you later"
        """
        logger.info("[MAIN MENU] User requested shutdown")

        name = self.user_name

        # Signal main.py to initiate graceful shutdown
        self.state.set("shutdown_requested", True)
        self.state.save_state()

        self._log_function_call("shutdown", {}, "shutdown_requested")

        return None, (
            f"The user wants to shut down. Say a warm, brief goodbye to {name}. "
            f"Something like: 'Take care {name}, great chatting with you! See you next time.' "
            f"Keep it friendly and natural — one or two sentences max."
        )
