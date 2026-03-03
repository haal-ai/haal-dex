import { useState, useEffect, useCallback } from 'react'
import { useLanguage } from '../providers/I18nProvider'
import { useAuth } from '../hooks/useAuth'
import { cn } from '../lib/utils'
import type { PipelineConfig, AgentConfig } from '../types/models'

interface PipelineEntry {
  name: string
  config: PipelineConfig
}

interface ValidationError {
  message?: string
  validation_errors?: string[]
}

function emptyAgent(): AgentConfig {
  return {
    name: '',
    model: '',
    provider_config: {
      provider_type: 'bedrock',
      model_id: '',
      temperature: 0.7,
      max_tokens: 2048,
    },
    description: '',
    faiss_indexes: [],
    tools: [],
  }
}

function emptyConfig(): PipelineConfig {
  return {
    name: '',
    agents: [emptyAgent()],
    output: { template: '', formats: [] },
    execution_timeout: 600,
  }
}

async function fetchPipelines(token: string): Promise<PipelineEntry[]> {
  const res = await fetch('/api/config/pipelines', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return []
  const data = await res.json()
  return data.pipelines ?? []
}

async function createPipeline(
  config: PipelineConfig,
  token: string
): Promise<{ ok: boolean; error?: ValidationError }> {
  const raw = JSON.stringify(config)
  const res = await fetch('/api/config/pipelines', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ raw, format: 'json' }),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    return { ok: false, error: detail.detail ?? { message: 'Create failed' } }
  }
  return { ok: true }
}

async function updatePipeline(
  name: string,
  config: PipelineConfig,
  token: string
): Promise<{ ok: boolean; error?: ValidationError }> {
  const raw = JSON.stringify(config)
  const res = await fetch(`/api/config/pipelines/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ raw, format: 'json' }),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    return { ok: false, error: detail.detail ?? { message: 'Update failed' } }
  }
  return { ok: true }
}

async function deletePipeline(name: string, token: string): Promise<boolean> {
  const res = await fetch(`/api/config/pipelines/${encodeURIComponent(name)}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
  return res.ok
}

export function ConfigPanel() {
  const { t } = useLanguage()
  const { user, isAdmin } = useAuth()
  const [pipelines, setPipelines] = useState<PipelineEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState<PipelineConfig | null>(null)
  const [editingOriginalName, setEditingOriginalName] = useState<string | null>(null)
  const [validationError, setValidationError] = useState<string | null>(null)

  const loadPipelines = useCallback(async () => {
    if (!user?.token) return
    setLoading(true)
    const data = await fetchPipelines(user.token)
    setPipelines(data)
    setLoading(false)
  }, [user?.token])

  useEffect(() => {
    if (isAdmin) {
      loadPipelines()
    } else {
      setLoading(false)
    }
  }, [isAdmin, loadPipelines])

  const handleCreate = useCallback(() => {
    setEditing(emptyConfig())
    setEditingOriginalName(null)
    setValidationError(null)
  }, [])

  const handleEdit = useCallback((entry: PipelineEntry) => {
    setEditing({ ...entry.config })
    setEditingOriginalName(entry.name)
    setValidationError(null)
  }, [])

  const handleDelete = useCallback(
    async (name: string) => {
      if (!user?.token) return
      const ok = await deletePipeline(name, user.token)
      if (ok) {
        await loadPipelines()
      }
    },
    [user?.token, loadPipelines]
  )

  const handleCancel = useCallback(() => {
    setEditing(null)
    setEditingOriginalName(null)
    setValidationError(null)
  }, [])

  const handleSave = useCallback(async () => {
    if (!user?.token || !editing) return
    const result = editingOriginalName
      ? await updatePipeline(editingOriginalName, editing, user.token)
      : await createPipeline(editing, user.token)

    if (!result.ok && result.error) {
      const err = result.error
      const msg =
        err.validation_errors?.join(', ') ?? err.message ?? 'Unknown error'
      setValidationError(msg)
      return
    }

    setEditing(null)
    setEditingOriginalName(null)
    setValidationError(null)
    await loadPipelines()
  }, [user?.token, editing, editingOriginalName, loadPipelines])

  if (!isAdmin) {
    return (
      <div data-testid="config-panel" className="flex items-center justify-center h-full">
        <p data-testid="config-unauthorized" className="text-red-500">
          {t('auth.unauthorized')}
        </p>
      </div>
    )
  }

  return (
    <div data-testid="config-panel" className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 border-b dark:border-gray-700">
        <h2 className="text-lg font-semibold">{t('config.title')}</h2>
        {!editing && (
          <button
            data-testid="config-create"
            onClick={handleCreate}
            className="px-3 py-1 rounded-md bg-blue-600 text-white text-sm hover:bg-blue-700"
            type="button"
          >
            {t('config.create')}
          </button>
        )}
      </div>

      {validationError && (
        <div
          data-testid="config-validation-error"
          className="mx-4 mt-2 p-2 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded text-sm"
        >
          {t('config.validation', { message: validationError })}
        </div>
      )}

      {editing ? (
        <ConfigForm
          config={editing}
          onChange={setEditing}
          onSave={handleSave}
          onCancel={handleCancel}
          t={t}
        />
      ) : loading ? (
        <div className="flex-1 flex items-center justify-center text-gray-500">…</div>
      ) : (
        <div data-testid="config-list" className="flex-1 overflow-y-auto">
          {pipelines.length === 0 ? (
            <p className="p-4 text-gray-500">{t('config.pipelines')}: 0</p>
          ) : (
            <ul className="divide-y dark:divide-gray-700">
              {pipelines.map((entry) => (
                <li
                  key={entry.name}
                  data-testid="config-item"
                  className="flex items-center justify-between px-4 py-3"
                >
                  <span className="font-medium">{entry.name}</span>
                  <div className="flex gap-2">
                    <button
                      data-testid={`config-edit-${entry.name}`}
                      onClick={() => handleEdit(entry)}
                      className="px-2 py-1 text-sm rounded bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600"
                      type="button"
                    >
                      {t('config.edit')}
                    </button>
                    <button
                      data-testid={`config-delete-${entry.name}`}
                      onClick={() => handleDelete(entry.name)}
                      className="px-2 py-1 text-sm rounded bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 hover:bg-red-200 dark:hover:bg-red-800"
                      type="button"
                    >
                      {t('config.delete')}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

interface ConfigFormProps {
  config: PipelineConfig
  onChange: (config: PipelineConfig) => void
  onSave: () => void
  onCancel: () => void
  t: (key: string) => string
}

const AVAILABLE_TOOLS = ['read', 'write', 'python_repl', 'shell'] as const
const FAISS_INDEXES = [0, 1, 2, 3] as const
const PROVIDER_TYPES = ['bedrock', 'openai_compatible', 'github_copilot'] as const

function ConfigForm({ config, onChange, onSave, onCancel, t }: ConfigFormProps) {
  const updateField = <K extends keyof PipelineConfig>(key: K, value: PipelineConfig[K]) => {
    onChange({ ...config, [key]: value })
  }

  const updateAgent = (index: number, agent: AgentConfig) => {
    const agents = [...config.agents]
    agents[index] = agent
    updateField('agents', agents)
  }

  const addAgent = () => {
    updateField('agents', [...config.agents, emptyAgent()])
  }

  const removeAgent = (index: number) => {
    updateField('agents', config.agents.filter((_, i) => i !== index))
  }

  return (
    <div data-testid="config-form" className="flex-1 overflow-y-auto p-4 space-y-4">
      {/* Pipeline name */}
      <div>
        <label className="block text-sm font-medium mb-1">{t('config.pipelines')}</label>
        <input
          data-testid="config-name"
          type="text"
          value={config.name}
          onChange={(e) => updateField('name', e.target.value)}
          className="w-full border rounded px-3 py-2 dark:bg-gray-800 dark:border-gray-600"
        />
      </div>

      {/* Template selection */}
      <div>
        <label className="block text-sm font-medium mb-1">{t('config.templates')}</label>
        <input
          data-testid="config-template"
          type="text"
          value={config.output.template}
          onChange={(e) =>
            updateField('output', { ...config.output, template: e.target.value })
          }
          className="w-full border rounded px-3 py-2 dark:bg-gray-800 dark:border-gray-600"
        />
      </div>

      {/* Agents */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-sm font-medium">{t('config.agents')}</label>
          <button
            data-testid="config-add-agent"
            onClick={addAgent}
            className="text-sm text-blue-600 hover:underline"
            type="button"
          >
            + {t('config.agents')}
          </button>
        </div>

        {config.agents.map((agent, idx) => (
          <AgentForm
            key={idx}
            agent={agent}
            index={idx}
            onChange={(a) => updateAgent(idx, a)}
            onRemove={() => removeAgent(idx)}
            t={t}
          />
        ))}
      </div>

      {/* Actions */}
      <div className="flex gap-2 pt-2 border-t dark:border-gray-700">
        <button
          data-testid="config-save"
          onClick={onSave}
          className="px-4 py-2 rounded-md bg-blue-600 text-white text-sm hover:bg-blue-700"
          type="button"
        >
          {t('config.save')}
        </button>
        <button
          data-testid="config-cancel"
          onClick={onCancel}
          className="px-4 py-2 rounded-md bg-gray-200 dark:bg-gray-700 text-sm hover:bg-gray-300 dark:hover:bg-gray-600"
          type="button"
        >
          {t('config.cancel')}
        </button>
      </div>
    </div>
  )
}

interface AgentFormProps {
  agent: AgentConfig
  index: number
  onChange: (agent: AgentConfig) => void
  onRemove: () => void
  t: (key: string) => string
}

function AgentForm({ agent, index, onChange, onRemove, t }: AgentFormProps) {
  const update = <K extends keyof AgentConfig>(key: K, value: AgentConfig[K]) => {
    onChange({ ...agent, [key]: value })
  }

  const toggleTool = (tool: string) => {
    const tools = agent.tools.includes(tool)
      ? agent.tools.filter((t) => t !== tool)
      : [...agent.tools, tool]
    update('tools', tools)
  }

  const toggleFaissIndex = (idx: number) => {
    const indexes = agent.faiss_indexes.includes(idx)
      ? agent.faiss_indexes.filter((i) => i !== idx)
      : [...agent.faiss_indexes, idx]
    update('faiss_indexes', indexes)
  }

  return (
    <div
      data-testid={`config-agent-${index}`}
      className={cn(
        'border rounded p-3 mb-3 dark:border-gray-600 space-y-2'
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">
          {t('config.agents')} #{index + 1}
        </span>
        <button
          data-testid={`config-remove-agent-${index}`}
          onClick={onRemove}
          className="text-xs text-red-500 hover:underline"
          type="button"
        >
          {t('config.delete')}
        </button>
      </div>

      <input
        data-testid={`config-agent-name-${index}`}
        type="text"
        placeholder="Agent name"
        value={agent.name}
        onChange={(e) => update('name', e.target.value)}
        className="w-full border rounded px-2 py-1 text-sm dark:bg-gray-800 dark:border-gray-600"
      />

      {/* Model assignment */}
      <div>
        <label className="block text-xs mb-1">{t('config.models')}</label>
        <select
          data-testid={`config-agent-provider-${index}`}
          value={agent.provider_config.provider_type}
          onChange={(e) =>
            update('provider_config', {
              ...agent.provider_config,
              provider_type: e.target.value,
            })
          }
          className="w-full border rounded px-2 py-1 text-sm dark:bg-gray-800 dark:border-gray-600"
        >
          {PROVIDER_TYPES.map((pt) => (
            <option key={pt} value={pt}>
              {pt}
            </option>
          ))}
        </select>
        <input
          data-testid={`config-agent-model-${index}`}
          type="text"
          placeholder="Model ID"
          value={agent.provider_config.model_id}
          onChange={(e) =>
            update('provider_config', {
              ...agent.provider_config,
              model_id: e.target.value,
            })
          }
          className="w-full border rounded px-2 py-1 text-sm mt-1 dark:bg-gray-800 dark:border-gray-600"
        />
      </div>

      {/* Tools */}
      <div>
        <label className="block text-xs mb-1">{t('config.tools')}</label>
        <div className="flex flex-wrap gap-2">
          {AVAILABLE_TOOLS.map((tool) => (
            <label key={tool} className="flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={agent.tools.includes(tool)}
                onChange={() => toggleTool(tool)}
                data-testid={`config-agent-tool-${index}-${tool}`}
              />
              {tool}
            </label>
          ))}
        </div>
      </div>

      {/* FAISS Indexes */}
      <div>
        <label className="block text-xs mb-1">{t('config.faissIndexes')}</label>
        <div className="flex flex-wrap gap-2">
          {FAISS_INDEXES.map((fi) => (
            <label key={fi} className="flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={agent.faiss_indexes.includes(fi)}
                onChange={() => toggleFaissIndex(fi)}
                data-testid={`config-agent-faiss-${index}-${fi}`}
              />
              Index {fi}
            </label>
          ))}
        </div>
      </div>

      {/* Template */}
      <div>
        <label className="block text-xs mb-1">{t('config.templates')}</label>
        <input
          data-testid={`config-agent-template-${index}`}
          type="text"
          placeholder="Template ID (optional)"
          value={agent.template ?? ''}
          onChange={(e) => update('template', e.target.value || undefined)}
          className="w-full border rounded px-2 py-1 text-sm dark:bg-gray-800 dark:border-gray-600"
        />
      </div>
    </div>
  )
}
