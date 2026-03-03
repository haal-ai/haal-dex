import { render, screen, waitFor, cleanup, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { I18nProvider, resetI18nInstance } from '../../providers/I18nProvider'
import { AuthProvider } from '../../hooks/useAuth'
import { DropZone } from '../DropZone'

// Mock fetch globally
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function createFile(name: string, size = 1024, type = ''): File {
  const buffer = new ArrayBuffer(size)
  return new File([buffer], name, { type })
}

function createDtWithFiles(files: File[]) {
  return {
    dataTransfer: {
      files,
      items: files.map((file) => ({
        kind: 'file',
        type: file.type,
        getAsFile: () => file,
      })),
      types: ['Files'],
    },
  }
}

function renderDropZone() {
  // Mock auth: provide a logged-in user by mocking the /api/auth/me endpoint
  mockFetch.mockImplementation(async (url: string, options?: RequestInit) => {
    if (typeof url === 'string' && url.includes('/api/auth/me')) {
      return {
        ok: true,
        json: async () => ({ user_id: 'u1', username: 'testuser', roles: ['user'] }),
      }
    }
    if (typeof url === 'string' && url.includes('/api/auth/login')) {
      return {
        ok: true,
        json: async () => ({ access_token: 'test-token', user_id: 'u1', roles: ['user'] }),
      }
    }
    if (typeof url === 'string' && url.includes('/api/files/upload')) {
      const method = options?.method ?? 'GET'
      if (method === 'POST') {
        return {
          ok: true,
          json: async () => ({
            files: [{ id: 'f1', original_name: 'test.pdf', format: 'pdf', size_bytes: 1024 }],
            session_id: 's1',
          }),
        }
      }
    }
    return { ok: false, json: async () => ({}) }
  })

  // Set a token in localStorage so AuthProvider picks it up
  localStorage.setItem('intent-auth-token', 'test-token')

  return render(
    <AuthProvider>
      <I18nProvider>
        <DropZone />
      </I18nProvider>
    </AuthProvider>
  )
}

async function dropFiles(files: File[]) {
  const input = screen.getByTestId('dropzone-input') as HTMLInputElement
  await userEvent.upload(input, files)
}

async function dropFilesViaDrag(files: File[]) {
  const dropzone = screen.getByTestId('dropzone')
  const dt = createDtWithFiles(files)
  fireEvent.drop(dropzone, dt)
}

describe('DropZone', () => {
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

  describe('renders drop zone area', () => {
    it('renders the drop zone with correct text', async () => {
      renderDropZone()
      await waitFor(() => {
        expect(screen.getByTestId('dropzone')).toBeInTheDocument()
      })
      expect(screen.getByText('Drag and drop files here, or click to browse')).toBeInTheDocument()
      expect(screen.getByText('Supported formats: PPTX, DOCX, PDF, TXT, HTML, MD')).toBeInTheDocument()
    })

    it('renders the file upload title', async () => {
      renderDropZone()
      await waitFor(() => {
        expect(screen.getByText('File Upload')).toBeInTheDocument()
      })
    })
  })

  describe('accepts supported file formats', () => {
    it.each([
      ['test.pptx', 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'PPTX'],
      ['test.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'DOCX'],
      ['test.pdf', 'application/pdf', 'PDF'],
      ['test.txt', 'text/plain', 'TXT'],
      ['test.html', 'text/html', 'HTML'],
      ['test.md', 'text/markdown', 'MD'],
    ])('accepts %s files', async (name, type, expectedFormat) => {
      renderDropZone()
      await waitFor(() => {
        expect(screen.getByTestId('dropzone')).toBeInTheDocument()
      })

      const file = createFile(name, 2048, type)
      await dropFiles([file])

      await waitFor(() => {
        expect(screen.getByTestId('file-preview-list')).toBeInTheDocument()
      })

      const previewItems = screen.getAllByTestId('file-preview-item')
      expect(previewItems.length).toBe(1)
      expect(screen.getByText(name)).toBeInTheDocument()
      expect(screen.getByText(new RegExp(`Format: ${expectedFormat}`))).toBeInTheDocument()
    })
  })

  describe('rejects unsupported file formats with error', () => {
    it('shows error for unsupported .exe file', async () => {
      renderDropZone()
      await waitFor(() => {
        expect(screen.getByTestId('dropzone')).toBeInTheDocument()
      })

      const file = createFile('malware.exe', 1024, 'application/x-msdownload')
      await dropFilesViaDrag([file])

      await waitFor(() => {
        expect(screen.getByTestId('dropzone-errors')).toBeInTheDocument()
      })

      expect(screen.getByText(/Unsupported format: exe/)).toBeInTheDocument()
    })

    it('shows error for unsupported .jpg file', async () => {
      renderDropZone()
      await waitFor(() => {
        expect(screen.getByTestId('dropzone')).toBeInTheDocument()
      })

      const file = createFile('photo.jpg', 1024, 'image/jpeg')
      await dropFilesViaDrag([file])

      await waitFor(() => {
        expect(screen.getByTestId('dropzone-errors')).toBeInTheDocument()
      })

      expect(screen.getByText(/Unsupported format: jpg/)).toBeInTheDocument()
    })
  })

  describe('shows file preview with format and size', () => {
    it('displays file name, format, and size in preview', async () => {
      renderDropZone()
      await waitFor(() => {
        expect(screen.getByTestId('dropzone')).toBeInTheDocument()
      })

      const file = createFile('report.pdf', 5120, 'application/pdf')
      await dropFiles([file])

      await waitFor(() => {
        expect(screen.getByTestId('file-preview-list')).toBeInTheDocument()
      })

      expect(screen.getByText('report.pdf')).toBeInTheDocument()
      expect(screen.getByText(/Format: PDF/)).toBeInTheDocument()
      expect(screen.getByText(/Size: 5\.0 KB/)).toBeInTheDocument()
    })

    it('shows preview header', async () => {
      renderDropZone()
      await waitFor(() => {
        expect(screen.getByTestId('dropzone')).toBeInTheDocument()
      })

      const file = createFile('doc.txt', 100, 'text/plain')
      await dropFiles([file])

      await waitFor(() => {
        expect(screen.getByText('File Preview')).toBeInTheDocument()
      })
    })
  })

  describe('remove button removes file from list', () => {
    it('removes a file when remove button is clicked', async () => {
      renderDropZone()
      await waitFor(() => {
        expect(screen.getByTestId('dropzone')).toBeInTheDocument()
      })

      const file = createFile('doc.pdf', 1024, 'application/pdf')
      await dropFiles([file])

      await waitFor(() => {
        expect(screen.getByTestId('file-preview-list')).toBeInTheDocument()
      })

      expect(screen.getAllByTestId('file-preview-item').length).toBe(1)

      const user = userEvent.setup()
      await user.click(screen.getByTestId('remove-file-button'))

      expect(screen.queryByTestId('file-preview-list')).not.toBeInTheDocument()
    })

    it('removes only the targeted file from multiple files', async () => {
      renderDropZone()
      await waitFor(() => {
        expect(screen.getByTestId('dropzone')).toBeInTheDocument()
      })

      const file1 = createFile('a.pdf', 1024, 'application/pdf')
      const file2 = createFile('b.txt', 512, 'text/plain')
      await dropFiles([file1, file2])

      await waitFor(() => {
        expect(screen.getAllByTestId('file-preview-item').length).toBe(2)
      })

      const user = userEvent.setup()
      const removeButtons = screen.getAllByTestId('remove-file-button')
      await user.click(removeButtons[0])

      expect(screen.getAllByTestId('file-preview-item').length).toBe(1)
      expect(screen.getByText('b.txt')).toBeInTheDocument()
    })
  })

  describe('calls upload API with auth token', () => {
    it('sends files to POST /api/files/upload with Authorization header', async () => {
      renderDropZone()
      await waitFor(() => {
        expect(screen.getByTestId('dropzone')).toBeInTheDocument()
      })

      const file = createFile('report.pdf', 1024, 'application/pdf')
      await dropFiles([file])

      await waitFor(() => {
        expect(screen.getByTestId('upload-button')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      await user.click(screen.getByTestId('upload-button'))

      await waitFor(() => {
        const uploadCalls = mockFetch.mock.calls.filter(
          (call: unknown[]) => typeof call[0] === 'string' && call[0].includes('/api/files/upload')
        )
        expect(uploadCalls.length).toBe(1)

        const [url, options] = uploadCalls[0]
        expect(url).toBe('/api/files/upload')
        expect(options.method).toBe('POST')
        expect(options.headers.Authorization).toBe('Bearer test-token')
        expect(options.body).toBeInstanceOf(FormData)
      })
    })

    it('clears files after successful upload', async () => {
      renderDropZone()
      await waitFor(() => {
        expect(screen.getByTestId('dropzone')).toBeInTheDocument()
      })

      const file = createFile('report.pdf', 1024, 'application/pdf')
      await dropFiles([file])

      await waitFor(() => {
        expect(screen.getByTestId('upload-button')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      await user.click(screen.getByTestId('upload-button'))

      await waitFor(() => {
        expect(screen.queryByTestId('file-preview-list')).not.toBeInTheDocument()
      })
    })

    it('shows upload error when API fails', async () => {
      // Override fetch to fail on upload
      mockFetch.mockImplementation(async (url: string) => {
        if (typeof url === 'string' && url.includes('/api/auth/me')) {
          return {
            ok: true,
            json: async () => ({ user_id: 'u1', username: 'testuser', roles: ['user'] }),
          }
        }
        if (typeof url === 'string' && url.includes('/api/files/upload')) {
          return {
            ok: false,
            statusText: 'Internal Server Error',
            json: async () => ({ error: { message: 'Disk full' } }),
          }
        }
        return { ok: false, json: async () => ({}) }
      })

      localStorage.setItem('intent-auth-token', 'test-token')

      render(
        <AuthProvider>
          <I18nProvider>
            <DropZone />
          </I18nProvider>
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('dropzone')).toBeInTheDocument()
      })

      const file = createFile('report.pdf', 1024, 'application/pdf')
      await dropFiles([file])

      await waitFor(() => {
        expect(screen.getByTestId('upload-button')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      await user.click(screen.getByTestId('upload-button'))

      await waitFor(() => {
        expect(screen.getByTestId('upload-error')).toBeInTheDocument()
        expect(screen.getByText(/Upload failed: Disk full/)).toBeInTheDocument()
      })
    })
  })
})
