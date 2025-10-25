"""
Migration: Fix workouts table column name
Changes program_id to user_generated_program_id to match the model
"""
import sys
sys.path.insert(0, '/Users/naiahoard/NowvaLiveKit/src')

from db.database import SessionLocal
from sqlalchemy import text

def run_migration():
    db = SessionLocal()

    try:
        print("Checking if migration is needed...")

        # Check if user_generated_program_id already exists
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'workouts'
            AND column_name = 'user_generated_program_id'
        """))

        if result.fetchone():
            print("✅ Column 'user_generated_program_id' already exists. No migration needed.")
            return

        # Check if program_id exists
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'workouts'
            AND column_name = 'program_id'
        """))

        if not result.fetchone():
            print("❌ Neither 'program_id' nor 'user_generated_program_id' exists!")
            print("You may need to run init_db() first.")
            return

        print("Renaming 'program_id' to 'user_generated_program_id'...")

        # Rename the column
        db.execute(text("""
            ALTER TABLE workouts
            RENAME COLUMN program_id TO user_generated_program_id
        """))

        db.commit()
        print("✅ Migration complete! Column renamed successfully.")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print("="*60)
    print("Running migration: Fix workouts table column name")
    print("="*60)
    run_migration()
