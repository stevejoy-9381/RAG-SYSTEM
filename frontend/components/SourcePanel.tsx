'use client'

import { useState } from 'react'
import { ChevronDown, ChevronUp, FileText } from 'lucide-react'
import type { Source } from '@/types'

interface Props {
  sources: Source[]
}

export default function SourcePanel({ sources }: Props) {
  const [open, setOpen] = useState(false)

  if (!sources.length) return null

  return (
    <div className="mt-3 border border-slate-200 rounded-xl overflow-hidden">
      {/* Toggle header */}
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-2.5
                   bg-slate-50 hover:bg-slate-100 transition-colors text-left"
      >
        <span className="flex items-center gap-2 text-xs font-medium text-slate-600">
          <FileText className="w-3.5 h-3.5 text-indigo-500" />
          {sources.length} source{sources.length > 1 ? 's' : ''} used
        </span>
        {open
          ? <ChevronUp  className="w-3.5 h-3.5 text-slate-400" />
          : <ChevronDown className="w-3.5 h-3.5 text-slate-400" />}
      </button>

      {/* Source cards */}
      {open && (
        <div className="divide-y divide-slate-100 bg-white">
          {sources.map((src, i) => (
            <div key={i} className="px-4 py-3">
              <div className="flex items-start justify-between gap-3 mb-2">
                <span className="text-xs font-semibold text-slate-700 truncate max-w-[200px]">
                  📄 {src.file}
                </span>
                <span className="shrink-0 text-xs bg-indigo-50 text-indigo-700
                                 font-medium px-2 py-0.5 rounded-full">
                  Page {src.page} / {src.total_pages}
                </span>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed line-clamp-3 italic">
                "{src.preview}"
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
