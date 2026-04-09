"""Create or update a user in a local users.json file.

For proof of concept, this script is intended to be run offline by an admin. It hashes the
provided plaintext password before persisting it to the JSON file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from theme_analysis_ui.auth.password_utils import generate_password_hash_value

VALID_ROLES = frozenset({"user", "admin", "tester"})


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        The parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Create or update a user in a users.json file.",
    )
    parser.add_argument(
        "users_file",
        type=Path,
        help="Path to the users.json file.",
    )
    parser.add_argument(
        "--username",
        required=True,
        help="User email address.",
    )
    parser.add_argument(
        "--password",
        required=True,
        help="Plaintext password to hash and store.",
    )
    parser.add_argument(
        "--role",
        required=True,
        choices=sorted(VALID_ROLES),
        help="Role for the user.",
    )
    return parser.parse_args()


def load_users(users_file: Path) -> list[dict[str, str]]:
    """Load the users file.

    Args:
        users_file: Path to the JSON file.

    Returns:
        The parsed list of user records.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the JSON structure is invalid.
    """
    raw_payload = users_file.read_text(encoding="utf-8")
    parsed_payload = json.loads(raw_payload)

    if not isinstance(parsed_payload, list):
        msg = "users.json must contain a list of user records."
        raise ValueError(msg)

    users: list[dict[str, str]] = []
    for record in parsed_payload:
        if not isinstance(record, dict):
            msg = "Each user record must be a JSON object."
            raise ValueError(msg)

        username = str(record.get("username", "")).strip().lower()
        password = str(record.get("password", ""))
        role = str(record.get("role", "")).strip().lower()

        if not username:
            msg = "Each user record must include a username."
            raise ValueError(msg)
        if not password:
            msg = f"User record for '{username}' must include a password."
            raise ValueError(msg)
        if role not in VALID_ROLES:
            msg = f"User record for '{username}' has an invalid role '{role}'."
            raise ValueError(msg)

        users.append(
            {
                "username": username,
                "password": password,
                "role": role,
            },
        )

    return users


def upsert_user(
    users: list[dict[str, str]],
    username: str,
    password: str,
    role: str,
) -> tuple[list[dict[str, str]], bool]:
    """Create or update a user record.

    Args:
        users: Existing user records.
        username: User email address.
        password: Plaintext password to hash.
        role: User role.

    Returns:
        A tuple containing the updated user list and a boolean indicating
        whether an existing user was updated.

    Raises:
        ValueError: If the role is invalid.
    """
    normalised_username = username.strip().lower()
    normalised_role = role.strip().lower()

    if normalised_role not in VALID_ROLES:
        msg = f"Invalid role '{role}'. Expected one of {sorted(VALID_ROLES)}."
        raise ValueError(msg)

    hashed_password = generate_password_hash_value(password)
    new_record = {
        "username": normalised_username,
        "password": hashed_password,
        "role": normalised_role,
    }

    for index, existing_record in enumerate(users):
        if existing_record["username"] == normalised_username:
            users[index] = new_record
            return users, True

    users.append(new_record)
    users.sort(key=lambda item: item["username"])
    return users, False


def save_users(users_file: Path, users: list[dict[str, str]]) -> None:
    """Write the updated users list to disk.

    Args:
        users_file: Path to the JSON file.
        users: User records to persist.
    """
    payload = json.dumps(users, indent=4)
    users_file.write_text(f"{payload}\n", encoding="utf-8")


def main() -> int:
    """Run the user provisioning script.

    Returns:
        Process exit code.
    """
    args = parse_args()
    users = load_users(args.users_file)
    updated_users, was_updated = upsert_user(
        users=users,
        username=args.username,
        password=args.password,
        role=args.role,
    )
    save_users(args.users_file, updated_users)

    action = "Updated" if was_updated else "Created"
    print(f"{action} user '{args.username.strip().lower()}' in {args.users_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
