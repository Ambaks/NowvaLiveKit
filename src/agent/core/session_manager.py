"""
Session Management
Handles local session storage with encryption
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
from cryptography.fernet import Fernet, InvalidToken


class SessionManager:
    """Manages encrypted user sessions stored locally"""

    def __init__(self, session_file: str = ".session.dat", key_file: str = ".session.key"):
        """
        Initialize session manager with encryption

        Args:
            session_file: Path to encrypted session file (relative to src/)
            key_file: Path to encryption key file (relative to src/)
        """
        # Store in src/ directory (parent of core/)
        src_dir = Path(__file__).parent.parent
        self.session_file = src_dir / session_file
        self.key_file = src_dir / key_file

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

    def get_username(self) -> Optional[str]:
        """Get username from current session"""
        session = self.load_session()
        return session.get("username") if session else None
