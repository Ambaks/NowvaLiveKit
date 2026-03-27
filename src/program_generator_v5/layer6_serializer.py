"""
V5 Layer 6: Serializer

Converts V5 BuiltProgram → output JSON format.
100% deterministic — pure data mapping, no LLM.

Output format is a clean JSON structure ready for:
- API responses
- Database storage
- PDF rendering

NOTE: The V3 CompletedProgram schema mapping would be plugged in here
when integrating with the existing API. For now, we output a well-structured
dict that contains all the program information.
"""

from __future__ import annotations

from typing import Optional

from .schemas import (
    AthleteProfile,
    ProgramStrategy,
    BuiltProgram,
    BuiltWeek,
    BuiltWorkout,
    PrescribedExercise,
    PrescribedSet,
)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN SERIALIZATION ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────


def serialize_to_v3(
    program: BuiltProgram,
    validation_issues: list[dict] = None,
    llm_review: dict = None,
) -> dict:
    """
    Convert BuiltProgram to output JSON format.

    This produces a well-structured dict that can be:
    - Returned via API
    - Stored in database
    - Rendered as PDF

    Args:
        program: The completed BuiltProgram
        validation_issues: List of validation issues from Layer 5
        llm_review: LLM review results from Layer 5

    Returns:
        dict: Complete program in serialized format
    """
    validation_issues = validation_issues or []
    llm_review = llm_review or {}

    # Calculate validation pass rate
    critical = len([i for i in validation_issues if i.get("severity") == "critical"])
    major = len([i for i in validation_issues if i.get("severity") == "major"])
    warnings = len([i for i in validation_issues if i.get("severity") == "warning"])

    if critical > 0:
        validation_pass_rate = 70
    elif major > 0:
        validation_pass_rate = 85
    elif warnings > 0:
        validation_pass_rate = 95
    else:
        validation_pass_rate = 100

    return {
        # ── Metadata ──────────────────────────────────────────────────────────
        "program_id": f"v5_{program.profile.user_id}",
        "version": "5.0",
        "generator": "V5 Program Generator",

        # ── Athlete Profile ───────────────────────────────────────────────────
        "athlete": _serialize_profile(program.profile),

        # ── Program Overview ──────────────────────────────────────────────────
        "overview": {
            "name": _generate_program_name(program.profile, program.strategy),
            "description": _generate_program_description(program.profile, program.strategy),
            "duration_weeks": program.profile.program_duration_weeks,
            "days_per_week": program.profile.training_days_per_week,
            "session_duration_minutes": program.profile.session_duration_minutes,
            "training_goal": program.profile.training_goal,
            "effective_goal": program.profile.effective_goal,
            "split_name": program.strategy.split.name,
            "periodization_model": program.strategy.periodization_model,
            "mesocycle_count": program.strategy.mesocycle_count,
            "vbt_enabled": program.strategy.vbt_enabled,
            "vbt_protocol": program.strategy.vbt_protocol,
        },

        # ── Stats ─────────────────────────────────────────────────────────────
        "stats": {
            "total_workouts": program.total_workouts,
            "total_sets": program.total_sets,
            "unique_exercises": program.unique_exercises_used,
            "generation_time_seconds": program.generation_time_seconds,
            "validation_pass_rate": validation_pass_rate,
            "llm_grade": llm_review.get("overall_grade", "N/A"),
        },

        # ── Program Content ───────────────────────────────────────────────────
        "weeks": [_serialize_week(week) for week in program.weeks],

        # ── Quality Assessment ────────────────────────────────────────────────
        "quality": {
            "validation_issues": {
                "critical": critical,
                "major": major,
                "warnings": warnings,
            },
            "llm_review": {
                "grade": llm_review.get("overall_grade", "N/A"),
                "strengths": llm_review.get("strengths", []),
                "issues": llm_review.get("issues", []),
                "coaching_summary": llm_review.get("coaching_summary", ""),
            },
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# PROFILE SERIALIZATION
# ─────────────────────────────────────────────────────────────────────────────


def _serialize_profile(profile: AthleteProfile) -> dict:
    """Serialize athlete profile."""
    return {
        "user_id": profile.user_id,
        "name": profile.name,
        "age": profile.age,
        "sex": profile.sex,
        "body_weight_kg": profile.body_weight_kg,
        "training_level": profile.training_level,
        "training_age_years": profile.training_age_years,
        "sport": profile.sport,
        "equipment_tier": profile.equipment_tier.value,
        "recovery_capacity": profile.recovery_capacity,
        "weak_points": profile.weak_points,
        "injuries": profile.injuries,
    }


# ─────────────────────────────────────────────────────────────────────────────
# WEEK SERIALIZATION
# ─────────────────────────────────────────────────────────────────────────────


def _serialize_week(week: BuiltWeek) -> dict:
    """Serialize a week of training."""
    return {
        "week_number": week.week_number,
        "mesocycle": week.mesocycle,
        "phase": week.phase_name,
        "workouts": [_serialize_workout(w) for w in week.workouts],
        "volume_summary": {
            "actual": week.weekly_volume_actual,
            "target": week.weekly_volume_target,
            "adherence": week.volume_adherence,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# WORKOUT SERIALIZATION
# ─────────────────────────────────────────────────────────────────────────────


def _serialize_workout(workout: BuiltWorkout) -> dict:
    """Serialize a single workout."""
    return {
        "day_number": workout.day_number,
        "day_label": workout.day_label,
        "session_type": workout.session_type,
        "estimated_duration_minutes": workout.estimated_duration_minutes,
        "total_sets": workout.total_sets,
        "warmup_notes": workout.warmup_notes,
        "warmup_protocol": workout.warmup_protocol.model_dump() if workout.warmup_protocol else None,
        "exercises": [_serialize_exercise(ex) for ex in workout.exercises],
        "volume_delivered": workout.volume_delivered,
    }


# ─────────────────────────────────────────────────────────────────────────────
# EXERCISE SERIALIZATION
# ─────────────────────────────────────────────────────────────────────────────


def _serialize_exercise(exercise: PrescribedExercise) -> dict:
    """Serialize a prescribed exercise."""
    return {
        "exercise_id": exercise.exercise_id,
        "exercise_name": exercise.exercise_name,
        "exercise_type": exercise.exercise_type.value,
        "movement_pattern": exercise.movement_pattern.value,
        "order": exercise.order_in_session,
        "total_sets": exercise.total_sets,
        "superset_group": exercise.superset_group,
        "muscle_contributions": exercise.muscle_contributions,
        "rationale": exercise.rationale,
        "vbt_eligible": exercise.vbt_eligible,
        "sets": [_serialize_set(s) for s in exercise.sets],
        # Compact set notation for display
        "set_notation": _build_set_notation(exercise),
    }


def _serialize_set(set_obj: PrescribedSet) -> dict:
    """Serialize a single set."""
    result = {
        "set_number": set_obj.set_number,
        "reps": set_obj.reps,
        "rpe": set_obj.rpe,
        "rir": set_obj.rir,
        "intensity_percent": set_obj.intensity_percent,
        "rest_seconds": set_obj.rest_seconds,
        "tempo": set_obj.tempo,
        "notes": set_obj.notes,
        "set_type": set_obj.set_type.value if set_obj.set_type else "standard",
    }
    # Include VBT fields when present
    if set_obj.velocity_target is not None:
        result["velocity_target"] = set_obj.velocity_target
        result["velocity_min"] = set_obj.velocity_min
        result["velocity_max"] = set_obj.velocity_max
    return result


def _build_set_notation(exercise: PrescribedExercise) -> str:
    """
    Build compact set notation for display.

    Examples:
    - "3×8-10 @ RPE 7"
    - "4×5 @ RPE 8, rest 180s"
    - "3×12-15 @ RPE 8, tempo 3-1-1-1"
    """
    if not exercise.sets:
        return f"{exercise.total_sets} sets"

    first_set = exercise.sets[0]
    reps = first_set.reps

    # Check if all sets have same reps
    all_same_reps = all(s.reps == reps for s in exercise.sets)
    if all_same_reps:
        reps_str = str(reps)
    else:
        min_reps = min(s.reps for s in exercise.sets)
        max_reps = max(s.reps for s in exercise.sets)
        reps_str = f"{min_reps}-{max_reps}"

    notation = f"{exercise.total_sets}×{reps_str}"

    # Add RPE if present
    if first_set.rpe is not None:
        notation += f" @ RPE {first_set.rpe}"

    # Add rest if notable
    if first_set.rest_seconds and first_set.rest_seconds >= 120:
        notation += f", rest {first_set.rest_seconds}s"

    # Add velocity target if present
    if first_set.velocity_target is not None:
        notation += f", {first_set.velocity_target} m/s target"

    # Add tempo if present
    if first_set.tempo:
        notation += f", tempo {first_set.tempo}"

    return notation


# ─────────────────────────────────────────────────────────────────────────────
# PROGRAM METADATA GENERATION
# ─────────────────────────────────────────────────────────────────────────────


def _generate_program_name(profile: AthleteProfile, strategy: ProgramStrategy) -> str:
    """Generate a descriptive program name."""
    goal_names = {
        "hypertrophy": "Muscle Building",
        "strength": "Strength Development",
        "power": "Athletic Power",
    }

    goal_display = goal_names.get(profile.effective_goal, profile.effective_goal.title())

    if profile.sport:
        return f"{profile.sport.title()} {goal_display} Program"
    else:
        return f"{profile.training_level.title()} {goal_display} Program"


def _generate_program_description(profile: AthleteProfile, strategy: ProgramStrategy) -> str:
    """Generate a program description."""
    duration = profile.program_duration_weeks
    days = profile.training_days_per_week
    split = strategy.split.name
    periodization = strategy.periodization_model.replace("_", " ").title()

    description = (
        f"A {duration}-week {profile.training_goal} program designed for "
        f"{profile.training_level} lifters. This program uses a {split} "
        f"with {periodization} periodization, training {days} days per week "
        f"for approximately {profile.session_duration_minutes} minutes per session."
    )

    if profile.sport:
        description += f" Optimized for {profile.sport} athletes."

    if profile.weak_points:
        weak_points_str = ", ".join(profile.weak_points)
        description += f" Emphasis on {weak_points_str}."

    return description


# ─────────────────────────────────────────────────────────────────────────────
# ALTERNATIVE SERIALIZATION FORMATS
# ─────────────────────────────────────────────────────────────────────────────


def serialize_to_markdown(program: BuiltProgram) -> str:
    """
    Convert BuiltProgram to markdown format for human-readable output.
    """
    lines = []

    # Header
    lines.append(f"# {_generate_program_name(program.profile, program.strategy)}")
    lines.append("")
    lines.append(_generate_program_description(program.profile, program.strategy))
    lines.append("")

    # Program stats
    lines.append("## Program Statistics")
    lines.append(f"- **Duration**: {program.profile.program_duration_weeks} weeks")
    lines.append(f"- **Days per week**: {program.profile.training_days_per_week}")
    lines.append(f"- **Split**: {program.strategy.split.name}")
    lines.append(f"- **Total workouts**: {program.total_workouts}")
    lines.append(f"- **Unique exercises**: {program.unique_exercises_used}")
    lines.append("")

    # Weeks
    for week in program.weeks:
        lines.append(f"## Week {week.week_number} — {week.phase_name}")
        lines.append("")

        for workout in week.workouts:
            lines.append(f"### {workout.day_label}")
            lines.append(f"*Estimated duration: {workout.estimated_duration_minutes} minutes*")
            lines.append("")

            for ex in workout.exercises:
                notation = _build_set_notation(ex)
                superset = f" [Superset {ex.superset_group}]" if ex.superset_group else ""
                lines.append(f"{ex.order_in_session}. **{ex.exercise_name}**{superset} — {notation}")

                # Add notes from first set if present
                if ex.sets and ex.sets[0].notes:
                    lines.append(f"   - *{ex.sets[0].notes}*")

            lines.append("")

    return "\n".join(lines)


def serialize_to_csv(program: BuiltProgram) -> str:
    """
    Convert BuiltProgram to CSV format for spreadsheet import.
    """
    lines = ["Week,Day,Exercise,Sets,Reps,RPE,Rest,Tempo,Notes"]

    for week in program.weeks:
        for workout in week.workouts:
            for ex in workout.exercises:
                if ex.sets:
                    first_set = ex.sets[0]
                    line = ",".join([
                        str(week.week_number),
                        workout.day_label,
                        f'"{ex.exercise_name}"',
                        str(ex.total_sets),
                        str(first_set.reps),
                        str(first_set.rpe) if first_set.rpe else "",
                        str(first_set.rest_seconds),
                        first_set.tempo or "",
                        f'"{first_set.notes}"' if first_set.notes else "",
                    ])
                    lines.append(line)

    return "\n".join(lines)


def serialize_summary(program: BuiltProgram) -> dict:
    """
    Serialize a minimal summary for quick display.
    """
    return {
        "program_name": _generate_program_name(program.profile, program.strategy),
        "duration_weeks": program.profile.program_duration_weeks,
        "days_per_week": program.profile.training_days_per_week,
        "training_goal": program.profile.training_goal,
        "split": program.strategy.split.name,
        "total_workouts": program.total_workouts,
        "unique_exercises": program.unique_exercises_used,
        "generation_time_seconds": round(program.generation_time_seconds, 2),
    }
