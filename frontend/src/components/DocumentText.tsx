import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../api'

interface PageText {
  page_number: number
  text: string
  method: string
}

interface DocumentTextProps {
  documentId: number
  filename: string
  token: string
  onClose: () => void
}

function DocumentText({ documentId, filename, token, onClose }: DocumentTextProps) {
  const [pages, setPages] = useState<PageText[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${API_BASE_URL}/documents/${documentId}/text`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((response) => {
        if (!response.ok) throw new Error('Could not load the text')
        return response.json()
      })
      .then((data: PageText[]) => setPages(data))
      .catch((err: Error) => setError(err.message))
      .finally(() => setIsLoading(false))
  }, [documentId, token])

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={`Extracted text of ${filename}`}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-header">
          <div>
            <h2>Extracted text</h2>
            <p className="doc-meta">{filename}</p>
          </div>
          <button type="button" className="btn-icon" onClick={onClose}>
            Close
          </button>
        </header>

        <div className="modal-body">
          {isLoading && <p className="subtitle">Loading...</p>}
          {error && <p className="login-error">{error}</p>}

          {pages.map((page) => (
            <section key={page.page_number} className="page-text">
              <p className="page-label">
                Page {page.page_number}
                <span className={`method-pill method-${page.method}`}>
                  {page.method === 'ocr' ? 'OCR' : 'Text'}
                </span>
              </p>
              <pre>{page.text || '(no text found on this page)'}</pre>
            </section>
          ))}
        </div>
      </div>
    </div>
  )
}

export default DocumentText
