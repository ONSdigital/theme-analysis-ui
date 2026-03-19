"""Utility functions for managing user accounts."""

from werkzeug.security import generate_password_hash


def generate_password_hash_value(password: str) -> str:
    """Generate a secure password hash for offline user provisioning.

    Args:
        password: The plaintext password to hash.

    Returns:
        A Werkzeug-compatible password hash string.

    Raises:
        ValueError: If the password is empty or only whitespace.
    """
    candidate_password = password.strip()
    if not candidate_password:
        msg = "Password must not be empty."
        raise ValueError(msg)

    return generate_password_hash(candidate_password)
