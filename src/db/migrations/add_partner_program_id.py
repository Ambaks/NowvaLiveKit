"""
Migration: Add partner_program_id column to workouts table
"""
import sys
sys.path.insert(0, '/Users/naiahoard/NowvaLiveKit/src')

from db.database import SessionLocal
from sqlalchemy import text

def run_migration():
    db = SessionLocal()

    try:
        print("Checking if partner_program_id column exists...")

        # Check if partner_program_id already exists
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'workouts'
            AND column_name = 'partner_program_id'
        """))

        if result.fetchone():
            print("✅ Column 'partner_program_id' already exists. No migration needed.")
            return

        print("Adding 'partner_program_id' column to workouts table...")

        # Add the column
        db.execute(text("""
            ALTER TABLE workouts
            ADD COLUMN partner_program_id INTEGER
        """))

        # Add foreign key constraint (optional, but good practice)
        print("Adding foreign key constraint...")
        db.execute(text("""
            ALTER TABLE workouts
            ADD CONSTRAINT fk_workouts_partner_program
            FOREIGN KEY (partner_program_id)
            REFERENCES partner_programs(id)
            ON DELETE CASCADE
        """))

        db.commit()
        print("✅ Migration complete! Column 'partner_program_id' added successfully.")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print("="*60)
    print("Running migration: Add partner_program_id to workouts")
    print("="*60)
    run_migration()
