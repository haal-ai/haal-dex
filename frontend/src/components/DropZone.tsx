import { useState, useCallback } from 'react'
import { useDropzone, type FileRejection } from 'react-dropzone'
import { useLanguage } from '../providers/I18nProvider'
import { useAuth } from '../hooks/useAuth'
import { cn } from '../lib/utils'
import type { FileUploadResponse } from '../types/api'

const ACCEPTED_EXTENSIONS: Record<string, string[]> = {
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
  'application/pdf': ['.pdf'],
  'text/plain': ['.txt'],
  'text/html': ['.html'],
  'text/markdown': ['.md'],
}

export interface DroppedFile {
  file: File
  format: string
}

function detectFormat(file: File): string {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  return ext
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const SUPPORTED_FORMATS = new Set(['pptx', 'docx', 'pdf', 'txt', 'html', 'md'])

export interface DropZoneProps {
  onSessionCreated?: (sessionId: string) => void
}

export function DropZone({ onSessionCreated }: DropZoneProps) {
  const { t } = useLanguage()
  const { user } = useAuth()
  const [files, setFiles] = useState<DroppedFile[]>([])
  const [errors, setErrors] = useState<string[]>([])
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const onDrop = useCallback(
    (acceptedFiles: File[], rejectedFiles: FileRejection[]) => {
      const newErrors: string[] = []

      // Check rejected files for unsupported format errors
      for (const rejection of rejectedFiles) {
        const format = detectFormat(rejection.file)
        newErrors.push(t('fileUpload.unsupported', { format }))
      }

      // Also validate accepted files by extension (belt-and-suspenders)
      const validFiles: DroppedFile[] = []
      for (const file of acceptedFiles) {
        const format = detectFormat(file)
        if (SUPPORTED_FORMATS.has(format)) {
          validFiles.push({ file, format })
        } else {
          newErrors.push(t('fileUpload.unsupported', { format }))
        }
      }

      setErrors(newErrors)
      if (validFiles.length > 0) {
        setFiles((prev) => [...prev, ...validFiles])
      }
    },
    [t]
  )

  const removeFile = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }, [])

  const uploadFiles = useCallback(async () => {
    if (files.length === 0 || !user?.token) return

    setUploading(true)
    setUploadError(null)

    const formData = new FormData()
    for (const { file } of files) {
      formData.append('files', file)
    }

    try {
      const res = await fetch('/api/files/upload', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${user.token}`,
        },
        body: formData,
      })

      if (!res.ok) {
        const errorData = await res.json().catch(() => null)
        const reason = errorData?.error?.message ?? res.statusText
        throw new Error(reason)
      }

      const data = await res.json() as FileUploadResponse
      onSessionCreated?.(data.session_id)
      setFiles([])
      setErrors([])
    } catch (err) {
      const reason = err instanceof Error ? err.message : 'Unknown error'
      setUploadError(t('fileUpload.uploadError', { reason }))
    } finally {
      setUploading(false)
    }
  }, [files, user, t, onSessionCreated])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_EXTENSIONS,
  })

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">{t('fileUpload.title')}</h2>

      <div
        {...getRootProps()}
        data-testid="dropzone"
        className={cn(
          'border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors',
          isDragActive
            ? 'border-blue-500 bg-blue-50 dark:bg-blue-950'
            : 'border-gray-300 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500'
        )}
      >
        <input {...getInputProps()} data-testid="dropzone-input" />
        <p className="text-gray-600 dark:text-gray-300">
          {isDragActive ? t('fileUpload.dropzoneActive') : t('fileUpload.dropzone')}
        </p>
        <p className="text-sm text-gray-400 dark:text-gray-500 mt-2">
          {t('fileUpload.supported')}
        </p>
      </div>

      {errors.length > 0 && (
        <div data-testid="dropzone-errors" className="space-y-1">
          {errors.map((error, i) => (
            <p key={i} className="text-sm text-red-500" role="alert">
              {error}
            </p>
          ))}
        </div>
      )}

      {uploadError && (
        <p data-testid="upload-error" className="text-sm text-red-500" role="alert">
          {uploadError}
        </p>
      )}

      {files.length > 0 && (
        <div data-testid="file-preview-list" className="space-y-2">
          <h3 className="text-sm font-medium">{t('fileUpload.preview')}</h3>
          {files.map((droppedFile, index) => (
            <div
              key={`${droppedFile.file.name}-${index}`}
              data-testid="file-preview-item"
              className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-md"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{droppedFile.file.name}</p>
                <p className="text-xs text-gray-500">
                  {t('fileUpload.format', { format: droppedFile.format.toUpperCase() })}
                  {' · '}
                  {t('fileUpload.size', { size: formatFileSize(droppedFile.file.size) })}
                </p>
              </div>
              <button
                data-testid="remove-file-button"
                onClick={() => removeFile(index)}
                className="ml-2 text-sm text-red-500 hover:text-red-700"
                type="button"
              >
                {t('fileUpload.remove')}
              </button>
            </div>
          ))}

          <button
            data-testid="upload-button"
            onClick={uploadFiles}
            disabled={uploading}
            className={cn(
              'px-4 py-2 rounded-md text-white text-sm font-medium',
              uploading
                ? 'bg-gray-400 cursor-not-allowed'
                : 'bg-blue-600 hover:bg-blue-700'
            )}
            type="button"
          >
            {uploading ? '...' : t('fileUpload.title')}
          </button>
        </div>
      )}
    </div>
  )
}
