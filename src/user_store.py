"""
src/user_store.py — User Registry
────────────────────────────────────
WHAT THIS FILE DOES:
  Manages user accounts stored in a simple JSON file.
  Handles registration, login verification, and user lookup.

WHY A JSON FILE (NOT A DATABASE)?
  For a portfolio project, a JSON file is the right starting point:
    - Zero setup: no Postgres, no SQLite schema, no migrations
    - Human-readable: you can open users.json and inspect it
    - Sufficient for demo-scale (tens to hundreds of users)
    - Clear upgrade path: replace this file with SQLAlchemy when needed

  The JSON file stores hashed passwords (bcrypt) — NEVER plain text.
  Even if someone stole the file, they couldn't recover passwords.

  For real production: use SQLite (via SQLAlchemy) or Supabase.
  The auth.py and api.py files would need no changes — only this file.

USER RECORD FORMAT:
  {
    "user_id":       "a1b2c3d4-...",  ← UUID, permanent identifier
    "username":      "alice",          ← display name, must be unique
    "email":         "a@example.com",  ← optional, for future use
    "password_hash": "$2b$12$...",     ← bcrypt hash (never plain text)
    "created_at":    "2024-01-15T..."  ← ISO timestamp
  }

CONNECTIONS:
  → Uses src/auth.py for password hashing/verification
  → Called by api.py on /auth/register and /auth/login endpoints
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from src.auth import hash_password, verify_password


USER_REGISTRY_PATH = "vectorstore/users.json"


# ─── Internal registry I/O ────────────────────────────────────────────────────

def _load_registry() -> dict:
    """
    Load the user registry from disk.

    FORMAT:
    {
        "users": {
            "alice": { user record dict },
            "bob":   { user record dict },
        }
    }

    Keyed by username for O(1) username lookup during login.
    """
    if not os.path.exists(USER_REGISTRY_PATH):
        return {"users": {}}
    try:
        with open(USER_REGISTRY_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        print("[USERS] ⚠️  User registry corrupted. Starting fresh.")
        return {"users": {}}


def _save_registry(registry: dict) -> None:
    os.makedirs(os.path.dirname(USER_REGISTRY_PATH), exist_ok=True)
    with open(USER_REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)


# ─── Public API ───────────────────────────────────────────────────────────────

def register_user(username: str, password: str, email: str = "") -> dict:
    """
    Create a new user account.

    VALIDATION:
      - Username must be 3–30 chars, alphanumeric + underscore only
      - Password must be at least 8 characters
      - Username must not already exist

    WHAT HAPPENS:
      1. Validate username + password format
      2. Check username isn't taken
      3. Hash the password with bcrypt
      4. Create user record with a new UUID
      5. Save to users.json

    RETURNS:
      The new user record (without password_hash for safety).

    RAISES:
      ValueError with a human-readable message for all validation failures.
      api.py catches ValueError and returns a 400 HTTP error.
    """
    # ── Validate username ─────────────────────────────────────────────────────
    username = username.strip().lower()   # normalize to lowercase
    if len(username) < 3:
        raise ValueError("Username must be at least 3 characters.")
    if len(username) > 30:
        raise ValueError("Username must be 30 characters or fewer.")
    if not all(c.isalnum() or c == "_" for c in username):
        raise ValueError(
            "Username may only contain letters, numbers, and underscores."
        )

    # ── Validate password ─────────────────────────────────────────────────────
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    # ── Check for duplicate username ──────────────────────────────────────────
    registry = _load_registry()
    if username in registry["users"]:
        raise ValueError(f"Username '{username}' is already taken.")

    # ── Create user record ────────────────────────────────────────────────────
    user_id = str(uuid.uuid4())
    user = {
        "user_id":       user_id,
        "username":      username,
        "email":         email.strip().lower() if email else "",
        "password_hash": hash_password(password),   # bcrypt hash
        "created_at":    datetime.now(timezone.utc).isoformat(),
    }

    registry["users"][username] = user
    _save_registry(registry)

    print(f"[USERS] New user registered: '{username}' ({user_id[:8]}...)")

    # Return safe record (exclude password_hash)
    return {k: v for k, v in user.items() if k != "password_hash"}


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """
    Verify username + password and return the user record if valid.

    WHAT HAPPENS:
      1. Look up username in registry (O(1) dict lookup)
      2. If not found → return None (don't reveal "user doesn't exist")
      3. Verify bcrypt hash (takes ~100ms intentionally)
      4. If valid → return safe user record

    WHY NOT SAY "user not found" vs "wrong password"?
      Distinguishing them lets attackers enumerate valid usernames.
      Always return the same generic error for both cases.
      ("Invalid username or password" — not one or the other.)

    RETURNS:
      Safe user record (no password_hash) if valid.
      None if invalid — api.py returns 401 Unauthorized.
    """
    username = username.strip().lower()
    registry = _load_registry()

    user = registry["users"].get(username)
    if not user:
        return None   # User doesn't exist — return None, not an error

    if not verify_password(password, user["password_hash"]):
        return None   # Wrong password — same response as "not found"

    print(f"[USERS] Authenticated: '{username}' ({user['user_id'][:8]}...)")
    return {k: v for k, v in user.items() if k != "password_hash"}


def get_user_by_id(user_id: str) -> Optional[dict]:
    """
    Fetch a user record by their user_id (UUID).

    Used by the get_current_user dependency in api.py
    to validate that a user in a JWT token still exists
    (handles the case where a user was deleted after a token was issued).
    """
    registry = _load_registry()
    for user in registry["users"].values():
        if user["user_id"] == user_id:
            return {k: v for k, v in user.items() if k != "password_hash"}
    return None


def get_user_count() -> int:
    """Return total number of registered users (for admin/status endpoint)."""
    return len(_load_registry()["users"])


def username_exists(username: str) -> bool:
    """Quick check if a username is taken (for registration form validation)."""
    return username.strip().lower() in _load_registry()["users"]
