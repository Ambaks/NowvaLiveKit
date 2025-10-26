"""
Agent State Management
Handles persistent state for the Nova AI voice agent across different modes
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime


class AgentState:
    """
    Global state manager for the Nova AI agent

    Manages transitions between modes:
    - onboarding: New user setup
    - main_menu: Primary interaction hub
    - workout: Active workout session
    """

    def __init__(self, user_id: Optional[str] = None):
        """
        Initialize agent state

        Args:
            user_id: Optional user ID to load existing state
        """
        self._user_loaded_from_db = False  # Track if we've already loaded user info from DB
        self.state = {
            "mode": "onboarding",  # Current mode: onboarding, main_menu, workout
            "user": {
                "id": user_id,
                "username": None,
                "name": None,
                "email": None,
                "first_time_main_menu": True,
                "created_at": None,
            },
            "session": {
                "started_at": datetime.now().isoformat(),
                "last_mode_switch": None,
                "conversation_history": [],
            },
            "workout": {
                "active": False,
                "exercise": None,
                "reps": 0,
                "sets": 0,
            },
            "program_creation": {
                "has_vbt_capability": False,  # Automatically set based on fitness level + goal + sport
            }
        }

        # Load existing state if user_id provided
        if user_id:
            self.load_state(user_id)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get state value by key path (supports dot notation)

        Args:
            key: Key path (e.g., "user.name" or "mode")
            default: Default value if key not found

        Returns:
            Value at key path or default
        """
        keys = key.split(".")
        value = self.state

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any):
        """
        Set state value by key path (supports dot notation)

        Args:
            key: Key path (e.g., "user.name" or "mode")
            value: Value to set
        """
        keys = key.split(".")
        target = self.state

        # Navigate to parent
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            elif target[k] is None:
                # If the key exists but is None, replace it with an empty dict
                target[k] = {}
            target = target[k]

        # Set final value
        target[keys[-1]] = value

    def switch_mode(self, new_mode: str):
        """
        Switch to a new mode

        Args:
            new_mode: Mode to switch to (onboarding, main_menu, workout)
        """
        old_mode = self.state["mode"]
        self.state["mode"] = new_mode
        self.state["session"]["last_mode_switch"] = {
            "from": old_mode,
            "to": new_mode,
            "timestamp": datetime.now().isoformat()
        }

        print(f"[STATE] Mode switched: {old_mode} → {new_mode}")

    def update_user(self, **kwargs):
        """
        Update user information

        Args:
            **kwargs: User fields to update (name, email, username, etc.)
        """
        for key, value in kwargs.items():
            if key in self.state["user"]:
                self.state["user"][key] = value
                print(f"[STATE] User.{key} updated: {value}")

    def mark_main_menu_visited(self):
        """Mark that user has visited main menu (no longer first time)"""
        self.state["user"]["first_time_main_menu"] = False

    def is_first_time_main_menu(self) -> bool:
        """Check if this is the user's first time in main menu"""
        return self.state["user"].get("first_time_main_menu", True)

    def get_mode(self) -> str:
        """Get current mode"""
        return self.state["mode"]

    def get_user(self) -> Dict:
        """Get user information"""
        return self.state["user"]

    def get_session(self) -> Dict:
        """Get session information"""
        return self.state["session"]

    def save_state(self, filepath: Optional[str] = None):
        """
        Save state to file

        Args:
            filepath: Optional custom filepath, defaults to .agent_state.json
        """
        if filepath is None:
            user_id = self.state["user"].get("id", "guest")
            filepath = f".agent_state_{user_id}.json"

        try:
            with open(filepath, 'w') as f:
                json.dump(self.state, f, indent=2)
            print(f"[STATE] Saved to {filepath}")
        except Exception as e:
            print(f"[STATE] Failed to save state: {e}")

    def load_state(self, user_id: str):
        """
        Load state from file AND populate user info from database

        Args:
            user_id: User ID to load state for
        """
        filepath = f".agent_state_{user_id}.json"

        if not os.path.exists(filepath):
            print(f"[STATE] No saved state found for user {user_id}")
            # Still continue to load user info from database
        else:
            try:
                with open(filepath, 'r') as f:
                    loaded_state = json.load(f)
                    self.state.update(loaded_state)
                # Suppressed verbose logging - uncomment for debugging
                # print(f"[STATE] Loaded state for user {user_id}")
            except Exception as e:
                print(f"[STATE] Failed to load state: {e}")

        # Load user info from database ONLY if not already loaded (prevent spam)
        if not self._user_loaded_from_db:
            self._load_user_from_database(user_id)

    def _load_user_from_database(self, user_id: str):
        """
        Load user information from database (cached - only loads once)

        Args:
            user_id: User ID to load
        """
        if self._user_loaded_from_db:
            return  # Already loaded, skip to prevent DB spam

        try:
            from db.database import SessionLocal
            from db.models import User

            db = SessionLocal()
            try:
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    self.state["user"]["id"] = str(user.id)
                    self.state["user"]["username"] = user.username
                    self.state["user"]["name"] = user.name
                    self.state["user"]["email"] = user.email
                    self.state["user"]["created_at"] = user.created_at.isoformat() if user.created_at else None
                    self._user_loaded_from_db = True  # Mark as loaded
                    print(f"[STATE] Loaded user info from database: {user.name} ({user.username})")
                else:
                    print(f"[STATE] User {user_id} not found in database")
                    self._user_loaded_from_db = True  # Mark as attempted
            finally:
                db.close()
        except Exception as e:
            print(f"[STATE] Failed to load user from database: {e}")
            self._user_loaded_from_db = True  # Mark as attempted even if failed

    def reload_state(self):
        """
        Reload state from file for the current user
        """
        user_id = self.state["user"].get("id")
        if not user_id:
            print(f"[STATE] Cannot reload - no user ID set")
            return

        self.load_state(user_id)

    def to_dict(self) -> Dict:
        """Get state as dictionary"""
        return self.state

    def __repr__(self) -> str:
        """String representation of state"""
        return f"AgentState(mode={self.state['mode']}, user={self.state['user']['name']})"
