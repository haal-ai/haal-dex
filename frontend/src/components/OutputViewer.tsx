import { useState, useEffect, useCallback } from 'react'
import { useLanguage } from '../providers/I18nProvider'
import { useAuth } from '../hooks/useAuth'
import { cn } from '../lib/utils'
import type { OutputPreview } from '../types/api'

export interface OutputViewerProps {
  sessionId: string
}

const EXPORT_FORMATS = ['pdf', 'docx', 'pptx'] as const
type ExportFormat = (typeof EXPORT_FORMATS)[number]

const FORMAT_LABEL_KEYS: Record<ExportFormat, string> = {
  pdf: 'output.exportPdf',
  docx: 'output.exportDocx',
  pptx: 'output.exportPptx',
}

async function fetchPreview(sessionId: string, token: string): Promise<OutputPreview | null> {
  const res = await fetch(`/api/output/${sessionId}/preview`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return null
  return res.json()
}

async function downloadExport(sessionId: string, format: ExportFormat, token: string): Promise<void> {
  const res = await fetch(`/api/output/${sessionId}/export?format=${format}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return

  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `output.${format}`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function OutputViewer({ sessionId }: OutputViewerProps) {
  const { t } = useLanguage()
  const { user } = useAuth()
  const [preview, setPreview] = useState<OutputPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState<ExportFormat | null>(null)

  useEffect(() => {
    if (!user?.token || !sessionId) {
      setLoading(false)
      return
    }
    setLoading(true)
    fetchPreview(sessionId, user.token)
      .then(setPreview)
      .finally(() => setLoading(false))
  }, [sessionId, user?.token])

  const handleExport = useCallback(
    async (format: ExportFormat) => {
      if (!user?.token || !sessionId) return
      setExporting(format)
      try {
        await downloadExport(sessionId, format, user.token)
      } finally {
        setExporting(null)
      }
    },
    [sessionId, user?.token]
  )

  return (
    <div data-testid="output-viewer" className="flex flex-col h-full">
      <h2 className="text-lg font-semibold px-4 py-2 border-b dark:border-gray-700">
        {t('output.title')}
      </h2>

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-gray-500">
          <span data-testid="output-loading">…</span>
        </div>
      ) : preview ? (
        <>
          <div className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400" data-testid="output-template-name">
            {t('output.template', { name: preview.template_name })}
          </div>

          <div
            data-testid="output-preview"
            className="flex-1 overflow-y-auto px-4 py-3 prose dark:prose-invert max-w-none"
            dangerouslySetInnerHTML={{ __html: preview.content_html }}
          />

          <div className="border-t dark:border-gray-700 px-4 py-3 flex gap-2">
            {EXPORT_FORMATS.map((format) => (
              <button
                key={format}
                data-testid={`export-${format}`}
                onClick={() => handleExport(format)}
                disabled={exporting !== null}
                className={cn(
                  'px-4 py-2 rounded-md text-white text-sm font-medium',
                  exporting === format
                    ? 'bg-gray-400 cursor-not-allowed'
                    : 'bg-blue-600 hover:bg-blue-700'
                )}
                type="button"
              >
                {t(FORMAT_LABEL_KEYS[format])}
              </button>
            ))}
          </div>
        </>
      ) : (
        <div
          data-testid="output-no-output"
          className="flex-1 flex items-center justify-center text-gray-500 dark:text-gray-400"
        >
          {t('output.noOutput')}
        </div>
      )}
    </div>
  )
}
