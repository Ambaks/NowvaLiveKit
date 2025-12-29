"""
Database migration: Add schedule modification fields (PostgreSQL)
Adds support for skipping workouts, deload weeks, and schedule tracking
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def upgrade():
    """Add new columns to schedule table"""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("✗ DATABASE_URL environment variable not set")
        return

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    try:
        # Add new columns (PostgreSQL syntax)
        print("Adding new columns to schedule table...")

        cursor.execute("ALTER TABLE schedule ADD COLUMN IF NOT EXISTS skipped BOOLEAN NOT NULL DEFAULT FALSE")
        cursor.execute("ALTER TABLE schedule ADD COLUMN IF NOT EXISTS skipped_at TIMESTAMP")
        cursor.execute("ALTER TABLE schedule ADD COLUMN IF NOT EXISTS skip_reason VARCHAR(500)")
        cursor.execute("ALTER TABLE schedule ADD COLUMN IF NOT EXISTS is_deload BOOLEAN NOT NULL DEFAULT FALSE")
        cursor.execute("ALTER TABLE schedule ADD COLUMN IF NOT EXISTS deload_intensity_modifier DECIMAL(4, 2) DEFAULT 1.0")
        cursor.execute("ALTER TABLE schedule ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP")
        cursor.execute("ALTER TABLE schedule ADD COLUMN IF NOT EXISTS modified_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP")

        # Create indexes for performance
        print("Creating performance indexes...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedule_date_user ON schedule(scheduled_date, user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedule_skipped ON schedule(skipped)")

        conn.commit()
        print("✓ Migration completed successfully")
        print("  - Added skipped, skipped_at, skip_reason columns")
        print("  - Added is_deload, deload_intensity_modifier columns")
        print("  - Added created_at, modified_at columns")
        print("  - Created performance indexes")

    except psycopg2.Error as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def downgrade():
    """Remove schedule modification columns"""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("✗ DATABASE_URL environment variable not set")
        return

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    try:
        print("Removing schedule modification columns...")

        cursor.execute("DROP INDEX IF EXISTS idx_schedule_skipped")
        cursor.execute("DROP INDEX IF EXISTS idx_schedule_date_user")
        cursor.execute("ALTER TABLE schedule DROP COLUMN IF EXISTS modified_at")
        cursor.execute("ALTER TABLE schedule DROP COLUMN IF EXISTS created_at")
        cursor.execute("ALTER TABLE schedule DROP COLUMN IF EXISTS deload_intensity_modifier")
        cursor.execute("ALTER TABLE schedule DROP COLUMN IF EXISTS is_deload")
        cursor.execute("ALTER TABLE schedule DROP COLUMN IF EXISTS skip_reason")
        cursor.execute("ALTER TABLE schedule DROP COLUMN IF EXISTS skipped_at")
        cursor.execute("ALTER TABLE schedule DROP COLUMN IF EXISTS skipped")

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
