"""
Database migration: Add training load tracking tables (PostgreSQL)
Enables deload week recommendations based on fatigue monitoring
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def upgrade():
    """Create training_load_metrics and deload_history tables"""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("✗ DATABASE_URL environment variable not set")
        return

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    try:
        print("Creating training_load_metrics table...")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS training_load_metrics (
                id SERIAL PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                week_start_date DATE NOT NULL,
                week_end_date DATE NOT NULL,

                -- Volume metrics
                total_sets INTEGER DEFAULT 0,
                total_reps INTEGER DEFAULT 0,
                total_volume_kg DECIMAL(10, 2) DEFAULT 0,

                -- Intensity metrics
                avg_rpe DECIMAL(3, 1),
                high_rpe_sets INTEGER DEFAULT 0,

                -- Velocity metrics
                avg_velocity DECIMAL(4, 2),
                velocity_decline_percent DECIMAL(5, 2),

                -- Fatigue indicators
                fatigue_score DECIMAL(5, 2),
                deload_recommended BOOLEAN DEFAULT FALSE,

                calculated_at TIMESTAMP DEFAULT NOW(),
                workouts_completed INTEGER DEFAULT 0,

                UNIQUE (user_id, week_start_date)
            )
        """)

        print("Creating deload_history table...")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS deload_history (
                id SERIAL PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                week_start_date DATE NOT NULL,
                week_end_date DATE NOT NULL,
                intensity_modifier DECIMAL(4, 2) DEFAULT 0.7,
                trigger_reason TEXT,
                fatigue_score_at_trigger DECIMAL(5, 2),
                applied BOOLEAN DEFAULT FALSE,
                applied_at TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Create performance indexes
        print("Creating performance indexes...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_week ON training_load_metrics(user_id, week_start_date DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_applied ON deload_history(user_id, applied, created_at DESC)")

        conn.commit()
        print("✓ Migration completed successfully")
        print("  - Created training_load_metrics table")
        print("  - Created deload_history table")
        print("  - Added indexes for user_id + week_start_date and user_id + applied")

    except psycopg2.Error as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def downgrade():
    """Remove training load tables"""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("✗ DATABASE_URL environment variable not set")
        return

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    try:
        print("Removing training load tables...")

        cursor.execute("DROP INDEX IF EXISTS idx_user_applied")
        cursor.execute("DROP INDEX IF EXISTS idx_user_week")
        cursor.execute("DROP TABLE IF EXISTS deload_history")
        cursor.execute("DROP TABLE IF EXISTS training_load_metrics")

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
