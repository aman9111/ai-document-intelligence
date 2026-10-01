import { useCallback, useEffect, useMemo, useState } from 'react'
import { API_BASE_URL, getErrorMessage } from '../api'

interface PageItem {
  page_number: number
  doc_type: string | null
  doc_type_label: string
  category: string | null
  confidence: number | null
  needs_review: boolean
  reason: string | null
  corrected: boolean
  text_preview: string
}

interface TypeOption {
  value: string
  label: string
  category: string
}

interface ClassificationOptions {
  categories: Record<string, string>
  types: TypeOption[]
}

interface DocumentPagesProps {
  documentId: number
  filename: string
  token: string
  onClose: () => void
  onClassify: () => void
}

const FAILED_TAB = 'failed'
const REVIEW_TAB = 'review'

// Loads one page thumbnail. The image API needs the login token, so a plain
// <img src> can't be used: fetch it, then show it from a temporary blob URL.
function PageThumb({ documentId, pageNumber, token }: { documentId: number; pageNumber: number; token: string }) {
  const [url, setUrl] = useState<string | null>(null)
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    let objectUrl: string | null = null
    let cancelled = false

    fetch(`${API_BASE_URL}/documents/${documentId}/pages/${pageNumber}/image?width=320`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((response) => (response.ok ? response.blob() : Promise.reject()))
      .then((blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => !cancelled && setMissing(true))

    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [documentId, pageNumber, token])

  if (missing) return <div className="page-thumb page-thumb-empty">No preview</div>
  if (!url) return <div className="page-thumb page-thumb-loading" />
  return <img className="page-thumb" src={url} alt={`Page ${pageNumber}`} loading="lazy" />
}

function DocumentPages({ documentId, filename, token, onClose, onClassify }: DocumentPagesProps) {
  const [pages, setPages] = useState<PageItem[] | null>(null)
  const [options, setOptions] = useState<ClassificationOptions | null>(null)
  const [activeTab, setActiveTab] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState<number | null>(null)

  const authHeader = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token])

  const loadPages = useCallback(() => {
    return fetch(`${API_BASE_URL}/documents/${documentId}/pages`, { headers: authHeader })
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((data: PageItem[]) => setPages(data))
      .catch(() => setError('Could not load the pages'))
  }, [documentId, authHeader])

  useEffect(() => {
    loadPages()
    fetch(`${API_BASE_URL}/classification/types`, { headers: authHeader })
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((data: ClassificationOptions) => setOptions(data))
      .catch(() => setError('Could not load the document types'))
  }, [loadPages, authHeader])

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  // Tabs like "Medical Documents (70)", plus failed pages and pages to review
  const tabs = useMemo(() => {
    if (!pages || !options) return []
    const count = (test: (page: PageItem) => boolean) => pages.filter(test).length
    return [
      ...Object.entries(options.categories).map(([key, label]) => ({
        key,
        label,
        count: count((p) => p.category === key),
      })),
      { key: FAILED_TAB, label: 'Failed pages', count: count((p) => p.doc_type === FAILED_TAB) },
      { key: REVIEW_TAB, label: '⚠️ Needs review', count: count((p) => p.needs_review && p.doc_type !== FAILED_TAB) },
    ]
  }, [pages, options])

  const unclassified = pages?.filter((p) => !p.doc_type).length ?? 0
  const currentTab = activeTab ?? tabs.find((t) => t.count > 0)?.key ?? null

  const visiblePages = useMemo(() => {
    if (!pages || !currentTab) return []
    if (currentTab === REVIEW_TAB) return pages.filter((p) => p.needs_review && p.doc_type !== FAILED_TAB)
    if (currentTab === FAILED_TAB) return pages.filter((p) => p.doc_type === FAILED_TAB)
    return pages.filter((p) => p.category === currentTab)
  }, [pages, currentTab])

  // Inside a tab, group pages by type: "Lab report (3)", "Prescription (1)"...
  const groups = useMemo(() => {
    const byType = new Map<string, PageItem[]>()
    for (const page of visiblePages) {
      const key = page.doc_type_label
      byType.set(key, [...(byType.get(key) ?? []), page])
    }
    return [...byType.entries()]
  }, [visiblePages])

  async function changeType(page: PageItem, docType: string) {
    setSaving(page.page_number)
    setError(null)

    try {
      const response = await fetch(`${API_BASE_URL}/documents/${documentId}/pages/${page.page_number}`, {
        method: 'PATCH',
        headers: { ...authHeader, 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_type: docType }),
      })
      const data = await response.json()

      if (!response.ok) {
        setError(getErrorMessage(data.detail, 'Could not change the type'))
        return
      }

      setPages((current) => current?.map((p) => (p.page_number === page.page_number ? (data as PageItem) : p)) ?? null)
    } catch {
      setError('Could not reach the server')
    } finally {
      setSaving(null)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal modal-pages"
        role="dialog"
        aria-modal="true"
        aria-label={`Pages of ${filename}`}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-header">
          <div>
            <h2>Pages by type</h2>
            <p className="doc-meta">
              {filename}
              {pages && ` · ${pages.length} page${pages.length === 1 ? '' : 's'}`}
            </p>
          </div>
          <button type="button" className="btn-icon" onClick={onClose}>
            Close
          </button>
        </header>

        {tabs.length > 0 && (
          <nav className="page-tabs" aria-label="Page categories">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                type="button"
                className={`page-tab${tab.key === currentTab ? ' page-tab-active' : ''}`}
                onClick={() => setActiveTab(tab.key)}
                disabled={tab.count === 0}
              >
                {tab.label} ({tab.count})
              </button>
            ))}
          </nav>
        )}

        <div className="modal-body">
          {error && <p className="login-error">{error}</p>}
          {!pages && !error && <p className="subtitle">Loading...</p>}

          {pages && unclassified > 0 && (
            <div className="empty-state classify-prompt">
              <strong>
                {unclassified === pages.length ? 'Pages not classified yet' : `${unclassified} pages not classified yet`}
              </strong>
              This document was uploaded before page types were added.
              <button type="button" className="btn btn-primary" onClick={onClassify}>
                Classify pages
              </button>
            </div>
          )}

          {groups.map(([label, groupPages]) => (
            <section key={label} className="page-group">
              <h3 className="page-group-title">
                {label} <span className="count-badge">{groupPages.length}</span>
              </h3>
              <div className="page-grid">
                {groupPages.map((page) => (
                  <article key={page.page_number} className={`page-card${page.needs_review ? ' page-card-review' : ''}`}>
                    <PageThumb documentId={documentId} pageNumber={page.page_number} token={token} />
                    <div className="page-card-body">
                      <p className="page-card-title">
                        Page {page.page_number}
                        {page.confidence !== null && page.doc_type !== FAILED_TAB && (
                          <span className="score-pill">{Math.round(page.confidence * 100)}%</span>
                        )}
                      </p>
                      {page.needs_review && page.doc_type !== FAILED_TAB && <p className="review-badge">⚠️ Needs review</p>}
                      {page.corrected && <p className="corrected-badge">✓ Set by you</p>}
                      {page.reason && !page.corrected && <p className="page-reason">{page.reason}</p>}
                      {options && (
                        <select
                          value={page.doc_type && page.doc_type !== FAILED_TAB ? page.doc_type : ''}
                          onChange={(e) => changeType(page, e.target.value)}
                          disabled={saving === page.page_number}
                          aria-label={`Type of page ${page.page_number}`}
                        >
                          {(!page.doc_type || page.doc_type === FAILED_TAB) && <option value="">Choose type…</option>}
                          {Object.entries(options.categories).map(([key, categoryLabel]) => (
                            <optgroup key={key} label={categoryLabel}>
                              {options.types
                                .filter((t) => t.category === key)
                                .map((t) => (
                                  <option key={t.value} value={t.value}>
                                    {t.label}
                                  </option>
                                ))}
                            </optgroup>
                          ))}
                        </select>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}

          {pages && pages.length > 0 && visiblePages.length === 0 && unclassified === 0 && (
            <p className="subtitle">No pages in this tab.</p>
          )}
        </div>
      </div>
    </div>
  )
}

export default DocumentPages
