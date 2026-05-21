'use client'

import { useRef, useState } from 'react'
import {
  Brain, Upload, FileText, Trash2, LogOut,
  Plus, Database, RotateCcw, ChevronRight,
} from 'lucide-react'
import { clsx } from 'clsx'
import type { DocumentInfo, StatusResponse } from '@/types'
import { uploadDocument, deleteDocument } from '@/lib/api'

interface Props {
  status:       StatusResponse | null
  token:        string
  username:     string
  onUpload:     () => void       // refresh status after upload
  onNewChat:    () => void
  onSignOut:    () => void
}

export default function Sidebar({
  status, token, username, onUpload, onNewChat, onSignOut,
}: Props) {
  const fileRef   = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState<{ text: string; ok: boolean } | null>(null)
  const [deleting,  setDeleting]  = useState<string | null>(null)

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.name.endsWith('.pdf')) {
      setUploadMsg({ text: 'Only PDF files are supported.', ok: false })
      return
    }

    setUploading(true)
    setUploadMsg(null)
    try {
      const res = await uploadDocument(file, token)
      setUploadMsg({ text: res.message, ok: true })
      onUpload()
    } catch (err) {
      setUploadMsg({
        text: err instanceof Error ? err.message : 'Upload failed.',
        ok: false,
      })
    } finally {
      setUploading(false)
      // Reset input so same file can be re-uploaded
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function handleDelete(filename: string) {
    if (!confirm(`Remove "${filename}" from your library?`)) return
    setDeleting(filename)
    try {
      await deleteDocument(filename, token)
      onUpload()
    } catch {}
    setDeleting(null)
  }

  const docs     = status?.documents ?? []
  const isReady  = status?.ready ?? false

  return (
    <aside className="w-72 shrink-0 h-full flex flex-col bg-white border-r border-slate-200">
      {/* ── Logo ─────────────────────────────────────────────────────────── */}
      <div className="px-5 py-4 border-b border-slate-100">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center">
            <Brain className="w-4.5 h-4.5 text-white" />
          </div>
          <span className="font-semibold text-slate-900 text-lg">DocMind</span>
        </div>
      </div>

      {/* ── Status chip ───────────────────────────────────────────────────── */}
      <div className="px-5 py-3 border-b border-slate-100">
        <div className={clsx(
          'inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full',
          isReady
            ? 'bg-green-50 text-green-700'
            : 'bg-amber-50 text-amber-700',
        )}>
          <span className={clsx(
            'w-1.5 h-1.5 rounded-full',
            isReady ? 'bg-green-500' : 'bg-amber-400',
          )} />
          {isReady
            ? `${status!.total_documents} doc${status!.total_documents !== 1 ? 's' : ''}, ${status!.total_chunks} chunks`
            : 'No documents yet'}
        </div>
      </div>

      {/* ── Document library ──────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        <div className="px-5 pt-4 pb-2">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Documents
            </h3>
            <span className="text-xs text-slate-400">{docs.length}</span>
          </div>

          {docs.length === 0 ? (
            <div className="text-center py-8 text-slate-400">
              <Database className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <p className="text-xs">No documents yet.<br/>Upload a PDF below.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {docs.map((doc: DocumentInfo) => (
                <div
                  key={doc.filename}
                  className="group flex items-start gap-2.5 p-2.5 rounded-lg
                             hover:bg-slate-50 transition-colors"
                >
                  <FileText className="w-4 h-4 text-indigo-400 mt-0.5 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-slate-700 truncate">
                      {doc.filename}
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {doc.pages}p · {doc.chunks} chunks · {doc.size_kb.toFixed(0)} KB
                    </p>
                  </div>
                  <button
                    onClick={() => handleDelete(doc.filename)}
                    disabled={deleting === doc.filename}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded
                               text-slate-400 hover:text-red-500 hover:bg-red-50
                               transition-all shrink-0"
                    title="Remove document"
                  >
                    {deleting === doc.filename
                      ? <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                      : <Trash2 className="w-3.5 h-3.5" />}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Upload area ────────────────────────────────────────────────────── */}
      <div className="px-5 pb-4 border-t border-slate-100 pt-3 space-y-2">
        <input
          ref={fileRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={handleFileChange}
        />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="w-full flex items-center justify-center gap-2 py-2 px-3
                     border-2 border-dashed border-slate-300 rounded-xl text-sm
                     text-slate-500 hover:border-indigo-400 hover:text-indigo-600
                     hover:bg-indigo-50 transition-all disabled:opacity-60
                     disabled:cursor-not-allowed font-medium"
        >
          {uploading
            ? <><span className="w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />Indexing…</>
            : <><Plus className="w-4 h-4" />Upload PDF</>}
        </button>

        {uploadMsg && (
          <p className={clsx(
            'text-xs px-2 py-1.5 rounded-lg',
            uploadMsg.ok
              ? 'text-green-700 bg-green-50'
              : 'text-red-600 bg-red-50',
          )}>
            {uploadMsg.text}
          </p>
        )}
      </div>

      {/* ── Bottom controls ────────────────────────────────────────────────── */}
      <div className="border-t border-slate-100 px-3 py-3 space-y-1">
        <button
          onClick={onNewChat}
          className="btn-ghost w-full justify-start text-slate-600"
        >
          <RotateCcw className="w-4 h-4" />
          New Chat
        </button>
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg
                        hover:bg-slate-50 transition-colors group cursor-pointer"
             onClick={onSignOut}>
          <div className="w-6 h-6 bg-indigo-100 rounded-full flex items-center
                          justify-center text-indigo-600 text-xs font-semibold uppercase">
            {username[0]}
          </div>
          <span className="flex-1 text-sm text-slate-700 font-medium">{username}</span>
          <LogOut className="w-4 h-4 text-slate-400 group-hover:text-slate-600 transition-colors" />
        </div>
      </div>
    </aside>
  )
}
