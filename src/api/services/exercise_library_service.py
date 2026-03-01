"""
Exercise Library Service

Loads and filters the exercise library based on user constraints.
Singleton pattern for efficient memory usage.
"""

import json
import os
from typing import Dict, List, Optional, Set
from pathlib import Path

from ..schemas.v3_schemas import (
    ExerciseDefinition,
    NormalizedUserProfile,
    InjuryConstraint,
    JointStress
)


class ExerciseLibraryService:
    """
    Singleton service for exercise library operations.

    Loads exercise_library.json once and provides filtering methods.
    """

    _instance = None
    _exercises: Dict[str, ExerciseDefinition] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_library()
        return cls._instance

    def _load_library(self):
        """Load exercise library from JSON file"""
        # Find exercise_library.json in project root
        current_dir = Path(__file__).resolve().parent
        project_root = current_dir.parent.parent.parent  # Go up to NowvaLiveKit/
        library_path = project_root / "exercise_library.json"

        if not library_path.exists():
            raise FileNotFoundError(
                f"exercise_library.json not found at {library_path}"
            )

        with open(library_path, 'r') as f:
            data = json.load(f)

        # Convert JSON to ExerciseDefinition objects
        self._exercises = {}
        for ex_data in data:
            try:
                # Map JSON structure to Pydantic model
                exercise = ExerciseDefinition(
                    id=ex_data["id"],
                    name=ex_data["name"],
                    modality=ex_data["modality"],
                    movement_pattern=ex_data["movement_pattern"],
                    exercise_type=ex_data["exercise_type"],
                    primary_muscles=ex_data["primary_muscles"],
                    secondary_muscles=ex_data["secondary_muscles"],
                    stabilizers=ex_data["stabilizers"],
                    joint_stress=JointStress(**ex_data["joint_stress"]),
                    force_vector=ex_data["force_vector"],
                    stance=ex_data["stance"],
                    loading_position=ex_data["loading_position"],
                    equipment=ex_data["equipment"],
                    equipment_optional=ex_data["equipment_optional"],
                    skill_level=ex_data["skill_level"],
                    stability_demand=ex_data["stability_demand"],
                    mobility_prerequisites=ex_data["mobility_prerequisites"],
                    typical_rep_range=ex_data["typical_rep_range"],
                    tempo_sensitive=ex_data["tempo_sensitive"],
                    eccentric_overload_suitable=ex_data["eccentric_overload_suitable"],
                    fatigue_profile=ex_data["fatigue_profile"],
                    cns_demand=ex_data["cns_demand"],
                    good_for_goals=ex_data["good_for_goals"],
                    contraindications=ex_data["contraindications"],
                    progression_friendly=ex_data["progression_friendly"],
                    regression_of=ex_data["regression_of"],
                    progression_to=ex_data["progression_to"],
                    substitutes=ex_data["substitutes"],
                    supersets_well_with=ex_data["supersets_well_with"],
                    warmup_suitable=ex_data["warmup_suitable"],
                    finisher_suitable=ex_data["finisher_suitable"],
                    coaching_cues=ex_data["coaching_cues"],
                    common_mistakes=ex_data["common_mistakes"],
                    bodyweight_progression_method=ex_data["bodyweight_progression_method"],
                    tags=ex_data["tags"]
                )
                self._exercises[exercise.id] = exercise
            except Exception as e:
                print(f"Warning: Failed to load exercise {ex_data.get('id', 'unknown')}: {e}")
                continue

        print(f"✅ Loaded {len(self._exercises)} exercises from library")

    def get_all_exercises(self) -> Dict[str, ExerciseDefinition]:
        """Get all exercises in library"""
        return self._exercises.copy()

    def get_exercise(self, exercise_id: str) -> Optional[ExerciseDefinition]:
        """Get a specific exercise by ID"""
        return self._exercises.get(exercise_id)

    def filter_for_user(
        self,
        profile: NormalizedUserProfile,
        additional_modalities: Optional[List[str]] = None
    ) -> Dict[str, ExerciseDefinition]:
        """
        Filter exercise library based on user profile constraints.

        Args:
            profile: Normalized user profile with constraints
            additional_modalities: Extra equipment modalities user has access to

        Returns:
            Dict of exercise_id -> ExerciseDefinition for valid exercises
        """
        filtered = {}

        # Build forbidden exercise set from injuries
        forbidden_ids = self._build_forbidden_exercise_set(profile.injury_constraints)

        # Determine allowed modalities
        allowed_modalities = self._determine_allowed_modalities(
            profile,
            additional_modalities
        )

        # Build joint stress limits from injuries
        joint_stress_limits = self._build_joint_stress_limits(profile.injury_constraints)

        for ex_id, exercise in self._exercises.items():
            # Check if exercise is explicitly forbidden
            if ex_id in forbidden_ids:
                continue

            # Check modality (equipment availability)
            if exercise.modality not in allowed_modalities:
                continue

            # Check fitness level requirement
            if not self._meets_fitness_level(exercise, profile.fitness_level):
                continue

            # Check goal suitability
            if not self._suitable_for_goal(exercise, profile.goal_category):
                continue

            # Check contraindications against user injuries
            if self._has_contraindication_conflict(exercise, profile.injury_constraints):
                continue

            # Check joint stress limits
            if not self._meets_joint_stress_limits(exercise, joint_stress_limits):
                continue

            # Exercise passes all filters
            filtered[ex_id] = exercise

        return filtered

    def _build_forbidden_exercise_set(
        self,
        injury_constraints: List[InjuryConstraint]
    ) -> Set[str]:
        """Build set of exercise IDs that are forbidden due to injuries"""
        forbidden = set()
        for constraint in injury_constraints:
            forbidden.update(constraint.forbidden_exercise_ids)
        return forbidden

    def _determine_allowed_modalities(
        self,
        profile: NormalizedUserProfile,
        additional_modalities: Optional[List[str]]
    ) -> Set[str]:
        """
        Determine which equipment modalities user has access to.

        Default: barbell, bodyweight, plyometric
        Additional: Based on user_notes or explicit parameter
        NEVER allows: machines (permanently blacklisted)
        """
        # Always allowed
        allowed = {"barbell", "bodyweight", "plyometric"}

        # Check user preferences for additional equipment
        for pref in profile.user_preferences:
            pref_lower = pref.lower()
            if "dumbbell" in pref_lower:
                allowed.add("dumbbell")
            if "cable" in pref_lower:
                allowed.add("cable")
            if "kettlebell" in pref_lower:
                allowed.add("kettlebell")
            if "band" in pref_lower:
                allowed.add("band")
            # Machine handling removed - never allow machines

        # Add explicitly specified modalities (except machines)
        if additional_modalities:
            # Filter out machines from additional modalities
            allowed.update([m for m in additional_modalities if m != "machine"])

        return allowed

    def _build_joint_stress_limits(
        self,
        injury_constraints: List[InjuryConstraint]
    ) -> Dict[str, str]:
        """
        Build maximum acceptable joint stress levels from injuries.

        Returns: {joint_name: max_acceptable_stress_level}
        """
        limits = {}

        # Map injury body parts to joints and stress limits
        injury_to_joint_map = {
            "shoulder": ("shoulder", "low"),
            "right_shoulder": ("shoulder", "low"),
            "left_shoulder": ("shoulder", "low"),
            "elbow": ("elbow", "low"),
            "wrist": ("wrist", "low"),
            "lower_back": ("spine", "medium"),
            "back": ("spine", "medium"),
            "knee": ("knee", "medium"),
            "right_knee": ("knee", "medium"),
            "left_knee": ("knee", "medium"),
            "ankle": ("ankle", "medium"),
            "hip": ("hip", "medium"),
        }

        for constraint in injury_constraints:
            body_part = constraint.body_part.lower()
            if body_part in injury_to_joint_map:
                joint, max_stress = injury_to_joint_map[body_part]
                # Take the most restrictive limit if multiple injuries affect same joint
                if joint not in limits:
                    limits[joint] = max_stress
                elif max_stress == "low":
                    limits[joint] = "low"

        return limits

    def _meets_fitness_level(
        self,
        exercise: ExerciseDefinition,
        user_level: str
    ) -> bool:
        """Check if user's fitness level is sufficient for exercise"""
        level_hierarchy = {"beginner": 1, "intermediate": 2, "advanced": 3}
        user_level_num = level_hierarchy[user_level]
        required_level_num = level_hierarchy[exercise.skill_level]
        return user_level_num >= required_level_num

    def _suitable_for_goal(
        self,
        exercise: ExerciseDefinition,
        goal: str
    ) -> bool:
        """Check if exercise is suitable for user's goal"""
        # Map goal_category to good_for_goals values
        goal_mapping = {
            "power": ["power"],
            "strength": ["strength"],
            "hypertrophy": ["hypertrophy"],
            "athletic_performance": ["athleticism", "power", "strength"],
        }

        required_goals = goal_mapping.get(goal, [])
        return any(g in exercise.good_for_goals for g in required_goals)

    def _has_contraindication_conflict(
        self,
        exercise: ExerciseDefinition,
        injury_constraints: List[InjuryConstraint]
    ) -> bool:
        """Check if exercise has contraindications that conflict with user injuries"""
        for constraint in injury_constraints:
            # Check if any contraindication matches the injury
            for contraindication in exercise.contraindications:
                contraindication_lower = contraindication.lower()
                body_part_lower = constraint.body_part.lower()
                injury_type_lower = constraint.injury_type.lower()

                # Check for matches
                if body_part_lower in contraindication_lower:
                    return True
                if injury_type_lower in contraindication_lower:
                    return True

        return False

    def _meets_joint_stress_limits(
        self,
        exercise: ExerciseDefinition,
        limits: Dict[str, str]
    ) -> bool:
        """Check if exercise joint stress is within acceptable limits"""
        if not limits:
            return True

        stress_hierarchy = {"none": 0, "low": 1, "medium": 2, "high": 3}

        for joint, max_stress in limits.items():
            max_stress_num = stress_hierarchy[max_stress]
            actual_stress = getattr(exercise.joint_stress, joint)
            actual_stress_num = stress_hierarchy[actual_stress]

            if actual_stress_num > max_stress_num:
                return False

        return True

    def get_exercises_by_movement_pattern(
        self,
        movement_pattern: str,
        filtered_exercises: Optional[Dict[str, ExerciseDefinition]] = None
    ) -> List[ExerciseDefinition]:
        """Get all exercises matching a movement pattern"""
        exercises = filtered_exercises or self._exercises
        return [
            ex for ex in exercises.values()
            if ex.movement_pattern == movement_pattern
        ]

    def get_exercises_by_type(
        self,
        exercise_type: str,
        filtered_exercises: Optional[Dict[str, ExerciseDefinition]] = None
    ) -> List[ExerciseDefinition]:
        """Get all exercises of a specific type (compound, isolation, isometric)"""
        exercises = filtered_exercises or self._exercises
        return [
            ex for ex in exercises.values()
            if ex.exercise_type == exercise_type
        ]

    def get_exercises_by_muscle(
        self,
        muscle_group: str,
        filtered_exercises: Optional[Dict[str, ExerciseDefinition]] = None
    ) -> List[ExerciseDefinition]:
        """Get all exercises that work a specific muscle group"""
        exercises = filtered_exercises or self._exercises
        return [
            ex for ex in exercises.values()
            if muscle_group in ex.primary_muscles or muscle_group in ex.secondary_muscles
        ]

    def get_category_counts(
        self,
        filtered_exercises: Dict[str, ExerciseDefinition]
    ) -> Dict[str, int]:
        """
        Get counts of exercises by category for LLM context.

        Returns: Dict with counts by movement_pattern, exercise_type, etc.
        """
        from collections import Counter

        movement_patterns = Counter([ex.movement_pattern for ex in filtered_exercises.values()])
        exercise_types = Counter([ex.exercise_type for ex in filtered_exercises.values()])

        return {
            "total_exercises": len(filtered_exercises),
            "by_movement_pattern": dict(movement_patterns),
            "by_type": dict(exercise_types),
        }

    def get_substitutes_for_exercise(
        self,
        exercise_id: str,
        filtered_exercises: Dict[str, ExerciseDefinition]
    ) -> List[ExerciseDefinition]:
        """Get valid substitute exercises from filtered set"""
        exercise = self._exercises.get(exercise_id)
        if not exercise:
            return []

        substitutes = []
        for sub_id in exercise.substitutes:
            if sub_id in filtered_exercises:
                substitutes.append(filtered_exercises[sub_id])

        return substitutes

    def estimate_exercise_time_seconds(
        self,
        exercise: ExerciseDefinition,
        num_sets: int,
        reps_per_set: int,
        rest_seconds: int
    ) -> int:
        """
        Estimate time for an exercise based on volume and rest.

        Returns: Estimated time in seconds
        """
        # Estimate work time per rep (varies by exercise type)
        if exercise.exercise_type == "compound":
            seconds_per_rep = 4  # Slower, more controlled
        elif exercise.exercise_type == "isolation":
            seconds_per_rep = 3
        elif exercise.exercise_type == "isometric":
            seconds_per_rep = 10  # Holds
        else:
            seconds_per_rep = 4

        # Work time per set
        work_time_per_set = reps_per_set * seconds_per_rep

        # Total time = (work time + rest) × sets - one rest period
        total_time = (work_time_per_set + rest_seconds) * num_sets - rest_seconds

        # Add setup/transition time
        setup_time = 30  # 30 seconds per exercise

        return total_time + setup_time


# Singleton instance
_exercise_service = None


def get_exercise_library_service() -> ExerciseLibraryService:
    """Get the singleton exercise library service instance"""
    global _exercise_service
    if _exercise_service is None:
        _exercise_service = ExerciseLibraryService()
    return _exercise_service
