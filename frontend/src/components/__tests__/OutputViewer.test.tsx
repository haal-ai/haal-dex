import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { I18nProvider, resetI18nInstance } from '../../providers/I18nProvider'
import { AuthProvider } from '../../hooks/useAuth'
import { OutputViewer } from '../OutputViewer'

// --- fetch mock ---
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

const MOCK_PREVIEW = {
  session_id: 'sess-1',
  template_id: 'tpl-1',
  template_name: 'Report Template',
  format: 'html',
  content_html: '<h1>Generated Report</h1><p>Content here</p>',
  metadata: {
    author: 'testuser',
    date: '2025-01-01',
    version: '1.0',
    classification: 'internal',
  },
}

function setupFetch(options?: { previewData?: typeof MOCK_PREVIEW | null; previewOk?: boolean }) {
  const { previewData = MOCK_PREVIEW, previewOk = true } = options ?? {}

  mockFetch.mockImplementation(async (url: string) => {
    if (typeof url === 'string' && url.includes('/api/auth/me')) {
      return {
        ok: true,
        json: async () => ({ user_id: 'u1', username: 'testuser', roles: ['user'] }),
      }
    }
    if (typeof url === 'string' && url.includes('/api/output/') && url.includes('/preview')) {
      return {
        ok: previewOk,
        json: async () => previewData,
      }
    }
    if (typeof url === 'string' && url.includes('/api/output/') && url.includes('/export')) {
      return {
        ok: true,
        blob: async () => new Blob(['file-content'], { type: 'application/octet-stream' }),
      }
    }
    return { ok: false, json: async () => ({}) }
  })
}

function renderOutputViewer(sessionId = 'sess-1') {
  setupFetch()
  localStorage.setItem('intent-auth-token', 'test-token')

  return render(
    <AuthProvider>
      <I18nProvider>
        <OutputViewer sessionId={sessionId} />
      </I18nProvider>
    </AuthProvider>
  )
}

describe('OutputViewer', () => {
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

  it('renders output viewer container', async () => {
    renderOutputViewer()
    await waitFor(() => {
      expect(screen.getByTestId('output-viewer')).toBeInTheDocument()
    })
  })

  it('renders the output title using i18n', async () => {
    renderOutputViewer()
    await waitFor(() => {
      expect(screen.getByText('Output')).toBeInTheDocument()
    })
  })

  it('fetches and displays preview content', async () => {
    renderOutputViewer()
    await waitFor(() => {
      expect(screen.getByTestId('output-preview')).toBeInTheDocument()
    })
    expect(screen.getByTestId('output-preview').innerHTML).toContain('Generated Report')
  })

  it('shows template name', async () => {
    renderOutputViewer()
    await waitFor(() => {
      expect(screen.getByTestId('output-template-name')).toBeInTheDocument()
      expect(screen.getByText('Template: Report Template')).toBeInTheDocument()
    })
  })

  it('shows export buttons for PDF, DOCX, PPTX', async () => {
    renderOutputViewer()
    await waitFor(() => {
      expect(screen.getByTestId('export-pdf')).toBeInTheDocument()
      expect(screen.getByTestId('export-docx')).toBeInTheDocument()
      expect(screen.getByTestId('export-pptx')).toBeInTheDocument()
    })
    expect(screen.getByText('Export PDF')).toBeInTheDocument()
    expect(screen.getByText('Export DOCX')).toBeInTheDocument()
    expect(screen.getByText('Export PPTX')).toBeInTheDocument()
  })

  it('shows "no output" message when preview is not available', async () => {
    setupFetch({ previewOk: false })
    localStorage.setItem('intent-auth-token', 'test-token')

    render(
      <AuthProvider>
        <I18nProvider>
          <OutputViewer sessionId="sess-empty" />
        </I18nProvider>
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('output-no-output')).toBeInTheDocument()
      expect(screen.getByText('No output available')).toBeInTheDocument()
    })
  })

  it('export button triggers file download', async () => {
    renderOutputViewer()
    const user = userEvent.setup()

    await waitFor(() => {
      expect(screen.getByTestId('export-pdf')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('export-pdf'))

    await waitFor(() => {
      // Verify fetch was called with the export URL
      const exportCalls = mockFetch.mock.calls.filter(
        (call: unknown[]) => typeof call[0] === 'string' && (call[0] as string).includes('/export')
      )
      expect(exportCalls.length).toBeGreaterThan(0)
      expect(exportCalls[0][0]).toContain('format=pdf')
    })
  })

  describe('uses i18n translations', () => {
    it('renders French translations when language is FR', async () => {
      localStorage.setItem('intent-language', 'fr')
      resetI18nInstance()
      setupFetch()
      localStorage.setItem('intent-auth-token', 'test-token')

      render(
        <AuthProvider>
          <I18nProvider>
            <OutputViewer sessionId="sess-1" />
          </I18nProvider>
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByText('Résultat')).toBeInTheDocument()
      })

      await waitFor(() => {
        expect(screen.getByText('Exporter en PDF')).toBeInTheDocument()
        expect(screen.getByText('Exporter en DOCX')).toBeInTheDocument()
        expect(screen.getByText('Exporter en PPTX')).toBeInTheDocument()
        expect(screen.getByText('Modèle : Report Template')).toBeInTheDocument()
      })
    })

    it('shows French "no output" message', async () => {
      localStorage.setItem('intent-language', 'fr')
      resetI18nInstance()
      setupFetch({ previewOk: false })
      localStorage.setItem('intent-auth-token', 'test-token')

      render(
        <AuthProvider>
          <I18nProvider>
            <OutputViewer sessionId="sess-empty" />
          </I18nProvider>
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByText('Aucun résultat disponible')).toBeInTheDocument()
      })
    })
  })
})
