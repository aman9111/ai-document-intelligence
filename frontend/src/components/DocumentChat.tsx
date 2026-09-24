import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { API_BASE_URL, getErrorMessage } from '../api'

interface AIUsage {
  tokens_used: number | null
  requests_limit: number | null
  requests_remaining: number | null
  tokens_limit: number | null
  tokens_remaining: number | null
}

interface Conversation {
  id: number
  title: string
  updated_at: string
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  // Only set on messages from this session, not on ones loaded from history
  tokensUsed?: number | null
  isStreaming?: boolean
  error?: string
}

interface DocumentChatProps {
  documentId: number
  filename: string
  token: string
  onClose: () => void
}

function formatNumber(value: number | null): string {
  return value === null ? '—' : value.toLocaleString()
}

// The LLM writes citations as [1] or 【1】 and bold text as **text**.
// Turn those into small source chips and <strong> tags.
function renderAnswer(answer: string): ReactNode {
  const parts = answer.split(/(\*\*[^*]+\*\*|[[【]\d+[\]】])/g)

  return parts.map((part, index) => {
    const citation = part.match(/^[[【](\d+)[\]】]$/)

    if (citation) {
      return (
        <span key={index} className="cite-chip">
          {citation[1]}
        </span>
      )
    }

    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={index}>{part.slice(2, -2)}</strong>
    }

    return <Fragment key={index}>{part}</Fragment>
  })
}

function UsageBar({ usage }: { usage: AIUsage | null }) {
  if (!usage) {
    return <p className="usage-bar">Free AI quota: shown after your first question</p>
  }

  const percentLeft =
    usage.requests_limit && usage.requests_remaining !== null
      ? (usage.requests_remaining / usage.requests_limit) * 100
      : 100

  return (
    <div className="usage-bar">
      <div className="usage-row">
        <span>
          <strong>{formatNumber(usage.requests_remaining)}</strong> /{' '}
          {formatNumber(usage.requests_limit)} questions left today
        </span>
        <span>
          <strong>{formatNumber(usage.tokens_remaining)}</strong> /{' '}
          {formatNumber(usage.tokens_limit)} tokens left this minute
        </span>
      </div>
      <div className="usage-track">
        <div
          className={`usage-fill${percentLeft < 20 ? ' usage-low' : ''}`}
          style={{ width: `${percentLeft}%` }}
        />
      </div>
    </div>
  )
}

// Reads a Server-Sent Events stream ("event: x\ndata: {...}\n\n") and calls
// onEvent for every event as soon as it arrives
async function readEventStream(
  response: Response,
  onEvent: (event: string, data: Record<string, unknown>) => void,
) {
  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // One event ends with a blank line. A network piece can hold several
    // events, or only half of one, so keep the unfinished part in the buffer.
    let end = buffer.indexOf('\n\n')
    while (end !== -1) {
      const raw = buffer.slice(0, end)
      buffer = buffer.slice(end + 2)

      const event = raw.match(/^event: (.*)$/m)?.[1]
      const data = raw.match(/^data: (.*)$/m)?.[1]
      if (event && data) onEvent(event, JSON.parse(data))

      end = buffer.indexOf('\n\n')
    }
  }
}

function DocumentChat({ documentId, filename, token, onClose }: DocumentChatProps) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [conversationId, setConversationId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [question, setQuestion] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [usage, setUsage] = useState<AIUsage | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const authHeader = { Authorization: `Bearer ${token}` }

  const loadConversations = useCallback(() => {
    return fetch(`${API_BASE_URL}/documents/${documentId}/conversations`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((response) => (response.ok ? response.json() : []))
      .then((data: Conversation[]) => setConversations(data))
      .catch(() => setConversations([]))
  }, [documentId, token])

  useEffect(() => {
    loadConversations()

    fetch(`${API_BASE_URL}/ai/usage`, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => (response.ok ? response.json() : null))
      .then((data: AIUsage | null) => setUsage(data))
      .catch(() => setUsage(null))
  }, [loadConversations, token])

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  // Keep the newest message in view while the answer streams in
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: 'end' })
  }, [messages])

  function updateLastMessage(change: (message: ChatMessage) => ChatMessage) {
    setMessages((current) => [...current.slice(0, -1), change(current[current.length - 1])])
  }

  async function openConversation(id: number | null) {
    setError(null)
    setConversationId(id)
    setMessages([])

    if (id === null) return

    try {
      const response = await fetch(`${API_BASE_URL}/conversations/${id}/messages`, {
        headers: authHeader,
      })
      if (!response.ok) throw new Error()
      setMessages(await response.json())
    } catch {
      setError('Could not load this chat')
    }
  }

  async function deleteConversation() {
    if (conversationId === null || !window.confirm('Delete this chat?')) return

    await fetch(`${API_BASE_URL}/conversations/${conversationId}`, {
      method: 'DELETE',
      headers: authHeader,
    })
    openConversation(null)
    loadConversations()
  }

  async function handleSend(event: FormEvent) {
    event.preventDefault()

    const text = question.trim()
    if (!text || isStreaming) return

    setError(null)
    setQuestion('')
    setIsStreaming(true)
    setMessages((current) => [
      ...current,
      { role: 'user', content: text },
      { role: 'assistant', content: '', isStreaming: true },
    ])

    try {
      const response = await fetch(`${API_BASE_URL}/documents/${documentId}/chat`, {
        method: 'POST',
        headers: { ...authHeader, 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text, conversation_id: conversationId }),
      })

      // Errors before the stream starts (not ready, not logged in...) come as normal JSON
      if (!response.ok) {
        const data = await response.json()
        updateLastMessage((message) => ({
          ...message,
          isStreaming: false,
          error: getErrorMessage(data.detail, 'Could not get an answer'),
        }))
        return
      }

      await readEventStream(response, (eventName, data) => {
        if (eventName === 'start') {
          setConversationId(data.conversation_id as number)
        } else if (eventName === 'token') {
          updateLastMessage((message) => ({
            ...message,
            content: message.content + (data.text as string),
          }))
        } else if (eventName === 'error') {
          updateLastMessage((message) => ({
            ...message,
            isStreaming: false,
            error: data.detail as string,
          }))
        } else if (eventName === 'done') {
          const doneUsage = data.usage as AIUsage | null
          if (doneUsage) setUsage(doneUsage)
          updateLastMessage((message) => ({
            ...message,
            isStreaming: false,
            tokensUsed: doneUsage?.tokens_used ?? null,
          }))
        }
      })

      loadConversations()
    } catch {
      updateLastMessage((message) => ({
        ...message,
        isStreaming: false,
        error: 'Could not reach the server',
      }))
    } finally {
      setIsStreaming(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal modal-chat"
        role="dialog"
        aria-modal="true"
        aria-label={`Chat about ${filename}`}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-header">
          <div>
            <h2>Ask AI ✨</h2>
            <p className="doc-meta">{filename}</p>
          </div>
          <button type="button" className="btn-icon" onClick={onClose}>
            Close
          </button>
        </header>

        <div className="chat-toolbar">
          <select
            value={conversationId ?? ''}
            onChange={(e) => openConversation(e.target.value ? Number(e.target.value) : null)}
            disabled={isStreaming}
            aria-label="Previous chats"
          >
            <option value="">New chat</option>
            {conversations.map((conversation) => (
              <option key={conversation.id} value={conversation.id}>
                {conversation.title}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn-icon"
            onClick={() => openConversation(null)}
            disabled={isStreaming || conversationId === null}
          >
            + New
          </button>
          {conversationId !== null && (
            <button
              type="button"
              className="btn-icon btn-icon-danger"
              onClick={deleteConversation}
              disabled={isStreaming}
            >
              Delete
            </button>
          )}
        </div>

        <div className="chat-messages">
          <UsageBar usage={usage} />

          {messages.length === 0 && (
            <div className="chat-empty">
              <strong>Ask anything about this document</strong>
              You can ask follow-up questions too, like "and for how many days?"
            </div>
          )}

          {messages.map((message, index) => (
            <div key={index} className={`chat-message chat-${message.role}`}>
              {message.role === 'user' ? (
                <div className="chat-bubble">{message.content}</div>
              ) : (
                <div className="chat-bubble">
                  {message.content && renderAnswer(message.content)}
                  {message.isStreaming && <span className="typing-cursor" aria-hidden="true" />}
                  {message.isStreaming && !message.content && (
                    <span className="chat-thinking">Reading the document...</span>
                  )}
                  {message.error && <p className="login-error">{message.error}</p>}
                  {message.tokensUsed != null && (
                    <p className="chat-meta">{formatNumber(message.tokensUsed)} tokens</p>
                  )}
                </div>
              )}
            </div>
          ))}

          {error && <p className="login-error">{error}</p>}
          <div ref={messagesEndRef} />
        </div>

        <form onSubmit={handleSend} className="chat-input">
          <input
            type="text"
            placeholder={conversationId ? 'Ask a follow-up...' : 'e.g. Which medicines should the patient take?'}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={500}
            autoFocus
          />
          <button type="submit" className="btn btn-primary" disabled={isStreaming || !question.trim()}>
            {isStreaming ? '...' : 'Send'}
          </button>
        </form>
        <p className="chat-disclaimer">AI answers can be wrong. Check important details in the document.</p>
      </div>
    </div>
  )
}

export default DocumentChat
