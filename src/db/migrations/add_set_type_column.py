"""
Database Migration: Add set_type column to sets table

This migration adds:
1. set_type column to sets table (V6: advanced set scheme support)

Run this migration BEFORE deploying V6 code.

Usage:
    python3 src/db/migrations/add_set_type_column.py

Rollback:
    python3 src/db/migrations/add_set_type_column.py --rollback
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set in environment")

engine = create_engine(DATABASE_URL)


def migrate():
    """Apply the migration (add set_type column)"""
    print("=" * 80)
    print("MIGRATION: Adding set_type column to sets table (V6)")
    print("=" * 80)

    with engine.connect() as conn:
        trans = conn.begin()

        try:
            print("\n1. Adding set_type to 'sets' table...")
            conn.execute(text("""
                ALTER TABLE sets
                ADD COLUMN IF NOT EXISTS set_type VARCHAR(20) DEFAULT 'standard';
            """))
            print("   Added: set_type (standard, cluster, rest_pause, myo_rep, drop_set, back_off, amrap, wave)")

            trans.commit()
            print("\n" + "=" * 80)
            print("MIGRATION COMPLETE")
            print("=" * 80)

        except Exception as e:
            trans.rollback()
            print(f"\nMIGRATION FAILED: {e}")
            sys.exit(1)


def rollback():
    """Rollback the migration (remove set_type column)"""
    print("=" * 80)
    print("ROLLBACK: Removing set_type column from sets table")
    print("=" * 80)

    confirm = input("\nType 'ROLLBACK' to confirm: ")
    if confirm != "ROLLBACK":
        print("Rollback cancelled.")
        return

    with engine.connect() as conn:
        trans = conn.begin()

        try:
            conn.execute(text("""
                ALTER TABLE sets
                DROP COLUMN IF EXISTS set_type;
            """))
            print("   Removed set_type from sets")

            trans.commit()
            print("\nROLLBACK COMPLETE")

        except Exception as e:
            trans.rollback()
            print(f"\nROLLBACK FAILED: {e}")
            sys.exit(1)


if __name__ == "__main__":
    if "--rollback" in sys.argv:
        rollback()
    else:
        migrate()
