import { useState, useCallback, useRef, useEffect } from 'react'
import { useLanguage } from '../providers/I18nProvider'
import { useAuth } from '../hooks/useAuth'
import { cn } from '../lib/utils'
import type { ChatResponse } from '../types/websocket'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  language: string
}

export interface ChatPanelProps {
  sessionId: string
}

function getWsUrl(sessionId: string, token: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/ws/chat/${sessionId}?token=${encodeURIComponent(token)}`
}

export function ChatPanel({ sessionId }: ChatPanelProps) {
  const { t, language } = useLanguage()
  const { user } = useAuth()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const streamBufferRef = useRef('')

  const scrollToBottom = useCallback(() => {
    if (messagesEndRef.current && typeof messagesEndRef.current.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, thinking, scrollToBottom])

  // WebSocket connection management
  useEffect(() => {
    if (!user?.token || !sessionId) return

    const ws = new WebSocket(getWsUrl(sessionId, user.token))
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const data: ChatResponse = JSON.parse(event.data)

        if (data.type === 'token') {
          streamBufferRef.current += data.content
          // Update the last assistant message with accumulated tokens
          setMessages((prev) => {
            const last = prev[prev.length - 1]
            if (last && last.role === 'assistant') {
              return [
                ...prev.slice(0, -1),
                { ...last, content: streamBufferRef.current },
              ]
            }
            // First token — create a new assistant message
            return [
              ...prev,
              { role: 'assistant', content: streamBufferRef.current, language },
            ]
          })
        } else if (data.type === 'complete') {
          setThinking(false)
          streamBufferRef.current = ''
        } else if (data.type === 'error') {
          setThinking(false)
          setError(data.content || t('chat.error'))
          streamBufferRef.current = ''
        }
      } catch {
        // Ignore malformed messages
      }
    }

    ws.onerror = () => {
      setError(t('chat.error'))
      setThinking(false)
    }

    ws.onclose = () => {
      wsRef.current = null
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [sessionId, user?.token, language, t])

  const sendMessage = useCallback(() => {
    const trimmed = input.trim()
    if (!trimmed || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return

    const userMessage: ChatMessage = {
      role: 'user',
      content: trimmed,
      language,
    }

    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setThinking(true)
    setError(null)
    streamBufferRef.current = ''

    wsRef.current.send(
      JSON.stringify({
        type: 'chat_message',
        content: trimmed,
        language,
      })
    )
  }, [input, language])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        sendMessage()
      }
    },
    [sendMessage]
  )

  return (
    <div data-testid="chat-panel" className="flex flex-col h-full">
      <h2 className="text-lg font-semibold px-4 py-2 border-b dark:border-gray-700">
        {t('chat.title')}
      </h2>

      {/* Messages area */}
      <div
        data-testid="chat-messages"
        className="flex-1 overflow-y-auto px-4 py-3 space-y-3"
      >
        {messages.map((msg, index) => (
          <div
            key={index}
            data-testid={`chat-message-${msg.role}`}
            className={cn(
              'max-w-[80%] rounded-lg px-3 py-2 text-sm',
              msg.role === 'user'
                ? 'ml-auto bg-blue-600 text-white'
                : 'mr-auto bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100'
            )}
          >
            {msg.content}
          </div>
        ))}

        {thinking && (
          <div
            data-testid="chat-thinking"
            className="mr-auto text-sm text-gray-500 dark:text-gray-400 italic"
          >
            {t('chat.thinking')}
          </div>
        )}

        {error && (
          <div
            data-testid="chat-error"
            className="text-sm text-red-500"
            role="alert"
          >
            {error}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="border-t dark:border-gray-700 px-4 py-3 flex gap-2">
        <input
          data-testid="chat-input"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t('chat.placeholder')}
          className="flex-1 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          disabled={thinking}
        />
        <button
          data-testid="chat-send"
          onClick={sendMessage}
          disabled={thinking || !input.trim()}
          className={cn(
            'px-4 py-2 rounded-md text-white text-sm font-medium',
            thinking || !input.trim()
              ? 'bg-gray-400 cursor-not-allowed'
              : 'bg-blue-600 hover:bg-blue-700'
          )}
          type="button"
        >
          {t('chat.send')}
        </button>
      </div>
    </div>
  )
}
