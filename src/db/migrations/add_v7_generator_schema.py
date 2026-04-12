"""
Database Migration: Add V7 generator schema

Adds:
- Generator versioning on jobs/programs
- Canonical exercise identity fields
- V7 program artifact storage
- Postgres-backed knowledge graph tables

Usage:
    python3 src/db/migrations/add_v7_generator_schema.py

Rollback:
    python3 src/db/migrations/add_v7_generator_schema.py --rollback
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set in environment")

engine = create_engine(DATABASE_URL)


def migrate():
    print("=" * 80)
    print("MIGRATION: Adding V7 generator schema")
    print("=" * 80)

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            print("\n1. Updating existing tables for V7 compatibility...")
            conn.execute(text("""
                ALTER TABLE user_generated_programs
                ADD COLUMN IF NOT EXISTS generator_version VARCHAR(20) NOT NULL DEFAULT 'v5',
                ADD COLUMN IF NOT EXISTS artifact_ref JSONB;
            """))
            conn.execute(text("""
                ALTER TABLE program_generation_jobs
                ADD COLUMN IF NOT EXISTS generator_version VARCHAR(20) NOT NULL DEFAULT 'v5';
            """))
            conn.execute(text("""
                ALTER TABLE exercises
                ADD COLUMN IF NOT EXISTS canonical_id VARCHAR(255);
            """))
            conn.execute(text("""
                ALTER TABLE workout_exercises
                ADD COLUMN IF NOT EXISTS canonical_exercise_id VARCHAR(255);
            """))
            conn.execute(text("""
                UPDATE user_generated_programs
                SET generator_version = 'v5'
                WHERE generator_version IS NULL;
            """))
            conn.execute(text("""
                UPDATE program_generation_jobs
                SET generator_version = 'v5'
                WHERE generator_version IS NULL;
            """))

            print("2. Creating V7 knowledge graph tables...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS kg_versions (
                    id SERIAL PRIMARY KEY,
                    version_label VARCHAR(100) NOT NULL UNIQUE,
                    description TEXT,
                    is_active BOOLEAN NOT NULL DEFAULT FALSE,
                    metadata_json JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS kg_exercises (
                    id SERIAL PRIMARY KEY,
                    version_id INTEGER NOT NULL REFERENCES kg_versions(id) ON DELETE CASCADE,
                    canonical_id VARCHAR(255) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    family_id VARCHAR(255) NOT NULL,
                    equipment_min INTEGER NOT NULL DEFAULT 1,
                    difficulty INTEGER NOT NULL DEFAULT 3,
                    movement_pattern VARCHAR(100) NOT NULL,
                    exercise_type VARCHAR(100) NOT NULL,
                    rotation_group VARCHAR(255) NOT NULL,
                    bilateral BOOLEAN NOT NULL DEFAULT TRUE,
                    vbt_eligible BOOLEAN NOT NULL DEFAULT FALSE,
                    tags TEXT[],
                    fatigue_json JSONB,
                    stimulus_json JSONB,
                    constraints_json JSONB,
                    metadata_json JSONB
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS kg_exercise_relations (
                    id SERIAL PRIMARY KEY,
                    version_id INTEGER NOT NULL REFERENCES kg_versions(id) ON DELETE CASCADE,
                    src_id VARCHAR(255) NOT NULL,
                    relation_type VARCHAR(100) NOT NULL,
                    dst_id VARCHAR(255) NOT NULL,
                    payload_json JSONB
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS kg_session_roles (
                    id SERIAL PRIMARY KEY,
                    version_id INTEGER NOT NULL REFERENCES kg_versions(id) ON DELETE CASCADE,
                    role_id VARCHAR(255) NOT NULL,
                    label VARCHAR(255) NOT NULL,
                    session_type VARCHAR(100) NOT NULL,
                    goal VARCHAR(50) NOT NULL,
                    config_json JSONB NOT NULL
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS kg_progression_templates (
                    id SERIAL PRIMARY KEY,
                    version_id INTEGER NOT NULL REFERENCES kg_versions(id) ON DELETE CASCADE,
                    family_id VARCHAR(255) NOT NULL,
                    session_role VARCHAR(255) NOT NULL,
                    goal_phase VARCHAR(100) NOT NULL,
                    training_level VARCHAR(50) NOT NULL,
                    template_json JSONB NOT NULL
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS kg_block_templates (
                    id SERIAL PRIMARY KEY,
                    version_id INTEGER NOT NULL REFERENCES kg_versions(id) ON DELETE CASCADE,
                    template_id VARCHAR(255) NOT NULL,
                    goal VARCHAR(50) NOT NULL,
                    phase VARCHAR(100) NOT NULL,
                    duration_weeks INTEGER NOT NULL,
                    days_per_week INTEGER NOT NULL,
                    season_context VARCHAR(50) NOT NULL DEFAULT 'standard',
                    periodization_model VARCHAR(100) NOT NULL,
                    template_json JSONB NOT NULL
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS kg_constraint_rules (
                    id SERIAL PRIMARY KEY,
                    version_id INTEGER NOT NULL REFERENCES kg_versions(id) ON DELETE CASCADE,
                    rule_id VARCHAR(255) NOT NULL,
                    rule_type VARCHAR(100) NOT NULL,
                    subject_type VARCHAR(100) NOT NULL,
                    subject_key VARCHAR(255) NOT NULL,
                    config_json JSONB NOT NULL
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS program_artifacts_v7 (
                    id SERIAL PRIMARY KEY,
                    user_generated_program_id INTEGER NOT NULL UNIQUE REFERENCES user_generated_programs(id) ON DELETE CASCADE,
                    job_id UUID REFERENCES program_generation_jobs(id) ON DELETE SET NULL,
                    directive_json JSONB NOT NULL,
                    block_plan_json JSONB NOT NULL,
                    assembly_trace_json JSONB NOT NULL,
                    validation_json JSONB NOT NULL,
                    critic_json JSONB,
                    metrics_json JSONB,
                    kg_version VARCHAR(100) NOT NULL,
                    prompt_version VARCHAR(100) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))

            trans.commit()
        except Exception as exc:
            trans.rollback()
            print(f"\nMIGRATION FAILED: {exc}")
            sys.exit(1)

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            print("\n3. Creating indexes...")
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_exercises_canonical_id
                ON exercises(canonical_id)
                WHERE canonical_id IS NOT NULL;
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_workout_exercises_canonical
                ON workout_exercises(canonical_exercise_id);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_program_generation_jobs_generator_version
                ON program_generation_jobs(generator_version);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_user_generated_programs_generator_version
                ON user_generated_programs(generator_version);
            """))
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_kg_exercises_version_canonical
                ON kg_exercises(version_id, canonical_id);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_kg_exercises_pattern
                ON kg_exercises(version_id, movement_pattern);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_kg_exercises_family
                ON kg_exercises(version_id, family_id);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_kg_relations_src
                ON kg_exercise_relations(version_id, src_id, relation_type);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_kg_session_roles_lookup
                ON kg_session_roles(version_id, role_id, goal);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_kg_progression_lookup
                ON kg_progression_templates(version_id, family_id, session_role, goal_phase, training_level);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_kg_block_lookup
                ON kg_block_templates(version_id, goal, phase, duration_weeks, days_per_week, season_context);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_kg_constraint_lookup
                ON kg_constraint_rules(version_id, rule_type, subject_key);
            """))
            trans.commit()
            print("\n✅ MIGRATION COMPLETE")
        except Exception as exc:
            trans.rollback()
            print(f"\nINDEX CREATION FAILED: {exc}")
            sys.exit(1)


def rollback():
    print("=" * 80)
    print("ROLLBACK: Removing V7 generator schema")
    print("=" * 80)

    confirm = input("\nType 'ROLLBACK' to confirm: ")
    if confirm != "ROLLBACK":
        print("Rollback cancelled.")
        return

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text("DROP TABLE IF EXISTS program_artifacts_v7 CASCADE;"))
            conn.execute(text("DROP TABLE IF EXISTS kg_constraint_rules CASCADE;"))
            conn.execute(text("DROP TABLE IF EXISTS kg_block_templates CASCADE;"))
            conn.execute(text("DROP TABLE IF EXISTS kg_progression_templates CASCADE;"))
            conn.execute(text("DROP TABLE IF EXISTS kg_session_roles CASCADE;"))
            conn.execute(text("DROP TABLE IF EXISTS kg_exercise_relations CASCADE;"))
            conn.execute(text("DROP TABLE IF EXISTS kg_exercises CASCADE;"))
            conn.execute(text("DROP TABLE IF EXISTS kg_versions CASCADE;"))
            conn.execute(text("""
                ALTER TABLE user_generated_programs
                DROP COLUMN IF EXISTS generator_version,
                DROP COLUMN IF EXISTS artifact_ref;
            """))
            conn.execute(text("""
                ALTER TABLE program_generation_jobs
                DROP COLUMN IF EXISTS generator_version;
            """))
            conn.execute(text("""
                ALTER TABLE exercises
                DROP COLUMN IF EXISTS canonical_id;
            """))
            conn.execute(text("""
                ALTER TABLE workout_exercises
                DROP COLUMN IF EXISTS canonical_exercise_id;
            """))
            trans.commit()
            print("✅ ROLLBACK COMPLETE")
        except Exception as exc:
            trans.rollback()
            print(f"ROLLBACK FAILED: {exc}")
            sys.exit(1)


if __name__ == "__main__":
    if "--rollback" in sys.argv:
        rollback()
    else:
        migrate()
