"""
Database migration: Add user_anthropometry table (PostgreSQL)
Stores per-user body segment measurements derived from bone-length calibration.
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()


def upgrade():
    """Create user_anthropometry table"""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("✗ DATABASE_URL environment variable not set")
        return

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    try:
        print("Creating user_anthropometry table...")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_anthropometry (
                user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                femur_length_avg DECIMAL(5,2) NOT NULL,
                tibia_length_avg DECIMAL(5,2) NOT NULL,
                torso_length DECIMAL(5,2) NOT NULL,
                hip_width DECIMAL(5,2) NOT NULL,
                shoulder_width DECIMAL(5,2) NOT NULL,
                femur_tibia_ratio DECIMAL(5,3) NOT NULL,
                femur_torso_ratio DECIMAL(5,3) NOT NULL,
                calibration_quality_score DECIMAL(5,3) NOT NULL,
                last_updated TIMESTAMP DEFAULT NOW()
            )
        """)

        conn.commit()
        print("✓ Migration completed successfully")
        print("  - Created user_anthropometry table")
        print("  - Primary key on user_id (one row per user)")

    except psycopg2.Error as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def downgrade():
    """Remove user_anthropometry table"""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("✗ DATABASE_URL environment variable not set")
        return

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    try:
        print("Removing user_anthropometry table...")
        cursor.execute("DROP TABLE IF EXISTS user_anthropometry")
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
