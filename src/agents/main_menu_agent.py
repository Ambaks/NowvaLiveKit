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
        super().__init__(state=state, userdata=userdata, instructions=get_main_menu_prompt())

    async def on_enter(self):
        """Generate main menu greeting only on first visit or first login; silent otherwise."""
        if self.state.is_first_time_main_menu():
            self.state.mark_main_menu_visited()
            self.state.save_state()
            await self._say(
                f"Welcome the user to the main menu for the first time! "
                f"Tell them about their options: start a workout, create or update a program, "
                f"check their progress, or update their profile. Keep it friendly and conversational."
            )
        elif not self.state.get("session.main_menu_greeted", False):
            self.state.set("session.main_menu_greeted", True)
            self.state.save_state()
            await self._say(
                f"The user is back at the main menu. Welcome them back and tell them "
                f"about their options which are to start a workout, create or update a program, "
                f"check their progress, or update their profile. Keep it friendly and conversational."
            )
        else:
            self._restore_turn_detection()

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
            workout = get_todays_workout(db, user_id)

            if not workout:
                logger.info("[WORKOUT] No workout scheduled for today")
                return None, f"Tell the user: 'Hey you don't have a workout scheduled for today. Would you like to check your upcoming schedule or create a new program?' Keep it helpful and supportive."

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
            await self._suppress_turn_detection()
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

        result = (None, (
            f"The user wants to do {normalized} as a quick exercise (not part of a scheduled workout). "
            f"Now ask the user conversationally about their plan. Ask how many sets they're thinking, "
            f"how many reps per set, what weight they want to use, and how long they want to rest between sets. "
            f"Once you have all the details, use the confirm_quick_exercise tool with the parameters. "
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
        await self._suppress_turn_detection()
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
            await self._suppress_turn_detection()
            from agents.program_creation_agent import ProgramCreationAgent
            return ProgramCreationAgent(state=self.state, userdata=self.userdata)

        except Exception as e:
            logger.error(f"[ERROR] Failed to enter program creation: {e}")
            return None, f"There was an error starting program creation. Say something like: 'I'm having trouble. Let's try again.' Keep it apologetic."
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
        db = SessionLocal()
        try:
            from db.program_utils import get_program_summary_list

            programs = get_program_summary_list(db, user_id)

            if len(programs) == 0:
                return None, f"Say something like: 'you don't have any programs yet. Would you like to create your first program?' Keep it encouraging."
            elif len(programs) == 1:
                program = programs[0]
                self.state.set("program_update.selected_program_id", program["id"])
                self.state.set("program_update.selected_program_name", program["name"])
                self.state.save_state()

                logger.info(f"[PROGRAM UPDATE] User has 1 program: {program['name']} (ID: {program['id']})")

                # Handoff to ProgramCreationAgent (which handles updates too)
                await self._suppress_turn_detection()
                from agents.program_creation_agent import ProgramCreationAgent
                return ProgramCreationAgent(state=self.state, userdata=self.userdata)
            else:
                # Multiple programs - store list and handoff to let ProgramCreationAgent handle selection
                self.state.set("program_update.available_programs", programs)
                self.state.save_state()

                logger.info(f"[PROGRAM UPDATE] User has {len(programs)} programs")

                await self._suppress_turn_detection()
                from agents.program_creation_agent import ProgramCreationAgent
                return ProgramCreationAgent(state=self.state, userdata=self.userdata)

        except Exception as e:
            logger.error(f"[ERROR] Failed to list programs: {e}")
            return None, f"Say something like: 'I'm having trouble accessing your programs right now. Let's try again in a moment.' Keep it apologetic."
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

    # ===== SCHEDULE MANAGEMENT ROUTING =====

    @function_tool
    async def manage_schedule(self, context: RunContext, user_request: str):
        """
        Call this when the user wants to modify their schedule. This includes:
        moving workouts, swapping workouts/weeks, skipping workouts, adding rest days,
        repeating workouts, applying deload weeks, vacation mode, pushing workouts forward,
        undoing changes, viewing change history, analyzing recovery, or checking training load.

        IMPORTANT: Pass the user's FULL original message as user_request.

        Args:
            user_request: The user's complete original request about schedule changes
        """
        logger.info(f"[MAIN MENU] Schedule management requested: {user_request}")

        intent = self._classify_schedule_intent(user_request)
        logger.info(f"[MAIN MENU] Classified schedule intent: {intent}")

        self.state.set("schedule.precaptured_intent", intent)
        self.state.set("schedule.precaptured_request", user_request)
        self.state.switch_mode("schedule")
        self.state.save_state()

        await self._suppress_turn_detection()
        await self._truncate_context_for_handoff()

        self._log_function_call("manage_schedule", {"user_request": user_request, "intent": intent}, "handoff to ScheduleMaintenanceAgent")

        from agents.schedule_agent import ScheduleMaintenanceAgent
        return ScheduleMaintenanceAgent(state=self.state, userdata=self.userdata)

    def _classify_schedule_intent(self, request: str) -> str:
        """Lightweight intent classification — fallback is 'general' (schedule agent LLM resolves)."""
        r = request.lower()
        if any(w in r for w in ['undo', 'revert', 'go back', 'nevermind']):
            return 'undo'
        if any(w in r for w in ['swap', 'switch']) and 'week' in r:
            return 'swap_weeks'
        if any(w in r for w in ['swap', 'switch']):
            return 'swap_workouts'
        if any(w in r for w in ['move', 'reschedule']) and 'remaining' not in r and 'push' not in r:
            return 'move_workout'
        if any(w in r for w in ['skip', "can't do today"]):
            return 'skip_workout'
        if any(w in r for w in ['rest day', 'add rest', 'need rest']):
            return 'add_rest_day'
        if any(w in r for w in ['repeat', 'duplicate', 'again']):
            return 'repeat_workout'
        if any(w in r for w in ['vacation', 'holiday', 'clear schedule', 'time off']):
            return 'vacation'
        if any(w in r for w in ['push', 'shift forward', 'push remaining']):
            return 'push_week'
        if any(w in r for w in ['change history', 'recent changes', 'what did i change']):
            return 'view_changes'
        if any(w in r for w in ['analyze', 'recovery analysis', 'suggest rest', 'check recovery']):
            return 'analyze_recovery'
        if any(w in r for w in ['apply rest', 'add those rest', 'apply recommendation']):
            return 'apply_rest_days'
        if any(w in r for w in ['need deload', 'should i deload', 'overtrained', 'check deload']):
            return 'check_deload'
        if any(w in r for w in ['apply deload', 'add deload']):
            return 'apply_deload'
        if any(w in r for w in ['deload', 'reduce intensity', 'lighter week']):
            return 'deload_week'
        if any(w in r for w in ['training load', 'fatigue', 'training history']):
            return 'view_training_load'
        return 'general'

    @function_tool
    async def view_progress(self, context: RunContext):
        """
        Call this when the user wants to view their progress, stats, or history.
        """
        logger.info("[MAIN MENU] User requested to view progress")
        return None, f"The user wants to see their progress. Acknowledge their request and let them know this feature is coming soon - they'll be able to see workout history, personal records, and progress charts. Keep it encouraging."

    @function_tool
    async def update_profile(self, context: RunContext):
        """
        Call this when the user wants to update their profile or settings.
        """
        logger.info("[MAIN MENU] User requested to update profile")
        return None, f"The user wants to update their profile. Say something like: 'profile updates are coming soon! For now, you can ask me to change specific things and I'll note them down.' Keep it helpful."

    @function_tool
    async def shutdown(self, context: RunContext):
        """
        Call this when the user wants to shut down, exit, turn off, or say goodbye.
        User might say: "shut down", "turn off", "exit", "goodbye", "I'm done",
        "quit", "close", "power off", "see you later"
        """
        logger.info("[MAIN MENU] User requested shutdown")

        # Signal main.py to initiate graceful shutdown
        self.state.set("shutdown_requested", True)
        self.state.save_state()

        self._log_function_call("shutdown", {}, "shutdown_requested")

        return None, (
            f"The user wants to shut down. Say a warm, brief goodbye to the user. "
            f"Something like: 'Take care great chatting with you! See you next time.' "
            f"Keep it friendly and natural — one or two sentences max."
        )
