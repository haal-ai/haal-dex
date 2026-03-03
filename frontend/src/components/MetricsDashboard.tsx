import { useState, useEffect, useCallback } from 'react'
import { useLanguage } from '../providers/I18nProvider'
import { useAuth } from '../hooks/useAuth'
import { cn } from '../lib/utils'
import type { SessionMetrics } from '../types/models'

export interface MetricsDashboardProps {
  sessionId: string
}

async function fetchMetrics(sessionId: string, token: string): Promise<SessionMetrics | null> {
  const res = await fetch(`/api/metrics/${sessionId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return null
  return res.json()
}

async function downloadCsv(sessionId: string, token: string): Promise<void> {
  const res = await fetch(`/api/metrics/${sessionId}/csv`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return

  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `metrics-${sessionId}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function MetricsDashboard({ sessionId }: MetricsDashboardProps) {
  const { t } = useLanguage()
  const { user } = useAuth()
  const [metrics, setMetrics] = useState<SessionMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    if (!user?.token || !sessionId) {
      setLoading(false)
      return
    }
    setLoading(true)
    fetchMetrics(sessionId, user.token)
      .then(setMetrics)
      .finally(() => setLoading(false))
  }, [sessionId, user?.token])

  const totals = metrics
    ? metrics.agent_metrics.reduce(
        (acc, m) => ({
          input_tokens: acc.input_tokens + m.input_tokens,
          output_tokens: acc.output_tokens + m.output_tokens,
          llm_call_count: acc.llm_call_count + m.llm_call_count,
        }),
        { input_tokens: 0, output_tokens: 0, llm_call_count: 0 }
      )
    : null

  const handleExportCsv = useCallback(async () => {
    if (!user?.token || !sessionId) return
    setExporting(true)
    try {
      await downloadCsv(sessionId, user.token)
    } finally {
      setExporting(false)
    }
  }, [sessionId, user?.token])

  return (
    <div data-testid="metrics-dashboard" className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 border-b dark:border-gray-700">
        <h2 className="text-lg font-semibold">{t('metrics.title')}</h2>
        <button
          data-testid="export-csv"
          onClick={handleExportCsv}
          disabled={exporting || !metrics}
          className={cn(
            'px-3 py-1.5 rounded-md text-white text-sm font-medium',
            exporting || !metrics
              ? 'bg-gray-400 cursor-not-allowed'
              : 'bg-blue-600 hover:bg-blue-700'
          )}
          type="button"
        >
          {t('metrics.exportCsv')}
        </button>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-gray-500">
          <span data-testid="metrics-loading">…</span>
        </div>
      ) : metrics && metrics.agent_metrics.length > 0 ? (
        <div className="flex-1 overflow-y-auto">
          {/* Per-agent metrics */}
          <div data-testid="per-agent-metrics" className="px-4 py-3">
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {t('metrics.perAgent')}
            </h3>
            <div className="space-y-2">
              {metrics.agent_metrics.map((agent) => (
                <div
                  key={agent.agent_id}
                  data-testid={`agent-metrics-${agent.agent_id}`}
                  className="rounded-md border dark:border-gray-700 p-3"
                >
                  <div className="font-medium text-sm mb-1">{agent.agent_name}</div>
                  <div className="grid grid-cols-3 gap-2 text-xs text-gray-600 dark:text-gray-400">
                    <div>
                      <span className="block text-gray-500 dark:text-gray-500">
                        {t('metrics.inputTokens')}
                      </span>
                      <span data-testid={`input-tokens-${agent.agent_id}`} className="font-mono">
                        {agent.input_tokens.toLocaleString()}
                      </span>
                    </div>
                    <div>
                      <span className="block text-gray-500 dark:text-gray-500">
                        {t('metrics.outputTokens')}
                      </span>
                      <span data-testid={`output-tokens-${agent.agent_id}`} className="font-mono">
                        {agent.output_tokens.toLocaleString()}
                      </span>
                    </div>
                    <div>
                      <span className="block text-gray-500 dark:text-gray-500">
                        {t('metrics.llmCalls')}
                      </span>
                      <span data-testid={`llm-calls-${agent.agent_id}`} className="font-mono">
                        {agent.llm_call_count.toLocaleString()}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Total metrics */}
          {totals && (
            <div
              data-testid="total-metrics"
              className="px-4 py-3 border-t dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50"
            >
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {t('metrics.total')}
              </h3>
              <div className="grid grid-cols-3 gap-2 text-xs text-gray-600 dark:text-gray-400">
                <div>
                  <span className="block text-gray-500 dark:text-gray-500">
                    {t('metrics.inputTokens')}
                  </span>
                  <span data-testid="total-input-tokens" className="font-mono">
                    {totals.input_tokens.toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="block text-gray-500 dark:text-gray-500">
                    {t('metrics.outputTokens')}
                  </span>
                  <span data-testid="total-output-tokens" className="font-mono">
                    {totals.output_tokens.toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="block text-gray-500 dark:text-gray-500">
                    {t('metrics.llmCalls')}
                  </span>
                  <span data-testid="total-llm-calls" className="font-mono">
                    {totals.llm_call_count.toLocaleString()}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div
          data-testid="metrics-empty"
          className="flex-1 flex items-center justify-center text-gray-500 dark:text-gray-400"
        >
          {t('metrics.title')}
        </div>
      )}
    </div>
  )
}
