"""
Migration: Add age and sex columns to users table

This migration adds:
- age: Integer (nullable) - User's age
- sex: String(10) (nullable) - User's sex ("male" or "female")

Run this migration ONCE to update your database schema.
"""

from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def run_migration():
    """Add age and sex columns to users table"""

    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    # Create engine
    engine = create_engine(database_url)

    print("=" * 60)
    print("Migration: Add age and sex to users table")
    print("=" * 60)

    with engine.connect() as conn:
        # Start transaction
        trans = conn.begin()

        try:
            # Check if columns already exist
            print("\n[1/3] Checking if columns already exist...")
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'users'
                AND column_name IN ('age', 'sex')
            """))
            existing_columns = [row[0] for row in result]

            if 'age' in existing_columns and 'sex' in existing_columns:
                print("✓ Columns already exist. No migration needed.")
                trans.rollback()
                return

            # Add age column if it doesn't exist
            if 'age' not in existing_columns:
                print("\n[2/3] Adding 'age' column...")
                conn.execute(text("""
                    ALTER TABLE users
                    ADD COLUMN age INTEGER NULL
                """))
                print("✓ 'age' column added successfully")
            else:
                print("\n[2/3] 'age' column already exists, skipping")

            # Add sex column if it doesn't exist
            if 'sex' not in existing_columns:
                print("\n[3/3] Adding 'sex' column...")
                conn.execute(text("""
                    ALTER TABLE users
                    ADD COLUMN sex VARCHAR(10) NULL
                """))
                print("✓ 'sex' column added successfully")
            else:
                print("\n[3/3] 'sex' column already exists, skipping")

            # Commit transaction
            trans.commit()
            print("\n" + "=" * 60)
            print("✅ Migration completed successfully!")
            print("=" * 60)

        except Exception as e:
            trans.rollback()
            print(f"\n❌ Migration failed: {e}")
            raise

if __name__ == "__main__":
    run_migration()
