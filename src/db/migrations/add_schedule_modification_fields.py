"""
Database migration: Add schedule modification fields
Adds support for skipping workouts, deload weeks, and schedule tracking
"""
import sqlite3
from datetime import datetime

def upgrade(db_path: str = "nowva.db"):
    """Add new columns to schedule table"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Add new columns
        cursor.execute("ALTER TABLE schedule ADD COLUMN skipped BOOLEAN NOT NULL DEFAULT 0")
        cursor.execute("ALTER TABLE schedule ADD COLUMN skipped_at DATETIME")
        cursor.execute("ALTER TABLE schedule ADD COLUMN skip_reason VARCHAR(500)")
        cursor.execute("ALTER TABLE schedule ADD COLUMN is_deload BOOLEAN NOT NULL DEFAULT 0")
        cursor.execute("ALTER TABLE schedule ADD COLUMN deload_intensity_modifier DECIMAL(4, 2) DEFAULT 1.0")
        cursor.execute("ALTER TABLE schedule ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")
        cursor.execute("ALTER TABLE schedule ADD COLUMN modified_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")

        # Create indexes for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedule_date_user ON schedule(scheduled_date, user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedule_skipped ON schedule(skipped)")

        conn.commit()
        print("✓ Migration completed successfully")
        print("  - Added skipped, skipped_at, skip_reason columns")
        print("  - Added is_deload, deload_intensity_modifier columns")
        print("  - Added created_at, modified_at columns")
        print("  - Created performance indexes")

    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("⚠ Columns already exist, skipping migration")
        else:
            print(f"✗ Migration failed: {e}")
            raise
    finally:
        conn.close()


def downgrade(db_path: str = "nowva.db"):
    """Remove schedule modification columns (SQLite doesn't support DROP COLUMN easily)"""
    print("⚠ Downgrade not fully supported in SQLite")
    print("  To revert, you would need to:")
    print("  1. Create new schedule table without new columns")
    print("  2. Copy data from old table")
    print("  3. Drop old table and rename new table")


if __name__ == "__main__":
    import sys

    db_path = sys.argv[1] if len(sys.argv) > 1 else "nowva.db"
    print(f"Running migration on database: {db_path}")
    upgrade(db_path)
