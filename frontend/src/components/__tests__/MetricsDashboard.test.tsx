import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { I18nProvider, resetI18nInstance } from '../../providers/I18nProvider'
import { AuthProvider } from '../../hooks/useAuth'
import { MetricsDashboard } from '../MetricsDashboard'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

const MOCK_METRICS = {
  session_id: 'sess-1',
  agent_metrics: [
    {
      agent_id: 'agent-1',
      agent_name: 'Context Analyzer',
      input_tokens: 1500,
      output_tokens: 800,
      llm_call_count: 3,
    },
    {
      agent_id: 'agent-2',
      agent_name: 'Content Generator',
      input_tokens: 2200,
      output_tokens: 1400,
      llm_call_count: 5,
    },
  ],
}

function setupFetch(options?: { metricsData?: typeof MOCK_METRICS | null; metricsOk?: boolean }) {
  const { metricsData = MOCK_METRICS, metricsOk = true } = options ?? {}

  mockFetch.mockImplementation(async (url: string) => {
    if (typeof url === 'string' && url.includes('/api/auth/me')) {
      return {
        ok: true,
        json: async () => ({ user_id: 'u1', username: 'testuser', roles: ['user'] }),
      }
    }
    if (typeof url === 'string' && url.includes('/api/metrics/') && url.includes('/csv')) {
      return {
        ok: true,
        blob: async () => new Blob(['agent_id,input_tokens\n'], { type: 'text/csv' }),
      }
    }
    if (typeof url === 'string' && url.includes('/api/metrics/')) {
      return {
        ok: metricsOk,
        json: async () => metricsData,
      }
    }
    return { ok: false, json: async () => ({}) }
  })
}

function renderDashboard(sessionId = 'sess-1') {
  setupFetch()
  localStorage.setItem('intent-auth-token', 'test-token')

  return render(
    <AuthProvider>
      <I18nProvider>
        <MetricsDashboard sessionId={sessionId} />
      </I18nProvider>
    </AuthProvider>
  )
}

describe('MetricsDashboard', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-US')
    resetI18nInstance()
    mockFetch.mockClear()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('renders metrics dashboard container', async () => {
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByTestId('metrics-dashboard')).toBeInTheDocument()
    })
  })

  it('fetches and displays per-agent metrics', async () => {
    renderDashboard()

    await waitFor(() => {
      expect(screen.getByTestId('per-agent-metrics')).toBeInTheDocument()
    })

    expect(screen.getByTestId('agent-metrics-agent-1')).toBeInTheDocument()
    expect(screen.getByTestId('agent-metrics-agent-2')).toBeInTheDocument()
    expect(screen.getByText('Context Analyzer')).toBeInTheDocument()
    expect(screen.getByText('Content Generator')).toBeInTheDocument()

    expect(screen.getByTestId('input-tokens-agent-1')).toHaveTextContent('1,500')
    expect(screen.getByTestId('output-tokens-agent-1')).toHaveTextContent('800')
    expect(screen.getByTestId('llm-calls-agent-1')).toHaveTextContent('3')

    expect(screen.getByTestId('input-tokens-agent-2')).toHaveTextContent('2,200')
    expect(screen.getByTestId('output-tokens-agent-2')).toHaveTextContent('1,400')
    expect(screen.getByTestId('llm-calls-agent-2')).toHaveTextContent('5')
  })

  it('shows total metrics summed across all agents', async () => {
    renderDashboard()

    await waitFor(() => {
      expect(screen.getByTestId('total-metrics')).toBeInTheDocument()
    })

    // 1500 + 2200 = 3700
    expect(screen.getByTestId('total-input-tokens')).toHaveTextContent('3,700')
    // 800 + 1400 = 2200
    expect(screen.getByTestId('total-output-tokens')).toHaveTextContent('2,200')
    // 3 + 5 = 8
    expect(screen.getByTestId('total-llm-calls')).toHaveTextContent('8')
  })

  it('shows export CSV button', async () => {
    renderDashboard()

    await waitFor(() => {
      expect(screen.getByTestId('export-csv')).toBeInTheDocument()
      expect(screen.getByText('Export CSV')).toBeInTheDocument()
    })
  })

  it('export CSV triggers download', async () => {
    renderDashboard()
    const user = userEvent.setup()

    await waitFor(() => {
      expect(screen.getByTestId('export-csv')).toBeEnabled()
    })

    await user.click(screen.getByTestId('export-csv'))

    await waitFor(() => {
      const csvCalls = mockFetch.mock.calls.filter(
        (call: unknown[]) => typeof call[0] === 'string' && (call[0] as string).includes('/csv')
      )
      expect(csvCalls.length).toBeGreaterThan(0)
      expect(csvCalls[0][0]).toContain('/api/metrics/sess-1/csv')
    })
  })

  describe('uses i18n translations', () => {
    it('renders English translations', async () => {
      renderDashboard()

      await waitFor(() => {
        expect(screen.getByText('Metrics')).toBeInTheDocument()
        expect(screen.getByText('Per Agent')).toBeInTheDocument()
        expect(screen.getByText('Total')).toBeInTheDocument()
        expect(screen.getByText('Export CSV')).toBeInTheDocument()
      })

      // Check column labels (multiple instances expected)
      const inputTokenLabels = screen.getAllByText('Input Tokens')
      expect(inputTokenLabels.length).toBeGreaterThan(0)
      const outputTokenLabels = screen.getAllByText('Output Tokens')
      expect(outputTokenLabels.length).toBeGreaterThan(0)
      const llmCallLabels = screen.getAllByText('LLM Calls')
      expect(llmCallLabels.length).toBeGreaterThan(0)
    })

    it('renders French translations when language is FR', async () => {
      localStorage.setItem('intent-language', 'fr')
      resetI18nInstance()
      setupFetch()
      localStorage.setItem('intent-auth-token', 'test-token')

      render(
        <AuthProvider>
          <I18nProvider>
            <MetricsDashboard sessionId="sess-1" />
          </I18nProvider>
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByText('Métriques')).toBeInTheDocument()
        expect(screen.getByText('Par agent')).toBeInTheDocument()
        expect(screen.getByText('Exporter en CSV')).toBeInTheDocument()
      })

      await waitFor(() => {
        expect(screen.getByText('Total')).toBeInTheDocument()
      })

      const inputTokenLabels = screen.getAllByText("Jetons d'entrée")
      expect(inputTokenLabels.length).toBeGreaterThan(0)
      const outputTokenLabels = screen.getAllByText('Jetons de sortie')
      expect(outputTokenLabels.length).toBeGreaterThan(0)
      const llmCallLabels = screen.getAllByText('Appels LLM')
      expect(llmCallLabels.length).toBeGreaterThan(0)
    })
  })
})
