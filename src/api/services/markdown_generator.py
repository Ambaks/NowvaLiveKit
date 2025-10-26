"""
Markdown Generator Service
Generates formatted markdown files for workout programs with VBT support
"""
from pathlib import Path
from typing import Dict, List, Any
from db.models import UserGeneratedProgram, Workout, WorkoutExercise, Set


def generate_program_markdown(
    program: UserGeneratedProgram,
    workouts: List[Workout],
    output_dir: str = "programs",
    user_name: str = None,
    vbt_enabled: bool = False,
    vbt_setup_notes: str = None,
    deload_schedule: str = None,
    injury_accommodations: str = None
) -> str:
    """
    Generate a formatted markdown file for a workout program.

    Args:
        program: UserGeneratedProgram database object
        workouts: List of Workout objects (with exercises and sets loaded)
        output_dir: Directory to save markdown files
        user_name: Name of the user (optional)
        vbt_enabled: Whether VBT is enabled for this program
        vbt_setup_notes: VBT equipment setup instructions (optional)
        deload_schedule: Deload schedule description (optional)
        injury_accommodations: Injury accommodation notes (optional)

    Returns:
        Path to the generated markdown file
    """
    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Build markdown content
    md_lines = []

    # Header
    md_lines.append(f"# {program.name}")
    md_lines.append("")

    if user_name:
        md_lines.append(f"**Created for:** {user_name}")

    md_lines.append(f"**Program ID:** {program.id}")
    md_lines.append(f"**Duration:** {program.duration_weeks} weeks")
    md_lines.append(f"**Created:** {program.created_at.strftime('%Y-%m-%d %H:%M')}")

    if vbt_enabled:
        md_lines.append(f"**VBT Enabled:** Yes")

    md_lines.append("")

    # Description
    if program.description:
        md_lines.append("## Description")
        md_lines.append("")
        md_lines.append(program.description)
        md_lines.append("")

    # VBT Setup Notes
    if vbt_enabled and vbt_setup_notes:
        md_lines.append("## VBT Setup")
        md_lines.append("")
        md_lines.append(vbt_setup_notes)
        md_lines.append("")

    # Deload Schedule
    if deload_schedule:
        md_lines.append("## Deload Schedule")
        md_lines.append("")
        md_lines.append(deload_schedule)
        md_lines.append("")

    # Injury Accommodations
    if injury_accommodations:
        md_lines.append("## Injury Accommodations")
        md_lines.append("")
        md_lines.append(injury_accommodations)
        md_lines.append("")

    md_lines.append("---")
    md_lines.append("")

    # Organize workouts by week
    weeks = {}
    for workout in workouts:
        week_num = workout.week_number
        if week_num not in weeks:
            weeks[week_num] = []
        weeks[week_num].append(workout)

    # Check if any workout has VBT data
    has_vbt_data = any(
        any(
            any(
                s.velocity_threshold is not None
                for s in we.sets
            )
            for we in w.workout_exercises
        )
        for w in workouts
    )

    # Generate markdown for each week
    for week_num in sorted(weeks.keys()):
        md_lines.append(f"## Week {week_num}")

        week_workouts = weeks[week_num]
        if week_workouts and week_workouts[0].phase:
            md_lines.append(f"**Phase:** {week_workouts[0].phase}")
        md_lines.append("")

        for workout in week_workouts:
            md_lines.append(f"### Day {workout.day_number}: {workout.name}")
            md_lines.append("")

            if workout.description:
                md_lines.append(f"*{workout.description}*")
                md_lines.append("")

            # Table header - include VBT column if any exercise has VBT data
            if has_vbt_data:
                md_lines.append("| # | Exercise | Category | Muscle Group | Sets | Reps | Intensity | RIR | VBT Target | Rest |")
                md_lines.append("|---|----------|----------|--------------|------|------|-----------|-----|------------|------|")
            else:
                md_lines.append("| # | Exercise | Category | Muscle Group | Sets | Reps | Intensity | RIR | Rest |")
                md_lines.append("|---|----------|----------|--------------|------|------|-----------|-----|------|")

            # Collect exercise notes
            exercise_notes = []

            # Add exercises to table
            for workout_exercise in sorted(workout.workout_exercises, key=lambda we: we.order_number):
                exercise = workout_exercise.exercise
                sets = sorted(workout_exercise.sets, key=lambda s: s.set_number)

                if not sets:
                    continue

                # Analyze sets to see if they're uniform or progressive
                set_groups = _group_similar_sets(sets)

                # Use first group for table display
                first_group = set_groups[0]
                first_set = first_group[0]
                num_sets = len(first_group)

                # Format sets column
                if len(set_groups) > 1:
                    sets_display = f"{len(sets)}"
                elif num_sets == 1:
                    sets_display = "1"
                else:
                    sets_display = f"{num_sets}"

                # Format reps
                reps = first_set.reps

                # Format intensity
                if first_set.intensity_percent:
                    intensity = f"{first_set.intensity_percent:.1f}%"
                else:
                    intensity = "-"

                # Format RIR (stored in rpe field)
                if first_set.rpe is not None:
                    rir = f"{first_set.rpe:.0f}"
                else:
                    rir = "-"

                # Format VBT
                vbt_display = "-"
                if first_set.velocity_threshold:
                    vbt_display = f"{first_set.velocity_threshold:.2f} m/s"

                # Format rest
                rest_min = first_set.rest_seconds // 60
                rest_sec = first_set.rest_seconds % 60
                if rest_min > 0:
                    rest = f"{rest_min}:{rest_sec:02d}"
                else:
                    rest = f"{rest_sec}s"

                # Add row to table
                if has_vbt_data:
                    md_lines.append(
                        f"| {workout_exercise.order_number} | {exercise.name} | "
                        f"{exercise.category} | {exercise.muscle_group} | "
                        f"{sets_display} | {reps} | {intensity} | {rir} | {vbt_display} | {rest} |"
                    )
                else:
                    md_lines.append(
                        f"| {workout_exercise.order_number} | {exercise.name} | "
                        f"{exercise.category} | {exercise.muscle_group} | "
                        f"{sets_display} | {reps} | {intensity} | {rir} | {rest} |"
                    )

                # Collect notes
                if workout_exercise.notes:
                    exercise_notes.append(
                        f"**{workout_exercise.order_number}. {exercise.name}:** {workout_exercise.notes}"
                    )

                # Add progressive set details if applicable
                if len(set_groups) > 1:
                    progressive_details = []
                    for i, group in enumerate(set_groups, 1):
                        g_set = group[0]
                        g_num = len(group)
                        g_intensity = f"{g_set.intensity_percent:.1f}%" if g_set.intensity_percent else "-"
                        if g_num == 1:
                            progressive_details.append(
                                f"Set {g_set.set_number}: {g_set.reps} reps @ {g_intensity}"
                            )
                        else:
                            progressive_details.append(
                                f"Sets {group[0].set_number}-{group[-1].set_number}: "
                                f"{g_num}x{g_set.reps} @ {g_intensity}"
                            )
                    exercise_notes.append(
                        f"**{workout_exercise.order_number}. {exercise.name} (Progressive):** "
                        f"{', '.join(progressive_details)}"
                    )

                # Add VBT details if present
                if first_set.velocity_threshold:
                    vbt_note_parts = [f"Target: {first_set.velocity_threshold:.2f} m/s"]
                    if first_set.velocity_min:
                        vbt_note_parts.append(f"stop if below {first_set.velocity_min:.2f} m/s")
                    if first_set.velocity_max:
                        vbt_note_parts.append(f"max {first_set.velocity_max:.2f} m/s")

                    exercise_notes.append(
                        f"**{workout_exercise.order_number}. {exercise.name} (VBT):** "
                        f"{', '.join(vbt_note_parts)}"
                    )

            md_lines.append("")

            # Display notes
            if exercise_notes:
                md_lines.append("**Notes:**")
                for note in exercise_notes:
                    md_lines.append(f"- {note}")
                md_lines.append("")

            md_lines.append("---")
            md_lines.append("")

    # Summary statistics
    md_lines.append("## Program Statistics")
    md_lines.append("")

    total_workouts = len(workouts)
    total_exercises = sum(len(w.workout_exercises) for w in workouts)
    total_sets = sum(sum(len(we.sets) for we in w.workout_exercises) for w in workouts)

    md_lines.append(f"- **Total Workouts:** {total_workouts}")
    md_lines.append(f"- **Total Exercises:** {total_exercises}")
    md_lines.append(f"- **Total Sets:** {total_sets}")

    if total_workouts > 0:
        md_lines.append(f"- **Average Exercises per Workout:** {total_exercises / total_workouts:.1f}")
        md_lines.append(f"- **Average Sets per Workout:** {total_sets / total_workouts:.1f}")

    md_lines.append("")

    # Exercise frequency
    md_lines.append("### Exercise Frequency")
    md_lines.append("")

    exercise_counts = {}
    for workout in workouts:
        for we in workout.workout_exercises:
            name = we.exercise.name
            exercise_counts[name] = exercise_counts.get(name, 0) + 1

    md_lines.append("| Exercise | Times Used |")
    md_lines.append("|----------|------------|")
    for exercise_name, count in sorted(exercise_counts.items(), key=lambda x: -x[1]):
        md_lines.append(f"| {exercise_name} | {count} |")

    md_lines.append("")

    # Write to file
    filename = f"{output_dir}/program_{program.user_id}_{program.id}.md"
    markdown_content = "\n".join(md_lines)

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(markdown_content)

    print(f"[MARKDOWN] Generated: {filename}")
    return filename


def _group_similar_sets(sets: List[Set]) -> List[List[Set]]:
    """
    Group consecutive sets with identical parameters.

    Returns:
        List of set groups, where each group contains sets with same parameters
    """
    if not sets:
        return []

    set_groups = []
    current_group = [sets[0]]

    for set_obj in sets[1:]:
        prev_set = current_group[-1]

        # Check if parameters match
        if (set_obj.reps == prev_set.reps and
            set_obj.intensity_percent == prev_set.intensity_percent and
            set_obj.rpe == prev_set.rpe and
            set_obj.rest_seconds == prev_set.rest_seconds and
            set_obj.velocity_threshold == prev_set.velocity_threshold):
            current_group.append(set_obj)
        else:
            # Start new group
            set_groups.append(current_group)
            current_group = [set_obj]

    # Add final group
    if current_group:
        set_groups.append(current_group)

    return set_groups
