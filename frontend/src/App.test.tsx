import { render, screen, waitFor, cleanup } from '@testing-library/react'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { resetI18nInstance } from './providers/I18nProvider'
import App from './App'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

// Mock WebSocket
class MockWebSocket {
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  readyState = 1
  close() {}
  send() {}
}
vi.stubGlobal('WebSocket', MockWebSocket)

function mockMatchMedia(prefersDark = false) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query === '(prefers-color-scheme: dark)' ? prefersDark : false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}

function setupFetchMock(authenticated: boolean, isAdmin = false) {
  mockFetch.mockImplementation(async (url: string) => {
    if (typeof url === 'string' && url.includes('/api/auth/me')) {
      if (!authenticated) {
        return { ok: false, json: async () => ({}) }
      }
      return {
        ok: true,
        json: async () => ({
          user_id: 'u1',
          username: 'testuser',
          roles: isAdmin ? ['admin'] : ['user'],
        }),
      }
    }
    if (typeof url === 'string' && url.includes('/api/auth/login')) {
      return {
        ok: true,
        json: async () => ({
          access_token: 'test-token',
          user_id: 'u1',
          roles: isAdmin ? ['admin'] : ['user'],
        }),
      }
    }
    return { ok: false, json: async () => ({}) }
  })
}

describe('App', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
    mockMatchMedia(false)
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-US')
    resetI18nInstance()
    mockFetch.mockClear()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('renders with providers and shows login form when not authenticated', async () => {
    setupFetchMock(false)
    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('login-form')).toBeInTheDocument()
    })

    expect(screen.getByTestId('username-input')).toBeInTheDocument()
    expect(screen.getByTestId('password-input')).toBeInTheDocument()
    expect(screen.getByTestId('login-button')).toBeInTheDocument()
  })

  it('shows main layout when authenticated', async () => {
    setupFetchMock(true)
    localStorage.setItem('intent-auth-token', 'test-token')
    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('chat-app-layout')).toBeInTheDocument()
    })

    expect(screen.getByTestId('chat-app-title')).toHaveTextContent('INTENT Chat')
    expect(screen.getByTestId('theme-toggle')).toBeInTheDocument()
    expect(screen.getByTestId('language-switch')).toBeInTheDocument()
    expect(screen.getByTestId('logout-button')).toBeInTheDocument()
    expect(screen.getByTestId('chat-panel')).toBeInTheDocument()
    expect(screen.queryByTestId('tab-navigation')).not.toBeInTheDocument()
    expect(screen.queryByTestId('dropzone')).not.toBeInTheDocument()
    expect(screen.queryByTestId('execution-timeline')).not.toBeInTheDocument()
    expect(screen.queryByTestId('output-viewer')).not.toBeInTheDocument()
  })

  it('does not render legacy builder controls', async () => {
    setupFetchMock(true, true)
    localStorage.setItem('intent-auth-token', 'test-token')
    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('chat-app-layout')).toBeInTheDocument()
    })

    expect(screen.queryByTestId('tab-upload')).not.toBeInTheDocument()
    expect(screen.queryByTestId('tab-pipeline')).not.toBeInTheDocument()
    expect(screen.queryByTestId('tab-output')).not.toBeInTheDocument()
    expect(screen.queryByTestId('tab-metrics')).not.toBeInTheDocument()
    expect(screen.queryByTestId('tab-replay')).not.toBeInTheDocument()
    expect(screen.queryByTestId('tab-config')).not.toBeInTheDocument()
  })
})
