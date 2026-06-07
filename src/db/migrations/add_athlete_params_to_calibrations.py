"""
Database migration: Add athlete_params and baseline columns to user_calibrations (PostgreSQL)
Persists body proportions and ROM baseline so returning users skip assessment + calibration.
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()


def upgrade():
    """Add athlete_params and baseline JSONB columns."""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("✗ DATABASE_URL environment variable not set")
        return

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    try:
        print("Adding athlete_params column to user_calibrations...")
        cursor.execute(
            "ALTER TABLE user_calibrations "
            "ADD COLUMN IF NOT EXISTS athlete_params JSONB"
        )

        print("Adding baseline column to user_calibrations...")
        cursor.execute(
            "ALTER TABLE user_calibrations "
            "ADD COLUMN IF NOT EXISTS baseline JSONB"
        )

        conn.commit()
        print("✓ Migration completed successfully")
        print("  - Added athlete_params (JSONB, nullable) column")
        print("  - Added baseline (JSONB, nullable) column")

    except psycopg2.Error as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def downgrade():
    """Remove athlete_params and baseline columns."""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("✗ DATABASE_URL environment variable not set")
        return

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    try:
        print("Removing athlete_params and baseline columns...")
        cursor.execute("ALTER TABLE user_calibrations DROP COLUMN IF EXISTS athlete_params")
        cursor.execute("ALTER TABLE user_calibrations DROP COLUMN IF EXISTS baseline")

        conn.commit()
        print("✓ Downgrade completed successfully")

    except psycopg2.Error as e:
        conn.rollback()
        print(f"✗ Downgrade failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        print("Running downgrade migration...")
        downgrade()
    else:
        print("Running upgrade migration...")
        upgrade()
