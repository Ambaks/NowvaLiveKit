from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Optional

from .schemas import KGExercise, KGProgressionTemplate, KGSnapshot, ProgramDirectiveV7, SessionSlot


class CandidateIndex:
    def __init__(self, snapshot: KGSnapshot):
        self.snapshot = snapshot
        self.by_pattern: dict[str, list[KGExercise]] = defaultdict(list)
        self.by_family: dict[str, list[KGExercise]] = defaultdict(list)
        self.by_canonical_id = snapshot.exercises
        self.relations_by_src: dict[tuple[str, str], list[str]] = defaultdict(list)

        for exercise in snapshot.exercises.values():
            self.by_pattern[exercise.movement_pattern].append(exercise)
            self.by_family[exercise.family_id].append(exercise)

        for relation in snapshot.relations:
            self.relations_by_src[(relation.src_id, relation.relation_type)].append(relation.dst_id)

    def query_candidates(
        self,
        slot: SessionSlot,
        directive: ProgramDirectiveV7,
        *,
        used_in_session: Iterable[str] = (),
        used_in_week: Iterable[str] = (),
        preferred_anchor_ids: Iterable[str] = (),
        top_k: int = 18,
    ) -> list[KGExercise]:
        excluded_ids = (
            set(directive.hard_constraints.forbidden_exercise_ids)
            | set(directive.derived_context.excluded_canonical_ids)
            | set(used_in_session)
        )
        candidate_pool = self._initial_pool(slot)
        filtered = []
        for exercise in candidate_pool:
            if exercise.canonical_id in excluded_ids:
                continue
            if exercise.equipment_min > directive.hard_constraints.equipment_tier:
                continue
            if exercise.difficulty > directive.derived_context.max_difficulty:
                continue
            if slot.required_pattern and exercise.movement_pattern != slot.required_pattern:
                continue
            if any(pattern == exercise.movement_pattern for pattern in directive.hard_constraints.forbidden_movement_patterns):
                continue
            if self._violates_fatigue_budget(exercise, slot.fatigue_budget, directive):
                continue
            filtered.append(exercise)

        def sort_key(exercise: KGExercise) -> tuple[float, float, float, str]:
            priority = 0.0
            if exercise.canonical_id in preferred_anchor_ids:
                priority += 3.5
            if exercise.canonical_id in slot.preferred_canonical_ids:
                priority += 3.0
            if exercise.family_id in slot.preferred_family_ids:
                priority += 2.0
            if exercise.canonical_id in directive.soft_preferences.liked_exercise_ids:
                priority += 2.0
            if exercise.canonical_id in used_in_week:
                priority -= 1.0
            if slot.slot_kind == "prehab" and "prehab" in exercise.tags:
                priority += 2.0
            if slot.slot_kind == "power" and exercise.exercise_type in {"power", "plyometric"}:
                priority += 2.5
            if slot.slot_kind == "isolation" and exercise.exercise_type == "isolation":
                priority += 1.5
            priority += float(exercise.metadata.get("sfr_rating", 0)) / 10.0
            return (-priority, exercise.equipment_min, exercise.difficulty, exercise.canonical_id)

        return sorted(filtered, key=sort_key)[:top_k]

    def get_related_ids(self, canonical_id: str, relation_type: str) -> list[str]:
        return list(self.relations_by_src.get((canonical_id, relation_type), []))

    def get_family_candidates(self, family_id: str) -> list[KGExercise]:
        return list(self.by_family.get(family_id, []))

    def get_progression_template(
        self,
        family_id: str,
        session_role_group: str,
        goal_phase: str,
        training_level: str,
    ) -> Optional[KGProgressionTemplate]:
        fallback = None
        for template in self.snapshot.progression_templates:
            if template.family_id != family_id:
                continue
            if template.training_level != training_level:
                continue
            if template.goal_phase == goal_phase and template.session_role == session_role_group:
                return template
            if template.goal_phase == goal_phase and fallback is None:
                fallback = template
            elif fallback is None and template.session_role == session_role_group:
                fallback = template
        return fallback

    def lookup_block_template(
        self,
        goal: str,
        phase: str,
        duration_weeks: int,
        days_per_week: int,
        season_context: str,
    ):
        for template in self.snapshot.block_templates:
            if template.goal != goal:
                continue
            if template.days_per_week != days_per_week:
                continue
            if template.season_context != season_context:
                continue
            if template.duration_weeks != min(duration_weeks, template.duration_weeks):
                continue
            if template.phase == phase:
                return template
        return None

    def _initial_pool(self, slot: SessionSlot) -> list[KGExercise]:
        if slot.required_pattern:
            pool = list(self.by_pattern.get(slot.required_pattern, []))
        else:
            pool = list(self.snapshot.exercises.values())
        if slot.preferred_family_ids:
            preferred = []
            remainder = []
            preferred_set = set(slot.preferred_family_ids)
            for exercise in pool:
                if exercise.family_id in preferred_set:
                    preferred.append(exercise)
                else:
                    remainder.append(exercise)
            return preferred + remainder
        return pool

    def _violates_fatigue_budget(
        self,
        exercise: KGExercise,
        fatigue_budget: str,
        directive: ProgramDirectiveV7,
    ) -> bool:
        fatigue = exercise.fatigue
        systemic = fatigue.get("systemic_fatigue", "moderate")
        if fatigue_budget in {"low", "very_low"} and systemic == "high":
            return True
        if directive.derived_context.fatigue_sensitivity in {"high", "moderate_high"}:
            if systemic == "high" and fatigue_budget != "high":
                return True
        if "in_season_recovery" in directive.derived_context.risk_flags:
            if fatigue.get("eccentric_stress") == "high" and fatigue_budget != "high":
                return True
        return False
