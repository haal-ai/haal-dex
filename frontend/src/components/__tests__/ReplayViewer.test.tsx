import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { I18nProvider, resetI18nInstance } from '../../providers/I18nProvider'
import { AuthProvider } from '../../hooks/useAuth'
import { ReplayViewer } from '../ReplayViewer'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

const MOCK_REPLAY = {
  session_id: 'sess-1',
  user_id: 'user-1',
  created_at: '2025-01-01T00:00:00Z',
  completed_at: '2025-01-01T00:05:00Z',
  steps: [
    {
      step_number: 1,
      agent_id: 'agent-1',
      agent_name: 'Context Analyzer',
      status: 'completed',
      timestamp: '2025-01-01T00:01:00Z',
      input_data: { text: 'hello' },
      prompts_sent: ['Analyze the context'],
      llm_responses: ['Context analyzed successfully'],
      llm_provider: 'bedrock',
      llm_model: 'claude-3-sonnet',
      decisions: ['proceed'],
      output_data: { result: 'analyzed' },
      error: null,
    },
    {
      step_number: 2,
      agent_id: 'agent-2',
      agent_name: 'Content Generator',
      status: 'completed',
      timestamp: '2025-01-01T00:03:00Z',
      input_data: { result: 'analyzed' },
      prompts_sent: ['Generate content'],
      llm_responses: ['Content generated'],
      llm_provider: 'openai',
      llm_model: 'gpt-4',
      decisions: ['finalize'],
      output_data: { content: 'final output' },
      error: null,
    },
  ],
  timeline: [
    { step_number: 1, agent_id: 'agent-1', agent_name: 'Context Analyzer', status: 'completed', timestamp: '2025-01-01T00:01:00Z' },
    { step_number: 2, agent_id: 'agent-2', agent_name: 'Content Generator', status: 'completed', timestamp: '2025-01-01T00:03:00Z' },
  ],
}

function setupFetch(options?: { replayData?: typeof MOCK_REPLAY | null; replayOk?: boolean }) {
  const { replayData = MOCK_REPLAY, replayOk = true } = options ?? {}

  mockFetch.mockImplementation(async (url: string) => {
    if (typeof url === 'string' && url.includes('/api/auth/me')) {
      return {
        ok: true,
        json: async () => ({ user_id: 'u1', username: 'testuser', roles: ['user'] }),
      }
    }
    if (typeof url === 'string' && url.includes('/api/replay/')) {
      return {
        ok: replayOk,
        json: async () => replayData,
      }
    }
    return { ok: false, json: async () => ({}) }
  })
}

function renderViewer(sessionId = 'sess-1') {
  setupFetch()
  localStorage.setItem('intent-auth-token', 'test-token')

  return render(
    <AuthProvider>
      <I18nProvider>
        <ReplayViewer sessionId={sessionId} />
      </I18nProvider>
    </AuthProvider>
  )
}

describe('ReplayViewer', () => {
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

  it('renders replay viewer container', async () => {
    renderViewer()
    await waitFor(() => {
      expect(screen.getByTestId('replay-viewer')).toBeInTheDocument()
    })
  })

  it('fetches and displays replay timeline', async () => {
    renderViewer()

    await waitFor(() => {
      expect(screen.getByTestId('replay-timeline')).toBeInTheDocument()
    })

    expect(screen.getByTestId('timeline-step-1')).toBeInTheDocument()
    expect(screen.getByTestId('timeline-step-2')).toBeInTheDocument()
    expect(screen.getByTestId('timeline-step-1')).toHaveTextContent('Step 1')
    expect(screen.getByTestId('timeline-step-2')).toHaveTextContent('Step 2')
  })

  it('shows step details (input, output, prompts, responses)', async () => {
    renderViewer()

    await waitFor(() => {
      expect(screen.getByTestId('step-details')).toBeInTheDocument()
    })

    // Step 1 is shown by default
    expect(screen.getByTestId('step-input')).toBeInTheDocument()
    expect(screen.getByTestId('step-output')).toBeInTheDocument()
    expect(screen.getByTestId('step-prompts')).toBeInTheDocument()
    expect(screen.getByTestId('step-responses')).toBeInTheDocument()

    // Verify content from step 1
    expect(screen.getByTestId('step-input')).toHaveTextContent('hello')
    expect(screen.getByTestId('step-output')).toHaveTextContent('analyzed')
    expect(screen.getByTestId('step-prompts')).toHaveTextContent('Analyze the context')
    expect(screen.getByTestId('step-responses')).toHaveTextContent('Context analyzed successfully')
  })

  it('Previous/Next navigation works', async () => {
    renderViewer()
    const user = userEvent.setup()

    await waitFor(() => {
      expect(screen.getByTestId('replay-navigation')).toBeInTheDocument()
    })

    // Initially on step 1, Previous should be disabled
    expect(screen.getByTestId('replay-previous')).toBeDisabled()
    expect(screen.getByTestId('replay-next')).toBeEnabled()

    // Click Next to go to step 2
    await user.click(screen.getByTestId('replay-next'))

    await waitFor(() => {
      expect(screen.getByTestId('step-input')).toHaveTextContent('analyzed')
      expect(screen.getByTestId('step-output')).toHaveTextContent('final output')
      expect(screen.getByTestId('step-prompts')).toHaveTextContent('Generate content')
      expect(screen.getByTestId('step-responses')).toHaveTextContent('Content generated')
    })

    // Now on step 2, Next should be disabled
    expect(screen.getByTestId('replay-next')).toBeDisabled()
    expect(screen.getByTestId('replay-previous')).toBeEnabled()

    // Click Previous to go back to step 1
    await user.click(screen.getByTestId('replay-previous'))

    await waitFor(() => {
      expect(screen.getByTestId('step-input')).toHaveTextContent('hello')
    })
  })

  it('highlights current step in the timeline', async () => {
    renderViewer()
    const user = userEvent.setup()

    await waitFor(() => {
      expect(screen.getByTestId('timeline-step-1')).toBeInTheDocument()
    })

    // Step 1 should be highlighted (has blue bg)
    expect(screen.getByTestId('timeline-step-1').className).toContain('bg-blue-600')
    expect(screen.getByTestId('timeline-step-2').className).not.toContain('bg-blue-600')

    // Navigate to step 2
    await user.click(screen.getByTestId('replay-next'))

    await waitFor(() => {
      expect(screen.getByTestId('timeline-step-2').className).toContain('bg-blue-600')
      expect(screen.getByTestId('timeline-step-1').className).not.toContain('bg-blue-600')
    })
  })

  it('clicking timeline step navigates directly', async () => {
    renderViewer()
    const user = userEvent.setup()

    await waitFor(() => {
      expect(screen.getByTestId('timeline-step-2')).toBeInTheDocument()
    })

    // Click step 2 directly in the timeline
    await user.click(screen.getByTestId('timeline-step-2'))

    await waitFor(() => {
      expect(screen.getByTestId('step-input')).toHaveTextContent('analyzed')
      expect(screen.getByTestId('timeline-step-2').className).toContain('bg-blue-600')
    })
  })

  describe('uses i18n translations', () => {
    it('renders English translations', async () => {
      renderViewer()

      await waitFor(() => {
        expect(screen.getByText('Replay')).toBeInTheDocument()
        expect(screen.getByText('Timeline')).toBeInTheDocument()
      })

      expect(screen.getByTestId('replay-previous')).toHaveTextContent('Previous')
      expect(screen.getByTestId('replay-next')).toHaveTextContent('Next')

      // Section labels
      expect(screen.getByTestId('step-input')).toHaveTextContent('Input')
      expect(screen.getByTestId('step-output')).toHaveTextContent('Output')
      expect(screen.getByTestId('step-prompts')).toHaveTextContent('Prompts')
      expect(screen.getByTestId('step-responses')).toHaveTextContent('Responses')
    })

    it('renders French translations when language is FR', async () => {
      localStorage.setItem('intent-language', 'fr')
      resetI18nInstance()
      setupFetch()
      localStorage.setItem('intent-auth-token', 'test-token')

      render(
        <AuthProvider>
          <I18nProvider>
            <ReplayViewer sessionId="sess-1" />
          </I18nProvider>
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByText('Relecture')).toBeInTheDocument()
        expect(screen.getByText('Chronologie')).toBeInTheDocument()
      })

      expect(screen.getByTestId('replay-previous')).toHaveTextContent('Précédent')
      expect(screen.getByTestId('replay-next')).toHaveTextContent('Suivant')

      expect(screen.getByTestId('step-input')).toHaveTextContent('Entrée')
      expect(screen.getByTestId('step-output')).toHaveTextContent('Sortie')
      expect(screen.getByTestId('step-prompts')).toHaveTextContent('Invites')
      expect(screen.getByTestId('step-responses')).toHaveTextContent('Réponses')
    })
  })
})
