"""
Script to regenerate PDF and resend email for a completed program.
Usage: python resend_program_email.py <program_id> <user_email>
"""
import sys
import os
import asyncio
from pathlib import Path
from sqlalchemy.orm import joinedload

# Add src to path
sys.path.insert(0, 'src')

from db.database import SessionLocal
from db.models import UserGeneratedProgram, User, Workout, WorkoutExercise
from api.services.html_generator import generate_html
from api.services.pdf_generator import generate_pdf_from_html
from services.email_service import send_program_email_async


def _build_program_data_dict(program, workouts):
    """Build a dictionary representation of the program for HTML/PDF generation"""

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

        # Build workout data
        workout_data = {
            'day_number': workout.day_number,
            'name': workout.name,
            'description': workout.description,
            'exercises': []
        }

        # Build exercises data
        for we in workout.workout_exercises:
            exercise = we.exercise
            sets_data = []
            for s in we.sets:
                set_info = {
                    'set_number': s.set_number,
                    'reps': s.reps,
                    'weight': s.weight,
                    'intensity_percent': s.intensity_percent,
                    'rpe': s.rpe,
                    'rest_seconds': s.rest_seconds
                }
                sets_data.append(set_info)

            exercise_data = {
                'exercise_name': exercise.name,
                'order': we.order_number,
                'notes': we.notes,
                'sets': sets_data
            }
            workout_data['exercises'].append(exercise_data)

        weeks_dict[week_num]['workouts'].append(workout_data)

    # Convert to list and sort by week number
    weeks_list = sorted(weeks_dict.values(), key=lambda x: x['week_number'])

    return {
        'name': program.name,
        'description': program.description,
        'duration_weeks': program.duration_weeks,
        'goal': 'Build Muscle',  # Default
        'weeks': weeks_list
    }


async def resend_program_email(program_id: int, user_email: str):
    """Regenerate PDF and resend email for a program"""

    db = SessionLocal()
    try:
        # Get the program with all related data
        program = db.query(UserGeneratedProgram).filter(
            UserGeneratedProgram.id == program_id
        ).first()

        if not program:
            print(f"❌ Program {program_id} not found")
            return False

        # Get user
        user = db.query(User).filter(User.email == user_email).first()
        if not user:
            print(f"❌ User with email {user_email} not found")
            return False

        user_name = user.name or "there"

        print(f"📋 Found program: {program.name}")
        print(f"👤 User: {user_name} ({user_email})")
        print(f"")

        # Fetch all workouts with exercises and sets
        workouts = db.query(Workout).filter(
            Workout.user_generated_program_id == program_id
        ).options(
            joinedload(Workout.workout_exercises).joinedload(WorkoutExercise.exercise),
            joinedload(Workout.workout_exercises).joinedload(WorkoutExercise.sets)
        ).order_by(Workout.week_number, Workout.day_number).all()

        print(f"📋 Found {len(workouts)} workouts")

        # Build program data structure
        print(f"🌐 Building program data...")
        program_data = _build_program_data_dict(program, workouts)

        # User data for cover page
        user_data = {
            'name': user_name,
            'email': user_email,
            'age': user.age,
        }

        # Generate HTML
        print(f"🌐 Generating HTML...")
        html_content = generate_html(program_data, user_data)

        if not html_content:
            print(f"❌ Failed to generate HTML")
            return False

        print(f"✅ HTML generated ({len(html_content)} chars)")

        # Generate PDF
        print(f"📄 Generating PDF...")
        pdf_path = f"programs/program_{user.id}_{program_id}.pdf"

        # Set base_url to templates directory so assets can be found
        templates_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "src", "templates"))
        base_url = f"file://{templates_dir}/"

        pdf_result = generate_pdf_from_html(html_content, pdf_path, base_url=base_url)

        if not pdf_result:
            print(f"❌ Failed to generate PDF")
            return False

        print(f"✅ PDF generated: {pdf_path}")

        # Check PDF size
        if os.path.exists(pdf_path):
            size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
            print(f"📊 PDF size: {size_mb:.2f} MB")

        # Send email
        print(f"📧 Sending email to {user_email}...")
        result = await send_program_email_async(
            to_email=user_email,
            user_name=user_name,
            program_id=program_id,
            pdf_path=pdf_path
        )

        if result:
            print(f"✅ Email sent successfully!")
            print(f"Response: {result}")
            return True
        else:
            print(f"❌ Failed to send email")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python resend_program_email.py <program_id> <user_email>")
        print("Example: python resend_program_email.py 68 user@example.com")
        sys.exit(1)

    program_id = int(sys.argv[1])
    user_email = sys.argv[2]

    print(f"🚀 Resending program email")
    print(f"Program ID: {program_id}")
    print(f"Email: {user_email}")
    print(f"")

    success = asyncio.run(resend_program_email(program_id, user_email))

    if success:
        print(f"\n✅ Done!")
        sys.exit(0)
    else:
        print(f"\n❌ Failed")
        sys.exit(1)
