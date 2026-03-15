"""
Migration: Hash existing plaintext passwords in users table.

Idempotent — bcrypt hashes always start with '$2b$', so already-hashed
entries are detected and skipped.  Safe to run multiple times.

Usage:
    From project root: python src/db/migrations/hash_existing_passwords.py
    From src/: python db/migrations/hash_existing_passwords.py
"""

import sys
from pathlib import Path

# Add src/ to path if needed
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from sqlalchemy import text
from db.database import engine
from auth.security import hash_password


def upgrade():
    """Hash all plaintext passwords in the users table."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, password_hash FROM users")).fetchall()
        hashed_count = 0
        skipped_count = 0

        for row in rows:
            pw = row.password_hash
            # Bcrypt hashes always start with "$2b$" — skip already-hashed entries
            if pw and pw.startswith("$2b$"):
                skipped_count += 1
                continue

            hashed = hash_password(pw)
            conn.execute(
                text("UPDATE users SET password_hash = :h WHERE id = :id"),
                {"h": hashed, "id": row.id},
            )
            hashed_count += 1

        conn.commit()

    print(f"Password migration complete: {hashed_count} hashed, {skipped_count} already hashed (skipped).")


if __name__ == "__main__":
    print("Hashing existing plaintext passwords...")
    upgrade()
    print("Done.")
