#!/usr/bin/env python3
"""
Create a test user for program generation testing
"""
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from db.database import SessionLocal
from db.models import User

def create_test_user():
    """Create or get a test user"""
    db = SessionLocal()

    try:
        # Check if test user already exists
        test_user = db.query(User).filter(User.email == "test@nowva.ai").first()

        if test_user:
            print(f"✅ Test user already exists")
            print(f"User ID: {test_user.id}")
            print(f"Name: {test_user.name}")
            print(f"Email: {test_user.email}")
            return str(test_user.id)

        # Create new test user
        print("Creating test user...")
        test_user = User(
            name="Test User",
            email="test@nowva.ai",
            password_hash="test_hash_not_for_login"  # Placeholder, not for actual login
        )

        db.add(test_user)
        db.commit()
        db.refresh(test_user)

        print(f"✅ Test user created successfully")
        print(f"User ID: {test_user.id}")
        print(f"Name: {test_user.name}")
        print(f"Email: {test_user.email}")

        return str(test_user.id)

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()

        # Try to get ANY user from database
        print("\nTrying to find any existing user...")
        any_user = db.query(User).first()

        if any_user:
            print(f"✅ Found existing user")
            print(f"User ID: {any_user.id}")
            print(f"Name: {any_user.name}")
            return str(any_user.id)
        else:
            print("❌ No users found in database")
            return None
    finally:
        db.close()

if __name__ == "__main__":
    user_id = create_test_user()
    if user_id:
        print(f"\n📋 Copy this User ID for testing:")
        print(f"{user_id}")
    else:
        print("\n❌ Could not create or find a test user")
        sys.exit(1)
