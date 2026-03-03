import { useState, useRef, useEffect, useCallback } from 'react'
import { useLanguage } from '../providers/I18nProvider'
import { useAuth } from '../hooks/useAuth'
import { cn } from '../lib/utils'
import type { ExecutionEvent, AgentStatusData, PipelineCompleteData } from '../types/websocket'

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
    if (!user?.token || !sessionId) return

    const ws = new WebSocket(getWsUrl(sessionId, user.token))
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const data: ExecutionEvent = JSON.parse(event.data)

        if (data.type === 'agent_start') {
          const agentData = data.data as AgentStatusData
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
              timestamp: data.timestamp,
              message: `${t('pipeline.agent')} ${agentData.agent_name} — ${t('pipeline.running')}`,
            },
          ])
        } else if (data.type === 'agent_complete') {
          const agentData = data.data as AgentStatusData
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
              timestamp: data.timestamp,
              message: `${t('pipeline.agent')} ${agentData.agent_name} — ${t('pipeline.completed')}`,
            },
          ])
        } else if (data.type === 'agent_fail') {
          const agentData = data.data as AgentStatusData
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
              timestamp: data.timestamp,
              message: `${t('pipeline.agent')} ${agentData.agent_name} — ${t('pipeline.failed')}${agentData.error ? `: ${agentData.error}` : ''}`,
            },
          ])
        } else if (data.type === 'llm_token') {
          // LLM tokens are streamed but we don't display them in the timeline log
        } else if (data.type === 'pipeline_complete') {
          const completeData = data.data as PipelineCompleteData
          setPipelineStatus(completeData.status)
          setLogs((prev) => [
            ...prev,
            {
              timestamp: data.timestamp,
              message: `${t('pipeline.title')} — ${completeData.status === 'COMPLETED' ? t('pipeline.completed') : t('pipeline.failed')}`,
            },
          ])
        } else if (data.type === 'log_entry') {
          setLogs((prev) => [
            ...prev,
            {
              timestamp: data.timestamp,
              message: (data.data as { message: string }).message,
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

    ws.onclose = () => {
      wsRef.current = null
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [sessionId, user?.token, t])

  const activeAgent = agents.find((a) => a.status === 'running')

  return (
    <div data-testid="execution-timeline" className="flex flex-col h-full">
      <h2 className="text-lg font-semibold px-4 py-2 border-b dark:border-gray-700">
        {t('pipeline.title')}
      </h2>

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
