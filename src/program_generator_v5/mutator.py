"""
V5 Program Mutator — The Fix Engine

Safely mutates a BuiltProgram while maintaining volume and constraint integrity.
Used by Layer 4 (LLM review application) and Layer 5 (auto-fix engine).

Core Principle: Every mutation recalculates volume. If the mutation would cause
a constraint violation, it either adjusts to stay in bounds or rejects the mutation.

Implements:
- 8 Primitive Mutations: swap_exercise, add_exercise, remove_exercise, add_sets,
  remove_sets, reorder_session, move_exercise, replace_prescription
- 5 Compound Mutations: fix_volume_deficit, fix_volume_excess, fix_missing_movement_pattern,
  fix_push_pull_imbalance, redistribute_muscle_volume
- Batch mutation system with rollback
"""

from __future__ import annotations

import copy
from typing import Optional

from .schemas import (
    AthleteProfile,
    ProgramStrategy,
    VolumeAllocation,
    BuiltProgram,
    BuiltWeek,
    BuiltWorkout,
    PrescribedExercise,
    PrescribedSet,
    Exercise,
    ExerciseType,
    MovementPattern,
    MuscleGroup,
    MuscleRole,
    MutationRequest,
    MutationResult,
)
from .volume_tables import get_volume_targets
from .utils import prescribe_exercise, estimate_session_duration, sort_exercises_for_session


class ProgramMutator:
    """
    Safely mutates a BuiltProgram while maintaining volume and constraint integrity.
    Used by Layer 4 (LLM review application) and Layer 5 (auto-fix engine).
    """

    def __init__(
        self,
        program: BuiltProgram,
        profile: AthleteProfile,
        strategy: ProgramStrategy,
        volume_allocation: VolumeAllocation,
        exercise_library: dict[str, Exercise],
    ):
        self.program = program
        self.profile = profile
        self.strategy = strategy
        self.volume_allocation = volume_allocation
        self.library = exercise_library  # {exercise_id: Exercise}

        # Track all mutations applied
        self.mutation_log: list[MutationResult] = []

    # ─────────────────────────────────────────────────────────────────────────────
    # PRIMITIVE MUTATIONS
    # ─────────────────────────────────────────────────────────────────────────────

    def swap_exercise(
        self,
        week_num: int,
        session_day: int,
        old_exercise_id: str,
        new_exercise_id: str,
        new_sets: Optional[int] = None,
        source: str = "",
        reason: str = "",
        force: bool = False,
    ) -> MutationResult:
        """
        Replace one exercise with another in a specific session.

        Logic:
        1. Find the old exercise in the specified session
        2. Calculate volume that will be REMOVED (old exercise sets × volume_credits)
        3. Calculate volume that will be ADDED (new exercise sets × volume_credits)
        4. If new_sets is None, use the same set count as the old exercise
        5. Simulate the swap: compute new weekly volumes
        6. Check constraints (skipped if force=True)
        7. If constraints pass: apply swap, recalculate volumes, return success
        8. If constraints fail: try adjusting sets (±1-2) to fix. If still fails: reject

        Args:
            force: If True, skip MRV constraint checking (for critical pattern fixes)
        """
        # Get week and workout
        week = self._get_week(week_num)
        if not week:
            return self._failure_result("swap_exercise", f"Week {week_num} not found", source, reason)

        workout = self._get_workout(week, session_day)
        if not workout:
            return self._failure_result("swap_exercise", f"Session {session_day} not found in week {week_num}", source, reason)

        # Find old exercise
        old_ex_idx = None
        old_prescribed_ex = None
        for idx, ex in enumerate(workout.exercises):
            if ex.exercise_id == old_exercise_id:
                old_ex_idx = idx
                old_prescribed_ex = ex
                break

        if old_ex_idx is None:
            return self._failure_result("swap_exercise", f"Exercise {old_exercise_id} not found in session", source, reason)

        # Get new exercise from library
        if new_exercise_id not in self.library:
            return self._failure_result("swap_exercise", f"Exercise {new_exercise_id} not in library", source, reason)

        new_exercise = self.library[new_exercise_id]

        # Validate new exercise is available
        if new_exercise.equipment_tier.value > self.profile.equipment_tier.value:
            return self._failure_result("swap_exercise", f"Exercise {new_exercise_id} requires higher equipment tier", source, reason)

        if new_exercise_id in self.profile.exercises_to_avoid:
            return self._failure_result("swap_exercise", f"Exercise {new_exercise_id} is in avoid list", source, reason)

        # Determine set count
        sets_count = new_sets if new_sets is not None else old_prescribed_ex.total_sets
        sets_count = max(new_exercise.min_sets_per_session, min(new_exercise.max_sets_per_session, sets_count))

        # Snapshot volume before
        volume_before = self._calculate_week_volume(week_num)

        # Get week profile for prescription
        week_profile = self.strategy.week_profiles[week_num - 1] if week_num <= len(self.strategy.week_profiles) else self.strategy.week_profiles[0]

        # Create new prescribed exercise
        new_sets_list = prescribe_exercise(
            exercise=new_exercise,
            total_sets=sets_count,
            week_profile=week_profile,
            program_goal=self.profile.training_goal,
        )

        # Calculate muscle contributions
        muscle_contributions = {}
        for ma in new_exercise.muscle_activations:
            muscle_contributions[ma.muscle.value] = sets_count * ma.volume_credit

        new_prescribed_ex = PrescribedExercise(
            exercise_id=new_exercise.id,
            exercise_name=new_exercise.name,
            exercise_type=new_exercise.exercise_type,
            movement_pattern=new_exercise.movement_pattern,
            sets=new_sets_list,
            total_sets=sets_count,
            muscle_contributions=muscle_contributions,
            superset_group=old_prescribed_ex.superset_group,
            order_in_session=old_prescribed_ex.order_in_session,
            rationale=f"Swapped from {old_exercise_id}: {reason}",
        )

        # Apply swap
        workout.exercises[old_ex_idx] = new_prescribed_ex

        # Recalculate volumes
        self._recalculate_session_volume(workout)
        self._recalculate_week_volume(week)

        # Check constraints - use worsened check to allow fixes even with pre-existing violations
        if force:
            violations = []  # Skip constraint checking in force mode
        else:
            violations = self._check_constraints_worsened(week_num, volume_before)

        volume_after = self._calculate_week_volume(week_num)

        if violations and not force:
            # Try adjusting sets
            for adjustment in [-1, -2, 1]:
                adjusted_sets = sets_count + adjustment
                if adjusted_sets < new_exercise.min_sets_per_session or adjusted_sets > new_exercise.max_sets_per_session:
                    continue

                # Represcribe with adjusted sets
                new_sets_list = prescribe_exercise(
                    exercise=new_exercise,
                    total_sets=adjusted_sets,
                    week_profile=week_profile,
                    program_goal=self.profile.training_goal,
                )
                muscle_contributions = {}
                for ma in new_exercise.muscle_activations:
                    muscle_contributions[ma.muscle.value] = adjusted_sets * ma.volume_credit

                new_prescribed_ex.sets = new_sets_list
                new_prescribed_ex.total_sets = adjusted_sets
                new_prescribed_ex.muscle_contributions = muscle_contributions

                self._recalculate_session_volume(workout)
                self._recalculate_week_volume(week)

                violations = self._check_constraints_worsened(week_num, volume_before)
                if not violations:
                    volume_after = self._calculate_week_volume(week_num)
                    break

        result = MutationResult(
            success=len(violations) == 0,
            mutation_type="swap_exercise",
            description=f"Swapped {old_exercise_id} → {new_exercise_id} in Week {week_num} Day {session_day}",
            volume_before=volume_before,
            volume_after=volume_after,
            constraint_violations=violations,
            rollback_applied=False,
        )

        if not result.success:
            # Rollback - restore old exercise
            workout.exercises[old_ex_idx] = old_prescribed_ex
            self._recalculate_session_volume(workout)
            self._recalculate_week_volume(week)
            result.rollback_applied = True

        self.mutation_log.append(result)
        return result

    def add_exercise(
        self,
        week_num: int,
        session_day: int,
        exercise_id: str,
        sets: int,
        source: str = "",
        reason: str = "",
        force: bool = False,
    ) -> MutationResult:
        """
        Add a new exercise to a session.

        Logic:
        1. Verify exercise is available (tier, not avoided, not already in session)
        2. Verify sets >= exercise.min_sets_per_session
        3. Calculate volume that will be added
        4. Check: would any muscle exceed MRV? (skipped if force=True)
        5. Check: would session duration exceed time cap?
        6. Apply: add exercise, prescribe sets/reps, insert at correct position
        7. Recalculate session and week volumes

        Args:
            force: If True, skip MRV constraint checking (for critical pattern fixes)
        """
        week = self._get_week(week_num)
        if not week:
            return self._failure_result("add_exercise", f"Week {week_num} not found", source, reason)

        workout = self._get_workout(week, session_day)
        if not workout:
            return self._failure_result("add_exercise", f"Session {session_day} not found", source, reason)

        # Get exercise from library
        if exercise_id not in self.library:
            return self._failure_result("add_exercise", f"Exercise {exercise_id} not in library", source, reason)

        exercise = self.library[exercise_id]

        # Check already in session
        if any(ex.exercise_id == exercise_id for ex in workout.exercises):
            return self._failure_result("add_exercise", f"Exercise {exercise_id} already in session", source, reason)

        # Check equipment tier
        if exercise.equipment_tier.value > self.profile.equipment_tier.value:
            return self._failure_result("add_exercise", f"Exercise {exercise_id} requires higher equipment tier", source, reason)

        # Check avoid list
        if exercise_id in self.profile.exercises_to_avoid:
            return self._failure_result("add_exercise", f"Exercise {exercise_id} is in avoid list", source, reason)

        # Clamp sets
        sets = max(exercise.min_sets_per_session, min(exercise.max_sets_per_session, sets))

        # Snapshot volume before
        volume_before = self._calculate_week_volume(week_num)

        # Get week profile
        week_profile = self.strategy.week_profiles[week_num - 1] if week_num <= len(self.strategy.week_profiles) else self.strategy.week_profiles[0]

        # Create prescribed exercise
        sets_list = prescribe_exercise(
            exercise=exercise,
            total_sets=sets,
            week_profile=week_profile,
            program_goal=self.profile.training_goal,
        )

        muscle_contributions = {}
        for ma in exercise.muscle_activations:
            muscle_contributions[ma.muscle.value] = sets * ma.volume_credit

        new_prescribed_ex = PrescribedExercise(
            exercise_id=exercise.id,
            exercise_name=exercise.name,
            exercise_type=exercise.exercise_type,
            movement_pattern=exercise.movement_pattern,
            sets=sets_list,
            total_sets=sets,
            muscle_contributions=muscle_contributions,
            superset_group=None,
            order_in_session=len(workout.exercises) + 1,
            rationale=reason,
        )

        # Add exercise
        workout.exercises.append(new_prescribed_ex)

        # Sort and update session
        workout.exercises = sort_exercises_for_session(workout.exercises, self.profile.training_goal)

        # Recalculate
        self._recalculate_session_volume(workout)
        self._recalculate_week_volume(week)

        # Check constraints - use worsened check to allow fixes even with pre-existing violations
        if force:
            # Force mode: only check hard limits (time cap, per-exercise max sets)
            violations = []
        else:
            violations = self._check_constraints_worsened(week_num, volume_before)

        # Check time cap (hard limit - always checked)
        if workout.estimated_duration_minutes > self.profile.session_duration_minutes * 1.15:
            violations.append(f"Session exceeds time cap: {workout.estimated_duration_minutes} min")

        volume_after = self._calculate_week_volume(week_num)

        result = MutationResult(
            success=len(violations) == 0,
            mutation_type="add_exercise",
            description=f"Added {exercise_id} ({sets} sets) to Week {week_num} Day {session_day}",
            volume_before=volume_before,
            volume_after=volume_after,
            constraint_violations=violations,
            rollback_applied=False,
        )

        if not result.success:
            # Rollback - remove the exercise
            workout.exercises = [ex for ex in workout.exercises if ex.exercise_id != exercise_id]
            self._recalculate_session_volume(workout)
            self._recalculate_week_volume(week)
            result.rollback_applied = True

        self.mutation_log.append(result)
        return result

    def remove_exercise(
        self,
        week_num: int,
        session_day: int,
        exercise_id: str,
        source: str = "",
        reason: str = ""
    ) -> MutationResult:
        """
        Remove an exercise from a session entirely.

        Logic:
        1. Find the exercise in the session
        2. Calculate volume that will be lost
        3. Check: would any muscle fall below MEV after removal?
        4. Apply: remove exercise, recalculate volumes
        """
        week = self._get_week(week_num)
        if not week:
            return self._failure_result("remove_exercise", f"Week {week_num} not found", source, reason)

        workout = self._get_workout(week, session_day)
        if not workout:
            return self._failure_result("remove_exercise", f"Session {session_day} not found", source, reason)

        # Find exercise
        exercise_to_remove = None
        for ex in workout.exercises:
            if ex.exercise_id == exercise_id:
                exercise_to_remove = ex
                break

        if not exercise_to_remove:
            return self._failure_result("remove_exercise", f"Exercise {exercise_id} not in session", source, reason)

        # Snapshot
        volume_before = self._calculate_week_volume(week_num)

        # Remove exercise
        workout.exercises = [ex for ex in workout.exercises if ex.exercise_id != exercise_id]

        # Update order
        for i, ex in enumerate(workout.exercises):
            ex.order_in_session = i + 1

        # Recalculate
        self._recalculate_session_volume(workout)
        self._recalculate_week_volume(week)

        # Check constraints
        violations = self._check_constraints(week_num)

        volume_after = self._calculate_week_volume(week_num)

        result = MutationResult(
            success=len(violations) == 0,
            mutation_type="remove_exercise",
            description=f"Removed {exercise_id} from Week {week_num} Day {session_day}",
            volume_before=volume_before,
            volume_after=volume_after,
            constraint_violations=violations,
            rollback_applied=False,
        )

        if not result.success:
            # Rollback - add exercise back
            workout.exercises.append(exercise_to_remove)
            workout.exercises = sort_exercises_for_session(workout.exercises, self.profile.training_goal)
            self._recalculate_session_volume(workout)
            self._recalculate_week_volume(week)
            result.rollback_applied = True

        self.mutation_log.append(result)
        return result

    def add_sets(
        self,
        week_num: int,
        session_day: int,
        exercise_id: str,
        sets_to_add: int,
        source: str = "",
        reason: str = ""
    ) -> MutationResult:
        """
        Add sets to an existing exercise in a session.

        Logic:
        1. Find the exercise
        2. Check: would new total exceed exercise.max_sets_per_session?
        3. Check: would any muscle exceed MRV?
        4. Check: would session duration exceed time cap?
        5. Apply: add sets with same prescription, recalculate volumes
        """
        week = self._get_week(week_num)
        if not week:
            return self._failure_result("add_sets", f"Week {week_num} not found", source, reason)

        workout = self._get_workout(week, session_day)
        if not workout:
            return self._failure_result("add_sets", f"Session {session_day} not found", source, reason)

        # Find exercise
        target_ex = None
        for ex in workout.exercises:
            if ex.exercise_id == exercise_id:
                target_ex = ex
                break

        if not target_ex:
            return self._failure_result("add_sets", f"Exercise {exercise_id} not in session", source, reason)

        # Get exercise from library
        if exercise_id not in self.library:
            return self._failure_result("add_sets", f"Exercise {exercise_id} not in library", source, reason)

        exercise = self.library[exercise_id]

        # Check max sets
        new_total = target_ex.total_sets + sets_to_add
        if new_total > exercise.max_sets_per_session:
            sets_to_add = exercise.max_sets_per_session - target_ex.total_sets
            if sets_to_add <= 0:
                return self._failure_result("add_sets", f"Exercise already at max sets ({exercise.max_sets_per_session})", source, reason)
            new_total = exercise.max_sets_per_session

        # Snapshot
        volume_before = self._calculate_week_volume(week_num)
        old_sets = target_ex.total_sets
        old_sets_list = target_ex.sets.copy()
        old_muscle_contributions = target_ex.muscle_contributions.copy()

        # Add sets (copy last set prescription)
        if target_ex.sets:
            template_set = target_ex.sets[-1]
            for i in range(sets_to_add):
                new_set = PrescribedSet(
                    set_number=len(target_ex.sets) + 1,
                    reps=template_set.reps,
                    rpe=template_set.rpe,
                    rir=template_set.rir,
                    intensity_percent=template_set.intensity_percent,
                    rest_seconds=template_set.rest_seconds,
                    tempo=template_set.tempo,
                    notes="",
                )
                target_ex.sets.append(new_set)

        target_ex.total_sets = new_total

        # Update muscle contributions
        for ma in exercise.muscle_activations:
            target_ex.muscle_contributions[ma.muscle.value] = new_total * ma.volume_credit

        # Recalculate
        self._recalculate_session_volume(workout)
        self._recalculate_week_volume(week)

        # Check constraints - use worsened check to allow fixes even with pre-existing violations
        violations = self._check_constraints_worsened(week_num, volume_before)

        volume_after = self._calculate_week_volume(week_num)

        result = MutationResult(
            success=len(violations) == 0,
            mutation_type="add_sets",
            description=f"Added {sets_to_add} sets to {exercise_id} in Week {week_num} Day {session_day}",
            volume_before=volume_before,
            volume_after=volume_after,
            constraint_violations=violations,
            rollback_applied=False,
        )

        if not result.success:
            # Rollback
            target_ex.total_sets = old_sets
            target_ex.sets = old_sets_list
            target_ex.muscle_contributions = old_muscle_contributions
            self._recalculate_session_volume(workout)
            self._recalculate_week_volume(week)
            result.rollback_applied = True

        self.mutation_log.append(result)
        return result

    def remove_sets(
        self,
        week_num: int,
        session_day: int,
        exercise_id: str,
        sets_to_remove: int,
        source: str = "",
        reason: str = ""
    ) -> MutationResult:
        """
        Remove sets from an existing exercise.

        Logic:
        1. Find the exercise
        2. Check: would remaining sets be < exercise.min_sets_per_session?
           If yes: remove the whole exercise instead
        3. Check: would any muscle fall below MEV?
        4. Apply: remove last N sets, recalculate volumes
        """
        week = self._get_week(week_num)
        if not week:
            return self._failure_result("remove_sets", f"Week {week_num} not found", source, reason)

        workout = self._get_workout(week, session_day)
        if not workout:
            return self._failure_result("remove_sets", f"Session {session_day} not found", source, reason)

        # Find exercise
        target_ex = None
        for ex in workout.exercises:
            if ex.exercise_id == exercise_id:
                target_ex = ex
                break

        if not target_ex:
            return self._failure_result("remove_sets", f"Exercise {exercise_id} not in session", source, reason)

        # Get exercise from library
        if exercise_id not in self.library:
            return self._failure_result("remove_sets", f"Exercise {exercise_id} not in library", source, reason)

        exercise = self.library[exercise_id]

        # Check if we should remove the whole exercise
        new_total = target_ex.total_sets - sets_to_remove
        if new_total < exercise.min_sets_per_session:
            # Remove whole exercise instead
            return self.remove_exercise(week_num, session_day, exercise_id, source, reason)

        # Snapshot
        volume_before = self._calculate_week_volume(week_num)
        old_sets = target_ex.total_sets
        old_sets_list = target_ex.sets.copy()
        old_muscle_contributions = target_ex.muscle_contributions.copy()

        # Remove last N sets
        target_ex.sets = target_ex.sets[:-sets_to_remove] if sets_to_remove < len(target_ex.sets) else []
        target_ex.total_sets = new_total

        # Update set numbers
        for i, s in enumerate(target_ex.sets):
            s.set_number = i + 1

        # Update muscle contributions
        for ma in exercise.muscle_activations:
            target_ex.muscle_contributions[ma.muscle.value] = new_total * ma.volume_credit

        # Recalculate
        self._recalculate_session_volume(workout)
        self._recalculate_week_volume(week)

        # Check constraints
        violations = self._check_constraints(week_num)

        volume_after = self._calculate_week_volume(week_num)

        result = MutationResult(
            success=len(violations) == 0,
            mutation_type="remove_sets",
            description=f"Removed {sets_to_remove} sets from {exercise_id} in Week {week_num} Day {session_day}",
            volume_before=volume_before,
            volume_after=volume_after,
            constraint_violations=violations,
            rollback_applied=False,
        )

        if not result.success:
            # Rollback
            target_ex.total_sets = old_sets
            target_ex.sets = old_sets_list
            target_ex.muscle_contributions = old_muscle_contributions
            self._recalculate_session_volume(workout)
            self._recalculate_week_volume(week)
            result.rollback_applied = True

        self.mutation_log.append(result)
        return result

    def reorder_session(
        self,
        week_num: int,
        session_day: int,
        new_exercise_order: list[str],
        source: str = "",
        reason: str = ""
    ) -> MutationResult:
        """
        Reorder exercises within a session.

        Logic:
        1. Verify all exercise IDs in new_order match existing exercises
        2. Reorder exercises
        3. Update order_in_session field for each exercise
        4. No volume changes — this is always safe
        """
        week = self._get_week(week_num)
        if not week:
            return self._failure_result("reorder_session", f"Week {week_num} not found", source, reason)

        workout = self._get_workout(week, session_day)
        if not workout:
            return self._failure_result("reorder_session", f"Session {session_day} not found", source, reason)

        # Verify all IDs match
        current_ids = {ex.exercise_id for ex in workout.exercises}
        new_ids = set(new_exercise_order)

        if current_ids != new_ids:
            return self._failure_result("reorder_session", "Exercise IDs don't match current session", source, reason)

        # Create mapping
        exercise_map = {ex.exercise_id: ex for ex in workout.exercises}

        # Snapshot
        volume_before = self._calculate_week_volume(week_num)

        # Reorder
        workout.exercises = [exercise_map[ex_id] for ex_id in new_exercise_order]

        # Update order_in_session
        for i, ex in enumerate(workout.exercises):
            ex.order_in_session = i + 1

        volume_after = self._calculate_week_volume(week_num)

        result = MutationResult(
            success=True,
            mutation_type="reorder_session",
            description=f"Reordered exercises in Week {week_num} Day {session_day}",
            volume_before=volume_before,
            volume_after=volume_after,
            constraint_violations=[],
            rollback_applied=False,
        )

        self.mutation_log.append(result)
        return result

    def move_exercise(
        self,
        week_num: int,
        from_session_day: int,
        to_session_day: int,
        exercise_id: str,
        source: str = "",
        reason: str = ""
    ) -> MutationResult:
        """
        Move an exercise from one session to another within the same week.

        Logic:
        1. Remove exercise from source session
        2. Check: does destination session target this muscle group?
        3. Check: would destination session exceed time cap?
        4. Add exercise to destination session at correct position
        5. Recalculate both sessions' and the week's volumes
        """
        week = self._get_week(week_num)
        if not week:
            return self._failure_result("move_exercise", f"Week {week_num} not found", source, reason)

        from_workout = self._get_workout(week, from_session_day)
        to_workout = self._get_workout(week, to_session_day)

        if not from_workout:
            return self._failure_result("move_exercise", f"Source session {from_session_day} not found", source, reason)
        if not to_workout:
            return self._failure_result("move_exercise", f"Destination session {to_session_day} not found", source, reason)

        # Find exercise
        exercise_to_move = None
        for ex in from_workout.exercises:
            if ex.exercise_id == exercise_id:
                exercise_to_move = ex
                break

        if not exercise_to_move:
            return self._failure_result("move_exercise", f"Exercise {exercise_id} not in source session", source, reason)

        # Check if already in destination
        if any(ex.exercise_id == exercise_id for ex in to_workout.exercises):
            return self._failure_result("move_exercise", f"Exercise {exercise_id} already in destination", source, reason)

        # Snapshot
        volume_before = self._calculate_week_volume(week_num)

        # Move
        from_workout.exercises = [ex for ex in from_workout.exercises if ex.exercise_id != exercise_id]
        to_workout.exercises.append(exercise_to_move)

        # Update orders
        for i, ex in enumerate(from_workout.exercises):
            ex.order_in_session = i + 1

        to_workout.exercises = sort_exercises_for_session(to_workout.exercises, self.profile.training_goal)

        # Recalculate
        self._recalculate_session_volume(from_workout)
        self._recalculate_session_volume(to_workout)
        self._recalculate_week_volume(week)

        # Check constraints
        violations = self._check_constraints(week_num)

        # Check time cap on destination
        if to_workout.estimated_duration_minutes > self.profile.session_duration_minutes * 1.1:
            violations.append(f"Destination session exceeds time cap: {to_workout.estimated_duration_minutes} min")

        volume_after = self._calculate_week_volume(week_num)

        result = MutationResult(
            success=len(violations) == 0,
            mutation_type="move_exercise",
            description=f"Moved {exercise_id} from Day {from_session_day} to Day {to_session_day} in Week {week_num}",
            volume_before=volume_before,
            volume_after=volume_after,
            constraint_violations=violations,
            rollback_applied=False,
        )

        if not result.success:
            # Rollback
            to_workout.exercises = [ex for ex in to_workout.exercises if ex.exercise_id != exercise_id]
            from_workout.exercises.append(exercise_to_move)
            from_workout.exercises = sort_exercises_for_session(from_workout.exercises, self.profile.training_goal)
            self._recalculate_session_volume(from_workout)
            self._recalculate_session_volume(to_workout)
            self._recalculate_week_volume(week)
            result.rollback_applied = True

        self.mutation_log.append(result)
        return result

    def replace_prescription(
        self,
        week_num: int,
        session_day: int,
        exercise_id: str,
        new_sets: list[PrescribedSet],
        source: str = "",
        reason: str = ""
    ) -> MutationResult:
        """
        Replace the set/rep/rest prescription for an exercise.

        Logic:
        1. Find the exercise
        2. Replace its sets with new_sets
        3. Recalculate volume (set count may have changed)
        4. Validate constraints
        """
        week = self._get_week(week_num)
        if not week:
            return self._failure_result("replace_prescription", f"Week {week_num} not found", source, reason)

        workout = self._get_workout(week, session_day)
        if not workout:
            return self._failure_result("replace_prescription", f"Session {session_day} not found", source, reason)

        # Find exercise
        target_ex = None
        for ex in workout.exercises:
            if ex.exercise_id == exercise_id:
                target_ex = ex
                break

        if not target_ex:
            return self._failure_result("replace_prescription", f"Exercise {exercise_id} not in session", source, reason)

        # Get exercise from library
        if exercise_id not in self.library:
            return self._failure_result("replace_prescription", f"Exercise {exercise_id} not in library", source, reason)

        exercise = self.library[exercise_id]

        # Snapshot
        volume_before = self._calculate_week_volume(week_num)
        old_sets = target_ex.sets.copy()
        old_total = target_ex.total_sets
        old_contributions = target_ex.muscle_contributions.copy()

        # Replace
        target_ex.sets = new_sets
        target_ex.total_sets = len(new_sets)

        # Update muscle contributions
        for ma in exercise.muscle_activations:
            target_ex.muscle_contributions[ma.muscle.value] = target_ex.total_sets * ma.volume_credit

        # Recalculate
        self._recalculate_session_volume(workout)
        self._recalculate_week_volume(week)

        # Check constraints
        violations = self._check_constraints(week_num)

        volume_after = self._calculate_week_volume(week_num)

        result = MutationResult(
            success=len(violations) == 0,
            mutation_type="replace_prescription",
            description=f"Replaced prescription for {exercise_id} in Week {week_num} Day {session_day}",
            volume_before=volume_before,
            volume_after=volume_after,
            constraint_violations=violations,
            rollback_applied=False,
        )

        if not result.success:
            # Rollback
            target_ex.sets = old_sets
            target_ex.total_sets = old_total
            target_ex.muscle_contributions = old_contributions
            self._recalculate_session_volume(workout)
            self._recalculate_week_volume(week)
            result.rollback_applied = True

        self.mutation_log.append(result)
        return result

    # ─────────────────────────────────────────────────────────────────────────────
    # COMPOUND MUTATIONS
    # ─────────────────────────────────────────────────────────────────────────────

    def fix_volume_deficit(
        self,
        week_num: int,
        muscle: str,
        target_sets: float,
        current_sets: float,
        source: str = "",
        reason: str = ""
    ) -> MutationResult:
        """
        Fix a muscle group that's below MEV for a given week.

        Strategy (in order of preference):
        1. ADD SETS to an existing exercise that targets this muscle
        2. ADD A NEW EXERCISE for this muscle
        3. SWAP a low-priority exercise for one that targets this muscle
        """
        deficit = target_sets - current_sets
        if deficit <= 0:
            return self._failure_result("fix_volume_deficit", "No deficit to fix", source, reason)

        week = self._get_week(week_num)
        if not week:
            return self._failure_result("fix_volume_deficit", f"Week {week_num} not found", source, reason)

        volume_before = self._calculate_week_volume(week_num)

        # Strategy 1: Add sets to existing exercises
        for workout in week.workouts:
            for ex in workout.exercises:
                if ex.exercise_id in self.library:
                    exercise = self.library[ex.exercise_id]
                    # Check if exercise targets this muscle as primary
                    targets_muscle = any(
                        ma.muscle.value == muscle and ma.role == MuscleRole.PRIMARY
                        for ma in exercise.muscle_activations
                    )

                    if targets_muscle and ex.total_sets < exercise.max_sets_per_session:
                        sets_can_add = min(
                            exercise.max_sets_per_session - ex.total_sets,
                            int(deficit + 0.5)  # Round up
                        )

                        if sets_can_add > 0:
                            result = self.add_sets(
                                week_num, workout.day_number, ex.exercise_id, sets_can_add,
                                source, f"{reason} - adding sets to existing exercise"
                            )

                            if result.success:
                                # Check if deficit is fixed
                                new_volume = self._calculate_week_volume(week_num)
                                if new_volume.get(muscle, 0) >= target_sets - 0.5:
                                    return result
                                # Continue trying to fix remaining deficit
                                deficit = target_sets - new_volume.get(muscle, 0)

        # Strategy 2: Add a new exercise
        best_exercise = self._find_best_exercise_for_muscle(muscle, week_num)

        if best_exercise:
            # Find session with most room (fewest exercises)
            best_session = min(week.workouts, key=lambda w: len(w.exercises))

            sets_to_add = max(best_exercise.min_sets_per_session, min(int(deficit + 0.5), best_exercise.max_sets_per_session))

            result = self.add_exercise(
                week_num, best_session.day_number, best_exercise.id, sets_to_add,
                source, f"{reason} - adding new exercise for {muscle}"
            )

            if result.success:
                return result

        # Strategy 3: Swap a low-priority exercise
        for workout in week.workouts:
            lowest_priority = self._find_lowest_priority_exercise(week_num, workout.day_number, [muscle])

            if lowest_priority and best_exercise:
                result = self.swap_exercise(
                    week_num, workout.day_number, lowest_priority, best_exercise.id,
                    source=source, reason=f"{reason} - swapping for {muscle} coverage"
                )

                if result.success:
                    return result

        # Strategy 4: Allow duplicate exercises across sessions (last resort)
        # This is for cases where all exercises targeting the muscle are already used elsewhere in the week
        best_exercise_dup = self._find_best_exercise_for_muscle(muscle, week_num, allow_week_duplicates=True)

        if best_exercise_dup:
            # Find session with fewest exercises targeting this muscle
            best_session = min(week.workouts, key=lambda w: sum(
                1 for ex in w.exercises
                if ex.exercise_id in self.library and any(
                    ma.muscle.value == muscle for ma in self.library[ex.exercise_id].muscle_activations
                )
            ))

            # Check this exercise isn't already in this specific session
            already_in_session = any(ex.exercise_id == best_exercise_dup.id for ex in best_session.exercises)

            if not already_in_session:
                sets_to_add = max(best_exercise_dup.min_sets_per_session, min(int(deficit + 0.5), best_exercise_dup.max_sets_per_session))

                result = self.add_exercise(
                    week_num, best_session.day_number, best_exercise_dup.id, sets_to_add,
                    source, f"{reason} - adding duplicate exercise for {muscle} (Strategy 4)"
                )

                if result.success:
                    return result

        # Could not fix
        volume_after = self._calculate_week_volume(week_num)
        return MutationResult(
            success=False,
            mutation_type="fix_volume_deficit",
            description=f"Failed to fix {muscle} deficit in Week {week_num}",
            volume_before=volume_before,
            volume_after=volume_after,
            constraint_violations=[f"Could not add enough volume for {muscle}"],
            rollback_applied=False,
        )

    def fix_volume_excess(
        self,
        week_num: int,
        muscle: str,
        target_sets: float,
        current_sets: float,
        source: str = "",
        reason: str = ""
    ) -> MutationResult:
        """
        Fix a muscle group that's above MRV for a given week.

        Strategy:
        1. Find exercises targeting this muscle, sorted by SFR ascending (remove lowest quality first)
        2. Remove sets from the lowest-SFR exercise until excess is eliminated
        3. If that drops below min_sets_per_session, remove the exercise entirely
        """
        excess = current_sets - target_sets
        if excess <= 0:
            return self._failure_result("fix_volume_excess", "No excess to fix", source, reason)

        week = self._get_week(week_num)
        if not week:
            return self._failure_result("fix_volume_excess", f"Week {week_num} not found", source, reason)

        volume_before = self._calculate_week_volume(week_num)

        # Find all exercises targeting this muscle, sorted by SFR ascending
        candidates = []
        for workout in week.workouts:
            for ex in workout.exercises:
                if ex.exercise_id in self.library:
                    exercise = self.library[ex.exercise_id]
                    targets_muscle = any(
                        ma.muscle.value == muscle and ma.role == MuscleRole.PRIMARY
                        for ma in exercise.muscle_activations
                    )
                    if targets_muscle:
                        candidates.append((workout, ex, exercise.sfr_rating))

        # Sort by SFR ascending (remove lowest quality first)
        candidates.sort(key=lambda x: x[2])

        for workout, ex, sfr in candidates:
            exercise = self.library[ex.exercise_id]

            # Calculate how much volume this exercise contributes
            contribution = sum(
                ma.volume_credit * ex.total_sets
                for ma in exercise.muscle_activations
                if ma.muscle.value == muscle
            )

            if contribution <= excess:
                # Remove entire exercise
                result = self.remove_exercise(
                    week_num, workout.day_number, ex.exercise_id,
                    source, f"{reason} - removing to reduce {muscle} volume"
                )
                if result.success:
                    excess -= contribution
                    if excess <= 0.5:
                        return result
            else:
                # Remove some sets
                sets_to_remove = int(excess + 0.5)
                if sets_to_remove > 0:
                    result = self.remove_sets(
                        week_num, workout.day_number, ex.exercise_id, sets_to_remove,
                        source, f"{reason} - reducing {muscle} volume"
                    )
                    if result.success:
                        return result

        volume_after = self._calculate_week_volume(week_num)
        return MutationResult(
            success=False,
            mutation_type="fix_volume_excess",
            description=f"Failed to fix {muscle} excess in Week {week_num}",
            volume_before=volume_before,
            volume_after=volume_after,
            constraint_violations=[f"Could not reduce enough volume for {muscle}"],
            rollback_applied=False,
        )

    def fix_missing_movement_pattern(
        self,
        week_num: int,
        session_day: int,
        pattern: str,
        source: str = "",
        reason: str = ""
    ) -> MutationResult:
        """
        Add an exercise to cover a missing movement pattern in a session.

        Strategy:
        1. Find the best compound exercise for this pattern
        2. If session is at time cap: swap lowest-priority exercise
        3. Otherwise: add the exercise
        """
        week = self._get_week(week_num)
        if not week:
            return self._failure_result("fix_missing_movement_pattern", f"Week {week_num} not found", source, reason)

        workout = self._get_workout(week, session_day)
        if not workout:
            return self._failure_result("fix_missing_movement_pattern", f"Session {session_day} not found", source, reason)

        volume_before = self._calculate_week_volume(week_num)

        # Find best exercise for this pattern (try without duplicates first, then with)
        best_exercise = self._find_best_exercise_for_pattern(pattern, week_num)

        if not best_exercise:
            # Try allowing duplicates if no unique exercise found
            best_exercise = self._find_best_exercise_for_pattern(pattern, week_num, allow_week_duplicates=True)

        if not best_exercise:
            return MutationResult(
                success=False,
                mutation_type="fix_missing_movement_pattern",
                description=f"No available exercise for pattern {pattern}",
                volume_before=volume_before,
                volume_after=volume_before,
                constraint_violations=[f"No exercise available for {pattern}"],
                rollback_applied=False,
            )

        # Try to add exercise (force=True because pattern coverage is critical)
        sets = best_exercise.min_sets_per_session + 1  # Start with reasonable sets
        result = self.add_exercise(
            week_num, session_day, best_exercise.id, sets,
            source, f"{reason} - adding {pattern} pattern",
            force=True,  # Skip MRV checks for critical pattern fixes
        )

        if result.success:
            return result

        # Session likely at capacity - try swapping
        lowest_priority = self._find_lowest_priority_exercise(week_num, session_day)

        if lowest_priority:
            result = self.swap_exercise(
                week_num, session_day, lowest_priority, best_exercise.id,
                source=source, reason=f"{reason} - swapping for {pattern} pattern",
                force=True,  # Skip MRV checks for critical pattern fixes
            )
            return result

        return MutationResult(
            success=False,
            mutation_type="fix_missing_movement_pattern",
            description=f"Failed to add {pattern} pattern to Week {week_num} Day {session_day}",
            volume_before=volume_before,
            volume_after=self._calculate_week_volume(week_num),
            constraint_violations=["Could not add or swap for pattern"],
            rollback_applied=False,
        )

    def fix_push_pull_imbalance(
        self,
        week_num: int,
        push_sets: float,
        pull_sets: float,
        source: str = "",
        reason: str = ""
    ) -> MutationResult:
        """
        Fix push:pull ratio being outside 0.7-1.3 range.

        Strategy:
        If push-heavy (ratio > 1.3): add pulling volume or reduce pushing
        If pull-heavy (ratio < 0.7): add pushing volume or reduce pulling
        """
        week = self._get_week(week_num)
        if not week:
            return self._failure_result("fix_push_pull_imbalance", f"Week {week_num} not found", source, reason)

        volume_before = self._calculate_week_volume(week_num)

        if pull_sets == 0:
            # Add pulling volume
            return self.fix_volume_deficit(
                week_num, "lats", 8, 0, source, f"{reason} - adding pull volume"
            )

        ratio = push_sets / pull_sets

        if ratio > 1.3:
            # Need more pulling
            target_pull = push_sets / 1.1  # Aim for 1.1 ratio
            deficit = target_pull - pull_sets

            return self.fix_volume_deficit(
                week_num, "lats", target_pull, pull_sets,
                source, f"{reason} - adding pull to balance push:pull"
            )

        elif ratio < 0.7:
            # Need more pushing
            target_push = pull_sets * 0.9  # Aim for 0.9 ratio
            deficit = target_push - push_sets

            return self.fix_volume_deficit(
                week_num, "chest", target_push, push_sets,
                source, f"{reason} - adding push to balance push:pull"
            )

        # Already balanced
        return MutationResult(
            success=True,
            mutation_type="fix_push_pull_imbalance",
            description=f"Push:pull ratio already balanced ({ratio:.2f})",
            volume_before=volume_before,
            volume_after=volume_before,
            constraint_violations=[],
            rollback_applied=False,
        )

    def redistribute_muscle_volume(
        self,
        week_num: int,
        muscle: str,
        from_session_day: int,
        to_session_day: int,
        sets_to_move: int,
        source: str = "",
        reason: str = ""
    ) -> MutationResult:
        """
        Move volume for a specific muscle from one session to another.

        Logic:
        1. Find exercises in source session that target this muscle
        2. Pick the one with the most sets (or lowest priority)
        3. Either move the exercise or adjust set counts
        """
        week = self._get_week(week_num)
        if not week:
            return self._failure_result("redistribute_muscle_volume", f"Week {week_num} not found", source, reason)

        from_workout = self._get_workout(week, from_session_day)
        to_workout = self._get_workout(week, to_session_day)

        if not from_workout or not to_workout:
            return self._failure_result("redistribute_muscle_volume", "Session not found", source, reason)

        volume_before = self._calculate_week_volume(week_num)

        # Find exercises in source that target this muscle
        candidates = []
        for ex in from_workout.exercises:
            if ex.exercise_id in self.library:
                exercise = self.library[ex.exercise_id]
                targets_muscle = any(
                    ma.muscle.value == muscle
                    for ma in exercise.muscle_activations
                )
                if targets_muscle:
                    candidates.append((ex, exercise))

        if not candidates:
            return self._failure_result(
                "redistribute_muscle_volume",
                f"No exercises targeting {muscle} in source session",
                source, reason
            )

        # Pick exercise with lowest SFR (safest to move)
        candidates.sort(key=lambda x: x[1].sfr_rating)
        ex_to_move, exercise = candidates[0]

        if ex_to_move.total_sets <= sets_to_move:
            # Move entire exercise
            return self.move_exercise(
                week_num, from_session_day, to_session_day, ex_to_move.exercise_id,
                source, f"{reason} - redistributing {muscle} volume"
            )
        else:
            # Remove sets from source, add to destination
            # First remove from source
            result1 = self.remove_sets(
                week_num, from_session_day, ex_to_move.exercise_id, sets_to_move,
                source, f"{reason} - reducing {muscle} in source"
            )

            if not result1.success:
                return result1

            # Find exercise in destination that targets same muscle, or add new one
            dest_exercise = None
            for ex in to_workout.exercises:
                if ex.exercise_id in self.library:
                    lib_ex = self.library[ex.exercise_id]
                    if any(ma.muscle.value == muscle for ma in lib_ex.muscle_activations):
                        dest_exercise = ex
                        break

            if dest_exercise:
                result2 = self.add_sets(
                    week_num, to_session_day, dest_exercise.exercise_id, sets_to_move,
                    source, f"{reason} - adding {muscle} to destination"
                )
            else:
                # Add new exercise
                best_ex = self._find_best_exercise_for_muscle(muscle, week_num)
                if best_ex:
                    result2 = self.add_exercise(
                        week_num, to_session_day, best_ex.id, sets_to_move,
                        source, f"{reason} - adding {muscle} exercise to destination"
                    )
                else:
                    result2 = self._failure_result(
                        "redistribute_muscle_volume",
                        f"No exercise available for {muscle}",
                        source, reason
                    )

            volume_after = self._calculate_week_volume(week_num)
            return MutationResult(
                success=result2.success,
                mutation_type="redistribute_muscle_volume",
                description=f"Redistributed {sets_to_move} sets of {muscle} from Day {from_session_day} to Day {to_session_day}",
                volume_before=volume_before,
                volume_after=volume_after,
                constraint_violations=result2.constraint_violations,
                rollback_applied=result2.rollback_applied,
            )

    # ─────────────────────────────────────────────────────────────────────────────
    # BATCH MUTATION SYSTEM
    # ─────────────────────────────────────────────────────────────────────────────

    def apply_mutation_batch(self, mutations: list[MutationRequest]) -> list[MutationResult]:
        """
        Apply a batch of mutations in sequence, rolling back any that cause violations.

        Logic:
        1. Sort mutations by priority
        2. For each mutation: snapshot → apply → check → rollback if needed
        3. Return list of results
        """
        results = []

        # Sort by priority (critical fixes first)
        sorted_mutations = sorted(mutations, key=lambda m: self._mutation_priority(m))

        for mutation in sorted_mutations:
            # Snapshot
            snapshot = self._snapshot_week(mutation.week_number)

            # Apply
            result = self._apply_single_mutation(mutation)

            if not result.success:
                results.append(result)
                continue

            # Check constraints
            violations = self._check_constraints(mutation.week_number)

            if violations:
                # Rollback
                self._restore_snapshot(mutation.week_number, snapshot)
                result.success = False
                result.rollback_applied = True
                result.constraint_violations = violations

            results.append(result)

        return results

    def _apply_single_mutation(self, mutation: MutationRequest) -> MutationResult:
        """Dispatch a single mutation request to the appropriate method."""
        mt = mutation.mutation_type

        if mt == "swap_exercise":
            return self.swap_exercise(
                mutation.week_number, mutation.session_day,
                mutation.exercise_id, mutation.new_exercise_id,
                mutation.new_sets, source=mutation.source, reason=mutation.rationale
            )
        elif mt == "add_exercise":
            return self.add_exercise(
                mutation.week_number, mutation.session_day,
                mutation.new_exercise_id or mutation.exercise_id,
                mutation.new_sets or 3,
                source=mutation.source, reason=mutation.rationale
            )
        elif mt == "remove_exercise":
            return self.remove_exercise(
                mutation.week_number, mutation.session_day,
                mutation.exercise_id,
                source=mutation.source, reason=mutation.rationale
            )
        elif mt == "add_sets":
            return self.add_sets(
                mutation.week_number, mutation.session_day,
                mutation.exercise_id, mutation.new_sets or 1,
                source=mutation.source, reason=mutation.rationale
            )
        elif mt == "remove_sets":
            return self.remove_sets(
                mutation.week_number, mutation.session_day,
                mutation.exercise_id, mutation.new_sets or 1,
                source=mutation.source, reason=mutation.rationale
            )
        elif mt == "reorder_session":
            return self.reorder_session(
                mutation.week_number, mutation.session_day,
                mutation.new_order or [],
                source=mutation.source, reason=mutation.rationale
            )
        elif mt == "move_exercise":
            return self.move_exercise(
                mutation.week_number, mutation.session_day,
                mutation.target_session_day or mutation.session_day,
                mutation.exercise_id,
                source=mutation.source, reason=mutation.rationale
            )
        else:
            return self._failure_result(mt, f"Unknown mutation type: {mt}", mutation.source, mutation.rationale)

    def _mutation_priority(self, mutation: MutationRequest) -> int:
        """Return priority for sorting mutations (lower = higher priority)."""
        # Critical fixes first
        if "VOL_001" in mutation.rationale or "VOL_002" in mutation.rationale:
            return 0
        if "PAT_001" in mutation.rationale or "GOAL_" in mutation.rationale:
            return 1
        if "SES_" in mutation.rationale:
            return 2
        return 3

    def _snapshot_week(self, week_num: int) -> BuiltWeek:
        """Deep copy of a week's state for rollback."""
        week = self._get_week(week_num)
        if week:
            return week.model_copy(deep=True)
        return None

    def _restore_snapshot(self, week_num: int, snapshot: BuiltWeek) -> None:
        """Restore a week from snapshot."""
        if snapshot and week_num <= len(self.program.weeks):
            self.program.weeks[week_num - 1] = snapshot

    # ─────────────────────────────────────────────────────────────────────────────
    # VOLUME ACCOUNTING
    # ─────────────────────────────────────────────────────────────────────────────

    def _recalculate_session_volume(self, workout: BuiltWorkout) -> dict[str, float]:
        """Recalculate volume for a single session."""
        volume = {}
        for ex in workout.exercises:
            for muscle, contrib in ex.muscle_contributions.items():
                volume[muscle] = volume.get(muscle, 0) + contrib

        workout.volume_check = volume
        workout.volume_delivered = volume
        workout.total_sets = sum(ex.total_sets for ex in workout.exercises)
        workout.estimated_duration_minutes = estimate_session_duration(workout.exercises)

        return volume

    def _recalculate_week_volume(self, week: BuiltWeek) -> dict[str, float]:
        """Recalculate volume for an entire week."""
        weekly_volume = {}
        for workout in week.workouts:
            for muscle, vol in workout.volume_delivered.items():
                weekly_volume[muscle] = weekly_volume.get(muscle, 0) + vol

        week.weekly_volume_actual = weekly_volume

        # Update adherence if targets exist
        if week.weekly_volume_target:
            week.volume_adherence = {}
            for muscle, target in week.weekly_volume_target.items():
                actual = weekly_volume.get(muscle, 0)
                week.volume_adherence[muscle] = actual / target if target > 0 else 1.0

        return weekly_volume

    def _calculate_week_volume(self, week_num: int) -> dict[str, float]:
        """Get current weekly volume without modifying the program."""
        week = self._get_week(week_num)
        if not week:
            return {}

        volume = {}
        for workout in week.workouts:
            for ex in workout.exercises:
                for muscle, contrib in ex.muscle_contributions.items():
                    volume[muscle] = volume.get(muscle, 0) + contrib
        return volume

    def _check_constraints(self, week_num: int) -> list[str]:
        """Check all hard constraints for a week. Returns list of violations."""
        violations = []

        week = self._get_week(week_num)
        if not week:
            return ["Week not found"]

        # Check if deload
        is_deload = False
        if week_num <= len(self.strategy.week_profiles):
            is_deload = self.strategy.week_profiles[week_num - 1].is_deload

        weekly_volume = self._calculate_week_volume(week_num)

        # Check MEV (non-deload only) and MRV
        for muscle in MuscleGroup:
            muscle_key = muscle.value
            try:
                targets = get_volume_targets(self.profile.training_level, muscle_key)
            except ValueError:
                continue

            actual = weekly_volume.get(muscle_key, 0)

            # MEV check (non-deload)
            if not is_deload and actual < targets["mev"] - 1:
                violations.append(f"{muscle_key}: {actual:.1f} < MEV ({targets['mev']})")

            # MRV check (always)
            if actual > targets["mrv"] + 1:
                violations.append(f"{muscle_key}: {actual:.1f} > MRV ({targets['mrv']})")

        # Check per-exercise set cap
        for workout in week.workouts:
            for ex in workout.exercises:
                if ex.exercise_id in self.library:
                    exercise = self.library[ex.exercise_id]
                    if ex.total_sets > exercise.max_sets_per_session:
                        violations.append(f"{ex.exercise_name}: {ex.total_sets} > max {exercise.max_sets_per_session}")

        # Check per-muscle session cap (10 sets)
        for workout in week.workouts:
            muscle_sets = {}
            for ex in workout.exercises:
                for muscle, contrib in ex.muscle_contributions.items():
                    muscle_sets[muscle] = muscle_sets.get(muscle, 0) + contrib

            for muscle, sets in muscle_sets.items():
                if sets > 10:
                    violations.append(f"{workout.day_label}: {muscle} has {sets:.1f} sets (>10)")

        return violations

    def _check_constraints_worsened(
        self,
        week_num: int,
        volume_before: dict[str, float],
    ) -> list[str]:
        """
        Check if a mutation WORSENED constraints compared to before state.

        This is the key fix: mutations should only be rejected if they make things
        worse, not if pre-existing violations still exist.

        Returns list of violations that are NEW or WORSE than before.
        """
        new_violations = []

        week = self._get_week(week_num)
        if not week:
            return ["Week not found"]

        # Check if deload
        is_deload = False
        if week_num <= len(self.strategy.week_profiles):
            is_deload = self.strategy.week_profiles[week_num - 1].is_deload

        volume_after = self._calculate_week_volume(week_num)

        # Check MEV and MRV - only flag if mutation made things WORSE
        for muscle in MuscleGroup:
            muscle_key = muscle.value
            try:
                targets = get_volume_targets(self.profile.training_level, muscle_key)
            except ValueError:
                continue

            before = volume_before.get(muscle_key, 0)
            after = volume_after.get(muscle_key, 0)
            mev = targets["mev"]
            mrv = targets["mrv"]

            # MEV check - only flag if we went MORE below MEV than before
            if not is_deload:
                mev_gap_before = max(0, mev - before)  # How far below MEV before
                mev_gap_after = max(0, mev - after)    # How far below MEV after
                if mev_gap_after > mev_gap_before + 0.5:
                    new_violations.append(f"{muscle_key}: worsened MEV gap ({mev_gap_before:.1f} → {mev_gap_after:.1f})")

            # MRV check - only flag if we went MORE above MRV than before
            mrv_excess_before = max(0, before - mrv)  # How far above MRV before
            mrv_excess_after = max(0, after - mrv)    # How far above MRV after
            if mrv_excess_after > mrv_excess_before + 0.5:
                new_violations.append(f"{muscle_key}: worsened MRV excess ({mrv_excess_before:.1f} → {mrv_excess_after:.1f})")

        # Check per-exercise set cap (these should still block - they're hard limits)
        for workout in week.workouts:
            for ex in workout.exercises:
                if ex.exercise_id in self.library:
                    exercise = self.library[ex.exercise_id]
                    if ex.total_sets > exercise.max_sets_per_session:
                        new_violations.append(f"{ex.exercise_name}: {ex.total_sets} > max {exercise.max_sets_per_session}")

        # Check per-muscle session cap (10 sets) - hard limit, always block
        for workout in week.workouts:
            muscle_sets = {}
            for ex in workout.exercises:
                for muscle, contrib in ex.muscle_contributions.items():
                    muscle_sets[muscle] = muscle_sets.get(muscle, 0) + contrib

            for muscle, sets in muscle_sets.items():
                if sets > 12:  # Allow up to 12 (slightly relaxed from 10)
                    new_violations.append(f"{workout.day_label}: {muscle} has {sets:.1f} sets (>12)")

        return new_violations

    # ─────────────────────────────────────────────────────────────────────────────
    # HELPER FUNCTIONS
    # ─────────────────────────────────────────────────────────────────────────────

    def _get_week(self, week_num: int) -> Optional[BuiltWeek]:
        """Get a week by number (1-indexed)."""
        if 1 <= week_num <= len(self.program.weeks):
            return self.program.weeks[week_num - 1]
        return None

    def _get_workout(self, week: BuiltWeek, session_day: int) -> Optional[BuiltWorkout]:
        """Get a workout by day number within a week."""
        for workout in week.workouts:
            if workout.day_number == session_day:
                return workout
        return None

    def _failure_result(
        self,
        mutation_type: str,
        description: str,
        source: str,
        reason: str
    ) -> MutationResult:
        """Create a failure result."""
        return MutationResult(
            success=False,
            mutation_type=mutation_type,
            description=description,
            volume_before={},
            volume_after={},
            constraint_violations=[description],
            rollback_applied=False,
        )

    def _find_best_exercise_for_muscle(
        self,
        muscle: str,
        week_num: int,
        exclude_ids: list[str] = None,
        allow_week_duplicates: bool = False,
    ) -> Optional[Exercise]:
        """Find the best available exercise that targets a specific muscle group."""
        exclude_ids = exclude_ids or []

        # Get exercises already used this week (unless allowing duplicates)
        if not allow_week_duplicates:
            week = self._get_week(week_num)
            if week:
                for workout in week.workouts:
                    for ex in workout.exercises:
                        exclude_ids.append(ex.exercise_id)

        candidates = []
        for ex_id, exercise in self.library.items():
            # Check exclusions
            if ex_id in exclude_ids:
                continue
            if ex_id in self.profile.exercises_to_avoid:
                continue
            if exercise.equipment_tier.value > self.profile.equipment_tier.value:
                continue

            # Check difficulty
            difficulty_cap = {"beginner": 3, "intermediate": 4, "advanced": 5}[self.profile.training_level]
            if exercise.difficulty > difficulty_cap:
                continue

            # Check proficiency
            if exercise.requires_proficiency and self.profile.training_level == "beginner":
                continue

            # Must have muscle as primary
            has_primary = any(
                ma.muscle.value == muscle and ma.role == MuscleRole.PRIMARY
                for ma in exercise.muscle_activations
            )

            if has_primary:
                candidates.append(exercise)

        if not candidates:
            return None

        # Sort by SFR descending
        candidates.sort(key=lambda e: -e.sfr_rating)
        return candidates[0]

    def _find_best_exercise_for_pattern(
        self,
        pattern: str,
        week_num: int,
        exclude_ids: list[str] = None,
        allow_week_duplicates: bool = False,
    ) -> Optional[Exercise]:
        """Find the best available exercise for a movement pattern."""
        exclude_ids = exclude_ids or []

        # Get exercises already used this week (unless allowing duplicates)
        if not allow_week_duplicates:
            week = self._get_week(week_num)
            if week:
                for workout in week.workouts:
                    for ex in workout.exercises:
                        exclude_ids.append(ex.exercise_id)

        candidates = []
        for ex_id, exercise in self.library.items():
            # Check exclusions
            if ex_id in exclude_ids:
                continue
            if ex_id in self.profile.exercises_to_avoid:
                continue
            if exercise.equipment_tier.value > self.profile.equipment_tier.value:
                continue

            # Check difficulty
            difficulty_cap = {"beginner": 3, "intermediate": 4, "advanced": 5}[self.profile.training_level]
            if exercise.difficulty > difficulty_cap:
                continue

            # Must match pattern
            if exercise.movement_pattern.value == pattern:
                # Prefer compounds for pattern coverage
                if exercise.exercise_type in [ExerciseType.HEAVY_COMPOUND, ExerciseType.LIGHT_COMPOUND]:
                    candidates.append((exercise, 100))  # Compound bonus
                else:
                    candidates.append((exercise, 0))

        if not candidates:
            return None

        # Sort by compound bonus + SFR
        candidates.sort(key=lambda x: -(x[1] + x[0].sfr_rating))
        return candidates[0][0]

    def _find_lowest_priority_exercise(
        self,
        week_num: int,
        session_day: int,
        protect_muscles: list[str] = None
    ) -> Optional[str]:
        """Find the exercise in a session that is safest to remove or swap."""
        protect_muscles = protect_muscles or []

        week = self._get_week(week_num)
        if not week:
            return None

        workout = self._get_workout(week, session_day)
        if not workout:
            return None

        candidates = []
        for ex in workout.exercises:
            if ex.exercise_id not in self.library:
                continue

            exercise = self.library[ex.exercise_id]

            # Never remove heavy compounds or power exercises
            if exercise.exercise_type in [ExerciseType.HEAVY_COMPOUND, ExerciseType.POWER, ExerciseType.PLYOMETRIC]:
                continue

            # Check if exercise targets protected muscles
            targets_protected = any(
                ma.muscle.value in protect_muscles and ma.role == MuscleRole.PRIMARY
                for ma in exercise.muscle_activations
            )
            if targets_protected:
                continue

            # Calculate priority score (lower = more removable)
            score = 0
            if exercise.exercise_type == ExerciseType.ISOLATION:
                score -= 10  # Isolations are more removable
            if exercise.exercise_type == ExerciseType.LIGHT_COMPOUND:
                score -= 5

            # Check emphasis
            for ma in exercise.muscle_activations:
                if ma.muscle in self.strategy.emphasis_muscles:
                    score += 20  # Don't remove emphasis muscles
                if ma.muscle.value in self.profile.weak_points:
                    score += 20  # Don't remove weak point muscles

            score -= exercise.sfr_rating  # Lower SFR = more removable

            candidates.append((ex.exercise_id, score))

        if not candidates:
            return None

        # Return lowest score (most removable)
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]

    def _find_non_axial_alternative(
        self,
        exercise_id: str,
        week_num: int
    ) -> Optional[Exercise]:
        """Find a non-axial alternative to an axial exercise."""
        if exercise_id not in self.library:
            return None

        original = self.library[exercise_id]

        # Get primary muscles
        primary_muscles = [
            ma.muscle.value for ma in original.muscle_activations
            if ma.role == MuscleRole.PRIMARY
        ]

        # Get exercises already used this week
        week = self._get_week(week_num)
        exclude_ids = []
        if week:
            for workout in week.workouts:
                for ex in workout.exercises:
                    exclude_ids.append(ex.exercise_id)

        candidates = []
        for ex_id, exercise in self.library.items():
            if ex_id in exclude_ids:
                continue
            if ex_id in self.profile.exercises_to_avoid:
                continue
            if exercise.equipment_tier.value > self.profile.equipment_tier.value:
                continue

            # Must not be axial loading
            if exercise.is_axial_loading:
                continue

            # Should target similar muscles
            ex_primaries = [
                ma.muscle.value for ma in exercise.muscle_activations
                if ma.role == MuscleRole.PRIMARY
            ]

            overlap = set(primary_muscles) & set(ex_primaries)
            if overlap:
                candidates.append((exercise, len(overlap), exercise.sfr_rating))

        if not candidates:
            return None

        # Sort by muscle overlap then SFR
        candidates.sort(key=lambda x: (-x[1], -x[2]))
        return candidates[0][0]
