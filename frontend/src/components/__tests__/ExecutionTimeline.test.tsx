import { render, screen, waitFor, cleanup, act } from '@testing-library/react'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { I18nProvider, resetI18nInstance } from '../../providers/I18nProvider'
import { AuthProvider } from '../../hooks/useAuth'
import { ExecutionTimeline } from '../ExecutionTimeline'

// --- WebSocket mock (same pattern as ChatPanel.test.tsx) ---
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
    return { ok: false, json: async () => ({}) }
  })
}

function renderTimeline(sessionId = 'test-session') {
  setupAuthFetch()
  localStorage.setItem('intent-auth-token', 'test-token')

  return render(
    <AuthProvider>
      <I18nProvider>
        <ExecutionTimeline sessionId={sessionId} />
      </I18nProvider>
    </AuthProvider>
  )
}

function simulateWsMessage(data: Record<string, unknown>) {
  if (!mockWsInstance?.onmessage) throw new Error('WebSocket not connected')
  const event = new MessageEvent('message', { data: JSON.stringify(data) })
  mockWsInstance.onmessage(event)
}

function makeAgentStartEvent(agentId: string, agentName: string, stepNumber: number) {
  return {
    type: 'agent_start',
    session_id: 'test-session',
    timestamp: '2025-01-01T00:00:00Z',
    data: {
      agent_id: agentId,
      agent_name: agentName,
      step_number: stepNumber,
      status: 'running',
    },
  }
}

function makeAgentCompleteEvent(agentId: string, agentName: string, stepNumber: number) {
  return {
    type: 'agent_complete',
    session_id: 'test-session',
    timestamp: '2025-01-01T00:01:00Z',
    data: {
      agent_id: agentId,
      agent_name: agentName,
      step_number: stepNumber,
      status: 'completed',
    },
  }
}

function makeAgentFailEvent(agentId: string, agentName: string, stepNumber: number, error: string) {
  return {
    type: 'agent_fail',
    session_id: 'test-session',
    timestamp: '2025-01-01T00:01:00Z',
    data: {
      agent_id: agentId,
      agent_name: agentName,
      step_number: stepNumber,
      status: 'failed',
      error,
    },
  }
}

function makePipelineCompleteEvent(status: 'COMPLETED' | 'FAILED') {
  return {
    type: 'pipeline_complete',
    session_id: 'test-session',
    timestamp: '2025-01-01T00:02:00Z',
    data: {
      status,
      execution_order: ['agent-1'],
      execution_time_ms: 5000,
      total_tokens: { input: 100, output: 200 },
    },
  }
}

describe('ExecutionTimeline', () => {
  beforeEach(() => {
    localStorage.clear()
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

  describe('renders timeline container', () => {
    it('renders the timeline container element', async () => {
      renderTimeline()
      await waitFor(() => {
        expect(screen.getByTestId('execution-timeline')).toBeInTheDocument()
      })
    })

    it('renders the pipeline title', async () => {
      renderTimeline()
      await waitFor(() => {
        expect(screen.getByText('Pipeline Execution')).toBeInTheDocument()
      })
    })

    it('renders the agent timeline area', async () => {
      renderTimeline()
      await waitFor(() => {
        expect(screen.getByTestId('agent-timeline')).toBeInTheDocument()
      })
    })

    it('renders the log entries area', async () => {
      renderTimeline()
      await waitFor(() => {
        expect(screen.getByTestId('log-entries')).toBeInTheDocument()
      })
    })
  })

  describe('WebSocket connection', () => {
    it('connects to execution WebSocket with session ID and token', async () => {
      renderTimeline('exec-session')
      await waitFor(() => {
        expect(WebSocket).toHaveBeenCalled()
        const url = (WebSocket as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0] as string
        expect(url).toContain('/api/ws/execution/exec-session')
        expect(url).toContain('token=test-token')
      })
    })
  })

  describe('shows agent status updates (pending → running → completed)', () => {
    it('shows agent as running when agent_start event arrives', async () => {
      renderTimeline()
      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull()
      })

      act(() => {
        simulateWsMessage(makeAgentStartEvent('agent-1', 'Content Analyzer', 1))
      })

      await waitFor(() => {
        expect(screen.getByTestId('agent-entry-agent-1')).toBeInTheDocument()
        expect(screen.getByText('Content Analyzer')).toBeInTheDocument()
        expect(screen.getByTestId('agent-status-agent-1')).toHaveTextContent('Running')
      })
    })

    it('shows agent as completed when agent_complete event arrives', async () => {
      renderTimeline()
      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull()
      })

      act(() => {
        simulateWsMessage(makeAgentStartEvent('agent-1', 'Content Analyzer', 1))
      })

      act(() => {
        simulateWsMessage(makeAgentCompleteEvent('agent-1', 'Content Analyzer', 1))
      })

      await waitFor(() => {
        expect(screen.getByTestId('agent-status-agent-1')).toHaveTextContent('Completed')
      })
    })

    it('shows step number for each agent', async () => {
      renderTimeline()
      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull()
      })

      act(() => {
        simulateWsMessage(makeAgentStartEvent('agent-1', 'Analyzer', 1))
      })

      await waitFor(() => {
        expect(screen.getByText('Step 1')).toBeInTheDocument()
      })
    })

    it('tracks multiple agents through status transitions', async () => {
      renderTimeline()
      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull()
      })

      act(() => {
        simulateWsMessage(makeAgentStartEvent('agent-1', 'Analyzer', 1))
      })

      act(() => {
        simulateWsMessage(makeAgentCompleteEvent('agent-1', 'Analyzer', 1))
      })

      act(() => {
        simulateWsMessage(makeAgentStartEvent('agent-2', 'Generator', 2))
      })

      await waitFor(() => {
        expect(screen.getByTestId('agent-status-agent-1')).toHaveTextContent('Completed')
        expect(screen.getByTestId('agent-status-agent-2')).toHaveTextContent('Running')
      })
    })
  })

  describe('shows failed agent status', () => {
    it('shows agent as failed when agent_fail event arrives', async () => {
      renderTimeline()
      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull()
      })

      act(() => {
        simulateWsMessage(makeAgentStartEvent('agent-1', 'Analyzer', 1))
      })

      act(() => {
        simulateWsMessage(makeAgentFailEvent('agent-1', 'Analyzer', 1, 'LLM timeout'))
      })

      await waitFor(() => {
        expect(screen.getByTestId('agent-status-agent-1')).toHaveTextContent('Failed')
      })
    })

    it('logs the failure error message', async () => {
      renderTimeline()
      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull()
      })

      act(() => {
        simulateWsMessage(makeAgentStartEvent('agent-1', 'Analyzer', 1))
      })

      act(() => {
        simulateWsMessage(makeAgentFailEvent('agent-1', 'Analyzer', 1, 'LLM timeout'))
      })

      await waitFor(() => {
        const logEntries = screen.getAllByTestId('log-entry')
        const failLog = logEntries.find((el) => el.textContent?.includes('LLM timeout'))
        expect(failLog).toBeDefined()
      })
    })
  })

  describe('shows pipeline completion', () => {
    it('shows pipeline completed status', async () => {
      renderTimeline()
      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull()
      })

      act(() => {
        simulateWsMessage(makePipelineCompleteEvent('COMPLETED'))
      })

      await waitFor(() => {
        expect(screen.getByTestId('pipeline-status')).toBeInTheDocument()
        expect(screen.getByTestId('pipeline-status')).toHaveTextContent('Completed')
      })
    })

    it('shows pipeline failed status', async () => {
      renderTimeline()
      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull()
      })

      act(() => {
        simulateWsMessage(makePipelineCompleteEvent('FAILED'))
      })

      await waitFor(() => {
        expect(screen.getByTestId('pipeline-status')).toBeInTheDocument()
        expect(screen.getByTestId('pipeline-status')).toHaveTextContent('Failed')
      })
    })

    it('adds pipeline completion to log entries', async () => {
      renderTimeline()
      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull()
      })

      act(() => {
        simulateWsMessage(makePipelineCompleteEvent('COMPLETED'))
      })

      await waitFor(() => {
        const logEntries = screen.getAllByTestId('log-entry')
        const completionLog = logEntries.find((el) =>
          el.textContent?.includes('Pipeline Execution') && el.textContent?.includes('Completed')
        )
        expect(completionLog).toBeDefined()
      })
    })
  })

  describe('shows error messages', () => {
    it('shows error on WebSocket error event', async () => {
      renderTimeline()
      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull()
      })

      act(() => {
        mockWsInstance!.onerror!(new Event('error'))
      })

      await waitFor(() => {
        expect(screen.getByTestId('timeline-error')).toBeInTheDocument()
        expect(screen.getByTestId('timeline-error')).toHaveTextContent('Pipeline error')
      })
    })
  })

  describe('shows currently active agent', () => {
    it('highlights the currently running agent', async () => {
      renderTimeline()
      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull()
      })

      act(() => {
        simulateWsMessage(makeAgentStartEvent('agent-1', 'Content Analyzer', 1))
      })

      await waitFor(() => {
        expect(screen.getByTestId('active-agent')).toBeInTheDocument()
        expect(screen.getByTestId('active-agent')).toHaveTextContent('Content Analyzer')
      })
    })

    it('removes active agent indicator when agent completes', async () => {
      renderTimeline()
      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull()
      })

      act(() => {
        simulateWsMessage(makeAgentStartEvent('agent-1', 'Analyzer', 1))
      })

      await waitFor(() => {
        expect(screen.getByTestId('active-agent')).toBeInTheDocument()
      })

      act(() => {
        simulateWsMessage(makeAgentCompleteEvent('agent-1', 'Analyzer', 1))
      })

      await waitFor(() => {
        expect(screen.queryByTestId('active-agent')).not.toBeInTheDocument()
      })
    })
  })

  describe('streams live log entries', () => {
    it('adds log entries as agent events arrive', async () => {
      renderTimeline()
      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull()
      })

      act(() => {
        simulateWsMessage(makeAgentStartEvent('agent-1', 'Analyzer', 1))
      })

      act(() => {
        simulateWsMessage(makeAgentCompleteEvent('agent-1', 'Analyzer', 1))
      })

      await waitFor(() => {
        const logEntries = screen.getAllByTestId('log-entry')
        expect(logEntries.length).toBeGreaterThanOrEqual(2)
      })
    })
  })

  describe('uses i18n translations', () => {
    it('renders French translations when language is FR', async () => {
      localStorage.setItem('intent-language', 'fr')
      resetI18nInstance()
      renderTimeline()

      await waitFor(() => {
        expect(screen.getByText('Exécution du pipeline')).toBeInTheDocument()
      })
    })

    it('shows French agent status labels', async () => {
      localStorage.setItem('intent-language', 'fr')
      resetI18nInstance()
      renderTimeline()

      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull()
      })

      act(() => {
        simulateWsMessage(makeAgentStartEvent('agent-1', 'Analyseur', 1))
      })

      await waitFor(() => {
        expect(screen.getByTestId('agent-status-agent-1')).toHaveTextContent('En cours')
      })
    })

    it('shows French completed status after pipeline completes', async () => {
      localStorage.setItem('intent-language', 'fr')
      resetI18nInstance()
      renderTimeline()

      await waitFor(() => {
        expect(mockWsInstance).not.toBeNull()
      })

      act(() => {
        simulateWsMessage(makePipelineCompleteEvent('COMPLETED'))
      })

      await waitFor(() => {
        expect(screen.getByTestId('pipeline-status')).toHaveTextContent('Terminé')
      })
    })
  })
})
