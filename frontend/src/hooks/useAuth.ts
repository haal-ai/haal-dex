import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { createElement } from 'react'

export interface AuthUser {
  username: string
  role: string
  token: string
}

interface AuthContextValue {
  user: AuthUser | null
  isAuthenticated: boolean
  isAdmin: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  loading: boolean
  error: string | null
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

const TOKEN_KEY = 'intent-auth-token'

async function loginRequest(username: string, password: string): Promise<{ access_token: string; user_id: string; roles: string[] }> {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) {
    throw new Error('login_failed')
  }
  return res.json()
}

async function fetchMe(token: string): Promise<{ user_id: string; username: string; roles: string[] }> {
  const res = await fetch('/api/auth/me', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) {
    throw new Error('token_invalid')
  }
  return res.json()
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Restore session from localStorage on mount
  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) {
      setLoading(false)
      return
    }
    fetchMe(token)
      .then((profile) => {
        setUser({
          username: profile.username,
          role: profile.roles.includes('admin') ? 'admin' : 'user',
          token,
        })
      })
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY)
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    setError(null)
    try {
      const data = await loginRequest(username, password)
      const token = data.access_token
      const role = data.roles.includes('admin') ? 'admin' : 'user'
      localStorage.setItem(TOKEN_KEY, token)
      setUser({ username, role, token })
    } catch {
      setError('login_failed')
      throw new Error('login_failed')
    }
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setUser(null)
    setError(null)
  }, [])

  const isAuthenticated = user !== null
  const isAdmin = user?.role === 'admin'

  const value: AuthContextValue = {
    user,
    isAuthenticated,
    isAdmin,
    login,
    logout,
    loading,
    error,
  }

  return createElement(AuthContext.Provider, { value }, children)
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
