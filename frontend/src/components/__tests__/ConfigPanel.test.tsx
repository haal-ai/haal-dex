import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { I18nProvider, resetI18nInstance } from '../../providers/I18nProvider'
import { AuthProvider } from '../../hooks/useAuth'
import { ConfigPanel } from '../ConfigPanel'

// --- fetch mock ---
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

const MOCK_PIPELINES = [
  {
    name: 'pipeline-a',
    config: {
      name: 'pipeline-a',
      agents: [
        {
          name: 'agent-1',
          model: 'bedrock/claude-3',
          provider_config: {
            provider_type: 'bedrock',
            model_id: 'claude-3',
            temperature: 0.7,
            max_tokens: 2048,
          },
          description: 'First agent',
          faiss_indexes: [0],
          tools: ['read', 'write'],
        },
      ],
      output: { template: 'tpl-1', formats: ['pdf'] },
      execution_timeout: 600,
    },
  },
  {
    name: 'pipeline-b',
    config: {
      name: 'pipeline-b',
      agents: [],
      output: { template: 'tpl-2', formats: ['pdf'] },
      execution_timeout: 300,
    },
  },
]

function setupAdminFetch(options?: { pipelines?: typeof MOCK_PIPELINES }) {
  const { pipelines = MOCK_PIPELINES } = options ?? {}

  mockFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    // Auth: /api/auth/me — return admin user
    if (typeof url === 'string' && url.includes('/api/auth/me')) {
      return {
        ok: true,
        json: async () => ({ user_id: 'u1', username: 'admin', roles: ['admin'] }),
      }
    }
    // GET /api/config/pipelines
    if (
      typeof url === 'string' &&
      url.includes('/api/config/pipelines') &&
      (!init || init.method === undefined || init.method === 'GET')
    ) {
      return { ok: true, json: async () => ({ pipelines }) }
    }
    // POST /api/config/pipelines
    if (
      typeof url === 'string' &&
      url.includes('/api/config/pipelines') &&
      init?.method === 'POST'
    ) {
      return { ok: true, json: async () => ({ name: 'new', config: {} }) }
    }
    // PUT /api/config/pipelines/:name
    if (
      typeof url === 'string' &&
      url.includes('/api/config/pipelines/') &&
      init?.method === 'PUT'
    ) {
      return { ok: true, json: async () => ({ name: 'updated', config: {} }) }
    }
    // DELETE /api/config/pipelines/:name
    if (
      typeof url === 'string' &&
      url.includes('/api/config/pipelines/') &&
      init?.method === 'DELETE'
    ) {
      return { ok: true }
    }
    return { ok: false, json: async () => ({}) }
  })
}

function setupNonAdminFetch() {
  mockFetch.mockImplementation(async (url: string) => {
    if (typeof url === 'string' && url.includes('/api/auth/me')) {
      return {
        ok: true,
        json: async () => ({ user_id: 'u2', username: 'viewer', roles: ['user'] }),
      }
    }
    return { ok: false, json: async () => ({}) }
  })
}

function setupValidationErrorFetch() {
  mockFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    if (typeof url === 'string' && url.includes('/api/auth/me')) {
      return {
        ok: true,
        json: async () => ({ user_id: 'u1', username: 'admin', roles: ['admin'] }),
      }
    }
    if (
      typeof url === 'string' &&
      url.includes('/api/config/pipelines') &&
      (!init || !init.method || init.method === 'GET')
    ) {
      return { ok: true, json: async () => ({ pipelines: [] }) }
    }
    if (
      typeof url === 'string' &&
      url.includes('/api/config/pipelines') &&
      init?.method === 'POST'
    ) {
      return {
        ok: false,
        json: async () => ({
          detail: { validation_errors: ['name is required', 'agents cannot be empty'] },
        }),
      }
    }
    return { ok: false, json: async () => ({}) }
  })
}

function renderConfigPanel() {
  return render(
    <AuthProvider>
      <I18nProvider>
        <ConfigPanel />
      </I18nProvider>
    </AuthProvider>
  )
}

describe('ConfigPanel', () => {
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

  it('renders config panel container', async () => {
    setupAdminFetch()
    localStorage.setItem('intent-auth-token', 'test-token')
    renderConfigPanel()

    await waitFor(() => {
      expect(screen.getByTestId('config-panel')).toBeInTheDocument()
    })
  })

  it('fetches and displays pipeline configs list', async () => {
    setupAdminFetch()
    localStorage.setItem('intent-auth-token', 'test-token')
    renderConfigPanel()

    await waitFor(() => {
      const items = screen.getAllByTestId('config-item')
      expect(items).toHaveLength(2)
    })

    expect(screen.getByText('pipeline-a')).toBeInTheDocument()
    expect(screen.getByText('pipeline-b')).toBeInTheDocument()
  })

  it('shows create button', async () => {
    setupAdminFetch()
    localStorage.setItem('intent-auth-token', 'test-token')
    renderConfigPanel()

    await waitFor(() => {
      expect(screen.getByTestId('config-create')).toBeInTheDocument()
      expect(screen.getByText('Create New')).toBeInTheDocument()
    })
  })

  it('shows edit and delete buttons per config', async () => {
    setupAdminFetch()
    localStorage.setItem('intent-auth-token', 'test-token')
    renderConfigPanel()

    await waitFor(() => {
      expect(screen.getByTestId('config-edit-pipeline-a')).toBeInTheDocument()
      expect(screen.getByTestId('config-delete-pipeline-a')).toBeInTheDocument()
      expect(screen.getByTestId('config-edit-pipeline-b')).toBeInTheDocument()
      expect(screen.getByTestId('config-delete-pipeline-b')).toBeInTheDocument()
    })
  })

  it('shows config form when create is clicked', async () => {
    setupAdminFetch()
    localStorage.setItem('intent-auth-token', 'test-token')
    renderConfigPanel()
    const user = userEvent.setup()

    await waitFor(() => {
      expect(screen.getByTestId('config-create')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('config-create'))

    await waitFor(() => {
      expect(screen.getByTestId('config-form')).toBeInTheDocument()
      expect(screen.getByTestId('config-name')).toBeInTheDocument()
      expect(screen.getByTestId('config-save')).toBeInTheDocument()
      expect(screen.getByTestId('config-cancel')).toBeInTheDocument()
    })
  })

  it('shows config form when edit is clicked', async () => {
    setupAdminFetch()
    localStorage.setItem('intent-auth-token', 'test-token')
    renderConfigPanel()
    const user = userEvent.setup()

    await waitFor(() => {
      expect(screen.getByTestId('config-edit-pipeline-a')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('config-edit-pipeline-a'))

    await waitFor(() => {
      expect(screen.getByTestId('config-form')).toBeInTheDocument()
      expect(screen.getByTestId('config-name')).toHaveValue('pipeline-a')
    })
  })

  it('shows validation errors from backend', async () => {
    setupValidationErrorFetch()
    localStorage.setItem('intent-auth-token', 'test-token')
    renderConfigPanel()
    const user = userEvent.setup()

    await waitFor(() => {
      expect(screen.getByTestId('config-create')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('config-create'))

    await waitFor(() => {
      expect(screen.getByTestId('config-form')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('config-save'))

    await waitFor(() => {
      expect(screen.getByTestId('config-validation-error')).toBeInTheDocument()
      expect(screen.getByTestId('config-validation-error').textContent).toContain(
        'name is required'
      )
    })
  })

  it('uses i18n translations', async () => {
    setupAdminFetch()
    localStorage.setItem('intent-auth-token', 'test-token')
    renderConfigPanel()

    await waitFor(() => {
      expect(screen.getByText('Configuration')).toBeInTheDocument()
      expect(screen.getByText('Create New')).toBeInTheDocument()
    })

    // Check edit/delete button labels
    await waitFor(() => {
      const editButtons = screen.getAllByText('Edit')
      const deleteButtons = screen.getAllByText('Delete')
      expect(editButtons.length).toBeGreaterThan(0)
      expect(deleteButtons.length).toBeGreaterThan(0)
    })
  })

  it('renders French translations when language is FR', async () => {
    localStorage.setItem('intent-language', 'fr')
    resetI18nInstance()
    setupAdminFetch()
    localStorage.setItem('intent-auth-token', 'test-token')
    renderConfigPanel()

    await waitFor(() => {
      expect(screen.getByText('Configuration')).toBeInTheDocument()
      expect(screen.getByText('Créer')).toBeInTheDocument()
    })

    await waitFor(() => {
      const editButtons = screen.getAllByText('Modifier')
      const deleteButtons = screen.getAllByText('Supprimer')
      expect(editButtons.length).toBeGreaterThan(0)
      expect(deleteButtons.length).toBeGreaterThan(0)
    })
  })

  it('shows unauthorized message for non-admin users', async () => {
    setupNonAdminFetch()
    localStorage.setItem('intent-auth-token', 'test-token')
    renderConfigPanel()

    await waitFor(() => {
      expect(screen.getByTestId('config-unauthorized')).toBeInTheDocument()
      expect(screen.getByText('Access denied')).toBeInTheDocument()
    })
  })

  it('calls DELETE endpoint when delete button is clicked', async () => {
    setupAdminFetch()
    localStorage.setItem('intent-auth-token', 'test-token')
    renderConfigPanel()
    const user = userEvent.setup()

    await waitFor(() => {
      expect(screen.getByTestId('config-delete-pipeline-a')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('config-delete-pipeline-a'))

    await waitFor(() => {
      const deleteCalls = mockFetch.mock.calls.filter(
        (call: unknown[]) =>
          typeof call[0] === 'string' &&
          (call[0] as string).includes('/api/config/pipelines/pipeline-a') &&
          (call[1] as RequestInit)?.method === 'DELETE'
      )
      expect(deleteCalls.length).toBe(1)
    })
  })

  it('cancels editing and returns to list', async () => {
    setupAdminFetch()
    localStorage.setItem('intent-auth-token', 'test-token')
    renderConfigPanel()
    const user = userEvent.setup()

    await waitFor(() => {
      expect(screen.getByTestId('config-create')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('config-create'))

    await waitFor(() => {
      expect(screen.getByTestId('config-form')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('config-cancel'))

    await waitFor(() => {
      expect(screen.getByTestId('config-list')).toBeInTheDocument()
      expect(screen.queryByTestId('config-form')).not.toBeInTheDocument()
    })
  })
})
