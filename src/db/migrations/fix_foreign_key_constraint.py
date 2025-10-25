"""
Migration: Fix foreign key constraint on workouts table
The constraint 'workouts_program_id_fkey' references the wrong table ('programs' instead of 'user_generated_programs')
This migration drops the old constraint and creates the correct one.
"""
import sys
sys.path.insert(0, '/Users/naiahoard/NowvaLiveKit/src')

from db.database import SessionLocal
from sqlalchemy import text

def run_migration():
    db = SessionLocal()

    try:
        print("\n" + "="*80)
        print("Migration: Fix foreign key constraint on workouts.user_generated_program_id")
        print("="*80 + "\n")

        # Check if the bad constraint exists
        print("1. Checking for incorrect constraint 'workouts_program_id_fkey'...")
        result = db.execute(text("""
            SELECT con.conname
            FROM pg_constraint con
            JOIN pg_class cl ON con.conrelid = cl.oid
            WHERE cl.relname = 'workouts'
            AND con.conname = 'workouts_program_id_fkey'
        """))

        if not result.fetchone():
            print("   ✅ Constraint 'workouts_program_id_fkey' does not exist. Nothing to fix.")
            return

        print("   ⚠️  Found incorrect constraint 'workouts_program_id_fkey'")

        # Drop the incorrect constraint
        print("\n2. Dropping incorrect foreign key constraint...")
        db.execute(text("""
            ALTER TABLE workouts
            DROP CONSTRAINT workouts_program_id_fkey
        """))
        print("   ✅ Dropped constraint 'workouts_program_id_fkey'")

        # Create the correct constraint
        print("\n3. Creating correct foreign key constraint...")
        db.execute(text("""
            ALTER TABLE workouts
            ADD CONSTRAINT workouts_user_generated_program_id_fkey
            FOREIGN KEY (user_generated_program_id)
            REFERENCES user_generated_programs(id)
            ON DELETE CASCADE
        """))
        print("   ✅ Created constraint 'workouts_user_generated_program_id_fkey'")
        print("      References: user_generated_programs.id (correct!)")

        # Commit the changes
        db.commit()
        print("\n" + "="*80)
        print("✅ Migration complete! Foreign key constraint fixed.")
        print("="*80 + "\n")

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    run_migration()
