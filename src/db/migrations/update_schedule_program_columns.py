"""
Migration: Update Schedule table to support both user-generated and partner programs
Changes program_id to user_generated_program_id and adds partner_program_id
"""

import os
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def migrate():
    """Update schedule table to have separate program type columns"""

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("Error: DATABASE_URL not found in environment")
        return False

    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()

        print("Starting migration: Update schedule table program columns...")

        # Check if old column exists
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'schedule' AND column_name = 'program_id'
        """)

        if cur.fetchone():
            print("Found old 'program_id' column. Migrating...")

            # Step 1: Add new columns
            print("Step 1: Adding user_generated_program_id and partner_program_id columns...")
            cur.execute("""
                ALTER TABLE schedule
                ADD COLUMN IF NOT EXISTS user_generated_program_id INTEGER,
                ADD COLUMN IF NOT EXISTS partner_program_id INTEGER
            """)

            # Step 2: Copy data from program_id to user_generated_program_id
            # (assuming all existing programs are user-generated)
            print("Step 2: Copying data from program_id to user_generated_program_id...")
            cur.execute("""
                UPDATE schedule
                SET user_generated_program_id = program_id
                WHERE program_id IS NOT NULL
            """)

            # Step 3: Add foreign key constraints
            print("Step 3: Adding foreign key constraints...")
            cur.execute("""
                ALTER TABLE schedule
                ADD CONSTRAINT fk_schedule_user_generated_program
                FOREIGN KEY (user_generated_program_id)
                REFERENCES user_generated_programs(id)
                ON DELETE CASCADE
            """)

            cur.execute("""
                ALTER TABLE schedule
                ADD CONSTRAINT fk_schedule_partner_program
                FOREIGN KEY (partner_program_id)
                REFERENCES partner_programs(id)
                ON DELETE CASCADE
            """)

            # Step 4: Drop old column
            print("Step 4: Dropping old program_id column...")
            cur.execute("""
                ALTER TABLE schedule DROP COLUMN program_id
            """)

            conn.commit()
            print("✓ Migration completed successfully!")
            return True

        else:
            print("Column 'program_id' not found. Checking if new columns exist...")

            # Check if new columns already exist
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'schedule'
                AND column_name IN ('user_generated_program_id', 'partner_program_id')
            """)

            existing = [row[0] for row in cur.fetchall()]

            if 'user_generated_program_id' in existing and 'partner_program_id' in existing:
                print("✓ New columns already exist. Migration already applied.")
                return True
            else:
                print("Warning: Schema is in an unexpected state.")
                print(f"Existing columns: {existing}")
                return False

    except Exception as e:
        print(f"Error during migration: {e}")
        if conn:
            conn.rollback()
        return False

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
