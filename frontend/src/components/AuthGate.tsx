import { useRef, useState, type ReactNode, type FormEvent, type KeyboardEvent } from 'react'
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
  const formRef = useRef<HTMLFormElement | null>(null)

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

    const handleEnterSubmit = (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key !== 'Enter') {
        return
      }
      e.preventDefault()
      formRef.current?.requestSubmit()
    }

    return (
      <div className="min-h-screen flex items-center justify-center px-4 bg-gradient-to-br from-gray-50 to-gray-200 dark:from-gray-950 dark:to-gray-900">
        <div className="w-full max-w-md">
          <div className="text-center mb-6">
            <div className="mx-auto h-12 w-12 rounded-xl bg-blue-600 text-white flex items-center justify-center font-semibold text-lg shadow">
              HD
            </div>
            <h1 className="mt-4 text-2xl font-semibold tracking-tight text-gray-900 dark:text-gray-50">
              HAAL DEX
            </h1>
            <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
              {t('auth.login')}
            </p>
          </div>

          <form
            ref={formRef}
            onSubmit={handleSubmit}
            data-testid="login-form"
            className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white/90 dark:bg-gray-950/70 backdrop-blur shadow-lg p-6 space-y-4"
          >
            <div className="space-y-1">
              <label htmlFor="auth-username" className="text-sm font-medium text-gray-800 dark:text-gray-200">
                {t('auth.username')}
              </label>
              <input
                id="auth-username"
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                onKeyDown={handleEnterSubmit}
                data-testid="username-input"
                className="w-full rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-50 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div className="space-y-1">
              <label htmlFor="auth-password" className="text-sm font-medium text-gray-800 dark:text-gray-200">
                {t('auth.password')}
              </label>
              <input
                id="auth-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={handleEnterSubmit}
                data-testid="password-input"
                className="w-full rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-50 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <button
              type="submit"
              disabled={submitting}
              data-testid="login-button"
              className={
                submitting
                  ? 'w-full rounded-md bg-blue-600/70 text-white text-sm font-medium py-2.5 cursor-not-allowed'
                  : 'w-full rounded-md bg-blue-600 text-white text-sm font-medium py-2.5 hover:bg-blue-700 active:bg-blue-800'
              }
            >
              {t('auth.login')}
            </button>

            {error && (
              <p data-testid="login-error" className="text-sm text-red-600 dark:text-red-400" role="alert">
                {t('auth.loginError')}
              </p>
            )}
          </form>

          <p className="mt-6 text-center text-xs text-gray-500 dark:text-gray-400">
            {t('auth.username')} / {t('auth.password')}
          </p>
        </div>
      </div>
    )
  }

  if (requireAdmin && !isAdmin) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4 bg-gradient-to-br from-gray-50 to-gray-200 dark:from-gray-950 dark:to-gray-900">
        <div className="w-full max-w-md rounded-2xl border border-gray-200 dark:border-gray-800 bg-white/90 dark:bg-gray-950/70 backdrop-blur shadow-lg p-6 text-center">
          <p data-testid="unauthorized-message" className="text-sm text-red-600 dark:text-red-400" role="alert">
            {t('auth.unauthorized')}
          </p>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
