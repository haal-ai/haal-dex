import { useEffect, useState } from 'react'
import { ThemeProvider, useTheme } from '../providers/ThemeProvider'
import { I18nProvider, useLanguage } from '../providers/I18nProvider'
import { AuthProvider, useAuth } from '../hooks/useAuth'
import { AuthGate } from '../components/AuthGate'
import { ChatPanel } from '../components/ChatPanel'

function generateSessionId(): string {
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function ChatAppContent() {
  const { theme, toggleTheme } = useTheme()
  const { language, setLanguage, t } = useLanguage()
  const { logout } = useAuth()
  const [sessionId, setSessionId] = useState<string>('')

  useEffect(() => {
    if (!sessionId) {
      setSessionId(generateSessionId())
    }
  }, [sessionId])

  return (
    <div data-testid="chat-app-layout" className="flex flex-col h-screen bg-background text-foreground">
      <header
        data-testid="chat-top-bar"
        className="flex items-center justify-between px-4 py-2 border-b border-border bg-card"
      >
        <h1 className="text-xl font-bold" data-testid="chat-app-title">INTENT Chat</h1>
        <div className="flex items-center gap-2">
          <button
            data-testid="theme-toggle"
            onClick={toggleTheme}
            className="px-3 py-1.5 rounded-md text-sm border border-border hover:bg-accent"
            type="button"
          >
            {t('theme.toggle')} ({theme === 'dark' ? t('theme.dark') : t('theme.light')})
          </button>
          <button
            data-testid="language-switch"
            onClick={() => setLanguage(language === 'en' ? 'fr' : 'en')}
            className="px-3 py-1.5 rounded-md text-sm border border-border hover:bg-accent"
            type="button"
          >
            {t('language.switch')} ({language.toUpperCase()})
          </button>
          <button
            data-testid="logout-button"
            onClick={logout}
            className="px-3 py-1.5 rounded-md text-sm bg-destructive text-destructive-foreground hover:opacity-90"
            type="button"
          >
            {t('auth.logout')}
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-hidden">
        <div className="mx-auto h-full max-w-6xl p-4">
          <div className="h-full rounded-xl border border-border bg-sidebar text-sidebar-foreground overflow-hidden">
            <ChatPanel sessionId={sessionId} />
          </div>
        </div>
      </main>
    </div>
  )
}

export default function ChatApp() {
  return (
    <ThemeProvider>
      <I18nProvider>
        <AuthProvider>
          <AuthGate>
            <ChatAppContent />
          </AuthGate>
        </AuthProvider>
      </I18nProvider>
    </ThemeProvider>
  )
}
