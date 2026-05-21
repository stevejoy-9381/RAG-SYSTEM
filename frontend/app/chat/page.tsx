'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { Send, Brain } from 'lucide-react'
import { v4 as uuid } from 'uuid'
import { clsx } from 'clsx'

import { auth }       from '@/lib/auth'
import { getStatus, streamAnswer, clearSession, verifyToken } from '@/lib/api'
import type { Message, StatusResponse, Source } from '@/types'

import Sidebar     from '@/components/Sidebar'
import ChatMessage from '@/components/ChatMessage'

// ── UUID shim (uuid package may not be available — use crypto.randomUUID) ────
function newId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return Math.random().toString(36).slice(2)
}

const WELCOME_MSG: Message = {
  id:        'welcome',
  role:      'assistant',
  content:   'Hi! Upload a PDF document in the sidebar, then ask me anything about it. I\'ll answer using only what\'s in your documents.',
  sources:   [],
  timestamp: new Date(),
}

export default function ChatPage() {
  const router    = useRouter()
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef  = useRef<HTMLTextAreaElement>(null)

  const [token,     setToken]     = useState<string | null>(null)
  const [username,  setUsername]  = useState('')
  const [sessionId, setSessionId] = useState(newId)
  const [status,    setStatus]    = useState<StatusResponse | null>(null)
  const [messages,  setMessages]  = useState<Message[]>([WELCOME_MSG])
  const [input,     setInput]     = useState('')
  const [streaming, setStreaming] = useState(false)

  // ── Auth gate ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const t = auth.getToken()
    if (!t) { router.replace('/auth'); return }

    verifyToken(t).then(valid => {
      if (!valid) { auth.clear(); router.replace('/auth'); return }
      setToken(t)
      setUsername(auth.getUsername() ?? '')
    })
  }, [router])

  // ── Load status ───────────────────────────────────────────────────────────
  const refreshStatus = useCallback(async () => {
    if (!token) return
    try {
      const s = await getStatus(token)
      setStatus(s)
    } catch {}
  }, [token])

  useEffect(() => { refreshStatus() }, [refreshStatus])

  // ── Auto-scroll to bottom on new messages ─────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── Submit question ───────────────────────────────────────────────────────
  async function handleSubmit(e?: React.FormEvent) {
    e?.preventDefault()
    const question = input.trim()
    if (!question || !token || streaming) return
    if (!status?.ready) return

    setInput('')
    setStreaming(true)

    // Add user message
    const userMsg: Message = {
      id: newId(), role: 'user', content: question, sources: [], timestamp: new Date(),
    }

    // Add placeholder assistant message (streaming = true)
    const assistantId = newId()
    const assistantPlaceholder: Message = {
      id: assistantId, role: 'assistant', content: '', sources: [],
      isStreaming: true, timestamp: new Date(),
    }

    setMessages(prev => [...prev, userMsg, assistantPlaceholder])

    // Stream the answer
    let   fullContent = ''
    let   finalSources: Source[] = []

    await streamAnswer({
      question,
      sessionId,
      token,
      onToken(t) {
        fullContent += t
        // Update the placeholder message with each new token
        setMessages(prev => prev.map(m =>
          m.id === assistantId ? { ...m, content: fullContent } : m
        ))
      },
      onMetadata(sources, newSessionId) {
        finalSources = sources
        setSessionId(newSessionId)
      },
      onError(msg) {
        setMessages(prev => prev.map(m =>
          m.id === assistantId
            ? { ...m, content: `⚠️ ${msg}`, isStreaming: false, error: true }
            : m
        ))
      },
      onDone() {
        // Finalise the assistant message: mark streaming done, attach sources
        setMessages(prev => prev.map(m =>
          m.id === assistantId
            ? { ...m, content: fullContent || m.content, sources: finalSources, isStreaming: false }
            : m
        ))
        setStreaming(false)
        inputRef.current?.focus()
      },
    })
  }

  // ── Handle Enter key (Shift+Enter = newline) ──────────────────────────────
  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  // ── New chat ──────────────────────────────────────────────────────────────
  async function handleNewChat() {
    if (token) clearSession(sessionId, token)
    setSessionId(newId())
    setMessages([WELCOME_MSG])
    setInput('')
    inputRef.current?.focus()
  }

  // ── Sign out ──────────────────────────────────────────────────────────────
  function handleSignOut() {
    if (token) clearSession(sessionId, token)
    auth.clear()
    router.replace('/auth')
  }

  // ── Loading state ─────────────────────────────────────────────────────────
  if (!token) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  const canAsk = status?.ready && !streaming

  return (
    <div className="h-screen flex overflow-hidden bg-slate-50">

      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <Sidebar
        status={status}
        token={token}
        username={username}
        onUpload={refreshStatus}
        onNewChat={handleNewChat}
        onSignOut={handleSignOut}
      />

      {/* ── Main chat area ───────────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0">

        {/* Top bar */}
        <header className="h-14 shrink-0 border-b border-slate-200 bg-white
                           flex items-center px-6 gap-3">
          <Brain className="w-5 h-5 text-indigo-500" />
          <span className="font-semibold text-slate-800">Document Q&A</span>
          {streaming && (
            <span className="ml-auto flex items-center gap-1.5 text-xs text-indigo-600 font-medium">
              <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-pulse-slow" />
              Generating…
            </span>
          )}
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          {messages.map(msg => (
            <ChatMessage key={msg.id} message={msg} />
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div className="shrink-0 border-t border-slate-200 bg-white px-6 py-4">
          {!status?.ready && (
            <p className="text-xs text-center text-amber-600 bg-amber-50 rounded-lg
                           px-3 py-2 mb-3">
              Upload a PDF document in the sidebar to start asking questions.
            </p>
          )}
          <form onSubmit={handleSubmit} className="flex items-end gap-3">
            <div className="flex-1 relative">
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={!canAsk}
                placeholder={
                  !status?.ready
                    ? 'Upload a document first…'
                    : 'Ask a question about your documents… (Enter to send)'
                }
                rows={1}
                className={clsx(
                  'w-full resize-none input py-3 pr-4 max-h-36',
                  'disabled:bg-slate-50 disabled:cursor-not-allowed',
                )}
                style={{ minHeight: '48px' }}
              />
            </div>
            <button
              type="submit"
              disabled={!canAsk || !input.trim()}
              className="btn-primary h-12 w-12 p-0 rounded-xl shrink-0"
              title="Send (Enter)"
            >
              {streaming
                ? <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                : <Send className="w-4 h-4" />}
            </button>
          </form>
          <p className="text-xs text-slate-400 text-center mt-2">
            Answers are generated from your documents only — no hallucinations.
          </p>
        </div>
      </main>
    </div>
  )
}
