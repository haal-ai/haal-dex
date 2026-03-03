import { useState, useRef, useEffect, useCallback } from 'react'
import { useLanguage } from '../providers/I18nProvider'
import { useAuth } from '../hooks/useAuth'
import { cn } from '../lib/utils'
import type { AgentStatusData, PipelineCompleteData } from '../types/websocket'
import type { PipelineListResponse, PipelineConfig } from '../types/api'

export interface AgentEntry {
  agent_id: string
  agent_name: string
  step_number: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  error?: string
}

export interface LogEntry {
  timestamp: string
  message: string
}

export interface ExecutionTimelineProps {
  sessionId: string
}

const isObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null

const isAgentStatusData = (v: unknown): v is AgentStatusData => {
  if (!isObject(v)) return false
  return (
    typeof v.agent_id === 'string' &&
    typeof v.agent_name === 'string' &&
    typeof v.step_number === 'number'
  )
}

const extractAgentStatus = (raw: Record<string, unknown>): AgentEntry | null => {
  const nested = (raw as { data?: unknown }).data
  if (isAgentStatusData(nested)) {
    const nestedError = (nested as { error?: unknown }).error
    return {
      agent_id: nested.agent_id,
      agent_name: nested.agent_name,
      step_number: nested.step_number,
      status: 'pending',
      ...(typeof nestedError === 'string' ? { error: nestedError } : {}),
    }
  }

  const agent_id = raw.agent_id
  const step = raw.step
  if (typeof agent_id !== 'string' || typeof step !== 'number') return null

  const error = raw.error
  return {
    agent_id,
    agent_name: agent_id,
    step_number: step,
    status: 'pending',
    ...(typeof error === 'string' ? { error } : {}),
  }
}

const isPipelineCompleteData = (v: unknown): v is PipelineCompleteData => {
  if (!isObject(v)) return false
  return typeof v.status === 'string'
}

function getWsUrl(sessionId: string, token: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/ws/execution/${sessionId}?token=${encodeURIComponent(token)}`
}

const STATUS_ICONS: Record<AgentEntry['status'], string> = {
  pending: '○',
  running: '◉',
  completed: '●',
  failed: '✕',
}

export function ExecutionTimeline({ sessionId }: ExecutionTimelineProps) {
  const { t } = useLanguage()
  const { user } = useAuth()
  const [agents, setAgents] = useState<AgentEntry[]>([])
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [pipelineStatus, setPipelineStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pipelines, setPipelines] = useState<Array<{ name: string; config: PipelineConfig }>>([])
  const [selectedPipeline, setSelectedPipeline] = useState<string>('')
  const [loadingPipelines, setLoadingPipelines] = useState(false)
  const [starting, setStarting] = useState(false)
  const [hasStarted, setHasStarted] = useState(false)
  const errorRef = useRef<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const logsEndRef = useRef<HTMLDivElement>(null)

  const scrollLogsToBottom = useCallback(() => {
    if (logsEndRef.current && typeof logsEndRef.current.scrollIntoView === 'function') {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [])

  useEffect(() => {
    scrollLogsToBottom()
  }, [logs, scrollLogsToBottom])

  useEffect(() => {
    errorRef.current = error
  }, [error])

  useEffect(() => {
    if (!user?.token) return
    setLoadingPipelines(true)
    fetch('/api/config/pipelines', {
      headers: { Authorization: `Bearer ${user.token}` },
    })
      .then(async (res) => {
        if (!res.ok) {
          let message = ''
          try {
            if (typeof res.text === 'function') {
              message = await res.text()
            } else if (typeof res.json === 'function') {
              const raw: unknown = await res.json()
              message = typeof raw === 'string' ? raw : JSON.stringify(raw)
            }
          } catch {
            message = ''
          }
          throw new Error(message || res.statusText)
        }
        return res.json() as Promise<PipelineListResponse>
      })
      .then((data) => {
        const list = data.pipelines ?? []
        setPipelines(list.map((p) => ({ name: p.name, config: p.config })))
        if (list.length > 0) setSelectedPipeline(list[0].name)
      })
      .catch((e) => {
        const msg = e instanceof Error ? e.message : 'Failed to load pipelines'
        setError(t('pipeline.error', { message: msg }))
      })
      .finally(() => setLoadingPipelines(false))
  }, [user?.token, t])

  const startExecution = useCallback(async () => {
    if (!user?.token || !sessionId) return
    const chosen = pipelines.find((p) => p.name === selectedPipeline)
    if (!chosen) {
      setError(t('pipeline.error', { message: 'No pipeline selected' }))
      return
    }

    setStarting(true)
    setError(null)
    setAgents([])
    setLogs([])
    setPipelineStatus(null)

    try {
      const res = await fetch(`/api/pipeline/sessions/${encodeURIComponent(sessionId)}/config`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${user.token}`,
        },
        body: JSON.stringify(chosen.config),
      })
      if (!res.ok) {
        let message = ''
        try {
          if (typeof res.text === 'function') {
            message = await res.text()
          } else if (typeof res.json === 'function') {
            const raw: unknown = await res.json()
            message = typeof raw === 'string' ? raw : JSON.stringify(raw)
          }
        } catch {
          message = ''
        }
        throw new Error(message || res.statusText)
      }
      setHasStarted(true)
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to start pipeline'
      setError(t('pipeline.error', { message: msg }))
    } finally {
      setStarting(false)
    }
  }, [pipelines, selectedPipeline, sessionId, t, user?.token])

  useEffect(() => {
    if (!hasStarted || !user?.token || !sessionId) return

    const ws = new WebSocket(getWsUrl(sessionId, user.token))
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const raw: unknown = JSON.parse(event.data)

        if (
          typeof raw === 'object' &&
          raw !== null &&
          'type' in raw &&
          (raw as { type: unknown }).type === 'error'
        ) {
          const detail = (raw as { detail?: unknown; message?: unknown }).detail
          const message = (raw as { detail?: unknown; message?: unknown }).message
          const rendered =
            typeof detail === 'string'
              ? detail
              : typeof message === 'string'
                ? message
                : 'Unknown error'
          setError(t('pipeline.error', { message: rendered }))
          return
        }

        if (!isObject(raw) || typeof raw.type !== 'string') return
        const type = raw.type
        const timestamp = typeof raw.timestamp === 'string' ? raw.timestamp : new Date().toISOString()
        const payload = (raw as { data?: unknown }).data

        if (type === 'agent_start') {
          const agentData = isObject(raw) ? extractAgentStatus(raw) : null
          if (!agentData) return
          setAgents((prev) => {
            const existing = prev.find((a) => a.agent_id === agentData.agent_id)
            if (existing) {
              return prev.map((a) =>
                a.agent_id === agentData.agent_id
                  ? { ...a, status: 'running' }
                  : a
              )
            }
            return [
              ...prev,
              {
                agent_id: agentData.agent_id,
                agent_name: agentData.agent_name,
                step_number: agentData.step_number,
                status: 'running',
              },
            ]
          })
          setLogs((prev) => [
            ...prev,
            {
              timestamp,
              message: `${t('pipeline.agent')} ${agentData.agent_name} — ${t('pipeline.running')}`,
            },
          ])
        } else if (type === 'agent_complete') {
          const agentData = isObject(raw) ? extractAgentStatus(raw) : null
          if (!agentData) return
          setAgents((prev) =>
            prev.map((a) =>
              a.agent_id === agentData.agent_id
                ? { ...a, status: 'completed' }
                : a
            )
          )
          setLogs((prev) => [
            ...prev,
            {
              timestamp,
              message: `${t('pipeline.agent')} ${agentData.agent_name} — ${t('pipeline.completed')}`,
            },
          ])
        } else if (type === 'agent_fail') {
          const agentData = isObject(raw) ? extractAgentStatus(raw) : null
          if (!agentData) return
          setAgents((prev) =>
            prev.map((a) =>
              a.agent_id === agentData.agent_id
                ? { ...a, status: 'failed', error: agentData.error }
                : a
            )
          )
          setLogs((prev) => [
            ...prev,
            {
              timestamp,
              message: `${t('pipeline.agent')} ${agentData.agent_name} — ${t('pipeline.failed')}${agentData.error ? `: ${agentData.error}` : ''}`,
            },
          ])
        } else if (type === 'llm_token') {
          // LLM tokens are streamed but we don't display them in the timeline log
        } else if (type === 'pipeline_complete') {
          const completeData = isPipelineCompleteData(payload) ? payload : (isPipelineCompleteData(raw) ? raw : null)
          if (!completeData) return
          setPipelineStatus(completeData.status)
          setLogs((prev) => [
            ...prev,
            {
              timestamp,
              message: `${t('pipeline.title')} — ${completeData.status === 'COMPLETED' ? t('pipeline.completed') : t('pipeline.failed')}`,
            },
          ])
        } else if (type === 'log_entry') {
          if (!isObject(payload)) return
          const msg = payload.message
          if (typeof msg !== 'string') return
          setLogs((prev) => [
            ...prev,
            {
              timestamp,
              message: msg,
            },
          ])
        }
      } catch {
        // Ignore malformed messages
      }
    }

    ws.onerror = () => {
      setError(t('pipeline.error', { message: 'WebSocket connection failed' }))
    }

    ws.onclose = (ev) => {
      wsRef.current = null

      if (!errorRef.current && ev.code && ev.code !== 1000) {
        const reason = ev.reason || `WebSocket closed (code ${ev.code})`
        setError(t('pipeline.error', { message: reason }))
      }
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [hasStarted, sessionId, user?.token, t])

  const activeAgent = agents.find((a) => a.status === 'running')

  return (
    <div data-testid="execution-timeline" className="flex flex-col h-full">
      <h2 className="text-lg font-semibold px-4 py-2 border-b dark:border-gray-700">
        {t('pipeline.title')}
      </h2>

      <div className="px-4 py-3 space-y-2 border-b dark:border-gray-700">
        <div className="flex items-center gap-2">
          <select
            value={selectedPipeline}
            onChange={(e) => setSelectedPipeline(e.target.value)}
            disabled={loadingPipelines || pipelines.length === 0 || starting}
            className="px-3 py-2 rounded-md text-sm border border-border bg-card"
          >
            {pipelines.map((p) => (
              <option key={p.name} value={p.name}>{p.name}</option>
            ))}
          </select>
          <button
            onClick={startExecution}
            disabled={starting || loadingPipelines || pipelines.length === 0 || !selectedPipeline}
            className={cn(
              'px-3 py-2 rounded-md text-sm font-medium text-white',
              starting || loadingPipelines || pipelines.length === 0 || !selectedPipeline
                ? 'bg-gray-400 cursor-not-allowed'
                : 'bg-blue-600 hover:bg-blue-700'
            )}
            type="button"
          >
            {starting ? '...' : 'Start'}
          </button>
        </div>

        {pipelines.length === 0 && !loadingPipelines && (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No pipeline configs available. Create one in Configuration (admin).
          </p>
        )}
      </div>

      {/* Agent timeline */}
      <div data-testid="agent-timeline" className="px-4 py-3 space-y-2 border-b dark:border-gray-700">
        {agents.length === 0 && (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {t('pipeline.status')}: {t('pipeline.pending')}
          </p>
        )}
        {agents.map((agent) => (
          <div
            key={agent.agent_id}
            data-testid={`agent-entry-${agent.agent_id}`}
            className={cn(
              'flex items-center gap-3 rounded-md px-3 py-2 text-sm',
              agent.status === 'running' && 'bg-blue-50 dark:bg-blue-900/20 ring-1 ring-blue-400',
              agent.status === 'completed' && 'bg-green-50 dark:bg-green-900/20',
              agent.status === 'failed' && 'bg-red-50 dark:bg-red-900/20',
              agent.status === 'pending' && 'bg-gray-50 dark:bg-gray-800'
            )}
          >
            <span
              data-testid={`agent-status-icon-${agent.agent_id}`}
              className={cn(
                'text-base',
                agent.status === 'running' && 'text-blue-600 dark:text-blue-400',
                agent.status === 'completed' && 'text-green-600 dark:text-green-400',
                agent.status === 'failed' && 'text-red-600 dark:text-red-400',
                agent.status === 'pending' && 'text-gray-400 dark:text-gray-500'
              )}
            >
              {STATUS_ICONS[agent.status]}
            </span>
            <div className="flex-1 min-w-0">
              <span className="font-medium">{agent.agent_name}</span>
              <span className="ml-2 text-gray-500 dark:text-gray-400">
                {t('pipeline.step', { number: agent.step_number })}
              </span>
            </div>
            <span
              data-testid={`agent-status-${agent.agent_id}`}
              className={cn(
                'text-xs font-medium',
                agent.status === 'running' && 'text-blue-600 dark:text-blue-400',
                agent.status === 'completed' && 'text-green-600 dark:text-green-400',
                agent.status === 'failed' && 'text-red-600 dark:text-red-400',
                agent.status === 'pending' && 'text-gray-500 dark:text-gray-400'
              )}
            >
              {t(`pipeline.${agent.status}`)}
            </span>
          </div>
        ))}
      </div>

      {/* Active agent indicator */}
      {activeAgent && (
        <div data-testid="active-agent" className="px-4 py-2 text-sm bg-blue-50 dark:bg-blue-900/20 border-b dark:border-gray-700">
          <span className="font-medium">{t('pipeline.agent')}:</span>{' '}
          {activeAgent.agent_name} — {t('pipeline.running')}
        </div>
      )}

      {/* Pipeline status */}
      {pipelineStatus && (
        <div
          data-testid="pipeline-status"
          className={cn(
            'px-4 py-2 text-sm font-medium border-b dark:border-gray-700',
            pipelineStatus === 'COMPLETED'
              ? 'text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-900/20'
              : 'text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20'
          )}
        >
          {t('pipeline.status')}: {pipelineStatus === 'COMPLETED' ? t('pipeline.completed') : t('pipeline.failed')}
        </div>
      )}

      {/* Error display */}
      {error && (
        <div data-testid="timeline-error" className="px-4 py-2 text-sm text-red-500" role="alert">
          {error}
        </div>
      )}

      {/* Live log entries */}
      <div data-testid="log-entries" className="flex-1 overflow-y-auto px-4 py-3 space-y-1">
        {logs.map((log, index) => (
          <div
            key={index}
            data-testid="log-entry"
            className="text-xs text-gray-600 dark:text-gray-400 font-mono"
          >
            <span className="text-gray-400 dark:text-gray-500 mr-2">
              {log.timestamp}
            </span>
            {log.message}
          </div>
        ))}
        <div ref={logsEndRef} />
      </div>
    </div>
  )
}
