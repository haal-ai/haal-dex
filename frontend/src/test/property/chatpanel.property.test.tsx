/**
 * Property 3: Chat session context accumulation
 * Validates: Requirements 2.4
 *
 * For N messages in a session, context contains all N messages in order.
 */
import { render, screen, waitFor, cleanup, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import * as fc from 'fast-check'
import { I18nProvider, resetI18nInstance } from '../../providers/I18nProvider'
import { AuthProvider } from '../../hooks/useAuth'
import { ChatPanel } from '../../components/ChatPanel'

// --- WebSocket mock ---
interface MockWebSocket {
  url: string
  readyState: number
  onopen: ((ev: Event) => void) | null
  onmessage: ((ev: MessageEvent) => void) | null
  onerror: ((ev: Event) => void) | null
  onclose: ((ev: CloseEvent) => void) | null
  send: ReturnType<typeof vi.fn>
  close: ReturnType<typeof vi.fn>
}

let mockWsInstance: MockWebSocket | null = null

function createMockWebSocket(url: string): MockWebSocket {
  const ws: MockWebSocket = {
    url,
    readyState: WebSocket.OPEN,
    onopen: null,
    onmessage: null,
    onerror: null,
    onclose: null,
    send: vi.fn(),
    close: vi.fn(),
  }
  mockWsInstance = ws
  return ws
}

vi.stubGlobal('WebSocket', vi.fn(createMockWebSocket))

// --- fetch mock for auth ---
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function setupAuthFetch() {
  mockFetch.mockImplementation(async (url: string) => {
    if (typeof url === 'string' && url.includes('/api/auth/me')) {
      return {
        ok: true,
        json: async () => ({ user_id: 'u1', username: 'testuser', roles: ['user'] }),
      }
    }
    return { ok: false, json: async () => ({}) }
  })
}

function simulateWsMessage(data: Record<string, unknown>) {
  if (!mockWsInstance?.onmessage) throw new Error('WebSocket not connected')
  const event = new MessageEvent('message', { data: JSON.stringify(data) })
  mockWsInstance.onmessage(event)
}

function renderChatPanel(sessionId = 'test-session') {
  setupAuthFetch()
  localStorage.setItem('intent-auth-token', 'test-token')
  return render(
    <AuthProvider>
      <I18nProvider>
        <ChatPanel sessionId={sessionId} />
      </I18nProvider>
    </AuthProvider>
  )
}

// Arbitrary: generate non-empty arrays of non-empty printable message strings (no leading/trailing spaces to avoid trim mismatch)
const messageArb = fc.stringMatching(/^[a-zA-Z0-9][a-zA-Z0-9 ]{0,19}[a-zA-Z0-9]$/).filter((s) => s.trim().length > 0 && s === s.trim())
const messageListArb = fc.array(messageArb, { minLength: 1, maxLength: 5 })

describe('Property 3: Chat session context accumulation', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-US')
    resetI18nInstance()
    mockFetch.mockClear()
    mockWsInstance = null
    ;(WebSocket as unknown as ReturnType<typeof vi.fn>).mockClear()
    ;(WebSocket as unknown as ReturnType<typeof vi.fn>).mockImplementation(createMockWebSocket)
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('for N messages, context contains all N user messages and N assistant responses in order', { timeout: 30000 }, async () => {
    await fc.assert(
      fc.asyncProperty(messageListArb, async (messages) => {
        // Reset state for each property run
        cleanup()
        localStorage.clear()
        localStorage.setItem('intent-auth-token', 'test-token')
        vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-US')
        resetI18nInstance()
        mockFetch.mockClear()
        mockWsInstance = null
        ;(WebSocket as unknown as ReturnType<typeof vi.fn>).mockClear()
        ;(WebSocket as unknown as ReturnType<typeof vi.fn>).mockImplementation(createMockWebSocket)

        renderChatPanel()
        const user = userEvent.setup()

        await waitFor(() => {
          expect(screen.getByTestId('chat-input')).toBeInTheDocument()
        })

        // Send each message and simulate assistant response
        for (let i = 0; i < messages.length; i++) {
          const msg = messages[i]
          const assistantReply = `reply-${i}`

          await user.type(screen.getByTestId('chat-input'), msg)
          await user.click(screen.getByTestId('chat-send'))

          // Simulate assistant streaming response
          act(() => {
            simulateWsMessage({ type: 'token', session_id: 'test-session', content: assistantReply })
          })
          act(() => {
            simulateWsMessage({ type: 'complete', session_id: 'test-session', content: '' })
          })

          // Wait for thinking indicator to disappear before next message
          await waitFor(() => {
            expect(screen.queryByTestId('chat-thinking')).not.toBeInTheDocument()
          })
        }

        // Assert: all user messages and assistant messages are present
        await waitFor(() => {
          const userMessages = screen.getAllByTestId('chat-message-user')
          const assistantMessages = screen.getAllByTestId('chat-message-assistant')
          expect(userMessages).toHaveLength(messages.length)
          expect(assistantMessages).toHaveLength(messages.length)
        })

        // Assert: messages appear in order
        const userMessages = screen.getAllByTestId('chat-message-user')
        const assistantMessages = screen.getAllByTestId('chat-message-assistant')

        for (let i = 0; i < messages.length; i++) {
          expect(userMessages[i].textContent).toBe(messages[i])
          expect(assistantMessages[i].textContent).toBe(`reply-${i}`)
        }
      }),
      { numRuns: 10 }
    )
  })
})
