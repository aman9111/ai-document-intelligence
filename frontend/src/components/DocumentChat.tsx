import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { API_BASE_URL, getErrorMessage } from '../api'
import { IconSend, IconSparkle, IconTrash } from './Icons'

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

// Which page an excerpt number in the answer ([1], [2]...) came from
interface SourceRef {
  number: number
  page_number: number
  label: string
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  // Only set on messages from this session, not on ones loaded from history
  sources?: SourceRef[]
  tokensUsed?: number | null
  isStreaming?: boolean
  error?: string
}

interface DocumentChatProps {
  documentId: number
  filename: string
  token: string
  suggestions: string[]
  // Called when an answer is finished, with the pages it cited
  onAnswer: (pages: number[]) => void
  onFocusPage: (pageNumber: number) => void
}

const CITATION = /[[【](\d+)[\]】]/g

function formatNumber(value: number | null): string {
  return value === null ? '—' : value.toLocaleString()
}

function citedNumbers(answer: string): number[] {
  return [...new Set([...answer.matchAll(CITATION)].map((match) => Number(match[1])))]
}

// The LLM writes citations as [1] or 【1】 and bold text as **text**.
// Turn those into small clickable source chips and <strong> tags.
function renderAnswer(answer: string, sources: SourceRef[], onFocusPage: (page: number) => void): ReactNode {
  const parts = answer.split(/(\*\*[^*]+\*\*|[[【]\d+[\]】])/g)

  return parts.map((part, index) => {
    const citation = part.match(/^[[【](\d+)[\]】]$/)

    if (citation) {
      const source = sources.find((s) => s.number === Number(citation[1]))
      return source ? (
        <button
          key={index}
          type="button"
          className="cite-chip"
          title={`Page ${source.page_number}`}
          onClick={() => onFocusPage(source.page_number)}
        >
          {citation[1]}
        </button>
      ) : (
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

function DocumentChat({ documentId, filename, token, suggestions, onAnswer, onFocusPage }: DocumentChatProps) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [conversationId, setConversationId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [question, setQuestion] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [usage, setUsage] = useState<AIUsage | null>(null)
  const messagesRef = useRef<HTMLDivElement>(null)

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

  // Keep the newest message in view while the answer streams in. Scrolls only
  // the messages box, not the whole page.
  useEffect(() => {
    const box = messagesRef.current
    if (box) box.scrollTop = box.scrollHeight
  }, [messages])

  function updateLastMessage(change: (message: ChatMessage) => ChatMessage) {
    setMessages((current) => [...current.slice(0, -1), change(current[current.length - 1])])
  }

  async function openConversation(id: number | null) {
    setError(null)
    setConversationId(id)
    setMessages([])
    onAnswer([])

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

  async function ask(text: string) {
    if (!text || isStreaming) return

    setError(null)
    setQuestion('')
    setIsStreaming(true)
    setMessages((current) => [
      ...current,
      { role: 'user', content: text },
      { role: 'assistant', content: '', isStreaming: true },
    ])

    // Kept here too (not only in state) to find the cited pages at the end
    let answer = ''
    let sources: SourceRef[] = []

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
          sources = (data.sources as SourceRef[] | undefined) ?? []
          updateLastMessage((message) => ({ ...message, sources }))
        } else if (eventName === 'token') {
          answer += data.text as string
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

          const pages = citedNumbers(answer)
            .map((n) => sources.find((s) => s.number === n)?.page_number)
            .filter((page): page is number => page !== undefined)
          onAnswer([...new Set(pages)])
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

  function handleSend(event: FormEvent) {
    event.preventDefault()
    ask(question.trim())
  }

  // Suggested questions the user hasn't asked yet in this chat
  const unasked = suggestions.filter((s) => !messages.some((m) => m.role === 'user' && m.content === s))

  const percentLeft =
    usage?.requests_limit && usage.requests_remaining !== null
      ? (usage.requests_remaining / usage.requests_limit) * 100
      : null

  return (
    <aside className="chat-panel" aria-label="Ask AI">
      <div className="chat-head">
        <span className="chat-head-icon">
          <IconSparkle size={16} />
        </span>
        <strong>Ask AI</strong>
        {usage && (
          <span className={`chat-quota${percentLeft !== null && percentLeft < 20 ? ' chat-quota-low' : ''}`}>
            {formatNumber(usage.requests_remaining)} / {formatNumber(usage.requests_limit)} questions left today
          </span>
        )}
      </div>

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
        {conversationId !== null && (
          <>
            <button
              type="button"
              className="btn-outline btn-sm"
              onClick={() => openConversation(null)}
              disabled={isStreaming}
            >
              + New
            </button>
            <button
              type="button"
              className="btn-outline btn-square btn-sm"
              aria-label="Delete this chat"
              onClick={deleteConversation}
              disabled={isStreaming}
            >
              <IconTrash size={16} />
            </button>
          </>
        )}
      </div>

      <div className="chat-messages" ref={messagesRef}>
        {messages.length === 0 && (
          <div className="chat-empty">
            <strong>Ask anything about this document</strong>
            Answers show which page they came from. Click a page number to jump to it.
          </div>
        )}

        {messages.map((message, index) => {
          const cited = message.sources
            ? citedNumbers(message.content)
                .map((n) => message.sources!.find((s) => s.number === n))
                .filter((s): s is SourceRef => s !== undefined)
            : []

          return (
            <div key={index} className={`chat-message chat-${message.role}`}>
              {message.role === 'user' ? (
                <div className="chat-bubble">{message.content}</div>
              ) : (
                <div className="chat-bubble">
                  {message.content && renderAnswer(message.content, message.sources ?? [], onFocusPage)}
                  {message.isStreaming && <span className="typing-cursor" aria-hidden="true" />}
                  {message.isStreaming && !message.content && (
                    <span className="chat-thinking">Reading the document...</span>
                  )}
                  {message.error && <p className="login-error">{message.error}</p>}
                  {!message.isStreaming && cited.length > 0 && (
                    <span className="source-chips">
                      {cited.map((source) => (
                        <button
                          key={source.number}
                          type="button"
                          className="source-chip"
                          onClick={() => onFocusPage(source.page_number)}
                        >
                          [{source.number}] Page {source.page_number}
                          {source.label && ` · ${source.label}`}
                        </button>
                      ))}
                    </span>
                  )}
                  {message.tokensUsed != null && (
                    <span className="chat-meta">{formatNumber(message.tokensUsed)} tokens</span>
                  )}
                </div>
              )}
            </div>
          )
        })}

        {error && <p className="login-error">{error}</p>}
      </div>

      {!isStreaming && unasked.length > 0 && (
        <div className="suggestions">
          {unasked.map((suggestion) => (
            <button key={suggestion} type="button" className="suggestion" onClick={() => ask(suggestion)}>
              {suggestion}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={handleSend} className="chat-input">
        <label className="sr-only" htmlFor={`chat-input-${documentId}`}>
          Ask a question about {filename}
        </label>
        <input
          id={`chat-input-${documentId}`}
          type="text"
          placeholder={conversationId ? 'Ask a follow-up...' : `Ask about ${filename}`}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={500}
        />
        <button type="submit" className="send-btn" aria-label="Send question" disabled={isStreaming || !question.trim()}>
          <IconSend />
        </button>
      </form>
      <p className="chat-disclaimer">AI answers can be wrong. Check important details in the document.</p>
    </aside>
  )
}

export default DocumentChat
