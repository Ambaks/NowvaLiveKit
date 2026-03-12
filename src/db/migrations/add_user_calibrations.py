"""
Database migration: Add user_calibrations table (PostgreSQL)
Stores per-user, per-movement-pattern biomechanical calibration data.
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()


def upgrade():
    """Create user_calibrations table"""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("✗ DATABASE_URL environment variable not set")
        return

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    try:
        print("Creating user_calibrations table...")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_calibrations (
                id SERIAL PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                movement_pattern VARCHAR(50) NOT NULL,
                peaks JSONB NOT NULL,
                thresholds JSONB NOT NULL,
                calibration_reps INTEGER NOT NULL DEFAULT 5,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),

                UNIQUE (user_id, movement_pattern)
            )
        """)

        print("Creating indexes...")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_calibrations_user_pattern "
            "ON user_calibrations(user_id, movement_pattern)"
        )

        conn.commit()
        print("✓ Migration completed successfully")
        print("  - Created user_calibrations table")
        print("  - Added unique constraint on (user_id, movement_pattern)")
        print("  - Added index on (user_id, movement_pattern)")

    except psycopg2.Error as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def downgrade():
    """Remove user_calibrations table"""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("✗ DATABASE_URL environment variable not set")
        return

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    try:
        print("Removing user_calibrations table...")

        cursor.execute("DROP INDEX IF EXISTS idx_user_calibrations_user_pattern")
        cursor.execute("DROP TABLE IF EXISTS user_calibrations")

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
