import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { API_BASE_URL, getErrorMessage } from '../api'

interface SearchResult {
  chunk_index: number
  page_number: number
  text: string
  best_line: string
  score: number
}

function HighlightedText({ text, highlight }: { text: string; highlight: string }) {
  const lines = text.split('\n')

  return (
    <p className="search-text">
      {lines.map((line, index) => (
        <span key={index} className={line.includes(highlight) ? 'best-line' : undefined}>
          {line}
          {index < lines.length - 1 && '\n'}
        </span>
      ))}
    </p>
  )
}

interface DocumentSearchProps {
  documentId: number
  filename: string
  token: string
  onClose: () => void
  onReprocess: () => void
}

function DocumentSearch({ documentId, filename, token, onClose, onReprocess }: DocumentSearchProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [isSearching, setIsSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [needsReprocess, setNeedsReprocess] = useState(false)

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  async function handleSearch(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setNeedsReprocess(false)
    setIsSearching(true)

    try {
      const response = await fetch(`${API_BASE_URL}/documents/${documentId}/search`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query, top_k: 1 }),
      })

      const data = await response.json()

      if (!response.ok) {
        const message = getErrorMessage(data.detail, 'Search failed')
        setError(message)
        setNeedsReprocess(message.includes('Re-process'))
        return
      }

      setResults(data as SearchResult[])
    } catch {
      setError('Could not reach the server')
    } finally {
      setIsSearching(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={`Find in ${filename}`}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-header">
          <div>
            <h2>Find in text</h2>
            <p className="doc-meta">{filename}</p>
          </div>
          <button type="button" className="btn-icon" onClick={onClose}>
            Close
          </button>
        </header>

        <div className="modal-body">
          <form onSubmit={handleSearch} className="search-form">
            <input
              type="text"
              placeholder="e.g. What was the glucose level?"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoFocus
              required
            />
            <button type="submit" className="btn btn-primary" disabled={isSearching}>
              {isSearching ? 'Finding...' : 'Find'}
            </button>
          </form>

          <p className="ai-note find-note">
            Shows the line in the document that best matches your words. It doesn't compare or
            calculate, so for questions like "what was the lowest...", use <strong>Ask AI</strong>.
          </p>

          {error && <p className="login-error">{error}</p>}

          {needsReprocess && (
            <button type="button" className="btn btn-primary" onClick={onReprocess}>
              Re-process now
            </button>
          )}

          {results && results.length === 0 && (
            <p className="subtitle">No matching text found.</p>
          )}

          {results?.map((result) => (
            <section key={result.chunk_index} className="search-result">
              <p className="page-label">
                Best answer · Page {result.page_number}
                <span className="score-pill">
                  {Math.round(result.score * 100)}% match
                </span>
              </p>
              <p className="best-answer">{result.best_line}</p>
              <HighlightedText text={result.text} highlight={result.best_line} />
            </section>
          ))}
        </div>
      </div>
    </div>
  )
}

export default DocumentSearch
