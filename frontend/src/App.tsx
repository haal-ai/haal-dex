import { useState, useCallback, useEffect, useRef } from 'react'
import { ThemeProvider, useTheme } from './providers/ThemeProvider'
import { I18nProvider, useLanguage } from './providers/I18nProvider'
import { AuthProvider, useAuth } from './hooks/useAuth'
import { AuthGate } from './components/AuthGate'
import { DropZone } from './components/DropZone'
import { ChatPanel } from './components/ChatPanel'
import { ExecutionTimeline } from './components/ExecutionTimeline'
import { OutputViewer } from './components/OutputViewer'
import { MetricsDashboard } from './components/MetricsDashboard'
import { ReplayViewer } from './components/ReplayViewer'
import { ConfigPanel } from './components/ConfigPanel'
import { cn } from './lib/utils'

type Tab = 'upload' | 'pipeline' | 'output' | 'metrics' | 'replay' | 'config'

const TABS: { id: Tab; labelKey: string; adminOnly?: boolean }[] = [
  { id: 'upload', labelKey: 'fileUpload.title' },
  { id: 'pipeline', labelKey: 'pipeline.title' },
  { id: 'output', labelKey: 'output.title' },
  { id: 'metrics', labelKey: 'metrics.title' },
  { id: 'replay', labelKey: 'replay.title' },
  { id: 'config', labelKey: 'config.title', adminOnly: true },
]

function generateSessionId(): string {
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function AppContent() {
  const { theme, toggleTheme } = useTheme()
  const { language, setLanguage, t } = useLanguage()
  const { logout, isAdmin } = useAuth()
  const [activeTab, setActiveTab] = useState<Tab>('upload')
  const [sessionId, setSessionId] = useState<string>('')
  const sidebarWidthStorageKey = 'intent-chat-sidebar-width'
  const minSidebarWidth = 260
  const maxSidebarWidth = 700
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    const raw = localStorage.getItem(sidebarWidthStorageKey)
    const parsed = raw ? Number(raw) : NaN
    if (Number.isFinite(parsed) && parsed >= minSidebarWidth && parsed <= maxSidebarWidth) {
      return parsed
    }
    return 320
  })
  const resizingRef = useRef(false)
  const resizeStartXRef = useRef(0)
  const resizeStartWidthRef = useRef(0)

  const clampSidebarWidth = useCallback(
    (value: number) => Math.min(maxSidebarWidth, Math.max(minSidebarWidth, value)),
    [maxSidebarWidth, minSidebarWidth]
  )

  useEffect(() => {
    localStorage.setItem(sidebarWidthStorageKey, String(sidebarWidth))
  }, [sidebarWidth, sidebarWidthStorageKey])

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!resizingRef.current) return
      const dx = e.clientX - resizeStartXRef.current
      setSidebarWidth(clampSidebarWidth(resizeStartWidthRef.current + dx))
    }

    const onMouseUp = () => {
      resizingRef.current = false
    }

    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [clampSidebarWidth])

  const onResizeMouseDown = useCallback(
    (e: React.MouseEvent) => {
      resizingRef.current = true
      resizeStartXRef.current = e.clientX
      resizeStartWidthRef.current = sidebarWidth
      e.preventDefault()
    },
    [sidebarWidth]
  )

  useEffect(() => {
    if (!sessionId) {
      setSessionId(generateSessionId())
    }
  }, [sessionId])

  const ensureSession = useCallback(() => {
    if (!sessionId) {
      const id = generateSessionId()
      setSessionId(id)
      return id
    }
    return sessionId
  }, [sessionId])

  const handleTabChange = useCallback((tab: Tab) => {
    setActiveTab(tab)
    // Ensure session exists when navigating to session-dependent tabs
    if (tab !== 'upload' && tab !== 'config') {
      ensureSession()
    }
  }, [ensureSession])

  const visibleTabs = TABS.filter((tab) => !tab.adminOnly || isAdmin)

  return (
    <div data-testid="app-layout" className="flex flex-col h-screen bg-background text-foreground">
      {/* Top bar */}
      <header
        data-testid="top-bar"
        className="flex items-center justify-between px-4 py-2 border-b border-border bg-card"
      >
        <h1 className="text-xl font-bold" data-testid="app-title">INTENT</h1>
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

      {/* Main content area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar — Chat */}
        <aside
          data-testid="sidebar"
          className="border-r border-border flex flex-col bg-sidebar text-sidebar-foreground flex-shrink-0"
          style={{ width: sidebarWidth }}
        >
          <ChatPanel sessionId={sessionId} />
        </aside>

        <div
          data-testid="sidebar-resizer"
          className="w-1 cursor-col-resize bg-border hover:bg-muted"
          onMouseDown={onResizeMouseDown}
          role="separator"
          aria-orientation="vertical"
          tabIndex={0}
        />

        {/* Main area */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Tab navigation */}
          <nav data-testid="tab-navigation" className="flex border-b border-border bg-card px-2">
            {visibleTabs.map((tab) => (
              <button
                key={tab.id}
                data-testid={`tab-${tab.id}`}
                onClick={() => handleTabChange(tab.id)}
                className={cn(
                  'px-4 py-2 text-sm font-medium border-b-2 transition-colors',
                  activeTab === tab.id
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
                )}
                type="button"
              >
                {t(tab.labelKey)}
              </button>
            ))}
          </nav>

          {/* Tab content */}
          <div data-testid="tab-content" className="flex-1 overflow-auto p-4">
            {activeTab === 'upload' && (
              <DropZone
                onSessionCreated={(newSessionId) => {
                  setSessionId(newSessionId)
                  setActiveTab('pipeline')
                }}
              />
            )}
            {activeTab === 'pipeline' && (
              <ExecutionTimeline sessionId={ensureSession()} />
            )}
            {activeTab === 'output' && (
              <OutputViewer sessionId={ensureSession()} />
            )}
            {activeTab === 'metrics' && (
              <MetricsDashboard sessionId={ensureSession()} />
            )}
            {activeTab === 'replay' && (
              <ReplayViewer sessionId={ensureSession()} />
            )}
            {activeTab === 'config' && (
              <AuthGate requireAdmin>
                <ConfigPanel />
              </AuthGate>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}

function App() {
  return (
    <ThemeProvider>
      <I18nProvider>
        <AuthProvider>
          <AuthGate>
            <AppContent />
          </AuthGate>
        </AuthProvider>
      </I18nProvider>
    </ThemeProvider>
  )
}

export default App
