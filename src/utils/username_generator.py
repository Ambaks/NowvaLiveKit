"""
Username Generation Utilities
Handles creating unique usernames from user first names
"""

from db.models import User


def generate_username(first_name: str, db) -> str:
    """
    Generate a unique username from first name.
    Format: firstname123 (adds random numbers if firstname is taken)

    Args:
        first_name: User's first name
        db: Database session

    Returns:
        Unique username

    Examples:
        - "John" -> "john" (if available)
        - "John" -> "john1" (if "john" is taken)
        - "John" -> "john2" (if "john" and "john1" are taken)
    """
    # Clean and lowercase the first name
    base_username = first_name.strip().lower().replace(" ", "")

    # Check if base username is available
    username = base_username
    counter = 1

    while db.query(User).filter(User.username == username).first() is not None:
        # Username exists, add a number
        username = f"{base_username}{counter}"
        counter += 1

    return username
