import { useEffect, useMemo, useRef, useState } from 'react'
import { API_BASE_URL } from '../api'
import { FAILED } from '../types'
import type { ClassificationOptions, PageItem } from '../types'
import { IconChevron, IconClose } from './Icons'

interface DocumentPagesProps {
  documentId: number
  token: string
  // DOCX files have no page images, so their pages show a bit of text instead
  hasImages: boolean
  // Pages of the open tab, and all pages (for moving through them in the viewer)
  pages: PageItem[]
  allPages: PageItem[]
  options: ClassificationOptions
  citedPages: number[]
  focus: { page: number; at: number } | null
  saving: number | null
  onChangeType: (page: PageItem, docType: string) => void
}

// Loads one page image. The image API needs the login token, so a plain
// <img src> can't be used: fetch it, then show it from a temporary blob URL.
function PageThumb({ documentId, pageNumber, token, width = 320, className = 'page-thumb' }: {
  documentId: number
  pageNumber: number
  token: string
  width?: number
  className?: string
}) {
  const [url, setUrl] = useState<string | null>(null)
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    let objectUrl: string | null = null
    let cancelled = false

    fetch(`${API_BASE_URL}/documents/${documentId}/pages/${pageNumber}/image?width=${width}`, {
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
  }, [documentId, pageNumber, token, width])

  if (missing) return <span className={`${className} thumb-empty`}>No preview</span>
  if (!url) return <span className={`${className} thumb-loading`} />
  return <img className={className} src={url} alt={`Page ${pageNumber}`} loading="lazy" />
}

function TypeSelect({ page, options, disabled, onChange }: {
  page: PageItem
  options: ClassificationOptions
  disabled: boolean
  onChange: (docType: string) => void
}) {
  const isUnset = !page.doc_type || page.doc_type === FAILED

  return (
    <select
      value={isUnset ? '' : page.doc_type!}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      aria-label={`Type of page ${page.page_number}`}
    >
      {isUnset && <option value="">Choose type…</option>}
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
  )
}

// Big view of one page, with previous / next
function PageViewer({ documentId, token, page, allPages, options, saving, onChangeType, onNavigate, onClose }: {
  documentId: number
  token: string
  page: PageItem
  allPages: PageItem[]
  options: ClassificationOptions
  saving: boolean
  onChangeType: (docType: string) => void
  onNavigate: (pageNumber: number) => void
  onClose: () => void
}) {
  const index = allPages.findIndex((p) => p.page_number === page.page_number)
  const previous = allPages[index - 1]
  const next = allPages[index + 1]

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
      // Arrow keys move between pages, unless the type dropdown has focus
      if (event.target instanceof HTMLSelectElement) return
      if (event.key === 'ArrowLeft' && previous) onNavigate(previous.page_number)
      if (event.key === 'ArrowRight' && next) onNavigate(next.page_number)
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose, onNavigate, previous, next])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal viewer"
        role="dialog"
        aria-modal="true"
        aria-label={`Page ${page.page_number}`}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-header">
          <div>
            <h2>
              Page {page.page_number} <span className="viewer-of">of {allPages.length}</span>
            </h2>
            <p className="doc-meta">{page.doc_type === FAILED ? 'Unreadable page' : page.doc_type_label}</p>
          </div>
          <div className="viewer-tools">
            <TypeSelect page={page} options={options} disabled={saving} onChange={onChangeType} />
            <button type="button" className="btn-outline btn-square" aria-label="Close" onClick={onClose}>
              <IconClose />
            </button>
          </div>
        </header>
        <div className="viewer-body">
          <button
            type="button"
            className="viewer-nav"
            aria-label="Previous page"
            disabled={!previous}
            onClick={() => previous && onNavigate(previous.page_number)}
          >
            <IconChevron left />
          </button>
          <PageThumb
            key={page.page_number}
            documentId={documentId}
            pageNumber={page.page_number}
            token={token}
            width={1000}
            className="viewer-image"
          />
          <button
            type="button"
            className="viewer-nav"
            aria-label="Next page"
            disabled={!next}
            onClick={() => next && onNavigate(next.page_number)}
          >
            <IconChevron />
          </button>
        </div>
      </div>
    </div>
  )
}

function DocumentPages({
  documentId,
  token,
  hasImages,
  pages,
  allPages,
  options,
  citedPages,
  focus,
  saving,
  onChangeType,
}: DocumentPagesProps) {
  const [viewing, setViewing] = useState<number | null>(null)
  const cardRefs = useRef(new Map<number, HTMLElement>())

  // Inside a tab, group pages by type: "Lab report (3)", "Prescription (1)"...
  const groups = useMemo(() => {
    const byType = new Map<string, PageItem[]>()
    for (const page of pages) {
      const key = page.doc_type === FAILED ? 'Unreadable pages' : page.doc_type_label
      byType.set(key, [...(byType.get(key) ?? []), page])
    }
    return [...byType.entries()]
  }, [pages])

  // Scroll a page into view when a citation in the chat is clicked
  useEffect(() => {
    if (focus) cardRefs.current.get(focus.page)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [focus])

  const viewingPage = allPages.find((p) => p.page_number === viewing)

  return (
    <>
      {groups.map(([label, groupPages]) => (
        <section key={label} className="page-group">
          <h3 className="page-group-title">
            {label}
            <span>
              {groupPages.length} page{groupPages.length === 1 ? '' : 's'}
            </span>
          </h3>
          <div className="page-grid">
            {groupPages.map((page) => {
              const citeIndex = citedPages.indexOf(page.page_number)
              const isFocused = focus?.page === page.page_number
              const isFailed = page.doc_type === FAILED
              const classes = [
                'page-card',
                page.needs_review && !isFailed ? 'page-card-review' : '',
                citeIndex !== -1 ? 'page-card-cited' : '',
                isFocused ? 'page-card-focus' : '',
              ]

              const badges = (
                <>
                  {page.confidence !== null && !isFailed && (
                    <span className={`conf-pill${page.needs_review ? ' conf-pill-low' : ''}`}>
                      {Math.round(page.confidence * 100)}%
                    </span>
                  )}
                  {citeIndex !== -1 && <span className="cited-pill">Cited by AI</span>}
                </>
              )

              return (
                <article
                  key={page.page_number}
                  ref={(element) => {
                    if (element) cardRefs.current.set(page.page_number, element)
                    else cardRefs.current.delete(page.page_number)
                  }}
                  className={classes.filter(Boolean).join(' ')}
                >
                  {hasImages ? (
                    <button
                      type="button"
                      className="page-thumb-btn"
                      onClick={() => setViewing(page.page_number)}
                      aria-label={`View page ${page.page_number}`}
                    >
                      <PageThumb documentId={documentId} pageNumber={page.page_number} token={token} />
                      {badges}
                    </button>
                  ) : (
                    <div className="page-thumb-btn page-thumb-text">
                      <span className="page-thumb">{page.text_preview || 'No text on this page'}</span>
                      {badges}
                    </div>
                  )}
                  <div className="page-card-body">
                    <p className="page-card-title">Page {page.page_number}</p>
                    {page.corrected ? (
                      <p className="page-note page-note-ok">Set by you</p>
                    ) : page.needs_review && !isFailed ? (
                      <p className="page-note page-note-warn">Not sure, please check the type</p>
                    ) : page.reason ? (
                      <p className="page-note">{page.reason}</p>
                    ) : null}
                    <TypeSelect
                      page={page}
                      options={options}
                      disabled={saving === page.page_number}
                      onChange={(docType) => onChangeType(page, docType)}
                    />
                  </div>
                </article>
              )
            })}
          </div>
        </section>
      ))}

      {pages.length === 0 && allPages.length > 0 && <p className="side-note">No pages in this tab.</p>}

      {viewingPage && (
        <PageViewer
          documentId={documentId}
          token={token}
          page={viewingPage}
          allPages={allPages}
          options={options}
          saving={saving === viewingPage.page_number}
          onChangeType={(docType) => onChangeType(viewingPage, docType)}
          onNavigate={setViewing}
          onClose={() => setViewing(null)}
        />
      )}
    </>
  )
}

export default DocumentPages
