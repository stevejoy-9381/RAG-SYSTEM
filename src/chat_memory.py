"""
src/chat_memory.py — In-Memory Chat History Store
──────────────────────────────────────────────────
WHAT THIS FILE DOES:
  Manages conversation history for every active user session.
  A "session" is one browser tab's conversation — it starts when
  the user loads the app and ends when the tab closes or they
  click "New Chat".

  This gives the LLM memory of what was discussed earlier in the
  conversation, enabling follow-up questions like:
    User:  "What datasets did they use?"
    Bot:   "The paper used ImageNet and COCO..."
    User:  "How large were those?"   ← "those" refers to the datasets above
    Bot:   "ImageNet has 1.2M images..."  ← only possible with memory

WHY IN-MEMORY (NOT A DATABASE)?
  Three options exist. Here's why we chose in-memory:

  Option A — Streamlit session_state (simplest):
    Only works if frontend and backend are the same process.
    Won't work in our FastAPI + Streamlit separation.

  Option B — FastAPI in-memory dict (THIS APPROACH):
    A Python dict in the API process: {session_id: [messages]}.
    Pros: zero setup, zero dependencies, fast.
    Cons: lost on server restart, can't scale to multiple API instances.
    Perfect for: portfolio projects, single-server deployments.

  Option C — Database (Redis/SQLite/Postgres):
    Persists across restarts, scales horizontally.
    Adds complexity: schema design, migrations, connection management.
    Use this when you have real users with login accounts.

  For Phase 2 (portfolio): Option B.
  When you add auth in Phase 3: migrate to Option C.

SLIDING WINDOW — WHY WE LIMIT HISTORY:
  LLMs have a context window — a maximum number of tokens they can
  process in one request. Llama3-8B has an 8192-token limit.

  If we sent the full conversation history on every request:
    - 10 exchanges × ~200 tokens each = 2000 tokens just for history
    - Plus 2000 tokens of retrieved chunks
    - Plus the question
    = 4000+ tokens already consumed, leaving little room for the answer

  The sliding window keeps only the last MAX_EXCHANGES pairs,
  which is typically 3-4 exchanges = ~600-800 tokens.
  Enough to handle "tell me more" and "what about X?" follow-ups.

CONNECTIONS:
  → Called by api.py on every POST /stream and POST /chat request
  → Session IDs are created by the Streamlit frontend (uuid4)
    and sent with every request
"""

import time
import uuid
from collections import defaultdict
from typing import Optional


# ─── Configuration ────────────────────────────────────────────────────────────

# How many user/assistant exchanges to remember
# 1 exchange = 1 user message + 1 assistant message
# 4 exchanges = 8 messages = ~600–800 tokens of context overhead
MAX_EXCHANGES = int(4)

# How many seconds of inactivity before a session is eligible for cleanup
# 7200 seconds = 2 hours
SESSION_TIMEOUT_SECONDS = 7200

# How many total sessions to allow before forcing cleanup
# Prevents memory leaks if the server runs for weeks
MAX_SESSIONS = 500


# ─── Session Store ────────────────────────────────────────────────────────────
#
# Structure:
# {
#   "session-uuid-1": {
#     "messages": [
#       {"role": "user",      "content": "What is BERT?"},
#       {"role": "assistant", "content": "BERT is a transformer model..."},
#       {"role": "user",      "content": "How was it trained?"},
#       {"role": "assistant", "content": "It was trained on..."}
#     ],
#     "last_active": 1705329811.23,  ← unix timestamp
#     "created_at":  1705329600.00
#   },
#   ...
# }
#
_sessions: dict = {}


# ─── Public API ───────────────────────────────────────────────────────────────

def create_session_id() -> str:
    """
    Generate a new unique session ID.

    The frontend calls this on first load and stores the ID
    in Streamlit's session_state. All subsequent requests
    from that browser tab include this ID.

    We use UUID4 (random) so session IDs are unguessable —
    important even without full auth, as it prevents one user
    from reading another's conversation history.
    """
    return str(uuid.uuid4())


def get_history(session_id: str) -> list[dict]:
    """
    Return the chat history for a session as a list of message dicts.

    FORMAT (standard OpenAI/Groq messages format):
      [
        {"role": "user",      "content": "What is attention?"},
        {"role": "assistant", "content": "Attention is a mechanism..."},
        ...
      ]

    Returns an empty list if the session doesn't exist yet.
    This handles the very first message in a session gracefully.

    IMPORTANT: Returns only the last MAX_EXCHANGES × 2 messages.
    Older messages are sliced off — the sliding window.
    """
    if session_id not in _sessions:
        return []

    # Update last_active timestamp
    _sessions[session_id]["last_active"] = time.time()

    messages = _sessions[session_id]["messages"]

    # Apply sliding window: keep only the last N exchanges
    max_messages = MAX_EXCHANGES * 2  # each exchange = 2 messages
    if len(messages) > max_messages:
        messages = messages[-max_messages:]

    return messages


def add_exchange(session_id: str, user_message: str, assistant_message: str) -> None:
    """
    Save a completed user/assistant exchange to the session history.

    Called AFTER the LLM response is complete (either streamed or full).
    We save the final full text of the assistant's answer, not tokens.

    WHY NOT SAVE DURING STREAMING?
      Streaming yields partial text. If the user closes the tab mid-stream,
      we'd save an incomplete response. It's cleaner to save the full
      answer only after generation is confirmed complete.
    """
    # Create session if it doesn't exist yet
    if session_id not in _sessions:
        _init_session(session_id)

    session = _sessions[session_id]

    # Append the user message
    session["messages"].append({
        "role": "user",
        "content": user_message.strip(),
    })

    # Append the assistant response
    session["messages"].append({
        "role": "assistant",
        "content": assistant_message.strip(),
    })

    session["last_active"] = time.time()

    # Trigger cleanup if we're approaching the session cap
    if len(_sessions) > MAX_SESSIONS * 0.9:
        _cleanup_old_sessions()

    print(f"[MEMORY] Session '{session_id[:8]}...' now has "
          f"{len(session['messages']) // 2} exchange(s)")


def clear_session(session_id: str) -> bool:
    """
    Clear all history for a session (but keep the session alive).

    Called when the user clicks "New Chat" in the UI.
    Returns True if the session existed and was cleared.
    """
    if session_id not in _sessions:
        return False

    _sessions[session_id]["messages"] = []
    _sessions[session_id]["last_active"] = time.time()
    print(f"[MEMORY] Session '{session_id[:8]}...' cleared.")
    return True


def get_session_summary(session_id: str) -> dict:
    """
    Return metadata about a session (for the /sessions/{id} endpoint).
    """
    if session_id not in _sessions:
        return {
            "session_id": session_id,
            "exists": False,
            "exchange_count": 0,
            "messages": [],
        }

    messages = _sessions[session_id]["messages"]
    return {
        "session_id": session_id,
        "exists": True,
        "exchange_count": len(messages) // 2,
        "messages": messages,
        "last_active": _sessions[session_id]["last_active"],
    }


def get_active_session_count() -> int:
    """Return the number of active sessions (for monitoring/status endpoint)."""
    return len(_sessions)


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _init_session(session_id: str) -> None:
    """Create a new empty session."""
    now = time.time()
    _sessions[session_id] = {
        "messages": [],
        "created_at": now,
        "last_active": now,
    }
    print(f"[MEMORY] New session created: '{session_id[:8]}...'")


def _cleanup_old_sessions() -> int:
    """
    Remove sessions that have been inactive beyond SESSION_TIMEOUT_SECONDS.

    This prevents memory leaks on long-running servers.
    Called automatically when approaching MAX_SESSIONS.

    Returns the number of sessions removed.
    """
    now = time.time()
    cutoff = now - SESSION_TIMEOUT_SECONDS

    expired = [
        sid for sid, data in _sessions.items()
        if data["last_active"] < cutoff
    ]

    for sid in expired:
        del _sessions[sid]

    if expired:
        print(f"[MEMORY] Cleaned up {len(expired)} expired session(s). "
              f"Active: {len(_sessions)}")

    return len(expired)
