"""
Migration: Add height_cm and weight_kg columns to users table
Run this script once to add the new columns to existing databases.

Usage:
    From project root: python src/db/migrations/add_height_weight_to_users.py
    From src/: python db/migrations/add_height_weight_to_users.py
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
    """Add height_cm and weight_kg columns to users table"""
    # Add each column in a separate transaction to avoid transaction state issues

    # Add height_cm column
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN height_cm DECIMAL(5, 2)"
            ))
            conn.commit()
            print("✓ Added height_cm column to users table")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                conn.rollback()
                print("✓ height_cm column already exists")
            else:
                conn.rollback()
                raise e

    # Add weight_kg column
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN weight_kg DECIMAL(5, 2)"
            ))
            conn.commit()
            print("✓ Added weight_kg column to users table")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                conn.rollback()
                print("✓ weight_kg column already exists")
            else:
                conn.rollback()
                raise e

    print("\n✅ Migration completed successfully!")


def downgrade():
    """Remove height_cm and weight_kg columns from users table"""
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS height_cm"))
        conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS weight_kg"))
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
