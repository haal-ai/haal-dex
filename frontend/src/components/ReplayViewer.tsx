import { useState, useEffect, useCallback } from 'react'
import { useLanguage } from '../providers/I18nProvider'
import { useAuth } from '../hooks/useAuth'
import { cn } from '../lib/utils'

export interface ReplayStep {
  step_number: number
  agent_id: string
  agent_name: string
  status: string
  timestamp: string
  input_data: Record<string, unknown>
  prompts_sent: string[]
  llm_responses: string[]
  llm_provider: string
  llm_model: string
  decisions: string[]
  output_data: Record<string, unknown>
  error: string | null
}

export interface TimelineEntry {
  step_number: number
  agent_id: string
  agent_name: string
  status: string
  timestamp: string
}

export interface ReplayData {
  session_id: string
  user_id: string
  created_at: string
  completed_at: string | null
  steps: ReplayStep[]
  timeline: TimelineEntry[]
}

export interface ReplayViewerProps {
  sessionId: string
}

async function fetchReplay(sessionId: string, token: string): Promise<ReplayData | null> {
  const res = await fetch(`/api/replay/${sessionId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return null
  return res.json()
}

export function ReplayViewer({ sessionId }: ReplayViewerProps) {
  const { t } = useLanguage()
  const { user } = useAuth()
  const [replay, setReplay] = useState<ReplayData | null>(null)
  const [loading, setLoading] = useState(true)
  const [currentStep, setCurrentStep] = useState(0)

  useEffect(() => {
    if (!user?.token || !sessionId) {
      setLoading(false)
      return
    }
    setLoading(true)
    fetchReplay(sessionId, user.token)
      .then((data) => {
        setReplay(data)
        setCurrentStep(0)
      })
      .finally(() => setLoading(false))
  }, [sessionId, user?.token])

  const handlePrevious = useCallback(() => {
    setCurrentStep((prev) => Math.max(0, prev - 1))
  }, [])

  const handleNext = useCallback(() => {
    if (!replay) return
    setCurrentStep((prev) => Math.min(replay.steps.length - 1, prev + 1))
  }, [replay])

  const step = replay?.steps[currentStep] ?? null

  return (
    <div data-testid="replay-viewer" className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 border-b dark:border-gray-700">
        <h2 className="text-lg font-semibold">{t('replay.title')}</h2>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-gray-500">
          <span data-testid="replay-loading">…</span>
        </div>
      ) : replay && replay.steps.length > 0 ? (
        <div className="flex-1 overflow-y-auto">
          {/* Timeline */}
          <div data-testid="replay-timeline" className="px-4 py-3 border-b dark:border-gray-700">
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {t('replay.timeline')}
            </h3>
            <div className="flex gap-2 flex-wrap">
              {replay.timeline.map((entry, idx) => (
                <button
                  key={entry.step_number}
                  data-testid={`timeline-step-${entry.step_number}`}
                  onClick={() => setCurrentStep(idx)}
                  className={cn(
                    'px-3 py-1.5 rounded-md text-sm font-medium border',
                    idx === currentStep
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700'
                  )}
                  type="button"
                >
                  {t('replay.step', { number: entry.step_number })}
                </button>
              ))}
            </div>
          </div>

          {/* Navigation controls */}
          <div data-testid="replay-navigation" className="flex items-center justify-between px-4 py-2 border-b dark:border-gray-700">
            <button
              data-testid="replay-previous"
              onClick={handlePrevious}
              disabled={currentStep === 0}
              className={cn(
                'px-3 py-1.5 rounded-md text-sm font-medium',
                currentStep === 0
                  ? 'bg-gray-200 text-gray-400 cursor-not-allowed dark:bg-gray-700 dark:text-gray-500'
                  : 'bg-blue-600 text-white hover:bg-blue-700'
              )}
              type="button"
            >
              {t('replay.previous')}
            </button>
            <span className="text-sm text-gray-600 dark:text-gray-400">
              {t('replay.step', { number: step?.step_number ?? 0 })}
            </span>
            <button
              data-testid="replay-next"
              onClick={handleNext}
              disabled={currentStep >= replay.steps.length - 1}
              className={cn(
                'px-3 py-1.5 rounded-md text-sm font-medium',
                currentStep >= replay.steps.length - 1
                  ? 'bg-gray-200 text-gray-400 cursor-not-allowed dark:bg-gray-700 dark:text-gray-500'
                  : 'bg-blue-600 text-white hover:bg-blue-700'
              )}
              type="button"
            >
              {t('replay.next')}
            </button>
          </div>

          {/* Step details */}
          {step && (
            <div data-testid="step-details" className="px-4 py-3 space-y-4">
              <div data-testid="step-input">
                <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('replay.input')}
                </h4>
                <pre className="text-xs bg-gray-50 dark:bg-gray-800 rounded p-2 overflow-x-auto">
                  {JSON.stringify(step.input_data, null, 2)}
                </pre>
              </div>
              <div data-testid="step-output">
                <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('replay.output')}
                </h4>
                <pre className="text-xs bg-gray-50 dark:bg-gray-800 rounded p-2 overflow-x-auto">
                  {JSON.stringify(step.output_data, null, 2)}
                </pre>
              </div>
              <div data-testid="step-prompts">
                <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('replay.prompts')}
                </h4>
                <ul className="text-xs space-y-1">
                  {step.prompts_sent.map((p, i) => (
                    <li key={i} className="bg-gray-50 dark:bg-gray-800 rounded p-2">{p}</li>
                  ))}
                </ul>
              </div>
              <div data-testid="step-responses">
                <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('replay.responses')}
                </h4>
                <ul className="text-xs space-y-1">
                  {step.llm_responses.map((r, i) => (
                    <li key={i} className="bg-gray-50 dark:bg-gray-800 rounded p-2">{r}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div
          data-testid="replay-empty"
          className="flex-1 flex items-center justify-center text-gray-500 dark:text-gray-400"
        >
          {t('replay.title')}
        </div>
      )}
    </div>
  )
}
