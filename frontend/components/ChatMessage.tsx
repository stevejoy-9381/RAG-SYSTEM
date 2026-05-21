'use client'

import { Brain, User } from 'lucide-react'
import type { Message } from '@/types'
import SourcePanel from './SourcePanel'
import { clsx } from 'clsx'

interface Props {
  message: Message
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function ChatMessage({ message }: Props) {
  const isUser = message.role === 'user'

  return (
    <div className={clsx(
      'flex gap-3 message-enter',
      isUser ? 'flex-row-reverse' : 'flex-row'
    )}>
      {/* Avatar */}
      <div className={clsx(
        'w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5',
        isUser
          ? 'bg-indigo-600 text-white'
          : 'bg-white border-2 border-slate-200 text-indigo-600'
      )}>
        {isUser
          ? <User  className="w-4 h-4" />
          : <Brain className="w-4 h-4" />}
      </div>

      {/* Bubble + sources */}
      <div className={clsx(
        'flex flex-col max-w-[75%]',
        isUser ? 'items-end' : 'items-start'
      )}>
        <div className={clsx(
          'px-4 py-3 rounded-2xl text-sm leading-relaxed',
          isUser
            ? 'bg-indigo-600 text-white rounded-tr-sm'
            : clsx(
                'bg-white border border-slate-200 text-slate-800 rounded-tl-sm shadow-sm',
                message.error && 'border-red-200 bg-red-50 text-red-700',
              )
        )}>
          {/* Message content — streaming cursor shown while typing */}
          <span className={clsx(
            message.isStreaming && !message.error && 'streaming-cursor'
          )}>
            {message.content || (message.isStreaming ? '' : '…')}
          </span>
        </div>

        {/* Source panel (assistant only, after streaming completes) */}
        {!isUser && !message.isStreaming && message.sources.length > 0 && (
          <div className="w-full max-w-lg mt-1">
            <SourcePanel sources={message.sources} />
          </div>
        )}

        {/* Timestamp */}
        <span className="text-xs text-slate-400 mt-1 px-1">
          {formatTime(message.timestamp)}
        </span>
      </div>
    </div>
  )
}
