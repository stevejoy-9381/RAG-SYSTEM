"""
app.py — Streamlit Frontend (Phase 3: Authentication)
──────────────────────────────────────────────────────
WHAT CHANGED FROM PHASE 2:

  PHASE 2 UI: Opened straight to the chat interface.

  PHASE 3 UI:
    ┌─ Not authenticated ──────────────────────┐
    │  "DocMind" header                        │
    │  [Login tab]  [Register tab]             │
    │  Username + password fields              │
    │  Submit button                           │
    └──────────────────────────────────────────┘

    ┌─ Authenticated ──────────────────────────┐
    │  Sidebar: status, doc library, upload    │
    │           "Logged in as: alice" + logout │
    │  Main: chat bubbles + streaming          │
    └──────────────────────────────────────────┘

AUTH STATE IN session_state:
  st.session_state.auth_token   → JWT string (or None if not logged in)
  st.session_state.username     → display name ("alice")
  st.session_state.user_id      → UUID (for debugging)

  On every page load, the app calls GET /auth/me with the stored token.
  If the API returns 401 (token expired / invalid), the token is cleared
  and the login page is shown. This handles token expiry gracefully.

HOW AUTHENTICATED API CALLS WORK:
  Every requests.post / requests.get call now includes:
    headers={"Authorization": f"Bearer {st.session_state.auth_token}"}

  Helper function auth_headers() returns this dict so we don't repeat it.
"""

import json
import uuid
import requests
import streamlit as st

st.set_page_config(
    page_title="DocMind — Document Q&A",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

import os
# API_BASE_URL env var makes this work in three environments:
#   Local dev (no Docker): http://localhost:8000  (default fallback)
#   Docker Compose:        http://api:8000        (set in docker-compose.yml)
#   Cloud deployment:      https://your-app.onrender.com  (set in Render/Railway)
API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")


# ─── CSS ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.source-card {
    background: var(--background-color, #f8fafc);
    border: 1px solid rgba(0,0,0,0.08);
    border-left: 3px solid #6366f1;
    border-radius: 0 8px 8px 0;
    padding: 10px 14px; margin: 6px 0;
    font-size: 0.82rem; line-height: 1.6;
}
.source-badge {
    background: #eef2ff; color: #4338ca;
    border-radius: 4px; padding: 1px 7px;
    font-size: 0.75rem; font-weight: 600; margin-right: 6px;
}
.doc-card {
    background: rgba(99,102,241,0.06);
    border: 1px solid rgba(99,102,241,0.15);
    border-radius: 8px; padding: 8px 12px; margin-bottom: 6px;
}
.doc-name { font-weight: 600; color: #374151; word-break: break-word; }
.doc-meta { color: #9ca3af; font-size: 0.75rem; margin-top: 2px; }
.user-pill {
    background: #eef2ff; color: #4338ca;
    border-radius: 20px; padding: 4px 12px;
    font-size: 0.82rem; font-weight: 600; display: inline-block;
}
.status-ready    { color: #059669; font-weight: 600; font-size: 0.85rem; }
.status-notready { color: #dc2626; font-weight: 600; font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)


# ─── Session state bootstrap ──────────────────────────────────────────────────
for key, default in [
    ("auth_token",      None),
    ("username",        None),
    ("user_id",         None),
    ("session_id",      str(uuid.uuid4())),
    ("messages",        []),
    ("pending_sources", []),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ─── Auth helpers ─────────────────────────────────────────────────────────────

def auth_headers() -> dict:
    """Return the Authorization header dict for all authenticated API calls."""
    return {"Authorization": f"Bearer {st.session_state.auth_token}"}


def api_health() -> bool:
    try:
        return requests.get(f"{API_BASE}/health", timeout=3).status_code == 200
    except Exception:
        return False


def verify_stored_token() -> bool:
    """
    Call GET /auth/me with the stored token.
    Returns True if the token is still valid.
    Clears auth state and returns False if invalid/expired.

    Called on every page load — this is how we detect expired tokens.
    """
    if not st.session_state.auth_token:
        return False
    try:
        r = requests.get(
            f"{API_BASE}/auth/me",
            headers=auth_headers(),
            timeout=5,
        )
        if r.status_code == 200:
            data = r.json()
            st.session_state.username = data["username"]
            st.session_state.user_id  = data["user_id"]
            return True
        # Token invalid or expired
        _clear_auth()
        return False
    except Exception:
        return False


def _clear_auth():
    """Reset all auth + chat state (used on logout or token expiry)."""
    st.session_state.auth_token      = None
    st.session_state.username        = None
    st.session_state.user_id         = None
    st.session_state.messages        = []
    st.session_state.pending_sources = []
    st.session_state.session_id      = str(uuid.uuid4())


def do_login(username: str, password: str) -> str | None:
    """
    POST /auth/login → store token, return error message or None.

    RETURNS None on success (token stored in session_state).
    RETURNS error string on failure (displayed in the login form).
    """
    try:
        r = requests.post(
            f"{API_BASE}/auth/login",
            json={"username": username, "password": password},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            st.session_state.auth_token = data["access_token"]
            st.session_state.username   = data["username"]
            st.session_state.user_id    = data["user_id"]
            return None   # success
        return r.json().get("detail", "Login failed.")
    except Exception as e:
        return f"Connection error: {e}"


def do_register(username: str, password: str, confirm: str) -> str | None:
    """
    POST /auth/register → store token, return error or None.
    """
    if password != confirm:
        return "Passwords do not match."
    if len(password) < 8:
        return "Password must be at least 8 characters."
    try:
        r = requests.post(
            f"{API_BASE}/auth/register",
            json={"username": username, "password": password},
            timeout=10,
        )
        if r.status_code == 201:
            data = r.json()
            st.session_state.auth_token = data["access_token"]
            st.session_state.username   = data["username"]
            st.session_state.user_id    = data["user_id"]
            return None
        return r.json().get("detail", "Registration failed.")
    except Exception as e:
        return f"Connection error: {e}"


# ─── Document / chat API helpers (all require auth headers) ──────────────────

def api_status() -> dict:
    try:
        r = requests.get(f"{API_BASE}/status", headers=auth_headers(), timeout=5)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


def api_upload(file) -> dict:
    try:
        r = requests.post(
            f"{API_BASE}/upload",
            files={"file": (file.name, file.getvalue(), "application/pdf")},
            headers=auth_headers(),
            timeout=180,
        )
        return r.json() if r.status_code == 200 else {"error": r.json().get("detail", "Upload failed")}
    except Exception as e:
        return {"error": str(e)}


def api_clear_session():
    try:
        requests.delete(
            f"{API_BASE}/sessions/{st.session_state.session_id}",
            headers=auth_headers(), timeout=5,
        )
    except Exception:
        pass


def stream_generator(question: str, session_id: str):
    """
    Generator for st.write_stream(). Identical to Phase 2 but includes
    auth headers in the streaming request.
    """
    st.session_state.pending_sources = []
    try:
        with requests.post(
            f"{API_BASE}/stream",
            json={"question": question, "session_id": session_id},
            headers=auth_headers(),
            stream=True,
            timeout=120,
        ) as resp:
            if resp.status_code == 401:
                _clear_auth()
                yield "⚠️ Your session has expired. Please log in again."
                return
            if resp.status_code != 200:
                try:
                    detail = resp.json().get("detail", "Unknown error")
                except Exception:
                    detail = f"HTTP {resp.status_code}"
                yield f"⚠️ Error: {detail}"
                return

            for raw in resp.iter_lines():
                if not raw:
                    continue
                line = raw.decode("utf-8")
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    event = json.loads(payload)
                    t = event.get("type")
                    if t == "token":
                        yield event["content"]
                    elif t == "metadata":
                        st.session_state.pending_sources = event.get("sources", [])
                        if event.get("session_id"):
                            st.session_state.session_id = event["session_id"]
                    elif t == "error":
                        yield f"\n\n⚠️ {event.get('content', 'Unknown error')}"
                        break
                except json.JSONDecodeError:
                    pass

    except requests.exceptions.ConnectionError:
        yield "\n\n⚠️ Cannot connect to backend. Is the API running?"
    except Exception as e:
        yield f"\n\n⚠️ {str(e)}"


def render_sources(sources: list):
    if not sources:
        return
    with st.expander(f"📚 {len(sources)} source(s)", expanded=False):
        for i, src in enumerate(sources, 1):
            st.markdown(
                f'<div class="source-card">'
                f'<span class="source-badge">Page {src.get("page","?")} / {src.get("total_pages","?")}</span>'
                f'<b>📄 {src.get("file","unknown")}</b>'
                f'<div style="color:#6b7280;margin-top:4px;font-style:italic">"{src.get("preview","")}"</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ═════════════════════════════════════════════════════════════════════════════
# AUTH GATE — everything below only runs if authenticated
# ═════════════════════════════════════════════════════════════════════════════

if not api_health():
    st.error(
        "**Backend offline.**  \nRun: `uvicorn api:app --reload --port 8000`"
    )
    st.stop()

is_authenticated = verify_stored_token()

# ─── Login / Register page ────────────────────────────────────────────────────
if not is_authenticated:
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("## 🧠 DocMind")
        st.caption("Intelligent document Q&A — sign in to get started")
        st.divider()

        login_tab, register_tab = st.tabs(["🔑 Sign In", "📝 Create Account"])

        with login_tab:
            with st.form("login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Sign In", type="primary", use_container_width=True)

            if submitted:
                if not username or not password:
                    st.error("Please enter both username and password.")
                else:
                    with st.spinner("Signing in..."):
                        err = do_login(username.strip(), password)
                    if err:
                        st.error(f"❌ {err}")
                    else:
                        st.success(f"Welcome, {st.session_state.username}!")
                        st.rerun()

        with register_tab:
            with st.form("register_form"):
                new_user = st.text_input("Choose a username", help="3–30 characters, letters/numbers/underscore only")
                new_pass = st.text_input("Password", type="password", help="At least 8 characters")
                confirm  = st.text_input("Confirm password", type="password")
                submitted_reg = st.form_submit_button("Create Account", type="primary", use_container_width=True)

            if submitted_reg:
                if not new_user or not new_pass:
                    st.error("Please fill in all fields.")
                else:
                    with st.spinner("Creating your account..."):
                        err = do_register(new_user.strip(), new_pass, confirm)
                    if err:
                        st.error(f"❌ {err}")
                    else:
                        st.success(f"Account created! Welcome, {st.session_state.username}!")
                        st.rerun()

        st.divider()
        st.caption("Your documents are private and isolated to your account.")
    st.stop()


# ═════════════════════════════════════════════════════════════════════════════
# MAIN APP — only reached when authenticated
# ═════════════════════════════════════════════════════════════════════════════

status = api_status()
is_ready    = status.get("ready", False)
total_docs  = status.get("total_documents", 0)
total_chunks = status.get("total_chunks", 0)

# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🧠 DocMind")

    # User pill
    st.markdown(
        f'<div class="user-pill">👤 {st.session_state.username}</div>',
        unsafe_allow_html=True,
    )
    st.divider()

    # System status
    if is_ready:
        st.markdown(
            f"<div class='status-ready'>● Ready — {total_docs} doc(s), {total_chunks} chunks</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='status-notready'>● No documents indexed</div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # Document library
    st.markdown("#### 📁 Your Documents")
    docs = status.get("documents", [])
    if docs:
        for doc in docs:
            st.markdown(
                f'<div class="doc-card">'
                f'<div class="doc-name">📄 {doc["filename"]}</div>'
                f'<div class="doc-meta">{doc["pages"]} pages · {doc["chunks"]} chunks · {doc["size_kb"]:.0f} KB</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("No documents yet.")

    st.divider()

    # Upload
    st.markdown("#### ➕ Add Document")
    uploaded = st.file_uploader("Upload PDF", type=["pdf"], label_visibility="collapsed")
    if uploaded:
        st.caption(f"📎 {uploaded.name} ({len(uploaded.getvalue())//1024} KB)")
        if st.button("⚙️ Index Document", type="primary", use_container_width=True):
            with st.spinner(f"Indexing '{uploaded.name}'..."):
                result = api_upload(uploaded)
            if "error" not in result:
                st.success(result.get("message", "Indexed!"))
                st.rerun()
            else:
                st.error(f"❌ {result['error']}")

    st.divider()

    # Session + auth controls
    st.markdown("#### 💬 Conversation")
    exchange_count = len(st.session_state.messages) // 2
    if exchange_count > 0:
        st.caption(f"{exchange_count} exchange(s) in memory")
        if st.button("🔄 New Chat", use_container_width=True):
            api_clear_session()
            st.session_state.messages        = []
            st.session_state.pending_sources = []
            st.session_state.session_id      = str(uuid.uuid4())
            st.rerun()
    else:
        st.caption("No history yet.")

    st.divider()
    if st.button("🚪 Sign Out", use_container_width=True):
        api_clear_session()
        _clear_auth()
        st.rerun()

    st.caption("Phase 3: Auth + Isolation\nFastAPI · JWT · FAISS · Groq")


# ─── Main chat area ───────────────────────────────────────────────────────────
st.title("🧠 DocMind")
st.caption(f"Signed in as **{st.session_state.username}** · Your documents are private to your account.")

if not is_ready and not st.session_state.messages:
    st.info("Upload a PDF in the sidebar to start asking questions.")

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("sources"):
            render_sources(msg["sources"])

# Chat input
placeholder = "Ask about your documents..." if is_ready else "Upload a PDF first..."
if prompt := st.chat_input(placeholder, disabled=not is_ready):
    st.session_state.messages.append({"role": "user", "content": prompt, "sources": []})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        full_response = st.write_stream(
            stream_generator(prompt, st.session_state.session_id)
        )
        sources = st.session_state.pending_sources
        render_sources(sources)

    st.session_state.messages.append({
        "role": "assistant", "content": full_response, "sources": sources,
    })
    st.session_state.pending_sources = []
