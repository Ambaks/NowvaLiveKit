#!/usr/bin/env python3
"""
Database Setup Script
Run this script to initialize your database tables.
"""

import sys
from pathlib import Path

# Add the parent directory to the path so we can import the module
sys.path.insert(0, str(Path(__file__).parent.parent))

from db import init_db, Base, engine


def main():
    print("=" * 50)
    print("Database Setup Script")
    print("=" * 50)

    print("\nThis will create all tables in your database.")
    print("Make sure your DATABASE_URL is set correctly in .env file.\n")

    response = input("Do you want to continue? (y/n): ")

    if response.lower() != 'y':
        print("Setup cancelled.")
        return

    try:
        print("\nCreating tables...")
        init_db()

        print("\nTables created successfully!")
        print("\nThe following tables were created:")
        for table_name in Base.metadata.tables.keys():
            print(f"  - {table_name}")

    except Exception as e:
        print(f"\nError creating tables: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
