"""
Database Migration: Add VBT Support and Enhanced Program Parameters

This migration adds:
1. VBT (Velocity-Based Training) fields to sets and progress_logs tables
2. Enhanced programming parameters to program_generation_jobs table
   (session_duration, injury_history, age, sex, specific_sport, has_vbt_capability)

Run this migration BEFORE deploying the updated code.

Usage:
    python3 src/db/migrations/add_vbt_and_enhanced_params.py

Rollback:
    python3 src/db/migrations/add_vbt_and_enhanced_params.py --rollback
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set in environment")

engine = create_engine(DATABASE_URL)


def migrate():
    """Apply the migration (add new columns)"""
    print("=" * 80)
    print("MIGRATION: Adding VBT and Enhanced Program Parameters")
    print("=" * 80)

    with engine.connect() as conn:
        # Start transaction
        trans = conn.begin()

        try:
            print("\n1. Adding VBT fields to 'sets' table...")
            # Add VBT columns to sets table
            conn.execute(text("""
                ALTER TABLE sets
                ADD COLUMN IF NOT EXISTS velocity_threshold DECIMAL(4, 2),
                ADD COLUMN IF NOT EXISTS velocity_min DECIMAL(4, 2),
                ADD COLUMN IF NOT EXISTS velocity_max DECIMAL(4, 2);
            """))
            print("   ✅ Added: velocity_threshold, velocity_min, velocity_max")

            print("\n2. Adding VBT tracking fields to 'progress_logs' table...")
            # Add VBT tracking columns to progress_logs table
            conn.execute(text("""
                ALTER TABLE progress_logs
                ADD COLUMN IF NOT EXISTS measured_velocity DECIMAL(4, 2),
                ADD COLUMN IF NOT EXISTS velocity_loss DECIMAL(5, 2);
            """))
            print("   ✅ Added: measured_velocity, velocity_loss")

            print("\n3. Adding enhanced parameters to 'program_generation_jobs' table...")
            # Add enhanced programming columns to program_generation_jobs table
            conn.execute(text("""
                ALTER TABLE program_generation_jobs
                ADD COLUMN IF NOT EXISTS session_duration INTEGER DEFAULT 60,
                ADD COLUMN IF NOT EXISTS injury_history TEXT DEFAULT 'none',
                ADD COLUMN IF NOT EXISTS age INTEGER,
                ADD COLUMN IF NOT EXISTS sex VARCHAR(10),
                ADD COLUMN IF NOT EXISTS specific_sport VARCHAR(100) DEFAULT 'none',
                ADD COLUMN IF NOT EXISTS has_vbt_capability BOOLEAN DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS user_notes TEXT;
            """))
            print("   ✅ Added: session_duration, injury_history, age, sex, specific_sport, has_vbt_capability, user_notes")

            # Commit transaction
            trans.commit()
            print("\n" + "=" * 80)
            print("✅ MIGRATION COMPLETE")
            print("=" * 80)
            print("\nAll tables updated successfully!")
            print("- Sets table: VBT velocity fields added")
            print("- Progress logs table: VBT tracking fields added")
            print("- Program generation jobs table: Enhanced parameters added")
            print("\nYou can now deploy the updated code.")

        except Exception as e:
            trans.rollback()
            print(f"\n❌ MIGRATION FAILED: {e}")
            print("Rolled back all changes.")
            sys.exit(1)


def rollback():
    """Rollback the migration (remove columns)"""
    print("=" * 80)
    print("ROLLBACK: Removing VBT and Enhanced Program Parameters")
    print("=" * 80)
    print("\n⚠️  WARNING: This will delete the following columns:")
    print("   - sets: velocity_threshold, velocity_min, velocity_max")
    print("   - progress_logs: measured_velocity, velocity_loss")
    print("   - program_generation_jobs: session_duration, injury_history, age, sex, specific_sport, has_vbt_capability, user_notes")
    print("\nAny data in these columns will be PERMANENTLY LOST.")

    confirm = input("\nType 'ROLLBACK' to confirm: ")
    if confirm != "ROLLBACK":
        print("Rollback cancelled.")
        return

    with engine.connect() as conn:
        trans = conn.begin()

        try:
            print("\n1. Removing VBT fields from 'sets' table...")
            conn.execute(text("""
                ALTER TABLE sets
                DROP COLUMN IF EXISTS velocity_threshold,
                DROP COLUMN IF EXISTS velocity_min,
                DROP COLUMN IF EXISTS velocity_max;
            """))
            print("   ✅ Removed VBT fields from sets")

            print("\n2. Removing VBT tracking fields from 'progress_logs' table...")
            conn.execute(text("""
                ALTER TABLE progress_logs
                DROP COLUMN IF EXISTS measured_velocity,
                DROP COLUMN IF EXISTS velocity_loss;
            """))
            print("   ✅ Removed VBT fields from progress_logs")

            print("\n3. Removing enhanced parameters from 'program_generation_jobs' table...")
            conn.execute(text("""
                ALTER TABLE program_generation_jobs
                DROP COLUMN IF EXISTS session_duration,
                DROP COLUMN IF EXISTS injury_history,
                DROP COLUMN IF EXISTS age,
                DROP COLUMN IF EXISTS sex,
                DROP COLUMN IF EXISTS specific_sport,
                DROP COLUMN IF EXISTS has_vbt_capability,
                DROP COLUMN IF EXISTS user_notes;
            """))
            print("   ✅ Removed enhanced parameters from program_generation_jobs")

            trans.commit()
            print("\n" + "=" * 80)
            print("✅ ROLLBACK COMPLETE")
            print("=" * 80)

        except Exception as e:
            trans.rollback()
            print(f"\n❌ ROLLBACK FAILED: {e}")
            sys.exit(1)


if __name__ == "__main__":
    if "--rollback" in sys.argv:
        rollback()
    else:
        migrate()
