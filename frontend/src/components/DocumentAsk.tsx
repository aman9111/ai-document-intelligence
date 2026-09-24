import { Fragment, useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { API_BASE_URL, getErrorMessage } from '../api'

interface AIUsage {
  tokens_used: number | null
  requests_limit: number | null
  requests_remaining: number | null
  requests_reset: string | null
  tokens_limit: number | null
  tokens_remaining: number | null
  tokens_reset: string | null
}

interface AskResult {
  answer: string
  usage: AIUsage
}

function formatNumber(value: number | null): string {
  return value === null ? '—' : value.toLocaleString()
}

function UsageBar({ usage }: { usage: AIUsage | null }) {
  if (!usage) {
    return (
      <p className="usage-bar">
        Free AI quota: shown after your first question
      </p>
    )
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

interface DocumentAskProps {
  documentId: number
  filename: string
  token: string
  onClose: () => void
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

function DocumentAsk({ documentId, filename, token, onClose }: DocumentAskProps) {
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<AskResult | null>(null)
  const [isAsking, setIsAsking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [usage, setUsage] = useState<AIUsage | null>(null)

  useEffect(() => {
    fetch(`${API_BASE_URL}/ai/usage`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((response) => (response.ok ? response.json() : null))
      .then((data: AIUsage | null) => setUsage(data))
      .catch(() => setUsage(null))
  }, [token])

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  async function handleAsk(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setResult(null)
    setIsAsking(true)

    try {
      const response = await fetch(`${API_BASE_URL}/documents/${documentId}/ask`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ question }),
      })

      const data = await response.json()

      if (!response.ok) {
        setError(getErrorMessage(data.detail, 'Could not get an answer'))
        return
      }

      setResult(data as AskResult)
      setUsage((data as AskResult).usage)
    } catch {
      setError('Could not reach the server')
    } finally {
      setIsAsking(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={`Ask AI about ${filename}`}
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

        <div className="modal-body">
          <UsageBar usage={usage} />

          <form onSubmit={handleAsk} className="search-form">
            <input
              type="text"
              placeholder="e.g. Which medicines should the patient take at home?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              autoFocus
              required
            />
            <button type="submit" className="btn btn-primary" disabled={isAsking}>
              {isAsking ? 'Thinking...' : 'Ask'}
            </button>
          </form>

          {error && <p className="login-error">{error}</p>}

          {isAsking && <p className="subtitle">Reading the document and writing an answer...</p>}

          {result && (
            <>
              <div className="ai-answer">{renderAnswer(result.answer)}</div>

              <p className="ai-note">
                AI answers can be wrong. Check important details in the document itself.
                {result.usage.tokens_used !== null &&
                  ` · This answer used ${formatNumber(result.usage.tokens_used)} tokens.`}
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default DocumentAsk
