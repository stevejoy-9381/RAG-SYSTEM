import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'DocMind — Document Q&A',
  description: 'Ask questions about your documents. Answers grounded in your content.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="h-screen overflow-hidden">{children}</body>
    </html>
  )
}
