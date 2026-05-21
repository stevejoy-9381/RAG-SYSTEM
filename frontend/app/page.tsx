'use client'
// Root page: immediately redirect to /chat.
// The chat page checks auth and redirects to /auth if not logged in.
// This keeps the routing logic in one place (chat/page.tsx).

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function RootPage() {
  const router = useRouter()
  useEffect(() => { router.replace('/chat') }, [router])
  return (
    <div className="h-screen flex items-center justify-center">
      <div className="w-5 h-5 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
    </div>
  )
}
