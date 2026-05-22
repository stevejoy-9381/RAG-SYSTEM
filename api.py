"""
api.py — FastAPI Backend (Phase 3: Authentication)
────────────────────────────────────────────────────
WHAT CHANGED FROM PHASE 2:

  NEW ENDPOINTS:
    POST /auth/register     → create a new user account
    POST /auth/login        → authenticate, receive JWT token
    GET  /auth/me           → verify token, return user profile

  ALL DOCUMENT + CHAT ENDPOINTS NOW PROTECTED:
    Every endpoint (except /health, /auth/*) now requires:
      Authorization: Bearer <token>
    in the request header.

    FastAPI's Depends(get_current_user) handles this automatically:
      1. Extracts "Bearer <token>" from the Authorization header
      2. Decodes and verifies the JWT
      3. Returns the user dict to the endpoint function
      4. Returns 401 Unauthorized if the token is missing/invalid/expired

  PER-USER STATE:
    Phase 2: _qa_chain was a global singleton (one chain for all users)
    Phase 3: No global chain. Each endpoint call gets the user_id from
             the JWT and builds/caches the chain for that user.
             _retriever_cache in retriever.py handles caching per user_id.

HOW get_current_user DEPENDENCY WORKS:
  FastAPI's dependency injection system:

  @app.post("/upload")
  async def upload(
      file: UploadFile,
      user: dict = Depends(get_current_user)   ← injected automatically
  ):
      user_id = user["user_id"]   ← from the verified JWT
      ...

  If the token is missing → FastAPI returns 401 before the function runs.
  If the token is valid → FastAPI calls get_current_user(), gets the user dict,
  passes it to the endpoint function as the "user" parameter.

  This is clean, reusable, and impossible to forget — unlike manually
  parsing the Authorization header in every endpoint.
"""

import os
import json
import asyncio
import tempfile
import threading
import queue
from pathlib import Path
import traceback
from typing import Optional
from urllib import response
from urllib import response
from xml.parsers.expat import model
from xmlrpc import client

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from groq import Groq
from dotenv import load_dotenv

from src.auth import create_access_token, decode_access_token
from src.user_store import (
    register_user, authenticate_user, get_user_by_id, get_user_count,
)
from src.ingest import run_ingestion
from src.retriever import (
    get_hybrid_retriever, build_qa_chain,
    format_sources, invalidate_user_cache,
)
from src.document_store import (
    get_all_documents, get_document_stats,
    is_duplicate, remove_document,
)
from src.chat_memory import (
    create_session_id, get_history, add_exchange,
    clear_session, get_session_summary, get_active_session_count,
)

load_dotenv()

# ─── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="RAG Document Q&A API — v4",
    description="Authenticated multi-user RAG with per-user document isolation.",
    version="4.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Auth dependency ──────────────────────────────────────────────────────────

# OAuth2PasswordBearer reads the token from:
#   Authorization: Bearer <token>
# tokenUrl is shown in /docs — the URL clients should POST to for a token.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """
    FastAPI dependency: validate JWT and return user dict.

    HOW FASTAPI DEPENDENCY INJECTION WORKS:
      When you add  user: dict = Depends(get_current_user)  to an endpoint,
      FastAPI automatically:
        1. Extracts the token from the Authorization header
        2. Calls this function with that token
        3. Passes the returned dict to the endpoint as "user"
        4. If this function raises HTTPException → the endpoint never runs

    WHY Depends() INSTEAD OF MANUAL TOKEN PARSING?
      - DRY: write auth logic once, use everywhere
      - Testable: swap get_current_user in tests easily
      - Self-documenting: /docs shows which endpoints require auth
      - Cannot be forgotten: forgetting Depends() = unprotected endpoint
        (visible in code review), not a subtle bug

    RAISES:
      401 Unauthorized if token is missing, invalid, or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token. Please log in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("sub")
    if not user_id:
        raise credentials_exception

    # Verify user still exists (handles deleted accounts)
    user = get_user_by_id(user_id)
    if user is None:
        raise credentials_exception

    return user


# ─── Request / Response models ────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str = ""

    class Config:
        json_schema_extra = {
            "example": {"username": "alice", "password": "securepass123"}
        }


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    username: str
    user_id: str
    message: str


class QuestionRequest(BaseModel):
    question: str


class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


class AnswerResponse(BaseModel):
    answer: str
    sources: list


class ChatResponse(BaseModel):
    answer: str
    sources: list
    session_id: str


class UploadResponse(BaseModel):
    status: str
    file: str
    pages: int
    chunks: int
    was_duplicate: bool
    message: str
    total_documents: int


class DocumentInfo(BaseModel):
    filename: str
    uploaded_at: str
    pages: int
    chunks: int
    size_kb: float


class DocumentLibraryResponse(BaseModel):
    total_documents: int
    total_pages: int
    total_chunks: int
    documents: list[DocumentInfo]


# ─── Groq helpers (same as Phase 2) ──────────────────────────────────────────

SYSTEM_PROMPT = """
You are a precise document Q&A assistant.

Your task is to answer questions using ONLY the information provided in the user's context.

Rules:
- Use ONLY the given context
- Do NOT use external knowledge
- Do NOT guess or assume missing information
- If the answer is not found, say:
  "I don't know — this isn't covered in the uploaded documents."

Response style:
- Be concise and factual
- Use bullet points when helpful
- Keep explanations short and clear

Grounding:
- Base your answer strictly on relevant parts of the context
- If multiple parts are relevant, combine them logically

Do not:
- Add information not present in the context
- Fabricate explanations or details
"""


def _get_groq_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY not set in .env file.")
    return Groq(api_key=api_key)


def _build_messages(question: str, context: str, history: list[dict]) -> list[dict]:
    """Build history-aware messages list for Groq API."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({
        "role": "user",
        "content": (
            f"Context (from your uploaded documents):\n"
            f"{'─'*40}\n{context}\n{'─'*40}\n\n"
            f"Question: {question}"
        ),
    })
    return messages


# ─── Auth endpoints (PUBLIC — no Depends(get_current_user)) ──────────────────

@app.post("/auth/register", response_model=TokenResponse, status_code=201)
def register(request: RegisterRequest):
    """
    Register a new user and return a JWT token immediately.

    WHY LOG IN AUTOMATICALLY AFTER REGISTER?
      Better UX — user doesn't have to fill the login form again.
      Standard practice in modern web apps.

    WHAT HAPPENS:
      1. Validate username/password format
      2. Check username is not taken
      3. Hash password with bcrypt and save
      4. Create JWT token
      5. Return token (client stores it, includes in future requests)
    """
    try:
        user = register_user(
            username=request.username,
            password=request.password,
            email=request.email,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    token = create_access_token({
        "sub": user["user_id"],
        "username": user["username"],
    })

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        username=user["username"],
        user_id=user["user_id"],
        message=f"Welcome, {user['username']}! Your account has been created.",
    )


@app.post("/auth/login", response_model=TokenResponse)
def login(request: LoginRequest):
    """
    Authenticate a user and return a JWT token.

    WHAT HAPPENS:
      1. Look up username in registry
      2. Verify password against bcrypt hash
      3. If valid → create and return JWT token
      4. If invalid → 401 Unauthorized (same error for wrong user/password)
    """
    user = authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({
        "sub": user["user_id"],
        "username": user["username"],
    })

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        username=user["username"],
        user_id=user["user_id"],
        message=f"Welcome back, {user['username']}!",
    )


@app.get("/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    """
    Return the authenticated user's profile.
    The frontend calls this on load to verify the stored token is still valid.
    If the token has expired, this returns 401 and the frontend shows the login page.
    """
    return {
        "user_id":   user["user_id"],
        "username":  user["username"],
        "email":     user.get("email", ""),
        "created_at": user.get("created_at", ""),
    }


# ─── Health (public) ──────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "version": "4.0.0",
        "registered_users": get_user_count(),
        "active_sessions": get_active_session_count(),
    }


# ─── Status (protected) ───────────────────────────────────────────────────────

@app.get("/status")
def get_status(user: dict = Depends(get_current_user)):
    """Return this user's document stats and readiness."""
    user_id = user["user_id"]
    stats = get_document_stats(user_id)
    index_path = f"vectorstore/{user_id}/faiss_index/index.faiss"
    return {
        "ready":           os.path.exists(index_path),
        "username":        user["username"],
        "active_sessions": get_active_session_count(),
        **stats,
    }


# ─── Document library (protected) ────────────────────────────────────────────

@app.get("/documents", response_model=DocumentLibraryResponse)
def list_documents(user: dict = Depends(get_current_user)):
    """Return this user's document library."""
    stats = get_document_stats(user["user_id"])
    return DocumentLibraryResponse(
        total_documents=stats["total_documents"],
        total_pages=stats["total_pages"],
        total_chunks=stats["total_chunks"],
        documents=[DocumentInfo(**d) for d in stats["documents"]],
    )


@app.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """
    Upload and index a PDF for the authenticated user.

    KEY CHANGE FROM PHASE 2:
      run_ingestion() now receives user_id → saves to user's own index path.
      invalidate_user_cache() clears only THIS user's cached retriever.
      Other users' caches are unaffected.
    """
    user_id = user["user_id"]

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail=f"Only PDF files supported. Got: '{Path(file.filename).suffix}'",
        )

    was_dup = is_duplicate(user_id, file.filename)
    print(f"[API] user='{user['username']}' upload='{file.filename}'")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        result = run_ingestion(
            file_path=tmp_path,
            user_id=user_id,
            original_filename=file.filename,
        )
        # Invalidate this user's cached retriever so next request rebuilds
        invalidate_user_cache(user_id)

        all_docs = get_all_documents(user_id)
        return UploadResponse(
            status="success",
            file=file.filename,
            pages=result["pages"],
            chunks=result["chunks"],
            was_duplicate=was_dup,
            message=(
                f"✓ {'Updated' if was_dup else 'Indexed'} '{file.filename}'. "
                f"{result['pages']} pages → {result['chunks']} chunks. "
                f"{len(all_docs)} document(s) in your library."
            ),
            total_documents=len(all_docs),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.delete("/documents/{filename}")
def delete_document(
    filename: str,
    user: dict = Depends(get_current_user),
):
    user_id = user["user_id"]
    removed = remove_document(user_id, filename)
    if not removed:
        raise HTTPException(
            status_code=404, detail=f"'{filename}' not found in your library."
        )
    invalidate_user_cache(user_id)
    return {
        "status": "removed",
        "filename": filename,
        "remaining": len(get_all_documents(user_id)),
    }


# ─── Streaming endpoint (protected) ──────────────────────────────────────────

@app.post("/stream")
async def stream_answer(
    request: ChatRequest,
    user: dict = Depends(get_current_user),
):
    """
    Stream answer tokens for the authenticated user.
    Identical to Phase 2 but retriever is scoped to this user's index.
    """
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    user_id = user["user_id"]
    session_id = request.session_id or create_session_id()
    question = request.question.strip()

    async def generate():
        full_answer = ""
        docs = []

        try:
            retriever = get_hybrid_retriever(user_id)
            loop = asyncio.get_event_loop()
            docs = await loop.run_in_executor(None, retriever.invoke, question)

            context_parts = []
            for i, doc in enumerate(docs, 1):
                src  = doc.metadata.get("source", "unknown")
                page = doc.metadata.get("page", 0) + 1
                context_parts.append(f"[Source {i}: {src}, Page {page}]\n{doc.page_content}")
            context = "\n\n".join(context_parts)

            if not context:
                yield f"data: {json.dumps({'type':'token','content':'I could not find relevant sections in your documents for this question.'})}\n\n"
                yield "data: [DONE]\n\n"
                return

            history  = get_history(session_id)
            messages = _build_messages(question, context, history)
            client   = _get_groq_client()
            model = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")
            temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))

            token_queue: queue.Queue = queue.Queue()
            error_box: list = []

            def producer():
                try:
                    response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=1024,
                    )

                    answer = response.choices[0].message.content

                    token_queue.put(answer)

              
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    print("STREAM ERROR FULL:", repr(e))
                    error_box.append(str(e))
                finally:
                    token_queue.put(None)

            threading.Thread(target=producer, daemon=True).start()

            while True:
                try:
                    token = token_queue.get(timeout=30)
                except queue.Empty:
                    yield f"data: {json.dumps({'type':'error','content':'Stream timed out.'})}\n\n"
                    break
                if token is None:
                    break
                if error_box:
                    yield f"data: {json.dumps({'type':'error','content':error_box[0]})}\n\n"
                    break
                full_answer += token
                yield f"data: {json.dumps({'type':'token','content':token})}\n\n"
                await asyncio.sleep(0)

        except FileNotFoundError as e:
            yield f"data: {json.dumps({'type':'error','content':str(e)})}\n\n"
            yield "data: [DONE]\n\n"
            return
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','content':f'Error: {str(e)}'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        if full_answer:
            add_exchange(session_id, question, full_answer)

        sources = format_sources(docs)
        yield f"data: {json.dumps({'type':'metadata','sources':sources,'session_id':session_id})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── Non-streaming chat (protected) ──────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user: dict = Depends(get_current_user),
):
    user_id = user["user_id"]
    session_id = request.session_id or create_session_id()
    question = request.question.strip()

    try:
        retriever = get_hybrid_retriever(user_id)
        docs = retriever.invoke(question)

        context_parts = []
        for i, doc in enumerate(docs, 1):
            src  = doc.metadata.get("source", "unknown")
            page = doc.metadata.get("page", 0) + 1
            context_parts.append(f"[Source {i}: {src}, Page {page}]\n{doc.page_content}")
        context = "\n\n".join(context_parts)

        history  = get_history(session_id)
        messages = _build_messages(question, context, history)
        client   = _get_groq_client()
        resp     = client.chat.completions.create(
            model=os.getenv("LLM_MODEL", "llama3-8b-8192"),
            messages=messages,
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
            max_tokens=1024,
        )
        answer = resp.choices[0].message.content
        add_exchange(session_id, question, answer)
        return ChatResponse(answer=answer, sources=format_sources(docs), session_id=session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Session endpoints (protected) ───────────────────────────────────────────

@app.get("/sessions/{session_id}")
def get_session(session_id: str, user: dict = Depends(get_current_user)):
    return get_session_summary(session_id)


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    cleared = clear_session(session_id)
    return {"status": "cleared" if cleared else "not_found", "session_id": session_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
