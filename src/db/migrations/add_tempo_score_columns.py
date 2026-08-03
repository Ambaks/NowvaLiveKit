"""
Migration: Add tempo score columns to biomechanics tracking

Rep scoring gained a fifth dimension (tempo — descent and ascent duration
against an ideal window), so both the per-rep and per-set score tables need a
column for it:
- biomechanics_reps.tempo_score
- biomechanics_sets.tempo_score_avg

Both are nullable: rows written before this migration have no tempo score and
must stay readable. Idempotent — safe to run more than once.

Run this migration ONCE per database to update the schema.
"""

from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

ALTER_SQL = """
ALTER TABLE biomechanics_reps ADD COLUMN IF NOT EXISTS tempo_score DOUBLE PRECISION;
ALTER TABLE biomechanics_sets ADD COLUMN IF NOT EXISTS tempo_score_avg DOUBLE PRECISION;
"""

VERIFY_SQL = """
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE (table_name = 'biomechanics_reps' AND column_name = 'tempo_score')
   OR (table_name = 'biomechanics_sets' AND column_name = 'tempo_score_avg')
ORDER BY table_name;
"""


def run_migration():
    """Add the tempo score columns to the biomechanics tables."""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    engine = create_engine(database_url)

    print("=" * 60)
    print("Migration: Add tempo score columns")
    print("=" * 60)

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            print("\n[1/2] Adding columns...")
            for statement in ALTER_SQL.split(";"):
                if statement.strip():
                    conn.execute(text(statement))
            print("✓ biomechanics_reps.tempo_score")
            print("✓ biomechanics_sets.tempo_score_avg")

            trans.commit()
        except Exception as e:
            trans.rollback()
            print(f"\n✗ Migration failed: {e}")
            raise

        print("\n[2/2] Verifying...")
        rows = conn.execute(text(VERIFY_SQL)).fetchall()
        for row in rows:
            print(f"  {row[0]}.{row[1]}: {row[2]}, nullable={row[3]}")

        if len(rows) != 2:
            raise RuntimeError(
                f"Expected 2 columns after migration, found {len(rows)}"
            )

    print("\n✓ Migration completed successfully")


if __name__ == "__main__":
    run_migration()
