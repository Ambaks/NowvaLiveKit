"""
Migration: Add program_generation_jobs table
This table tracks background job status for program generation via FastAPI.

Usage:
    From project root: python src/db/migrations/add_program_generation_jobs.py
    From src/: python db/migrations/add_program_generation_jobs.py
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
    """Create program_generation_jobs table"""

    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS program_generation_jobs (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    status VARCHAR(50) NOT NULL,
                    progress INTEGER DEFAULT 0,

                    -- Input parameters
                    height_cm DECIMAL(5, 2),
                    weight_kg DECIMAL(5, 2),
                    goal_category VARCHAR(50),
                    goal_raw VARCHAR(500),
                    duration_weeks INTEGER,
                    days_per_week INTEGER,
                    fitness_level VARCHAR(50),

                    -- Output
                    program_id INTEGER REFERENCES user_generated_programs(id) ON DELETE SET NULL,
                    error_message VARCHAR(1000),

                    -- Timestamps
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP WITH TIME ZONE,
                    completed_at TIMESTAMP WITH TIME ZONE
                )
            """))
            conn.commit()
            print("✓ Created program_generation_jobs table")
        except Exception as e:
            if "already exists" in str(e).lower():
                conn.rollback()
                print("✓ program_generation_jobs table already exists")
            else:
                conn.rollback()
                raise e

    # Add indexes for performance
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_pgj_user_id ON program_generation_jobs(user_id)"
            ))
            conn.commit()
            print("✓ Created index on user_id")
        except Exception as e:
            conn.rollback()
            print(f"⚠️  Index creation skipped: {e}")

        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_pgj_status ON program_generation_jobs(status)"
            ))
            conn.commit()
            print("✓ Created index on status")
        except Exception as e:
            conn.rollback()
            print(f"⚠️  Index creation skipped: {e}")

    print("\n✅ Migration completed successfully!")


def downgrade():
    """Remove program_generation_jobs table"""
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS program_generation_jobs CASCADE"))
        conn.commit()
        print("✅ Downgrade completed - table removed")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        print("Running downgrade migration...")
        downgrade()
    else:
        print("Running upgrade migration...")
        upgrade()
