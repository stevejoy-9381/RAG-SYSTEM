'use client'

import { useState, useEffect, FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { Brain, FileText, Zap, Shield } from 'lucide-react'
import { login, register } from '@/lib/api'
import { auth } from '@/lib/auth'

type Tab = 'login' | 'register'

export default function AuthPage() {
  const router = useRouter()
  const [tab,       setTab]       = useState<Tab>('login')
  const [username,  setUsername]  = useState('')
  const [password,  setPassword]  = useState('')
  const [confirm,   setConfirm]   = useState('')
  const [error,     setError]     = useState('')
  const [loading,   setLoading]   = useState(false)

  // If already authenticated, skip to chat
  useEffect(() => {
    if (auth.isAuthenticated()) router.replace('/chat')
  }, [router])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')

    if (tab === 'register' && password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    if (tab === 'register' && password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }

    setLoading(true)
    try {
      const data = tab === 'login'
        ? await login(username.trim(), password)
        : await register(username.trim(), password)

      auth.setToken(data.access_token, data.username, data.user_id)
      router.replace('/chat')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      setLoading(false)
    }
  }

  const features = [
    { icon: FileText, text: 'Upload any PDF document'       },
    { icon: Zap,      text: 'Stream answers in real time'   },
    { icon: Shield,   text: 'Your documents stay private'   },
    { icon: Brain,    text: 'Powered by Llama 3 + FAISS'    },
  ]

  return (
    <div className="h-screen flex">
      {/* ── Left panel — branding ─────────────────────────────────────────── */}
      <div className="hidden lg:flex flex-col justify-between w-[480px] bg-indigo-600 p-12 text-white">
        <div>
          <div className="flex items-center gap-3 mb-16">
            <div className="w-9 h-9 bg-white/20 rounded-xl flex items-center justify-center">
              <Brain className="w-5 h-5" />
            </div>
            <span className="text-xl font-semibold">DocMind</span>
          </div>

          <h1 className="text-4xl font-bold leading-tight mb-6">
            Your documents,<br />intelligently answered.
          </h1>
          <p className="text-indigo-200 text-lg leading-relaxed">
            Upload PDFs and ask questions in plain English.
            Answers are grounded in your content — no hallucinations.
          </p>
        </div>

        <div className="space-y-4">
          {features.map(({ icon: Icon, text }) => (
            <div key={text} className="flex items-center gap-3 text-indigo-100">
              <div className="w-8 h-8 bg-white/10 rounded-lg flex items-center justify-center shrink-0">
                <Icon className="w-4 h-4" />
              </div>
              <span className="text-sm">{text}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Right panel — form ────────────────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center p-8 bg-slate-50">
        <div className="w-full max-w-sm">

          {/* Mobile logo */}
          <div className="flex items-center gap-2 mb-10 lg:hidden">
            <Brain className="w-6 h-6 text-indigo-600" />
            <span className="text-xl font-semibold text-slate-900">DocMind</span>
          </div>

          <h2 className="text-2xl font-bold text-slate-900 mb-2">
            {tab === 'login' ? 'Welcome back' : 'Create an account'}
          </h2>
          <p className="text-slate-500 text-sm mb-8">
            {tab === 'login'
              ? 'Sign in to access your document library.'
              : 'Start asking questions about your documents.'}
          </p>

          {/* Tabs */}
          <div className="flex bg-slate-100 rounded-lg p-1 mb-6">
            {(['login', 'register'] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => { setTab(t); setError('') }}
                className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-all ${
                  tab === t
                    ? 'bg-white text-slate-900 shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                {t === 'login' ? 'Sign In' : 'Register'}
              </button>
            ))}
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Username
              </label>
              <input
                className="input"
                placeholder="your_username"
                value={username}
                onChange={e => setUsername(e.target.value)}
                autoComplete="username"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Password
              </label>
              <input
                className="input"
                type="password"
                placeholder={tab === 'register' ? 'Min. 8 characters' : '••••••••'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete={tab === 'login' ? 'current-password' : 'new-password'}
                required
              />
            </div>

            {tab === 'register' && (
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                  Confirm Password
                </label>
                <input
                  className="input"
                  type="password"
                  placeholder="••••••••"
                  value={confirm}
                  onChange={e => setConfirm(e.target.value)}
                  autoComplete="new-password"
                  required
                />
              </div>
            )}

            {error && (
              <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2.5 animate-fade-in">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full py-2.5 mt-2"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  {tab === 'login' ? 'Signing in…' : 'Creating account…'}
                </span>
              ) : (
                tab === 'login' ? 'Sign In' : 'Create Account'
              )}
            </button>
          </form>

          <p className="text-center text-xs text-slate-400 mt-8">
            Your documents are private and isolated to your account.
          </p>
        </div>
      </div>
    </div>
  )
}
