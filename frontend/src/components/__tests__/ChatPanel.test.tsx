import { render, screen, waitFor, cleanup, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { I18nProvider, resetI18nInstance } from '../../providers/I18nProvider'
import { AuthProvider } from '../../hooks/useAuth'
import { ChatPanel } from '../ChatPanel'

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
const mockWsInstances: MockWebSocket[] = []

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
  mockWsInstances.push(ws)
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
    if (typeof url === 'string' && url.includes('/api/personalities/')) {
      return {
        ok: true,
        json: async () => ({
          personalities: [
            { id: 'default', name: 'Default', description: 'General-purpose assistant.' },
            { id: 'create-otf-variable', name: 'OTF Variable Expert', description: 'OTF help' },
          ],
        }),
      }
    }
    return { ok: false, json: async () => ({}) }
  })
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

function simulateWsMessage(data: Record<string, unknown>) {
  if (!mockWsInstance?.onmessage) throw new Error('WebSocket not connected')
  const event = new MessageEvent('message', { data: JSON.stringify(data) })
  mockWsInstance.onmessage(event)
}

describe('ChatPanel', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-US')
    resetI18nInstance()
    mockFetch.mockClear()
    mockWsInstance = null
    mockWsInstances.length = 0
    ;(WebSocket as unknown as ReturnType<typeof vi.fn>).mockClear()
    ;(WebSocket as unknown as ReturnType<typeof vi.fn>).mockImplementation(createMockWebSocket)
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  describe('renders chat panel with input and send button', () => {
    it('renders the chat panel container', async () => {
      renderChatPanel()
      await waitFor(() => {
        expect(screen.getByTestId('chat-panel')).toBeInTheDocument()
      })
    })

    it('renders the chat title', async () => {
      renderChatPanel()
      await waitFor(() => {
        expect(screen.getByText('Chat')).toBeInTheDocument()
      })
    })

    it('renders the input field with placeholder', async () => {
      renderChatPanel()
      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument()
        expect(screen.getByPlaceholderText('Type a message...')).toBeInTheDocument()
      })
    })

    it('renders the send button', async () => {
      renderChatPanel()
      await waitFor(() => {
        expect(screen.getByTestId('chat-send')).toBeInTheDocument()
        expect(screen.getByText('Send')).toBeInTheDocument()
      })
    })

    it('renders the personality selector', async () => {
      renderChatPanel()
      await waitFor(() => {
        expect(screen.getByTestId('chat-personality')).toBeInTheDocument()
      })
    })

    it('renders the messages area', async () => {
      renderChatPanel()
      await waitFor(() => {
        expect(screen.getByTestId('chat-messages')).toBeInTheDocument()
      })
    })
  })

  describe('WebSocket connection', () => {
    it('connects to WebSocket with session ID and token', async () => {
      renderChatPanel('my-session')
      await waitFor(() => {
        expect(WebSocket).toHaveBeenCalled()
        const url = (WebSocket as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0] as string
        expect(url).toContain('/api/ws/chat/my-session')
        expect(url).toContain('token=test-token')
      })
    })
  })

  describe('sends message via WebSocket', () => {
    it('sends a message when send button is clicked', async () => {
      renderChatPanel()
      const user = userEvent.setup()

      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument()
      })

      await user.type(screen.getByTestId('chat-input'), 'Hello world')
      await user.click(screen.getByTestId('chat-send'))

      expect(mockWsInstance!.send).toHaveBeenCalledWith(
        JSON.stringify({
          type: 'message',
          content: 'Hello world',
          language: 'en',
          personality_id: 'default',
        })
      )
    })

    it('sends a message when Enter is pressed', async () => {
      renderChatPanel()
      const user = userEvent.setup()

      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument()
      })

      await user.type(screen.getByTestId('chat-input'), 'Bonjour{Enter}')

      expect(mockWsInstance!.send).toHaveBeenCalledWith(
        JSON.stringify({
          type: 'message',
          content: 'Bonjour',
          language: 'en',
          personality_id: 'default',
        })
      )
    })

    it('clears input after sending', async () => {
      renderChatPanel()
      const user = userEvent.setup()

      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument()
      })

      await user.type(screen.getByTestId('chat-input'), 'Test message')
      await user.click(screen.getByTestId('chat-send'))

      expect(screen.getByTestId('chat-input')).toHaveValue('')
    })

    it('does not send empty messages', async () => {
      renderChatPanel()
      const user = userEvent.setup()

      await waitFor(() => {
        expect(screen.getByTestId('chat-send')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('chat-send'))

      expect(mockWsInstance!.send).not.toHaveBeenCalled()
    })
  })

  describe('displays user messages', () => {
    it('shows user message in the chat area after sending', async () => {
      renderChatPanel()
      const user = userEvent.setup()

      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument()
      })

      await user.type(screen.getByTestId('chat-input'), 'My question')
      await user.click(screen.getByTestId('chat-send'))

      await waitFor(() => {
        expect(screen.getByTestId('chat-message-user')).toBeInTheDocument()
        expect(screen.getByText('My question')).toBeInTheDocument()
      })
    })
  })

  describe('displays streamed assistant responses', () => {
    it('shows assistant message as tokens arrive', async () => {
      renderChatPanel()
      const user = userEvent.setup()

      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument()
      })

      await user.type(screen.getByTestId('chat-input'), 'Hello')
      await user.click(screen.getByTestId('chat-send'))

      // Simulate streamed tokens
      act(() => {
        simulateWsMessage({ type: 'chat_token', session_id: 'test-session', content: 'Hi ' })
      })

      await waitFor(() => {
        const assistantMsg = screen.getByTestId('chat-message-assistant')
        expect(assistantMsg).toBeInTheDocument()
        expect(assistantMsg.textContent).toContain('Hi')
      })

      act(() => {
        simulateWsMessage({ type: 'chat_token', session_id: 'test-session', content: 'there!' })
      })

      await waitFor(() => {
        const assistantMsg = screen.getByTestId('chat-message-assistant')
        expect(assistantMsg.textContent).toBe('Hi there!')
      })

      act(() => {
        simulateWsMessage({ type: 'chat_response', session_id: 'test-session', content: 'Hi there!' })
      })

      await waitFor(() => {
        expect(screen.queryByTestId('chat-thinking')).not.toBeInTheDocument()
      })
    })
  })

  describe('shows thinking indicator', () => {
    it('displays thinking indicator after sending a message', async () => {
      renderChatPanel()
      const user = userEvent.setup()

      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument()
      })

      await user.type(screen.getByTestId('chat-input'), 'Question')
      await user.click(screen.getByTestId('chat-send'))

      await waitFor(() => {
        expect(screen.getByTestId('chat-thinking')).toBeInTheDocument()
        expect(screen.getByText('Thinking...')).toBeInTheDocument()
      })
    })

    it('hides thinking indicator when response completes', async () => {
      renderChatPanel()
      const user = userEvent.setup()

      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument()
      })

      await user.type(screen.getByTestId('chat-input'), 'Question')
      await user.click(screen.getByTestId('chat-send'))

      await waitFor(() => {
        expect(screen.getByTestId('chat-thinking')).toBeInTheDocument()
      })

      act(() => {
        simulateWsMessage({ type: 'chat_token', session_id: 'test-session', content: 'Answer' })
      })

      act(() => {
        simulateWsMessage({ type: 'chat_response', session_id: 'test-session', content: 'Answer' })
      })

      await waitFor(() => {
        expect(screen.queryByTestId('chat-thinking')).not.toBeInTheDocument()
      })
    })
  })

  describe('maintains conversation context', () => {
    it('shows multiple messages in order', async () => {
      renderChatPanel()
      const user = userEvent.setup()

      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument()
      })

      // Send first message
      await user.type(screen.getByTestId('chat-input'), 'First question')
      await user.click(screen.getByTestId('chat-send'))

      // Simulate assistant response
      act(() => {
        simulateWsMessage({ type: 'chat_token', session_id: 'test-session', content: 'First answer' })
      })
      act(() => {
        simulateWsMessage({ type: 'chat_response', session_id: 'test-session', content: 'First answer' })
      })

      await waitFor(() => {
        expect(screen.queryByTestId('chat-thinking')).not.toBeInTheDocument()
      })

      // Send second message
      await user.type(screen.getByTestId('chat-input'), 'Second question')
      await user.click(screen.getByTestId('chat-send'))

      // Simulate second assistant response
      act(() => {
        simulateWsMessage({ type: 'chat_token', session_id: 'test-session', content: 'Second answer' })
      })
      act(() => {
        simulateWsMessage({ type: 'chat_response', session_id: 'test-session', content: 'Second answer' })
      })

      await waitFor(() => {
        const userMessages = screen.getAllByTestId('chat-message-user')
        const assistantMessages = screen.getAllByTestId('chat-message-assistant')
        expect(userMessages).toHaveLength(2)
        expect(assistantMessages).toHaveLength(2)
        expect(screen.getByText('First question')).toBeInTheDocument()
        expect(screen.getByText('First answer')).toBeInTheDocument()
        expect(screen.getByText('Second question')).toBeInTheDocument()
        expect(screen.getByText('Second answer')).toBeInTheDocument()
      })
    })
  })

  describe('uses i18n translations', () => {
    it('renders French translations when language is FR', async () => {
      localStorage.setItem('intent-language', 'fr')
      resetI18nInstance()
      renderChatPanel()

      await waitFor(() => {
        expect(screen.getByText('Discussion')).toBeInTheDocument()
        expect(screen.getByPlaceholderText('Saisissez un message...')).toBeInTheDocument()
        expect(screen.getByText('Envoyer')).toBeInTheDocument()
      })
    })

    it('shows French thinking indicator', async () => {
      localStorage.setItem('intent-language', 'fr')
      resetI18nInstance()
      renderChatPanel()
      const user = userEvent.setup()

      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument()
      })

      await user.type(screen.getByTestId('chat-input'), 'Bonjour')
      await user.click(screen.getByTestId('chat-send'))

      await waitFor(() => {
        expect(screen.getByText('Réflexion en cours...')).toBeInTheDocument()
      })
    })

    it('sends messages with language "fr" when interface is French (Req 2.2)', async () => {
      localStorage.setItem('intent-language', 'fr')
      resetI18nInstance()
      renderChatPanel()
      const user = userEvent.setup()

      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument()
      })

      await user.type(screen.getByTestId('chat-input'), 'Bonjour le monde')
      await user.click(screen.getByTestId('chat-send'))

      expect(mockWsInstance!.send).toHaveBeenCalledWith(
        JSON.stringify({
          type: 'message',
          content: 'Bonjour le monde',
          language: 'fr',
          personality_id: 'default',
        })
      )
    })
  })

  describe('error handling', () => {
    it('shows error message on WebSocket error event', async () => {
      renderChatPanel()

      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull()
      })

      act(() => {
        mockWsInstance!.onerror!(new Event('error'))
      })

      await waitFor(() => {
        expect(screen.getByTestId('chat-error')).toBeInTheDocument()
      })
    })

    it('shows error message when server sends error response', async () => {
      renderChatPanel()
      const user = userEvent.setup()

      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument()
      })

      await user.type(screen.getByTestId('chat-input'), 'Hello')
      await user.click(screen.getByTestId('chat-send'))

      act(() => {
        simulateWsMessage({ type: 'error', session_id: 'test-session', content: 'Server error' })
      })

      await waitFor(() => {
        expect(screen.getByTestId('chat-error')).toBeInTheDocument()
        expect(screen.getByText('Server error')).toBeInTheDocument()
      })
    })
  })
})
