import { useEffect, useMemo, useState } from 'react'
import { API_BASE_URL, getErrorMessage } from '../api'
import { CATEGORY_LABELS, FAILED, SUGGESTED_QUESTIONS, formatSize, pageCount } from '../types'
import type { ClassificationOptions, DocumentItem, PageItem } from '../types'
import CategoryBar from './CategoryBar'
import DocumentChat from './DocumentChat'
import DocumentPages from './DocumentPages'
import DocumentSearch from './DocumentSearch'
import DocumentText from './DocumentText'
import { IconAlert, IconGrid, IconMore, IconOpen, IconRefresh, IconSearch, IconSparkle, IconText, IconTrash } from './Icons'

interface DocumentPanelProps {
  document: DocumentItem
  token: string
  onUnauthorized: () => void
  onProcess: () => void
  onClassify: () => void
  onDelete: () => void
  onError: (message: string) => void
}

const REVIEW_TAB = 'review'

function DocumentPanel({ document, token, onUnauthorized, onProcess, onClassify, onDelete, onError }: DocumentPanelProps) {
  const [pages, setPages] = useState<PageItem[] | null>(null)
  const [options, setOptions] = useState<ClassificationOptions | null>(null)
  const [pagesError, setPagesError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<string | null>(null)
  // Pages the last AI answer used, and a page the user asked to jump to
  const [citedPages, setCitedPages] = useState<number[]>([])
  const [focus, setFocus] = useState<{ page: number; at: number } | null>(null)
  const [saving, setSaving] = useState<number | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [dialog, setDialog] = useState<'search' | 'text' | null>(null)
  // On narrow screens pages and chat don't fit side by side: show one at a time
  const [mobileView, setMobileView] = useState<'pages' | 'chat'>('pages')

  const isReady = document.status === 'ready'
  const authHeader = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token])

  useEffect(() => {
    if (!isReady) return

    fetch(`${API_BASE_URL}/documents/${document.id}/pages`, { headers: authHeader })
      .then((response) => {
        if (response.status === 401) onUnauthorized()
        return response.ok ? response.json() : Promise.reject()
      })
      .then((data: PageItem[]) => setPages(data))
      .catch(() => setPagesError('Could not load the pages'))

    fetch(`${API_BASE_URL}/classification/types`, { headers: authHeader })
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((data: ClassificationOptions) => setOptions(data))
      .catch(() => setPagesError('Could not load the document types'))
  }, [document.id, isReady, authHeader, onUnauthorized])

  useEffect(() => {
    if (!menuOpen) return
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setMenuOpen(false)
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [menuOpen])

  // Tabs like "Medical 4", plus unreadable pages and pages to review
  const tabs = useMemo(() => {
    if (!pages || !options) return []
    const count = (test: (page: PageItem) => boolean) => pages.filter(test).length
    return [
      ...Object.keys(options.categories).map((key) => ({
        key,
        label: CATEGORY_LABELS[key] ?? options.categories[key],
        count: count((p) => p.category === key),
      })),
      { key: FAILED, label: CATEGORY_LABELS[FAILED], count: count((p) => p.doc_type === FAILED) },
      { key: REVIEW_TAB, label: 'Needs a look', count: count((p) => p.needs_review && p.doc_type !== FAILED) },
    ].filter((tab) => tab.count > 0)
  }, [pages, options])

  const currentTab = (activeTab && tabs.some((t) => t.key === activeTab) ? activeTab : tabs[0]?.key) ?? null

  const visiblePages = useMemo(() => {
    if (!pages || !currentTab) return []
    if (currentTab === REVIEW_TAB) return pages.filter((p) => p.needs_review && p.doc_type !== FAILED)
    if (currentTab === FAILED) return pages.filter((p) => p.doc_type === FAILED)
    return pages.filter((p) => p.category === currentTab)
  }, [pages, currentTab])

  const unclassified = pages?.filter((p) => !p.doc_type).length ?? 0

  const suggestions = useMemo(() => {
    const categories = Object.keys(document.doc_type_scores ?? {})
    const questions = categories.map((c) => SUGGESTED_QUESTIONS[c]).filter(Boolean)
    return questions.length > 0 ? questions.slice(0, 3) : ['What is this document about?']
  }, [document.doc_type_scores])

  // A citation was clicked: open the tab that holds that page and scroll to it
  function focusPage(pageNumber: number) {
    const page = pages?.find((p) => p.page_number === pageNumber)
    if (page) setActiveTab(page.doc_type === FAILED ? FAILED : page.category)
    setFocus({ page: pageNumber, at: Date.now() })
    setMobileView('pages')
  }

  async function changeType(page: PageItem, docType: string) {
    setSaving(page.page_number)

    try {
      const response = await fetch(`${API_BASE_URL}/documents/${document.id}/pages/${page.page_number}`, {
        method: 'PATCH',
        headers: { ...authHeader, 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_type: docType }),
      })
      const data = await response.json()

      if (!response.ok) {
        onError(getErrorMessage(data.detail, 'Could not change the type'))
        return
      }

      setPages((current) => current?.map((p) => (p.page_number === page.page_number ? (data as PageItem) : p)) ?? null)
    } catch {
      onError('Could not reach the server')
    } finally {
      setSaving(null)
    }
  }

  async function handleOpen() {
    // The file needs the auth header, so a plain <a href> won't work.
    // Open the tab first (so popup blockers allow it), then load the file.
    const newTab = window.open('', '_blank')

    try {
      const response = await fetch(`${API_BASE_URL}/documents/${document.id}/file`, { headers: authHeader })
      if (!response.ok) throw new Error()

      const url = URL.createObjectURL(await response.blob())
      if (newTab) newTab.location.href = url
      else window.open(url, '_blank')
    } catch {
      newTab?.close()
      onError('Could not open the file')
    }
  }

  function menuAction(action: () => void) {
    setMenuOpen(false)
    action()
  }

  const total = pageCount(document)

  return (
    <div className="panel">
      <header className="panel-header">
        <div className="panel-title">
          <h1 title={document.original_filename}>{document.original_filename}</h1>
          <p>
            {total > 0 && `${total} page${total === 1 ? '' : 's'} · `}
            {formatSize(document.size_bytes)} · Uploaded {new Date(document.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="panel-actions">
          {isReady && (
            <button type="button" className="btn-outline" onClick={() => setDialog('search')}>
              <IconSearch size={16} /> <span className="hide-sm">Find in text</span>
            </button>
          )}
          <button type="button" className="btn-outline" onClick={handleOpen}>
            <IconOpen size={16} /> <span className="hide-sm">Open</span>
          </button>
          <div className="menu-wrap">
            <button
              type="button"
              className="btn-outline btn-square"
              aria-label="More actions"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((open) => !open)}
            >
              <IconMore />
            </button>
            {menuOpen && (
              <>
                <button type="button" className="menu-scrim" aria-label="Close menu" onClick={() => setMenuOpen(false)} />
                <div className="menu" role="menu">
                  {isReady && (
                    <button type="button" role="menuitem" onClick={() => menuAction(() => setDialog('text'))}>
                      <IconText size={16} /> View text
                    </button>
                  )}
                  {isReady && (
                    <button type="button" role="menuitem" onClick={() => menuAction(onClassify)}>
                      <IconRefresh size={16} /> Sort pages again
                    </button>
                  )}
                  {document.status !== 'processing' && (
                    <button type="button" role="menuitem" onClick={() => menuAction(onProcess)}>
                      <IconText size={16} /> Read text again
                    </button>
                  )}
                  <span className="menu-divider" />
                  <button type="button" role="menuitem" className="menu-danger" onClick={() => menuAction(onDelete)}>
                    <IconTrash size={16} /> Delete
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </header>

      {document.status === 'processing' && (
        <div className="panel-state">
          <span className="spinner" aria-hidden="true" />
          <h2>Reading and sorting pages…</h2>
          <p>This usually takes under a minute. You can open other documents meanwhile.</p>
        </div>
      )}

      {(document.status === 'failed' || document.status === 'uploaded') && (
        <div className="panel-state">
          <span className="panel-state-icon">
            <IconAlert size={26} />
          </span>
          <h2>{document.status === 'failed' ? "We couldn't read this document" : 'This document has not been read yet'}</h2>
          <p>
            {document.status === 'failed'
              ? 'It may be blank, password protected or a very low quality scan.'
              : 'Read its text to sort the pages and ask questions.'}
          </p>
          <button type="button" className="btn btn-primary" onClick={onProcess}>
            {document.status === 'failed' ? 'Try again' : 'Read text'}
          </button>
        </div>
      )}

      {isReady && (
        <>
          <div className="panel-summary">
            <CategoryBar scores={document.doc_type_scores} />
            {tabs.length > 0 && (
              <nav className="cat-tabs" aria-label="Page categories">
                {tabs.map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    className={`cat-tab${tab.key === currentTab ? ' cat-tab-active' : ''}`}
                    onClick={() => setActiveTab(tab.key)}
                    aria-pressed={tab.key === currentTab}
                  >
                    <span className={`cat-dot cat-${tab.key}`} />
                    {tab.label}
                    <span className="cat-tab-count">{tab.count}</span>
                  </button>
                ))}
              </nav>
            )}
          </div>

          <div className="view-switch" role="tablist" aria-label="Show">
            <button
              type="button"
              role="tab"
              aria-selected={mobileView === 'pages'}
              className={mobileView === 'pages' ? 'view-switch-active' : ''}
              onClick={() => setMobileView('pages')}
            >
              <IconGrid size={16} /> Pages
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mobileView === 'chat'}
              className={mobileView === 'chat' ? 'view-switch-active' : ''}
              onClick={() => setMobileView('chat')}
            >
              <IconSparkle size={16} /> Ask AI
            </button>
          </div>

          <div className={`panel-split show-${mobileView}`}>
            <div className="panel-pages">
              {pagesError && <p className="login-error">{pagesError}</p>}
              {!pages && !pagesError && <p className="side-note">Loading pages...</p>}

              {pages && unclassified > 0 && (
                <div className="classify-prompt">
                  <strong>
                    {unclassified === pages.length ? 'Pages not sorted yet' : `${unclassified} pages not sorted yet`}
                  </strong>
                  <span>This document was uploaded before page sorting was added.</span>
                  <button type="button" className="btn btn-primary btn-sm" onClick={onClassify}>
                    Sort pages
                  </button>
                </div>
              )}

              {pages && options && (
                <DocumentPages
                  documentId={document.id}
                  token={token}
                  hasImages={!document.content_type.includes('wordprocessingml')}
                  pages={visiblePages}
                  allPages={pages}
                  options={options}
                  citedPages={citedPages}
                  focus={focus}
                  saving={saving}
                  onChangeType={changeType}
                />
              )}
            </div>

            <DocumentChat
              documentId={document.id}
              filename={document.original_filename}
              token={token}
              suggestions={suggestions}
              onAnswer={setCitedPages}
              onFocusPage={focusPage}
            />
          </div>
        </>
      )}

      {dialog === 'search' && (
        <DocumentSearch
          documentId={document.id}
          filename={document.original_filename}
          token={token}
          onClose={() => setDialog(null)}
          onReprocess={() => {
            setDialog(null)
            onProcess()
          }}
        />
      )}

      {dialog === 'text' && (
        <DocumentText
          documentId={document.id}
          filename={document.original_filename}
          token={token}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  )
}

export default DocumentPanel
