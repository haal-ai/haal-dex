/**
 * Property 2: File preview renders for each dropped file
 * Validates: Requirements 1.3
 *
 * For any list of valid files, UI renders a preview element per file with detected format.
 */
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import * as fc from 'fast-check'
import { I18nProvider, resetI18nInstance } from '../../providers/I18nProvider'
import { AuthProvider } from '../../hooks/useAuth'
import { DropZone } from '../../components/DropZone'

const SUPPORTED_EXTENSIONS = ['pptx', 'docx', 'pdf', 'txt', 'html', 'md'] as const

const MIME_TYPES: Record<string, string> = {
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  pdf: 'application/pdf',
  txt: 'text/plain',
  html: 'text/html',
  md: 'text/markdown',
}

// Mock fetch for auth
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function setupFetchMock() {
  mockFetch.mockImplementation(async (url: string) => {
    if (typeof url === 'string' && url.includes('/api/auth/me')) {
      return {
        ok: true,
        json: async () => ({ user_id: 'u1', username: 'testuser', roles: ['user'] }),
      }
    }
    if (typeof url === 'string' && url.includes('/api/files/upload')) {
      return {
        ok: true,
        json: async () => ({ files: [], session_id: 's1' }),
      }
    }
    return { ok: false, json: async () => ({}) }
  })
}

function createFile(name: string, ext: string): File {
  const fullName = `${name}.${ext}`
  const mime = MIME_TYPES[ext] || ''
  return new File([new ArrayBuffer(1024)], fullName, { type: mime })
}

function renderDropZone() {
  setupFetchMock()
  localStorage.setItem('intent-auth-token', 'test-token')
  return render(
    <AuthProvider>
      <I18nProvider>
        <DropZone />
      </I18nProvider>
    </AuthProvider>
  )
}

// Arbitrary: generate a non-empty array of { name, ext } pairs with supported extensions
const validFileArb = fc.record({
  name: fc.stringMatching(/^[a-zA-Z][a-zA-Z0-9_-]{0,19}$/).filter((s) => s.length > 0),
  ext: fc.constantFrom(...SUPPORTED_EXTENSIONS),
})

const validFileListArb = fc.array(validFileArb, { minLength: 1, maxLength: 6 })

describe('Property 2: File preview renders for each dropped file', () => {
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

  it('renders a preview element per valid file with detected format', async () => {
    await fc.assert(
      fc.asyncProperty(validFileListArb, async (fileSpecs) => {
        cleanup()
        localStorage.clear()
        localStorage.setItem('intent-auth-token', 'test-token')
        vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-US')
        resetI18nInstance()
        mockFetch.mockClear()
        setupFetchMock()

        renderDropZone()

        await waitFor(() => {
          expect(screen.getByTestId('dropzone')).toBeInTheDocument()
        })

        // Create File objects from the generated specs
        const files = fileSpecs.map((spec) => createFile(spec.name, spec.ext))

        // Upload files via the input element
        const input = screen.getByTestId('dropzone-input') as HTMLInputElement
        await userEvent.upload(input, files)

        // Assert: number of preview items equals number of files
        await waitFor(() => {
          expect(screen.getByTestId('file-preview-list')).toBeInTheDocument()
        })

        const previewItems = screen.getAllByTestId('file-preview-item')
        expect(previewItems.length).toBe(fileSpecs.length)

        // Assert: each file's format is displayed
        for (const spec of fileSpecs) {
          const formatRegex = new RegExp(`Format: ${spec.ext.toUpperCase()}`)
          const matches = screen.getAllByText(formatRegex)
          expect(matches.length).toBeGreaterThanOrEqual(1)
        }
      }),
      { numRuns: 15 }
    )
  })
})
