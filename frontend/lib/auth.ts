// lib/auth.ts — JWT token management
//
// WHY localStorage (not cookies)?
//   For a client-side Next.js app calling a FastAPI backend, localStorage
//   is the simplest approach. The token is sent manually in the
//   Authorization header, not automatically like cookies.
//
//   Cookies with httpOnly are more secure (immune to XSS) but require
//   the API and frontend to be on the same domain or use CORS with
//   credentials. For a portfolio app with separate domains (Render + Streamlit),
//   localStorage is the practical choice.
//
//   Production upgrade: use httpOnly cookies with Next.js API routes
//   as a proxy layer (standard enterprise pattern).

const TOKEN_KEY = 'docmind_auth_token'
const USERNAME_KEY = 'docmind_username'
const USER_ID_KEY = 'docmind_user_id'

export const auth = {
  setToken(token: string, username: string, userId: string): void {
    if (typeof window === 'undefined') return
    localStorage.setItem(TOKEN_KEY,    token)
    localStorage.setItem(USERNAME_KEY, username)
    localStorage.setItem(USER_ID_KEY,  userId)
  },

  getToken(): string | null {
    if (typeof window === 'undefined') return null
    return localStorage.getItem(TOKEN_KEY)
  },

  getUsername(): string | null {
    if (typeof window === 'undefined') return null
    return localStorage.getItem(USERNAME_KEY)
  },

  getUserId(): string | null {
    if (typeof window === 'undefined') return null
    return localStorage.getItem(USER_ID_KEY)
  },

  clear(): void {
    if (typeof window === 'undefined') return
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USERNAME_KEY)
    localStorage.removeItem(USER_ID_KEY)
  },

  isAuthenticated(): boolean {
    return !!this.getToken()
  },
}
