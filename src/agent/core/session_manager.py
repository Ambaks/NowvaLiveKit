"""
Session Management
Handles local session storage with encryption and user profile switching.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
from cryptography.fernet import Fernet, InvalidToken


class SessionManager:
    """Manages encrypted user sessions stored locally"""

    def __init__(self, session_file: str = ".session.dat", key_file: str = ".session.key"):
        # Store in src/ directory (core/ → agent/ → src/)
        src_dir = Path(__file__).parent.parent.parent
        self.session_file = src_dir / session_file
        self.key_file = src_dir / key_file
        self._profiles_dir = src_dir / ".profiles"

        # Load or generate encryption key
        if self.key_file.exists():
            self.key = self.key_file.read_bytes()
        else:
            self.key = Fernet.generate_key()
            self.key_file.write_bytes(self.key)

        self.fernet = Fernet(self.key)

    def session_exists(self) -> bool:
        """Check if a valid session exists"""
        return self.session_file.exists()

    def load_session(self) -> Optional[Dict]:
        """
        Load and decrypt session from file

        Returns:
            Session dict or None if no session exists
        """
        if not self.session_exists():
            return None

        try:
            # Read encrypted data
            encrypted_data = self.session_file.read_bytes()

            # Decrypt
            decrypted_data = self.fernet.decrypt(encrypted_data)

            # Parse JSON
            session = json.loads(decrypted_data.decode())
            return session
        except (InvalidToken, json.JSONDecodeError, IOError) as e:
            print(f"Error loading session: {e}")
            return None

    def save_session(self, user_id, username: str, email: str) -> bool:
        """
        Encrypt and save session to file

        Args:
            user_id: Database user ID (can be int, str, or UUID)
            username: Username
            email: User email

        Returns:
            True if successful, False otherwise
        """
        # Convert user_id to string to handle UUID objects
        user_id_str = str(user_id)

        session = {
            "user_id": user_id_str,
            "username": username,
            "email": email,
            "created_at": datetime.now().isoformat()
        }

        try:
            # Convert to JSON
            session_data = json.dumps(session).encode()

            # Encrypt
            encrypted_data = self.fernet.encrypt(session_data)

            # Write to file
            self.session_file.write_bytes(encrypted_data)

            print(f"Session saved for user: {username}")
            return True
        except (IOError, Exception) as e:
            print(f"Error saving session: {e}")
            return False

    def clear_session(self) -> bool:
        """
        Clear/delete session file

        Returns:
            True if successful, False otherwise
        """
        try:
            if self.session_file.exists():
                self.session_file.unlink()
                print("Session cleared")
            return True
        except IOError as e:
            print(f"Error clearing session: {e}")
            return False

    def get_user_id(self) -> Optional[str]:
        """Get user ID from current session (returns as string to handle UUIDs)"""
        session = self.load_session()
        return session.get("user_id") if session else None

    def get_username(self) -> str | None:
        """Get username from current session"""
        session = self.load_session()
        return session.get("username") if session else None

    # ── Profile switching ────────────────────────────────────────────

    def _ensure_profiles_dir(self) -> Path:
        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        return self._profiles_dir

    def save_profile(self, name: str) -> bool:
        """Copy current .session.dat to a named profile file."""
        if not self.session_exists():
            print("No active session to save as a profile.")
            return False
        dest = self._ensure_profiles_dir() / f"{name}.profile"
        dest.write_bytes(self.session_file.read_bytes())
        print(f"Profile '{name}' saved.")
        return True

    def load_profile(self, name: str) -> bool:
        """Replace .session.dat with a previously saved profile."""
        src = self._profiles_dir / f"{name}.profile"
        if not src.exists():
            print(f"Profile '{name}' not found.")
            return False
        self.session_file.write_bytes(src.read_bytes())
        session = self.load_session()
        if session:
            print(f"Switched to profile '{name}' (user: {session.get('username')})")
        return True

    def list_profiles(self) -> list[dict[str, str]]:
        """Return [{name, username, email}] for every saved profile."""
        if not self._profiles_dir.exists():
            return []
        profiles: list[dict[str, str]] = []
        for path in sorted(self._profiles_dir.glob("*.profile")):
            try:
                data = self.fernet.decrypt(path.read_bytes())
                info = json.loads(data.decode())
                profiles.append({
                    "name": path.stem,
                    "username": info.get("username", "?"),
                    "email": info.get("email", "?"),
                })
            except (InvalidToken, json.JSONDecodeError):
                profiles.append({"name": path.stem, "username": "?", "email": "?"})
        return profiles

    def delete_profile(self, name: str) -> bool:
        """Remove a saved profile file."""
        path = self._profiles_dir / f"{name}.profile"
        if not path.exists():
            print(f"Profile '{name}' not found.")
            return False
        path.unlink()
        print(f"Profile '{name}' deleted.")
        return True
