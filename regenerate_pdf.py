"""
Script to regenerate PDF for an existing program.
Usage: python regenerate_pdf.py <program_id>
"""
import sys
import os
import json
from pathlib import Path
from sqlalchemy.orm import joinedload

# Add src to path
sys.path.insert(0, 'src')

from db.database import SessionLocal
from db.models import UserGeneratedProgram, Workout, WorkoutExercise, Exercise
from api.services.html_generator import generate_html
from api.services.pdf_generator import generate_pdf_from_html


def get_program_file_path(user_id: str, program_id: str, file_type: str) -> Path:
    """Get the file path for a program file."""
    programs_dir = Path("programs")
    programs_dir.mkdir(parents=True, exist_ok=True)
    filename = f"program_{user_id}_{program_id}.{file_type}"
    return programs_dir / filename


def parse_markdown_metadata(markdown_path: Path) -> dict:
    """Parse metadata sections from markdown file."""
    if not markdown_path.exists():
        return {}

    with open(markdown_path, 'r', encoding='utf-8') as f:
        content = f.read()

    metadata = {}

    # Extract Deload Schedule
    if '## Deload Schedule' in content:
        start = content.find('## Deload Schedule')
        end = content.find('\n##', start + 1)
        if end == -1:
            end = content.find('\n---', start + 1)
        if end > start:
            metadata['deload_schedule'] = content[start:end].replace('## Deload Schedule', '').strip()

    # Extract Injury Accommodations
    if '## Injury Accommodations' in content:
        start = content.find('## Injury Accommodations')
        end = content.find('\n##', start + 1)
        if end == -1:
            end = content.find('\n---', start + 1)
        if end > start:
            metadata['injury_accommodations'] = content[start:end].replace('## Injury Accommodations', '').strip()

    # Extract Progression Strategy (if exists)
    if '## Progression Strategy' in content:
        start = content.find('## Progression Strategy')
        end = content.find('\n##', start + 1)
        if end == -1:
            end = content.find('\n---', start + 1)
        if end > start:
            metadata['progression_strategy'] = content[start:end].replace('## Progression Strategy', '').strip()

    return metadata


def build_program_data_dict(program, workouts, markdown_metadata=None):
    """Build program data dictionary matching the format expected by generate_html."""

    if markdown_metadata is None:
        markdown_metadata = {}

    # Group workouts by week
    weeks_dict = {}
    for workout in workouts:
        week_num = workout.week_number
        if week_num not in weeks_dict:
            weeks_dict[week_num] = {
                'week_number': week_num,
                'phase': workout.phase or 'Build',
                'notes': None,
                'workouts': []
            }

        # Build exercises list
        exercises = []
        for workout_exercise in sorted(workout.workout_exercises, key=lambda we: we.order_number):
            exercise_data = {
                'order': workout_exercise.order_number,
                'exercise_name': workout_exercise.exercise.name if workout_exercise.exercise else 'Unknown',
                'category': workout_exercise.exercise.category if workout_exercise.exercise else 'Strength',
                'muscle_group': workout_exercise.exercise.muscle_group if workout_exercise.exercise else '',
                'notes': workout_exercise.notes,
                'sets': []
            }

            # Build sets list
            for set_obj in sorted(workout_exercise.sets, key=lambda s: s.set_number):
                # Convert RPE to RIR (RIR ≈ 10 - RPE)
                rir_value = (10 - float(set_obj.rpe)) if set_obj.rpe else None

                set_data = {
                    'set_number': set_obj.set_number,
                    'reps': set_obj.reps,
                    'intensity_percent': set_obj.intensity_percent,
                    'rir': rir_value,
                    'rest_seconds': set_obj.rest_seconds,
                    'velocity_threshold': set_obj.velocity_threshold,
                    'velocity_min': set_obj.velocity_min,
                    'velocity_max': set_obj.velocity_max
                }
                exercise_data['sets'].append(set_data)

            exercises.append(exercise_data)

        # Build workout dict
        workout_data = {
            'day_number': workout.day_number,
            'name': workout.name,
            'description': workout.description or '',
            'exercises': exercises
        }

        weeks_dict[week_num]['workouts'].append(workout_data)

    # Convert weeks dict to sorted list
    weeks_list = [weeks_dict[week_num] for week_num in sorted(weeks_dict.keys())]

    # Build overall notes from metadata
    overall_notes_parts = []
    if markdown_metadata.get('deload_schedule'):
        overall_notes_parts.append(f"**Deload Schedule:** {markdown_metadata['deload_schedule']}")
    if markdown_metadata.get('injury_accommodations'):
        overall_notes_parts.append(f"**Injury Accommodations:** {markdown_metadata['injury_accommodations']}")
    overall_notes = ' '.join(overall_notes_parts)

    # Build complete program data
    program_data = {
        'id': program.id,
        'program_name': program.name,
        'description': program.description or '',
        'duration_weeks': program.duration_weeks,
        'goal': '',  # Not stored in program table
        'progression_strategy': markdown_metadata.get('progression_strategy', ''),
        'overall_notes': overall_notes,
        'vbt_enabled': False,  # Not stored in program table
        'weeks': weeks_list
    }

    return program_data


def regenerate_pdf(program_id: int):
    """Regenerate PDF for a program."""
    db = SessionLocal()
    try:
        # Fetch program with all relationships loaded
        program = db.query(UserGeneratedProgram).filter(
            UserGeneratedProgram.id == program_id
        ).first()

        if not program:
            print(f"❌ Program {program_id} not found")
            return False

        print(f"✅ Found program: {program.name}")
        print(f"   User ID: {program.user_id}")

        # Fetch all workouts with relationships
        print(f"\n📥 Fetching program data from database...")
        workouts = db.query(Workout).filter(
            Workout.user_generated_program_id == program_id
        ).options(
            joinedload(Workout.workout_exercises).joinedload(WorkoutExercise.exercise),
            joinedload(Workout.workout_exercises).joinedload(WorkoutExercise.sets)
        ).all()

        print(f"   Found {len(workouts)} workouts")

        # Parse markdown file for metadata
        markdown_path = get_program_file_path(str(program.user_id), str(program_id), "md")
        markdown_metadata = {}
        if markdown_path.exists():
            print(f"\n📖 Parsing markdown file for metadata...")
            markdown_metadata = parse_markdown_metadata(markdown_path)
            print(f"   Found {len(markdown_metadata)} metadata sections")
            for key in markdown_metadata.keys():
                print(f"   - {key}")
        else:
            print(f"\n⚠️  Markdown file not found, skipping metadata extraction")

        # Build program data using the same method as program_generator_v2.py
        program_data = build_program_data_dict(program, workouts, markdown_metadata)

        if not program_data:
            print(f"❌ Failed to build program data")
            return False

        # Get file paths
        html_path = get_program_file_path(str(program.user_id), str(program_id), "html")
        pdf_path = get_program_file_path(str(program.user_id), str(program_id), "pdf")

        print(f"\n📄 Generating HTML...")
        print(f"   Output: {html_path}")

        # Generate HTML
        user_data = {
            'name': program.user.name if program.user else 'Athlete',
        }
        html_content = generate_html(program_data, user_data)

        # Save HTML
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"✅ HTML generated successfully")

        print(f"\n📄 Generating PDF...")
        print(f"   Output: {pdf_path}")

        # Generate PDF with base_url for asset resolution
        templates_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "src", "templates"))
        base_url = f"file://{templates_dir}/"
        print(f"   Base URL: {base_url}")

        generate_pdf_from_html(html_content, str(pdf_path), base_url=base_url)

        print(f"✅ PDF generated successfully")
        print(f"\n📍 PDF location: {pdf_path.absolute()}")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python regenerate_pdf.py <program_id>")
        sys.exit(1)

    try:
        program_id = int(sys.argv[1])
    except ValueError:
        print("❌ Invalid program ID. Must be an integer.")
        sys.exit(1)

    print(f"🔄 Regenerating PDF for program {program_id}...\n")
    success = regenerate_pdf(program_id)

    if success:
        print("\n✅ Done!")
        sys.exit(0)
    else:
        print("\n❌ Failed to regenerate PDF")
        sys.exit(1)
