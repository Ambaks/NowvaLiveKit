"""
Migration: Add biomechanics tracking tables

Creates the 4-table retention + cue-effectiveness schema:
- biomechanics_sessions: one row per workout session
- biomechanics_sets: per-set scores + full diagnosis payload
- biomechanics_reps: every rep with kinematics, faults, keypoints
- cue_events: fault -> cue -> outcome (backfilled) for the flywheel

Run this migration ONCE to update your database schema.
"""

from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

TABLES_SQL = """
CREATE TABLE IF NOT EXISTS biomechanics_sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exercise VARCHAR(50) NOT NULL DEFAULT 'squat',
    started_at TIMESTAMP NOT NULL DEFAULT now(),
    completed_at TIMESTAMP,
    total_reps INTEGER NOT NULL DEFAULT 0,
    total_sets INTEGER NOT NULL DEFAULT 0,
    mean_session_score DOUBLE PRECISION,
    calibration_snapshot JSONB,
    session_causes JSONB
);

CREATE TABLE IF NOT EXISTS biomechanics_sets (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES biomechanics_sessions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    set_number INTEGER NOT NULL,
    rep_count INTEGER NOT NULL,
    mean_score DOUBLE PRECISION,
    depth_score_avg DOUBLE PRECISION,
    trunk_score_avg DOUBLE PRECISION,
    knee_score_avg DOUBLE PRECISION,
    symmetry_score_avg DOUBLE PRECISION,
    trend_slope DOUBLE PRECISION,
    best_rep_number INTEGER,
    worst_rep_number INTEGER,
    diagnosis JSONB,
    scoring JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS biomechanics_reps (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES biomechanics_sessions(id) ON DELETE CASCADE,
    set_id UUID REFERENCES biomechanics_sets(id) ON DELETE SET NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rep_number INTEGER NOT NULL,
    set_number INTEGER,
    is_clean BOOLEAN NOT NULL DEFAULT false,
    depth_class INTEGER,
    max_depth_angle DOUBLE PRECISION,
    composite_score DOUBLE PRECISION,
    depth_score DOUBLE PRECISION,
    trunk_control_score DOUBLE PRECISION,
    knee_tracking_score DOUBLE PRECISION,
    symmetry_score DOUBLE PRECISION,
    kinematics JSONB,
    faults JSONB,
    timing JSONB,
    bottom_kpts JSONB,
    standing_kpts JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cue_events (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES biomechanics_sessions(id) ON DELETE CASCADE,
    set_id UUID REFERENCES biomechanics_sets(id) ON DELETE SET NULL,
    rep_id UUID REFERENCES biomechanics_reps(id) ON DELETE SET NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rep_number INTEGER,
    fault_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20),
    severity_score DOUBLE PRECISION,
    cue_key VARCHAR(100),
    cue_source VARCHAR(30) NOT NULL DEFAULT 'cached_fault',
    cause_id VARCHAR(50),
    message TEXT,
    parameter_delta JSONB,
    delivered BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    present_next_rep BOOLEAN,
    severity_next_rep DOUBLE PRECISION,
    severity_next_set DOUBLE PRECISION,
    effective BOOLEAN
);
"""

INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS ix_biomechanics_sessions_user_id ON biomechanics_sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_biomech_sessions_user_started ON biomechanics_sessions (user_id, started_at);
CREATE INDEX IF NOT EXISTS ix_biomechanics_sets_session_id ON biomechanics_sets (session_id);
CREATE INDEX IF NOT EXISTS ix_biomechanics_sets_user_id ON biomechanics_sets (user_id);
CREATE INDEX IF NOT EXISTS ix_biomech_sets_user_created ON biomechanics_sets (user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_biomechanics_reps_session_id ON biomechanics_reps (session_id);
CREATE INDEX IF NOT EXISTS ix_biomechanics_reps_set_id ON biomechanics_reps (set_id);
CREATE INDEX IF NOT EXISTS ix_biomechanics_reps_user_id ON biomechanics_reps (user_id);
CREATE INDEX IF NOT EXISTS ix_biomech_reps_user_created ON biomechanics_reps (user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_cue_events_session_id ON cue_events (session_id);
CREATE INDEX IF NOT EXISTS ix_cue_events_user_id ON cue_events (user_id);
CREATE INDEX IF NOT EXISTS ix_cue_events_user_fault ON cue_events (user_id, fault_type);
"""

# Idempotent column additions for databases created by an earlier version
ALTER_SQL = """
ALTER TABLE cue_events ADD COLUMN IF NOT EXISTS delivered BOOLEAN NOT NULL DEFAULT false;
"""


def run_migration():
    """Create the biomechanics tracking tables and indexes."""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    engine = create_engine(database_url)

    print("=" * 60)
    print("Migration: Add biomechanics tracking tables")
    print("=" * 60)

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            print("\n[1/3] Creating tables...")
            for statement in TABLES_SQL.split(";"):
                if statement.strip():
                    conn.execute(text(statement))
            print("✓ Tables created (biomechanics_sessions, biomechanics_sets, "
                  "biomechanics_reps, cue_events)")

            print("\n[2/3] Creating indexes...")
            for statement in INDEXES_SQL.split(";"):
                if statement.strip():
                    conn.execute(text(statement))
            print("✓ Indexes created")

            print("\n[3/3] Applying column additions...")
            for statement in ALTER_SQL.split(";"):
                if statement.strip():
                    conn.execute(text(statement))
            print("✓ Columns up to date")

            trans.commit()
            print("\n✓ Migration completed successfully")
        except Exception as e:
            trans.rollback()
            print(f"\n✗ Migration failed: {e}")
            raise


if __name__ == "__main__":
    run_migration()
