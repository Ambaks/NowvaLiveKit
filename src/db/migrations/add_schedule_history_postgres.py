"""
Database migration: Add schedule change history table (PostgreSQL)
Enables undo functionality with JSONB snapshots of schedule state
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def upgrade():
    """Create schedule_change_history table"""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("✗ DATABASE_URL environment variable not set")
        return

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    try:
        print("Creating schedule_change_history table...")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedule_change_history (
                id SERIAL PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                change_type VARCHAR(50) NOT NULL,
                description TEXT NOT NULL,
                affected_schedule_ids INTEGER[],
                before_state JSONB NOT NULL,
                after_state JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                function_name VARCHAR(100),
                is_undone BOOLEAN DEFAULT FALSE,
                undone_at TIMESTAMP NULL,
                undo_change_id INTEGER NULL REFERENCES schedule_change_history(id)
            )
        """)

        # Create performance indexes
        print("Creating performance indexes...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_created ON schedule_change_history(user_id, created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_undone ON schedule_change_history(user_id, is_undone)")

        conn.commit()
        print("✓ Migration completed successfully")
        print("  - Created schedule_change_history table")
        print("  - Added indexes for user_id + created_at and user_id + is_undone")
        print("  - JSONB columns for before/after state snapshots")

    except psycopg2.Error as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def downgrade():
    """Remove schedule_change_history table"""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("✗ DATABASE_URL environment variable not set")
        return

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    try:
        print("Removing schedule_change_history table...")

        cursor.execute("DROP INDEX IF EXISTS idx_user_undone")
        cursor.execute("DROP INDEX IF EXISTS idx_user_created")
        cursor.execute("DROP TABLE IF EXISTS schedule_change_history")

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
