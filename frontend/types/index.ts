// types/index.ts — Shared TypeScript types for the entire frontend
// These mirror the Pydantic response models in the FastAPI backend.

export interface User {
  user_id: string
  username: string
  email: string
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  username: string
  user_id: string
  message: string
}

export interface Source {
  file: string
  page: number
  total_pages: number | string
  chunk_index: number | string
  upload_time: string
  preview: string
}

export interface Message {
  id: string                  // client-generated UUID for React key prop
  role: 'user' | 'assistant'
  content: string
  sources: Source[]
  isStreaming?: boolean       // true while the assistant is still typing
  error?: boolean             // true if the response was an error
  timestamp: Date
}

export interface DocumentInfo {
  filename: string
  uploaded_at: string
  pages: number
  chunks: number
  size_kb: number
}

export interface DocumentLibrary {
  total_documents: number
  total_pages: number
  total_chunks: number
  documents: DocumentInfo[]
}

export interface StatusResponse {
  ready: boolean
  username: string
  total_documents: number
  total_pages: number
  total_chunks: number
  documents: DocumentInfo[]
  active_sessions: number
}

export interface UploadResponse {
  status: string
  file: string
  pages: number
  chunks: number
  was_duplicate: boolean
  message: string
  total_documents: number
}

// SSE event types streamed from POST /stream
export type StreamEvent =
  | { type: 'token';    content: string }
  | { type: 'metadata'; sources: Source[]; session_id: string }
  | { type: 'error';    content: string }
