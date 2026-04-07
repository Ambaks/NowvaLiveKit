"""
Database Migration: Add Training Season & Equipment Fields to Program Generation Jobs

This migration adds:
1. training_season (VARCHAR) - off_season, pre_season, in_season, post_season
2. games_per_week (INTEGER) - Number of games/competitions per week
3. equipment_tier (INTEGER) - 1=Basic, 2=Full Gym, 3=Specialty

These fields were already passed to Celery tasks but not persisted on the job record.
Adding them enables form prefill for returning users.

Run this migration BEFORE deploying the updated code.

Usage:
    python3 src/db/migrations/add_season_equipment_to_jobs.py

Rollback:
    python3 src/db/migrations/add_season_equipment_to_jobs.py --rollback
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
    print("MIGRATION: Adding Training Season & Equipment Fields to Program Generation Jobs")
    print("=" * 80)

    with engine.connect() as conn:
        trans = conn.begin()

        try:
            print("\n1. Adding training season and equipment fields to 'program_generation_jobs' table...")
            conn.execute(text("""
                ALTER TABLE program_generation_jobs
                ADD COLUMN IF NOT EXISTS training_season VARCHAR(50),
                ADD COLUMN IF NOT EXISTS games_per_week INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS equipment_tier INTEGER DEFAULT 1;
            """))
            print("   ✅ Added: training_season, games_per_week, equipment_tier")

            trans.commit()
            print("\n" + "=" * 80)
            print("✅ MIGRATION COMPLETE")
            print("=" * 80)
            print("\nProgram generation jobs table updated successfully!")
            print("- training_season: VARCHAR(50), nullable")
            print("- games_per_week: INTEGER, default 0")
            print("- equipment_tier: INTEGER, default 1")

        except Exception as e:
            trans.rollback()
            print(f"\n❌ MIGRATION FAILED: {e}")
            print("Rolled back all changes.")
            sys.exit(1)


def rollback():
    """Rollback the migration (remove columns)"""
    print("=" * 80)
    print("ROLLBACK: Removing Training Season & Equipment Fields")
    print("=" * 80)
    print("\n⚠️  WARNING: This will delete the following columns:")
    print("   - program_generation_jobs: training_season, games_per_week, equipment_tier")
    print("\nAny data in these columns will be PERMANENTLY LOST.")

    confirm = input("\nType 'ROLLBACK' to confirm: ")
    if confirm != "ROLLBACK":
        print("Rollback cancelled.")
        return

    with engine.connect() as conn:
        trans = conn.begin()

        try:
            print("\n1. Removing fields from 'program_generation_jobs' table...")
            conn.execute(text("""
                ALTER TABLE program_generation_jobs
                DROP COLUMN IF EXISTS training_season,
                DROP COLUMN IF EXISTS games_per_week,
                DROP COLUMN IF EXISTS equipment_tier;
            """))
            print("   ✅ Removed training_season, games_per_week, equipment_tier")

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
