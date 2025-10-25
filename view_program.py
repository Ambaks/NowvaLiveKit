#!/usr/bin/env python3
"""
View Program Script
Fetches a generated workout program from the database and displays it in a formatted markdown file.
"""
import sys
sys.path.insert(0, 'src')

from db.database import SessionLocal
from db.models import UserGeneratedProgram, Workout, WorkoutExercise, Exercise, Set
from sqlalchemy.orm import joinedload
import argparse


def fetch_program(db, program_id: int):
    """Fetch a program with all related data."""
    program = db.query(UserGeneratedProgram).filter(
        UserGeneratedProgram.id == program_id
    ).first()

    if not program:
        return None

    # Fetch all workouts for this program, ordered by week and day
    workouts = db.query(Workout).filter(
        Workout.user_generated_program_id == program_id
    ).order_by(Workout.week_number, Workout.day_number).all()

    return program, workouts


def format_program_markdown(program, workouts):
    """Format program data as markdown."""
    md = []

    # Header
    md.append(f"# {program.name}")
    md.append("")
    md.append(f"**Program ID:** {program.id}")
    md.append(f"**Duration:** {program.duration_weeks} weeks")
    md.append(f"**Created:** {program.created_at.strftime('%Y-%m-%d %H:%M')}")
    md.append("")

    # Description
    md.append("## Description")
    md.append("")
    md.append(program.description)
    md.append("")
    md.append("---")
    md.append("")

    # Organize workouts by week
    weeks = {}
    for workout in workouts:
        week_num = workout.week_number
        if week_num not in weeks:
            weeks[week_num] = []
        weeks[week_num].append(workout)

    # Generate markdown for each week
    for week_num in sorted(weeks.keys()):
        md.append(f"## Week {week_num}")

        week_workouts = weeks[week_num]
        if week_workouts and week_workouts[0].phase:
            md.append(f"**Phase:** {week_workouts[0].phase}")
        md.append("")

        for workout in week_workouts:
            md.append(f"### Day {workout.day_number}: {workout.name}")
            md.append("")

            if workout.description:
                md.append(f"*{workout.description}*")
                md.append("")

            # Consolidated table header
            md.append("| # | Exercise | Category | Muscle Group | Sets | Reps | Intensity | RIR | Rest |")
            md.append("|---|----------|----------|--------------|------|------|-----------|-----|------|")

            # Collect exercise notes for display after table
            exercise_notes = []

            # Add all exercises as rows in the consolidated table
            for workout_exercise in sorted(workout.workout_exercises, key=lambda we: we.order_number):
                exercise = workout_exercise.exercise
                sets = sorted(workout_exercise.sets, key=lambda s: s.set_number)

                # Group consecutive sets with identical parameters
                set_groups = []
                current_group = []

                for set_obj in sets:
                    if not current_group:
                        current_group.append(set_obj)
                    else:
                        # Check if this set matches the previous one
                        prev_set = current_group[-1]
                        if (set_obj.reps == prev_set.reps and
                            set_obj.intensity_percent == prev_set.intensity_percent and
                            set_obj.rpe == prev_set.rpe and
                            set_obj.rest_seconds == prev_set.rest_seconds):
                            current_group.append(set_obj)
                        else:
                            # Start a new group
                            set_groups.append(current_group)
                            current_group = [set_obj]

                # Don't forget the last group
                if current_group:
                    set_groups.append(current_group)

                # For display, we'll show the first group's data (most exercises have straight sets)
                # If there are multiple groups, we'll show them in the notes
                first_group = set_groups[0]
                first_set = first_group[0]
                num_sets = len(first_group)

                # Format set numbers/count
                if len(set_groups) > 1:
                    # Progressive sets - show as "varied"
                    sets_display = f"{len(sets)} sets"
                elif num_sets == 1:
                    sets_display = "1"
                else:
                    sets_display = f"{num_sets}x"

                # Format other columns from first group
                reps = first_set.reps
                intensity = f"{first_set.intensity_percent:.1f}%" if first_set.intensity_percent else "N/A"
                rpe = f"{first_set.rpe:.1f}" if first_set.rpe else "N/A"
                rest_min = first_set.rest_seconds // 60
                rest_sec = first_set.rest_seconds % 60
                rest = f"{rest_min}:{rest_sec:02d}" if first_set.rest_seconds else "N/A"

                # Add row to table
                md.append(f"| {workout_exercise.order_number} | {exercise.name} | {exercise.category} | {exercise.muscle_group} | {sets_display} | {reps} | {intensity} | {rpe} | {rest} |")

                # Collect notes if present
                if workout_exercise.notes:
                    exercise_notes.append(f"**{workout_exercise.order_number}. {exercise.name}:** {workout_exercise.notes}")

                # If progressive sets, add details to notes
                if len(set_groups) > 1:
                    progressive_details = []
                    for i, group in enumerate(set_groups, 1):
                        g_set = group[0]
                        g_num = len(group)
                        g_intensity = f"{g_set.intensity_percent:.1f}%" if g_set.intensity_percent else "N/A"
                        if g_num == 1:
                            progressive_details.append(f"Set {g_set.set_number}: {g_set.reps} reps @ {g_intensity}")
                        else:
                            progressive_details.append(f"Sets {group[0].set_number}-{group[-1].set_number}: {g_num}x{g_set.reps} @ {g_intensity}")
                    exercise_notes.append(f"**{workout_exercise.order_number}. {exercise.name}:** {', '.join(progressive_details)}")

            md.append("")

            # Display exercise notes if any
            if exercise_notes:
                md.append("**Notes:**")
                for note in exercise_notes:
                    md.append(f"- {note}")
                md.append("")

            md.append("---")
            md.append("")

    # Summary statistics
    md.append("## Program Statistics")
    md.append("")

    total_workouts = len(workouts)
    total_exercises = sum(len(w.workout_exercises) for w in workouts)
    total_sets = sum(sum(len(we.sets) for we in w.workout_exercises) for w in workouts)

    md.append(f"- **Total Workouts:** {total_workouts}")
    md.append(f"- **Total Exercises:** {total_exercises}")
    md.append(f"- **Total Sets:** {total_sets}")
    md.append(f"- **Average Exercises per Workout:** {total_exercises / total_workouts:.1f}")
    md.append(f"- **Average Sets per Workout:** {total_sets / total_workouts:.1f}")
    md.append("")

    # Exercise frequency
    md.append("### Exercise Frequency")
    md.append("")

    exercise_counts = {}
    for workout in workouts:
        for we in workout.workout_exercises:
            name = we.exercise.name
            exercise_counts[name] = exercise_counts.get(name, 0) + 1

    md.append("| Exercise | Times Used |")
    md.append("|----------|------------|")
    for exercise, count in sorted(exercise_counts.items(), key=lambda x: -x[1]):
        md.append(f"| {exercise} | {count} |")

    md.append("")

    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description='View a workout program in markdown format')
    parser.add_argument('program_id', type=int, help='Program ID to fetch')
    parser.add_argument('-o', '--output', type=str, help='Output markdown file (default: program_<id>.md)')

    args = parser.parse_args()

    db = SessionLocal()

    try:
        print(f"Fetching program {args.program_id}...")
        result = fetch_program(db, args.program_id)

        if not result:
            print(f"❌ Program {args.program_id} not found")
            sys.exit(1)

        program, workouts = result
        print(f"✅ Found program: {program.name}")
        print(f"   {len(workouts)} workouts loaded")

        # Generate markdown
        markdown = format_program_markdown(program, workouts)

        # Write to file
        output_file = args.output or f"program_{args.program_id}.md"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(markdown)

        print(f"✅ Program saved to: {output_file}")
        print(f"\nPreview:")
        print("=" * 80)
        # Print first 30 lines as preview
        lines = markdown.split('\n')
        for line in lines[:30]:
            print(line)
        if len(lines) > 30:
            print(f"\n... ({len(lines) - 30} more lines)")
        print("=" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    main()
