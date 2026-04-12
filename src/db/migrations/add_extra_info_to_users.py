"""
Migration: Add extra_info column to users table

This migration adds:
- extra_info: Text (nullable) - Free-form user-volunteered context captured during
  voice onboarding (training background, personal goals, life context, etc.)

Run this migration ONCE to update your database schema.
"""

from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def run_migration():
    """Add extra_info column to users table"""

    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    # Create engine
    engine = create_engine(database_url)

    print("=" * 60)
    print("Migration: Add extra_info to users table")
    print("=" * 60)

    with engine.connect() as conn:
        # Start transaction
        trans = conn.begin()

        try:
            # Check if column already exists
            print("\n[1/2] Checking if column already exists...")
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'users'
                AND column_name = 'extra_info'
            """))
            existing_columns = [row[0] for row in result]

            if 'extra_info' in existing_columns:
                print("[OK] Column already exists. No migration needed.")
                trans.rollback()
                return

            # Add extra_info column
            print("\n[2/2] Adding 'extra_info' column...")
            conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN extra_info TEXT NULL
            """))
            print("[OK] 'extra_info' column added successfully")

            # Commit transaction
            trans.commit()
            print("\n" + "=" * 60)
            print("Migration completed successfully!")
            print("=" * 60)

        except Exception as e:
            trans.rollback()
            print(f"\nMigration failed: {e}")
            raise


if __name__ == "__main__":
    run_migration()
