from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from db.models import (
    KnowledgeGraphBlockTemplate,
    KnowledgeGraphConstraintRule,
    KnowledgeGraphExercise,
    KnowledgeGraphExerciseRelation,
    KnowledgeGraphProgressionTemplate,
    KnowledgeGraphSessionRole,
    KnowledgeGraphVersion,
)
from program_generator_v5.exercise_library import EXERCISE_LIBRARY
from program_generator_v5.schemas import ExerciseType, MuscleRole
from program_generator_v5.split_templates import SPLIT_TEMPLATES, get_split_for_config
from program_generator_v5.sport_mappings import SPORT_MAPPINGS

from .schemas import (
    KGBlockTemplate,
    KGConstraintRule,
    KGExercise,
    KGExerciseRelation,
    KGProgressionTemplate,
    KGSessionRole,
    KGSnapshot,
)


DEFAULT_KG_VERSION_LABEL = "v7_seed_v1"


def ensure_active_kg_snapshot(db: Session) -> KGSnapshot:
    version = (
        db.query(KnowledgeGraphVersion)
        .filter(KnowledgeGraphVersion.is_active.is_(True))
        .order_by(KnowledgeGraphVersion.id.desc())
        .first()
    )
    if version is None:
        version = seed_default_kg_snapshot(db)
    return load_kg_snapshot(db, version.version_label)


def build_fallback_snapshot() -> KGSnapshot:
    exercises = {}
    for exercise in EXERCISE_LIBRARY:
        exercises[exercise.id] = KGExercise(
            canonical_id=exercise.id,
            name=exercise.name,
            family_id=exercise.rotation_group,
            equipment_min=exercise.equipment_tier.value,
            difficulty=exercise.difficulty,
            movement_pattern=exercise.movement_pattern.value,
            exercise_type=exercise.exercise_type.value,
            rotation_group=exercise.rotation_group,
            bilateral=exercise.bilateral,
            vbt_eligible=exercise.vbt_eligible,
            tags=sorted(set(exercise.variation_tags + [exercise.exercise_type.value, exercise.movement_pattern.value])),
            fatigue={
                "axial_load": exercise.is_axial_loading,
                "systemic_fatigue": exercise.systemic_fatigue,
                "eccentric_stress": exercise.eccentric_stress.value,
                "grip_load": "high" if exercise.grip_intensive else "moderate",
            },
            stimulus={
                "muscles": [
                    {
                        "muscle": activation.muscle.value,
                        "role": activation.role.value,
                        "volume_credit": activation.volume_credit,
                    }
                    for activation in exercise.muscle_activations
                ],
                "primary_muscles": [
                    activation.muscle.value
                    for activation in exercise.muscle_activations
                    if activation.role == MuscleRole.PRIMARY
                ],
                "long_length_bias": exercise.trains_at_long_length,
            },
            constraints={
                "min_reps": exercise.min_reps,
                "max_reps": exercise.max_reps,
                "min_sets_per_session": exercise.min_sets_per_session,
                "max_sets_per_session": exercise.max_sets_per_session,
            },
            metadata={
                "sfr_rating": exercise.sfr_rating,
                "cues": list(exercise.cues),
                "common_mistakes": list(exercise.common_mistakes),
            },
        )

    relations = []
    grouped = defaultdict(list)
    for exercise in EXERCISE_LIBRARY:
        grouped[exercise.rotation_group].append(exercise.id)
    for exercise in EXERCISE_LIBRARY:
        for peer in grouped[exercise.rotation_group]:
            if peer == exercise.id:
                continue
            relations.append(KGExerciseRelation(
                src_id=exercise.id,
                relation_type="same_family",
                dst_id=peer,
                payload={"family_id": exercise.rotation_group},
            ))

    session_roles = {}
    for goal in ("hypertrophy", "strength", "power"):
        for split in SPLIT_TEMPLATES.values():
            if goal not in split.suitable_goals:
                continue
            for session in split.sessions_per_week:
                role_id = f"{goal}_{session.session_type}"
                session_roles[role_id] = KGSessionRole(
                    role_id=role_id,
                    label=f"{goal.title()} {session.day_label}",
                    session_type=session.session_type,
                    goal=goal,
                    required_patterns=[pattern.value for pattern in session.required_movement_patterns],
                    optional_patterns=[pattern.value for pattern in session.optional_movement_patterns],
                    target_muscles=[muscle.value for muscle in session.muscle_groups],
                    fatigue_budget="low" if goal == "power" else "moderate",
                    slot_budget=session.max_exercises,
                    sequencing_hints=_sequencing_hints_for_session(session.session_type, goal),
                    max_duration_minutes=session.max_duration_minutes,
                    metadata={"split_id": split.split_id, "is_primary": session.is_primary},
                )

    progression_templates = []
    family_representatives = {}
    for exercise in EXERCISE_LIBRARY:
        family_representatives.setdefault(exercise.rotation_group, exercise)
    role_groups = {
        "heavy_compound": "primary_strength",
        "light_compound": "secondary_strength_hypertrophy",
        "isolation": "isolation_volume",
        "power": "power_primer",
        "plyometric": "power_primer",
    }
    for family_id, exercise in family_representatives.items():
        for phase in ("accumulation", "transmutation", "realization", "deload"):
            for level in ("beginner", "intermediate", "advanced"):
                template = _build_progression_template(exercise.exercise_type.value, phase, level)
                progression_templates.append(KGProgressionTemplate(
                    family_id=family_id,
                    session_role=role_groups.get(exercise.exercise_type.value, "hypertrophy_accessory"),
                    goal_phase=phase,
                    training_level=level,
                    default_sets_by_week=list(template["default_sets_by_week"]),
                    rep_range=tuple(template["rep_range"]),
                    target_rpe_range=tuple(template["target_rpe_range"]),
                    anchor_duration_weeks=template["anchor_duration_weeks"],
                    metadata=dict(template.get("metadata", {})),
                ))

    block_templates = []
    for goal in ("hypertrophy", "strength", "power"):
        for days_per_week in range(2, 7):
            for season_context in ("standard", "in_season", "pre_season"):
                split_id = "maintenance_2x" if season_context == "in_season" else get_split_for_config(
                    days_per_week=days_per_week,
                    training_level="intermediate",
                    goal=goal,
                )
                split = SPLIT_TEMPLATES[split_id]
                block_templates.append(KGBlockTemplate(
                    template_id=f"{goal}_{days_per_week}d_{season_context}",
                    goal=goal,
                    phase=_periodization_for_context(goal, season_context),
                    duration_weeks=4,
                    days_per_week=days_per_week,
                    season_context=season_context,
                    periodization_model=_periodization_for_context(goal, season_context),
                    session_role_ids=[f"{goal}_{session.session_type}" for session in split.sessions_per_week],
                    template={
                        "split_id": split_id,
                        "session_role_ids": [f"{goal}_{session.session_type}" for session in split.sessions_per_week],
                        "phase_sequence": _default_phase_sequence(_periodization_for_context(goal, season_context)),
                    },
                ))

    constraint_rules = [
        KGConstraintRule(
            rule_id=f"sport_{sport}",
            rule_type="sport",
            subject_type="sport",
            subject_key=sport,
            config={
                "mandatory_movement_patterns": config.get("mandatory_movement_patterns", []),
                "forbidden_exercises": config.get("forbidden_exercises", []),
                "injury_prevention_additions": config.get("injury_prevention_additions", []),
                "interference_level": config.get("interference_level", "low"),
            },
        )
        for sport, config in SPORT_MAPPINGS.items()
    ]
    constraint_rules.extend([
        KGConstraintRule(
            rule_id="equipment_gate",
            rule_type="equipment",
            subject_type="system",
            subject_key="equipment_tier",
            config={"mode": "hard_filter"},
        ),
        KGConstraintRule(
            rule_id="in_season_eccentric_limit",
            rule_type="season",
            subject_type="system",
            subject_key="eccentric_stress",
            config={"mode": "penalty"},
        ),
    ])

    return KGSnapshot(
        version_id="fallback",
        version_label=f"{DEFAULT_KG_VERSION_LABEL}_fallback",
        exercises=exercises,
        relations=relations,
        session_roles=session_roles,
        progression_templates=progression_templates,
        block_templates=block_templates,
        constraint_rules=constraint_rules,
    )


def load_kg_snapshot(db: Session, version_label: str | None = None) -> KGSnapshot:
    version_query = db.query(KnowledgeGraphVersion)
    if version_label:
        version = version_query.filter(KnowledgeGraphVersion.version_label == version_label).first()
    else:
        version = version_query.filter(KnowledgeGraphVersion.is_active.is_(True)).first()
    if version is None:
        version = seed_default_kg_snapshot(db)

    exercises = {
        row.canonical_id: KGExercise(
            canonical_id=row.canonical_id,
            name=row.name,
            family_id=row.family_id,
            equipment_min=row.equipment_min,
            difficulty=row.difficulty,
            movement_pattern=row.movement_pattern,
            exercise_type=row.exercise_type,
            rotation_group=row.rotation_group,
            bilateral=row.bilateral,
            vbt_eligible=row.vbt_eligible,
            tags=list(row.tags or []),
            fatigue=dict(row.fatigue_json or {}),
            stimulus=dict(row.stimulus_json or {}),
            constraints=dict(row.constraints_json or {}),
            metadata=dict(row.metadata_json or {}),
        )
        for row in db.query(KnowledgeGraphExercise)
        .filter(KnowledgeGraphExercise.version_id == version.id)
        .all()
    }

    relations = [
        KGExerciseRelation(
            src_id=row.src_id,
            relation_type=row.relation_type,
            dst_id=row.dst_id,
            payload=dict(row.payload_json or {}),
        )
        for row in db.query(KnowledgeGraphExerciseRelation)
        .filter(KnowledgeGraphExerciseRelation.version_id == version.id)
        .all()
    ]

    session_roles = {
        row.role_id: KGSessionRole(
            role_id=row.role_id,
            label=row.label,
            session_type=row.session_type,
            goal=row.goal,
            required_patterns=list((row.config_json or {}).get("required_patterns", [])),
            optional_patterns=list((row.config_json or {}).get("optional_patterns", [])),
            target_muscles=list((row.config_json or {}).get("target_muscles", [])),
            fatigue_budget=(row.config_json or {}).get("fatigue_budget", "moderate"),
            slot_budget=(row.config_json or {}).get("slot_budget", 5),
            sequencing_hints=list((row.config_json or {}).get("sequencing_hints", [])),
            max_duration_minutes=(row.config_json or {}).get("max_duration_minutes", 60),
            metadata=dict((row.config_json or {}).get("metadata", {})),
        )
        for row in db.query(KnowledgeGraphSessionRole)
        .filter(KnowledgeGraphSessionRole.version_id == version.id)
        .all()
    }

    progression_templates = [
        KGProgressionTemplate(
            family_id=row.family_id,
            session_role=row.session_role,
            goal_phase=row.goal_phase,
            training_level=row.training_level,
            default_sets_by_week=list((row.template_json or {}).get("default_sets_by_week", [])),
            rep_range=tuple((row.template_json or {}).get("rep_range", [6, 10])),
            target_rpe_range=tuple((row.template_json or {}).get("target_rpe_range", [7.0, 9.0])),
            anchor_duration_weeks=(row.template_json or {}).get("anchor_duration_weeks", 4),
            metadata=dict((row.template_json or {}).get("metadata", {})),
        )
        for row in db.query(KnowledgeGraphProgressionTemplate)
        .filter(KnowledgeGraphProgressionTemplate.version_id == version.id)
        .all()
    ]

    block_templates = [
        KGBlockTemplate(
            template_id=row.template_id,
            goal=row.goal,
            phase=row.phase,
            duration_weeks=row.duration_weeks,
            days_per_week=row.days_per_week,
            season_context=row.season_context,
            periodization_model=row.periodization_model,
            session_role_ids=list((row.template_json or {}).get("session_role_ids", [])),
            template=dict(row.template_json or {}),
        )
        for row in db.query(KnowledgeGraphBlockTemplate)
        .filter(KnowledgeGraphBlockTemplate.version_id == version.id)
        .all()
    ]

    constraint_rules = [
        KGConstraintRule(
            rule_id=row.rule_id,
            rule_type=row.rule_type,
            subject_type=row.subject_type,
            subject_key=row.subject_key,
            config=dict(row.config_json or {}),
        )
        for row in db.query(KnowledgeGraphConstraintRule)
        .filter(KnowledgeGraphConstraintRule.version_id == version.id)
        .all()
    ]

    return KGSnapshot(
        version_id=str(version.id),
        version_label=version.version_label,
        exercises=exercises,
        relations=relations,
        session_roles=session_roles,
        progression_templates=progression_templates,
        block_templates=block_templates,
        constraint_rules=constraint_rules,
    )


def seed_default_kg_snapshot(db: Session) -> KnowledgeGraphVersion:
    existing = (
        db.query(KnowledgeGraphVersion)
        .filter(KnowledgeGraphVersion.version_label == DEFAULT_KG_VERSION_LABEL)
        .first()
    )
    if existing:
        _activate_version(db, existing)
        return existing

    version = KnowledgeGraphVersion(
        version_label=DEFAULT_KG_VERSION_LABEL,
        description="Seeded from V5 library, split templates, sport mappings, and volume tables.",
        is_active=True,
        metadata_json={"source": "program_generator_v5", "generator": "v7"},
    )
    db.add(version)
    db.flush()

    _seed_exercises(db, version.id)
    _seed_exercise_relations(db, version.id)
    _seed_session_roles(db, version.id)
    _seed_progression_templates(db, version.id)
    _seed_block_templates(db, version.id)
    _seed_constraint_rules(db, version.id)
    db.commit()
    db.refresh(version)
    _activate_version(db, version)
    return version


def _activate_version(db: Session, version: KnowledgeGraphVersion) -> None:
    db.query(KnowledgeGraphVersion).update({"is_active": False})
    version.is_active = True
    db.add(version)
    db.commit()
    db.refresh(version)


def _seed_exercises(db: Session, version_id: int) -> None:
    for exercise in EXERCISE_LIBRARY:
        tags = sorted(set(exercise.variation_tags + [exercise.exercise_type.value, exercise.movement_pattern.value]))
        stimulus = {
            "muscles": [
                {
                    "muscle": activation.muscle.value,
                    "role": activation.role.value,
                    "volume_credit": activation.volume_credit,
                }
                for activation in exercise.muscle_activations
            ],
            "primary_muscles": [
                activation.muscle.value
                for activation in exercise.muscle_activations
                if activation.role == MuscleRole.PRIMARY
            ],
            "long_length_bias": exercise.trains_at_long_length,
        }
        fatigue = {
            "axial_load": exercise.is_axial_loading,
            "systemic_fatigue": exercise.systemic_fatigue,
            "eccentric_stress": exercise.eccentric_stress.value,
            "grip_load": "high" if exercise.grip_intensive else "moderate",
        }
        constraints = {
            "min_reps": exercise.min_reps,
            "max_reps": exercise.max_reps,
            "min_sets_per_session": exercise.min_sets_per_session,
            "max_sets_per_session": exercise.max_sets_per_session,
            "requires_proficiency": exercise.requires_proficiency,
        }

        db.add(KnowledgeGraphExercise(
            version_id=version_id,
            canonical_id=exercise.id,
            name=exercise.name,
            family_id=exercise.rotation_group,
            equipment_min=exercise.equipment_tier.value,
            difficulty=exercise.difficulty,
            movement_pattern=exercise.movement_pattern.value,
            exercise_type=exercise.exercise_type.value,
            rotation_group=exercise.rotation_group,
            bilateral=exercise.bilateral,
            vbt_eligible=exercise.vbt_eligible,
            tags=tags,
            fatigue_json=fatigue,
            stimulus_json=stimulus,
            constraints_json=constraints,
            metadata_json={
                "sfr_rating": exercise.sfr_rating,
                "cues": list(exercise.cues),
                "common_mistakes": list(exercise.common_mistakes),
            },
        ))
    db.flush()


def _seed_exercise_relations(db: Session, version_id: int) -> None:
    by_group: dict[str, list[str]] = defaultdict(list)
    for exercise in EXERCISE_LIBRARY:
        by_group[exercise.rotation_group].append(exercise.id)

    for exercise in EXERCISE_LIBRARY:
        family_peers = [peer for peer in by_group[exercise.rotation_group] if peer != exercise.id]
        for peer in family_peers:
            db.add(KnowledgeGraphExerciseRelation(
                version_id=version_id,
                src_id=exercise.id,
                relation_type="same_family",
                dst_id=peer,
                payload_json={"family_id": exercise.rotation_group},
            ))
            db.add(KnowledgeGraphExerciseRelation(
                version_id=version_id,
                src_id=exercise.id,
                relation_type="substitutes_for",
                dst_id=peer,
                payload_json={"reason": "shared_rotation_group"},
            ))

        if "bodyweight" in exercise.variation_tags:
            continue
        if exercise.exercise_type == ExerciseType.HEAVY_COMPOUND:
            for peer in family_peers[:2]:
                db.add(KnowledgeGraphExerciseRelation(
                    version_id=version_id,
                    src_id=exercise.id,
                    relation_type="progresses_to",
                    dst_id=peer,
                    payload_json={"phase": "mesocycle_rotation"},
                ))
                db.add(KnowledgeGraphExerciseRelation(
                    version_id=version_id,
                    src_id=peer,
                    relation_type="regresses_to",
                    dst_id=exercise.id,
                    payload_json={"phase": "technique_or_recovery"},
                ))
    db.flush()


def _seed_session_roles(db: Session, version_id: int) -> None:
    goals = ("hypertrophy", "strength", "power")
    for goal in goals:
        for split in SPLIT_TEMPLATES.values():
            for session in split.sessions_per_week:
                if goal not in split.suitable_goals:
                    continue
                role_id = f"{goal}_{session.session_type}"
                label = f"{goal.replace('_', ' ').title()} {session.day_label}"
                fatigue_budget = "moderate"
                if "lower" in session.session_type or "legs" in session.session_type:
                    fatigue_budget = "moderate_high" if goal != "power" else "moderate"
                if goal == "power":
                    fatigue_budget = "low"
                db.add(KnowledgeGraphSessionRole(
                    version_id=version_id,
                    role_id=role_id,
                    label=label,
                    session_type=session.session_type,
                    goal=goal,
                    config_json={
                        "required_patterns": [pattern.value for pattern in session.required_movement_patterns],
                        "optional_patterns": [pattern.value for pattern in session.optional_movement_patterns],
                        "target_muscles": [muscle.value for muscle in session.muscle_groups],
                        "fatigue_budget": fatigue_budget,
                        "slot_budget": session.max_exercises,
                        "sequencing_hints": _sequencing_hints_for_session(session.session_type, goal),
                        "max_duration_minutes": session.max_duration_minutes,
                        "metadata": {
                            "split_id": split.split_id,
                            "is_primary": session.is_primary,
                        },
                    },
                ))
    db.flush()


def _seed_progression_templates(db: Session, version_id: int) -> None:
    family_representatives = {}
    for exercise in EXERCISE_LIBRARY:
        family_representatives.setdefault(exercise.rotation_group, exercise)

    role_groups = {
        "heavy_compound": "primary_strength",
        "light_compound": "secondary_strength_hypertrophy",
        "isolation": "isolation_volume",
        "power": "power_primer",
        "plyometric": "power_primer",
    }
    phases = ("accumulation", "transmutation", "realization", "deload")
    levels = ("beginner", "intermediate", "advanced")

    for family_id, exercise in family_representatives.items():
        session_role = role_groups.get(exercise.exercise_type.value, "hypertrophy_accessory")
        for phase in phases:
            for level in levels:
                db.add(KnowledgeGraphProgressionTemplate(
                    version_id=version_id,
                    family_id=family_id,
                    session_role=session_role,
                    goal_phase=phase,
                    training_level=level,
                    template_json=_build_progression_template(exercise.exercise_type.value, phase, level),
                ))
    db.flush()


def _seed_block_templates(db: Session, version_id: int) -> None:
    for goal in ("hypertrophy", "strength", "power"):
        for days_per_week in range(2, 7):
            for season_context in ("standard", "in_season", "pre_season"):
                split_id = "maintenance_2x" if season_context == "in_season" else get_split_for_config(
                    days_per_week=days_per_week,
                    training_level="intermediate",
                    goal=goal,
                )
                split = SPLIT_TEMPLATES[split_id]
                template_id = f"{goal}_{days_per_week}d_{season_context}"
                periodization_model = _periodization_for_context(goal, season_context)
                session_role_ids = [f"{goal}_{session.session_type}" for session in split.sessions_per_week]
                db.add(KnowledgeGraphBlockTemplate(
                    version_id=version_id,
                    template_id=template_id,
                    goal=goal,
                    phase=periodization_model,
                    duration_weeks=4,
                    days_per_week=days_per_week,
                    season_context=season_context,
                    periodization_model=periodization_model,
                    template_json={
                        "split_id": split_id,
                        "session_role_ids": session_role_ids,
                        "phase_sequence": _default_phase_sequence(periodization_model),
                    },
                ))
    db.flush()


def _seed_constraint_rules(db: Session, version_id: int) -> None:
    general_rules = [
        ("equipment_gate", "equipment", "system", "equipment_tier", {"mode": "hard_filter"}),
        ("difficulty_cap_age", "age", "system", "difficulty", {"mode": "hard_filter"}),
        ("in_season_eccentric_limit", "season", "system", "eccentric_stress", {"mode": "penalty"}),
        ("axial_load_spread", "fatigue", "system", "axial_load", {"mode": "weekly_balance"}),
    ]
    for rule_id, rule_type, subject_type, subject_key, config in general_rules:
        db.add(KnowledgeGraphConstraintRule(
            version_id=version_id,
            rule_id=rule_id,
            rule_type=rule_type,
            subject_type=subject_type,
            subject_key=subject_key,
            config_json=config,
        ))

    for sport, config in SPORT_MAPPINGS.items():
        db.add(KnowledgeGraphConstraintRule(
            version_id=version_id,
            rule_id=f"sport_{sport}",
            rule_type="sport",
            subject_type="sport",
            subject_key=sport,
            config_json={
                "mandatory_movement_patterns": config.get("mandatory_movement_patterns", []),
                "forbidden_exercises": config.get("forbidden_exercises", []),
                "injury_prevention_additions": config.get("injury_prevention_additions", []),
                "interference_level": config.get("interference_level", "low"),
                "volume_modifier": config.get("volume_modifier", 1.0),
            },
        ))
    db.flush()


def _sequencing_hints_for_session(session_type: str, goal: str) -> list[str]:
    hints = ["compounds_first", "lowest_skill_accessories_last"]
    if goal == "power":
        hints.insert(0, "power_first")
    if "upper" in session_type or "push" in session_type or "pull" in session_type:
        hints.append("alternate_push_pull_if_possible")
    return hints


def _build_progression_template(exercise_type: str, phase: str, level: str) -> dict:
    if exercise_type == "heavy_compound":
        rep_range = [3, 6]
        sets_map = {
            "accumulation": [4, 4, 5, 3],
            "transmutation": [4, 5, 5, 3],
            "realization": [3, 4, 4, 2],
            "deload": [2, 2, 2, 2],
        }
        rpe = [7.0, 9.0]
        anchor = 4
    elif exercise_type in {"power", "plyometric"}:
        rep_range = [2, 5]
        sets_map = {
            "accumulation": [3, 4, 4, 2],
            "transmutation": [3, 4, 5, 2],
            "realization": [3, 3, 4, 2],
            "deload": [2, 2, 2, 2],
        }
        rpe = [6.5, 8.5]
        anchor = 3
    elif exercise_type == "isolation":
        rep_range = [8, 15]
        sets_map = {
            "accumulation": [3, 3, 4, 2],
            "transmutation": [3, 4, 4, 2],
            "realization": [2, 3, 3, 2],
            "deload": [2, 2, 2, 2],
        }
        rpe = [7.5, 9.5]
        anchor = 2
    else:
        rep_range = [6, 10]
        sets_map = {
            "accumulation": [3, 4, 4, 2],
            "transmutation": [4, 4, 5, 2],
            "realization": [3, 3, 4, 2],
            "deload": [2, 2, 2, 2],
        }
        rpe = [7.0, 9.0]
        anchor = 3

    if level == "beginner":
        default_sets = [max(2, value - 1) for value in sets_map[phase]]
    elif level == "advanced":
        default_sets = [value + (0 if phase == "deload" else 1) for value in sets_map[phase]]
    else:
        default_sets = sets_map[phase]

    return {
        "default_sets_by_week": default_sets,
        "rep_range": rep_range,
        "target_rpe_range": rpe,
        "anchor_duration_weeks": anchor,
        "metadata": {"exercise_type": exercise_type},
    }


def _periodization_for_context(goal: str, season_context: str) -> str:
    if season_context == "in_season":
        return "maintenance"
    if season_context == "pre_season":
        return "block"
    if goal == "power":
        return "concurrent"
    if goal == "strength":
        return "dup"
    return "volume_ramp"


def _default_phase_sequence(periodization_model: str) -> list[str]:
    if periodization_model == "block":
        return ["accumulation", "transmutation", "realization", "deload"]
    if periodization_model == "maintenance":
        return ["maintenance", "maintenance", "maintenance", "maintenance"]
    if periodization_model == "concurrent":
        return ["accumulation", "accumulation", "transmutation", "deload"]
    return ["accumulation", "accumulation", "accumulation", "deload"]
