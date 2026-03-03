import { useState, type ReactNode, type FormEvent } from 'react'
import { useAuth } from '../hooks/useAuth'
import { useLanguage } from '../providers/I18nProvider'

interface AuthGateProps {
  children: ReactNode
  requireAdmin?: boolean
}

export function AuthGate({ children, requireAdmin = false }: AuthGateProps) {
  const { isAuthenticated, isAdmin, login, loading, error } = useAuth()
  const { t } = useLanguage()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (loading) {
    return null
  }

  if (!isAuthenticated) {
    const handleSubmit = async (e: FormEvent) => {
      e.preventDefault()
      setSubmitting(true)
      try {
        await login(username, password)
      } catch {
        // error is set in context
      } finally {
        setSubmitting(false)
      }
    }

    return (
      <form onSubmit={handleSubmit} data-testid="login-form">
        <label htmlFor="auth-username">{t('auth.username')}</label>
        <input
          id="auth-username"
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          data-testid="username-input"
        />
        <label htmlFor="auth-password">{t('auth.password')}</label>
        <input
          id="auth-password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          data-testid="password-input"
        />
        <button type="submit" disabled={submitting} data-testid="login-button">
          {t('auth.login')}
        </button>
        {error && <p data-testid="login-error">{t('auth.loginError')}</p>}
      </form>
    )
  }

  if (requireAdmin && !isAdmin) {
    return <p data-testid="unauthorized-message">{t('auth.unauthorized')}</p>
  }

  return <>{children}</>
}
