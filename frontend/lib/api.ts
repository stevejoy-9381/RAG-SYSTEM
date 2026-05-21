// lib/api.ts — Typed API client for the FastAPI backend
//
// DESIGN PRINCIPLES:
//   - Every function is typed end-to-end (request + response)
//   - Auth token is injected in one place (authHeaders())
//   - Streaming is handled with the browser's native fetch + ReadableStream API
//   - Errors are re-thrown with clear messages so components can display them

import type {
  TokenResponse, StatusResponse, DocumentLibrary,
  UploadResponse, Source, StreamEvent,
} from '@/types'

// NEXT_PUBLIC_ prefix exposes this to the browser bundle.
// Falls back to localhost for local development without .env.local.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// ── Helpers ──────────────────────────────────────────────────────────────────

function authHeaders(token: string): HeadersInit {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json()
      message = body.detail ?? message
    } catch {}
    throw new Error(message)
  }
  return res.json() as Promise<T>
}

// ── Auth endpoints (no token required) ───────────────────────────────────────

export async function login(username: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${API_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  return handleResponse<TokenResponse>(res)
}

export async function register(username: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${API_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  return handleResponse<TokenResponse>(res)
}

export async function verifyToken(token: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/auth/me`, {
      headers: { 'Authorization': `Bearer ${token}` },
    })
    return res.ok
  } catch {
    return false
  }
}

// ── Status + documents ────────────────────────────────────────────────────────

export async function getStatus(token: string): Promise<StatusResponse> {
  const res = await fetch(`${API_URL}/status`, { headers: authHeaders(token) })
  return handleResponse<StatusResponse>(res)
}

export async function getDocuments(token: string): Promise<DocumentLibrary> {
  const res = await fetch(`${API_URL}/documents`, { headers: authHeaders(token) })
  return handleResponse<DocumentLibrary>(res)
}

export async function uploadDocument(
  file: File,
  token: string,
): Promise<UploadResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_URL}/upload`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` }, // NO Content-Type — let browser set multipart boundary
    body: form,
  })
  return handleResponse<UploadResponse>(res)
}

export async function deleteDocument(filename: string, token: string): Promise<void> {
  const res = await fetch(`${API_URL}/documents/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  })
  await handleResponse<unknown>(res)
}

// ── Streaming answer ──────────────────────────────────────────────────────────
//
// HOW BROWSER STREAMING WORKS:
//   fetch() returns a Response whose .body is a ReadableStream<Uint8Array>.
//   We get a reader from it and loop: reader.read() returns { done, value }
//   where value is a Uint8Array chunk of raw bytes.
//
//   We decode bytes → string → split on '\n' → find lines starting with 'data: '
//   → parse the JSON payload → call the appropriate callback.
//
// WHY CALLBACKS INSTEAD OF async GENERATOR?
//   Callbacks integrate cleanly with React's setState:
//   onToken(t) → setCurrentAnswer(prev => prev + t)
//   An async generator would require a separate useEffect consumer.
//   Callbacks are simpler and more direct here.
//
// BUFFERING:
//   A TCP packet might arrive mid-line: "data: {"type":"tok\n"  (incomplete)
//   We keep a `buffer` string and only process complete lines (ending in \n).
//   Incomplete lines stay in the buffer until the next chunk arrives.

export async function streamAnswer(params: {
  question:    string
  sessionId:   string
  token:       string
  onToken:     (token: string) => void
  onMetadata:  (sources: Source[], sessionId: string) => void
  onError:     (message: string) => void
  onDone:      () => void
}): Promise<void> {
  const { question, sessionId, token, onToken, onMetadata, onError, onDone } = params

  let response: Response
  try {
    response = await fetch(`${API_URL}/stream`, {
      method:  'POST',
      headers: authHeaders(token),
      body:    JSON.stringify({ question, session_id: sessionId }),
    })
  } catch {
    onError('Cannot connect to the backend. Is the API running?')
    onDone()
    return
  }

  if (!response.ok) {
    let msg = `HTTP ${response.status}`
    try { msg = (await response.json()).detail ?? msg } catch {}
    onError(msg)
    onDone()
    return
  }

  const reader  = response.body!.getReader()
  const decoder = new TextDecoder()
  let   buffer  = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      // Decode the Uint8Array chunk into a string fragment
      buffer += decoder.decode(value, { stream: true })

      // Process all complete lines (split on newline)
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''          // last element may be incomplete — keep in buffer

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data: ')) continue

        const payload = trimmed.slice(6)  // strip "data: "
        if (payload === '[DONE]') { onDone(); return }

        try {
          const event = JSON.parse(payload) as StreamEvent
          switch (event.type) {
            case 'token':    onToken(event.content); break
            case 'metadata': onMetadata(event.sources, event.session_id); break
            case 'error':    onError(event.content); break
          }
        } catch {
          // Malformed JSON in stream — ignore and continue
        }
      }
    }
  } catch (err) {
    onError(err instanceof Error ? err.message : 'Stream interrupted')
  } finally {
    onDone()
  }
}

// ── Session management ────────────────────────────────────────────────────────

export async function clearSession(sessionId: string, token: string): Promise<void> {
  try {
    await fetch(`${API_URL}/sessions/${sessionId}`, {
      method:  'DELETE',
      headers: authHeaders(token),
    })
  } catch {}  // Silently ignore — clearing session is best-effort
}
