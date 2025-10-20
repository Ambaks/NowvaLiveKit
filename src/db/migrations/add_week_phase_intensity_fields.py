"""
Migration: Add week_number, phase to workouts and intensity_percent to sets
Created: 2025-10-20

Usage:
    From project root: python src/db/migrations/add_week_phase_intensity_fields.py
"""

import sys
from pathlib import Path

# Add src/ to path if needed
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from sqlalchemy import text
from db.database import engine


def upgrade():
    """Add new fields for week-by-week program structure"""

    # Add week_number to workouts
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE workouts ADD COLUMN week_number INTEGER"
            ))
            conn.commit()
            print("✓ Added week_number column to workouts table")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                conn.rollback()
                print("✓ week_number column already exists")
            else:
                conn.rollback()
                raise e

    # Add phase to workouts
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE workouts ADD COLUMN phase VARCHAR(50)"
            ))
            conn.commit()
            print("✓ Added phase column to workouts table")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                conn.rollback()
                print("✓ phase column already exists")
            else:
                conn.rollback()
                raise e

    # Add intensity_percent to sets
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE sets ADD COLUMN intensity_percent DECIMAL(5, 2)"
            ))
            conn.commit()
            print("✓ Added intensity_percent column to sets table")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                conn.rollback()
                print("✓ intensity_percent column already exists")
            else:
                conn.rollback()
                raise e

    print("\n✅ Migration completed successfully!")


def downgrade():
    """Remove the added fields"""
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE workouts DROP COLUMN IF EXISTS week_number"))
        conn.execute(text("ALTER TABLE workouts DROP COLUMN IF EXISTS phase"))
        conn.execute(text("ALTER TABLE sets DROP COLUMN IF EXISTS intensity_percent"))
        conn.commit()
        print("✅ Downgrade completed - columns removed")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        print("Running downgrade migration...")
        downgrade()
    else:
        print("Running upgrade migration...")
        upgrade()
