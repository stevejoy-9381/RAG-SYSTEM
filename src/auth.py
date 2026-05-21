"""
src/auth.py — JWT Authentication
──────────────────────────────────
WHAT THIS FILE DOES:
  Two jobs:
    1. Password hashing  — safely store and verify passwords using bcrypt
    2. JWT management    — create access tokens and verify them on each request

WHY JWT (JSON Web Tokens)?
  HTTP is stateless — the server doesn't "remember" you between requests.
  Two ways to solve this:
    Sessions: server stores a session dict {session_id: user_data}.
              Works but requires server memory, doesn't scale across instances.
    JWT:      server signs a token containing user data and sends it to the client.
              Client sends the token on every request.
              Server verifies the signature — no server-side storage needed.
              Scales horizontally, works with any number of API instances.

  For a portfolio RAG app: JWT is the right choice.

HOW JWT WORKS (simplified):
  Token = base64(header) + "." + base64(payload) + "." + HMAC_signature
  payload = {"sub": user_id, "username": "alice", "exp": 1705416000}
  signature = HMAC_SHA256(header + "." + payload, secret_key)

  Server creates: signs with SECRET_KEY
  Client stores: in session_state (browser memory)
  Client sends: Authorization: Bearer <token>
  Server verifies: checks HMAC signature with SECRET_KEY
                   checks "exp" field hasn't expired
                   extracts user_id from "sub" field

  If SECRET_KEY is kept private, tokens cannot be forged.
  If a token is stolen, it's valid until it expires (hence short expiry = safer).

WHY bcrypt FOR PASSWORDS?
  You must NEVER store plain-text passwords.
  bcrypt is a one-way hash function designed specifically for passwords:
    - Intentionally slow (100ms per hash) → brute-force attacks are impractical
    - Salted automatically → same password hashes differently each time
    - Industry standard since 1999

  SHA256/MD5 are NOT safe for passwords — they're too fast (attackers can
  try billions per second). Use bcrypt, scrypt, or argon2 for passwords.

CONNECTIONS:
  → Used by src/user_store.py for password operations
  → Used by api.py for the auth dependency (get_current_user)
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

# ─── Configuration ────────────────────────────────────────────────────────────

# The secret key signs every JWT. Must be secret and random.
# Minimum 32 characters — longer is safer.
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if not SECRET_KEY or SECRET_KEY == "replace_this_with_a_long_random_string_at_least_32_chars":
    import secrets
    # In development, generate a random key if not set.
    # WARNING: This means tokens are invalidated on every server restart.
    # Always set JWT_SECRET_KEY in .env for production.
    SECRET_KEY = secrets.token_hex(32)
    print(
        "[AUTH] ⚠️  JWT_SECRET_KEY not set in .env. "
        "A random key was generated — tokens won't survive server restarts. "
        "Set JWT_SECRET_KEY in your .env file."
    )

# HS256 = HMAC-SHA256. Simple and secure for single-server deployments.
# Use RS256 (asymmetric) if multiple services need to verify tokens.
ALGORITHM = "HS256"

# Token lifetime — 24 hours is standard for web apps.
# Shorter = more secure (stolen tokens expire faster).
# Longer = better UX (user doesn't have to log in as often).
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", 24))


# ─── Password hashing ─────────────────────────────────────────────────────────

# CryptContext manages hashing schemes.
# schemes=["bcrypt"] means bcrypt is the only accepted algorithm.
# deprecated="auto" means older schemes are rejected automatically.
pwd_context = CryptContext(
    schemes=["bcrypt"],
    bcrypt__rounds=12,
    deprecated="auto"
)


def hash_password(plain_password: str) -> str:
    """
    Hash a plain-text password using bcrypt.

    WHAT HAPPENS INSIDE:
      1. A random salt is generated (16 bytes)
      2. The password + salt is hashed with bcrypt (intentionally slow: ~100ms)
      3. Returns: "$2b$12$<salt><hash>" — all information needed to verify later

    The same password hashed twice produces DIFFERENT strings because the
    salt is random. This is correct behaviour — it prevents rainbow table attacks.

    EXAMPLE:
      hash_password("mysecret") → "$2b$12$N9qo8..."
      hash_password("mysecret") → "$2b$12$K3mR1..."   ← different! (different salt)
    """
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Check if a plain-text password matches a stored bcrypt hash.

    WHAT HAPPENS INSIDE:
      1. Extracts the salt from the stored hash
      2. Hashes plain_password WITH THAT SAME SALT
      3. Compares the result to the stored hash (constant-time comparison)

    Returns True if they match, False otherwise.
    The constant-time comparison prevents timing attacks.
    """
    return pwd_context.verify(plain_password, hashed_password)


# ─── JWT token operations ─────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    """
    Create a signed JWT access token.

    WHAT'S IN THE TOKEN:
      data should contain:
        {"sub": user_id, "username": "alice"}

      We add:
        {"exp": datetime_24h_from_now}   ← expiry timestamp

    The "sub" (subject) field is the standard JWT claim for user identity.
    We use user_id (UUID) as the subject — not username, because:
      - Usernames can change; UUIDs are permanent
      - UUIDs reveal no personal information if the token is logged

    RETURNS:
      A compact JWT string: "eyJhbGc....eyJzdWI....signature"
      This is what gets stored in the browser and sent in every request header.
    """
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload["exp"] = expire

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token


def decode_access_token(token: str) -> Optional[dict]:
    """
    Verify a JWT token and return its payload.

    VERIFIES:
      1. Signature — was this token signed by our SECRET_KEY?
         If no: someone tampered with it → reject
      2. Expiry — is "exp" in the future?
         If no: token is expired → reject

    RETURNS:
      The decoded payload dict if valid: {"sub": user_id, "username": "alice", "exp": ...}
      None if invalid or expired.

    WHY RETURN None INSTEAD OF RAISING?
      The FastAPI dependency (get_current_user in api.py) will raise
      the HTTPException with the right status code.
      Keeping this function pure (no HTTP concerns) makes it testable.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
