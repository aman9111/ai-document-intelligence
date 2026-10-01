import { useCallback, useEffect, useRef, useState } from 'react'
import type { ChangeEvent, DragEvent } from 'react'
import { API_BASE_URL, getErrorMessage } from '../api'
import { formatSize, getFileLabel, pageCount } from '../types'
import type { DocumentItem } from '../types'
import CategoryBar from './CategoryBar'
import DocumentPanel from './DocumentPanel'
import { IconCheck, IconClose, IconUpload } from './Icons'

interface DocumentsProps {
  token: string
  search: string
  onUnauthorized: () => void
}

const ACCEPTED_FILES = '.pdf,.docx,.png,.jpg,.jpeg'
const POLL_INTERVAL_MS = 3000
const TOAST_MS = 6000

function FileBadge({ contentType }: { contentType: string }) {
  const label = getFileLabel(contentType)
  return <span className={`file-badge file-badge-${label.toLowerCase()}`}>{label}</span>
}

// The colourful stack of pages used on the upload box and the welcome screen
function PagesIllustration({ large = false }: { large?: boolean }) {
  return (
    <span className={`pages-art${large ? ' pages-art-lg' : ''}`} aria-hidden="true">
      <span className="pages-art-sheet cat-insurance" />
      <span className="pages-art-sheet cat-medical" />
      <span className="pages-art-sheet cat-financial" />
      <span className="pages-art-dot">
        <IconUpload size={large ? 26 : 14} />
      </span>
    </span>
  )
}

// A file on its way: uploading (step 0) or being read and sorted (step 1)
function ReadingCard({ name, contentType, step, onSelect }: {
  name: string
  contentType: string
  step: 0 | 1
  onSelect?: () => void
}) {
  const steps = ['Uploading', 'Reading & sorting pages', 'Ready']

  return (
    <div className="reading-card">
      <div className="reading-top">
        <FileBadge contentType={contentType} />
        <div className="reading-info">
          {onSelect ? (
            <button type="button" className="reading-name link-btn" onClick={onSelect}>
              {name}
            </button>
          ) : (
            <span className="reading-name">{name}</span>
          )}
          <span className="reading-step">
            Step {step + 1} of 3 · {steps[step]}
          </span>
        </div>
      </div>
      <div className="steps" aria-hidden="true">
        {steps.map((label, index) => (
          <span
            key={label}
            className={`step${index < step ? ' step-done' : ''}${index === step ? ' step-active' : ''}`}
          />
        ))}
      </div>
    </div>
  )
}

function Documents({ token, search, onUnauthorized }: DocumentsProps) {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  // Files still being sent to the server (name + type), shown as "Uploading" cards
  const [uploading, setUploading] = useState<{ key: string; name: string; type: string }[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [toast, setToast] = useState<DocumentItem | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  // Status of every document at the last refresh, to notice "processing -> ready"
  const statusesRef = useRef(new Map<number, string>())

  const authHeader = { Authorization: `Bearer ${token}` }

  const loadDocuments = useCallback(() => {
    return fetch(`${API_BASE_URL}/documents`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((response) => {
        if (response.status === 401) {
          onUnauthorized()
          return null
        }
        if (!response.ok) throw new Error()
        return response.json()
      })
      .then((data: DocumentItem[] | null) => {
        if (!data) return
        const finished = data.find(
          (d) => d.status === 'ready' && statusesRef.current.get(d.id) === 'processing',
        )
        if (finished) setToast(finished)
        statusesRef.current = new Map(data.map((d) => [d.id, d.status]))
        setDocuments(data)
      })
      .catch(() => setError('Could not load documents'))
      .finally(() => setIsLoading(false))
  }, [token, onUnauthorized])

  useEffect(() => {
    loadDocuments()
  }, [loadDocuments])

  // While any document is still being processed, refresh the list every
  // few seconds so its status changes from "processing" to "ready" by itself
  const hasProcessing = documents.some((d) => d.status === 'processing')

  useEffect(() => {
    if (!hasProcessing) return

    const intervalId = setInterval(loadDocuments, POLL_INTERVAL_MS)
    return () => clearInterval(intervalId)
  }, [hasProcessing, loadDocuments])

  useEffect(() => {
    if (!toast) return
    const timeoutId = setTimeout(() => setToast(null), TOAST_MS)
    return () => clearTimeout(timeoutId)
  }, [toast])

  // Put a changed document (from upload, process or classify) into the list
  function saveDocument(document: DocumentItem) {
    statusesRef.current.set(document.id, document.status)
    setDocuments((current) =>
      current.some((d) => d.id === document.id)
        ? current.map((d) => (d.id === document.id ? document : d))
        : [document, ...current],
    )
  }

  async function uploadFile(file: File) {
    const key = `${file.name}-${Date.now()}-${Math.random()}`
    setUploading((current) => [...current, { key, name: file.name, type: file.type }])

    // Files are sent as multipart/form-data, not JSON.
    // The browser sets the Content-Type header (with boundary) itself.
    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await fetch(`${API_BASE_URL}/documents`, {
        method: 'POST',
        headers: authHeader,
        body: formData,
      })

      if (response.status === 401) return onUnauthorized()

      const data = await response.json()

      if (!response.ok) {
        setError(`${file.name}: ${getErrorMessage(data.detail, 'Upload failed')}`)
        return
      }

      saveDocument(data as DocumentItem)
      setSelectedId(data.id)
    } catch {
      setError('Could not reach the server')
    } finally {
      setUploading((current) => current.filter((u) => u.key !== key))
    }
  }

  function uploadFiles(files: FileList | null) {
    if (!files || files.length === 0) return
    setError(null)
    for (const file of Array.from(files)) uploadFile(file)
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    uploadFiles(event.target.files)
    event.target.value = ''
  }

  // The whole workspace accepts dropped files
  function handleDragOver(event: DragEvent) {
    if (!event.dataTransfer.types.includes('Files')) return
    event.preventDefault()
    setIsDragging(true)
  }

  function handleDragLeave(event: DragEvent) {
    // Moving over a child element also fires dragleave: ignore those
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setIsDragging(false)
  }

  function handleDrop(event: DragEvent) {
    event.preventDefault()
    setIsDragging(false)
    uploadFiles(event.dataTransfer.files)
  }

  async function postAction(document: DocumentItem, action: 'process' | 'classify', failMessage: string) {
    setError(null)
    // Keep this document open while it's processing (otherwise the panel would
    // jump to the newest finished document)
    setSelectedId(document.id)

    try {
      const response = await fetch(`${API_BASE_URL}/documents/${document.id}/${action}`, {
        method: 'POST',
        headers: authHeader,
      })

      if (response.status === 401) return onUnauthorized()

      const data = await response.json()

      if (!response.ok) {
        setError(getErrorMessage(data.detail, failMessage))
        return
      }

      // Status is now "processing", so the list refreshes itself until it's done
      saveDocument(data as DocumentItem)
    } catch {
      setError('Could not reach the server')
    }
  }

  async function handleDelete(document: DocumentItem) {
    if (!window.confirm(`Delete "${document.original_filename}"?`)) return

    setError(null)

    try {
      const response = await fetch(`${API_BASE_URL}/documents/${document.id}`, {
        method: 'DELETE',
        headers: authHeader,
      })

      if (response.status === 401) return onUnauthorized()
      if (!response.ok) throw new Error()

      setDocuments((current) => current.filter((d) => d.id !== document.id))
    } catch {
      setError('Could not delete the file')
    }
  }

  const query = search.trim().toLowerCase()
  const processing = documents.filter((d) => d.status === 'processing')
  const listed = documents.filter(
    (d) => d.status !== 'processing' && d.original_filename.toLowerCase().includes(query),
  )
  // The chosen document, or the newest finished one
  const selected =
    documents.find((d) => d.id === selectedId) ?? documents.find((d) => d.status !== 'processing') ?? null

  return (
    <div className="ws-body" onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}>
      <aside className="ws-side">
        <section className="upload-box" aria-label="Upload">
          <PagesIllustration />
          <div className="upload-text">
            <strong>Drop files to read &amp; sort</strong>
            <span>PDF, DOCX, PNG, JPG · up to 10 MB</span>
            <button type="button" className="btn btn-primary btn-sm" onClick={() => fileInputRef.current?.click()}>
              Choose files
            </button>
          </div>
          <input ref={fileInputRef} type="file" accept={ACCEPTED_FILES} onChange={handleFileChange} multiple hidden />
        </section>

        {error && (
          <p className="login-error" role="alert">
            {error}
          </p>
        )}

        {(uploading.length > 0 || processing.length > 0) && (
          <section className="reading-now" aria-label="Being read now">
            {uploading.map((u) => (
              <ReadingCard key={u.key} name={u.name} contentType={u.type} step={0} />
            ))}
            {processing.map((d) => (
              <ReadingCard
                key={d.id}
                name={d.original_filename}
                contentType={d.content_type}
                step={1}
                onSelect={() => setSelectedId(d.id)}
              />
            ))}
          </section>
        )}

        <div className="side-title">
          <h2>My documents</h2>
          <span>{listed.length}</span>
        </div>

        {isLoading ? (
          <p className="side-note">Loading...</p>
        ) : listed.length === 0 ? (
          <p className="side-note">{query ? 'No documents match your search.' : 'Nothing here yet. Upload your first file.'}</p>
        ) : (
          <ul className="doc-list">
            {listed.map((document) => {
              const pages = pageCount(document)
              const isActive = document.id === selected?.id
              return (
                <li key={document.id}>
                  <button
                    type="button"
                    className={`doc-row${isActive ? ' doc-row-active' : ''}`}
                    onClick={() => setSelectedId(document.id)}
                    aria-current={isActive ? 'true' : undefined}
                  >
                    <FileBadge contentType={document.content_type} />
                    <span className="doc-row-info">
                      <span className="doc-row-name" title={document.original_filename}>
                        {document.original_filename}
                      </span>
                      <span className="doc-row-meta">
                        <CategoryBar scores={document.doc_type_scores} size="sm" />
                        {pages > 0 ? `${pages} page${pages === 1 ? '' : 's'}` : formatSize(document.size_bytes)}
                      </span>
                    </span>
                    {document.status === 'failed' && <span className="row-flag">Failed</span>}
                    {document.status === 'uploaded' && <span className="row-flag row-flag-soft">Not read</span>}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </aside>

      <section className="ws-main">
        {selected ? (
          <DocumentPanel
            key={selected.id}
            document={selected}
            token={token}
            onUnauthorized={onUnauthorized}
            onProcess={() => postAction(selected, 'process', 'Could not process the file')}
            onClassify={() => postAction(selected, 'classify', 'Could not classify the pages')}
            onDelete={() => handleDelete(selected)}
            onError={setError}
          />
        ) : (
          <div className="welcome">
            <PagesIllustration large />
            <h1>Drop a document. We sort every page and answer your questions.</h1>
            <p>
              Bills, reports, policies and ID proofs. Each page goes to Insurance, Medical, Financial or KYC,
              and you can ask about anything inside.
            </p>
            <button type="button" className="btn btn-primary" onClick={() => fileInputRef.current?.click()}>
              <IconUpload /> Choose files
            </button>
          </div>
        )}
      </section>

      {isDragging && (
        <div className="drop-overlay" aria-hidden="true">
          <PagesIllustration large />
          <strong>Drop to upload</strong>
        </div>
      )}

      {toast && (
        <div className="toast" role="status">
          <span className="toast-icon">
            <IconCheck size={16} />
          </span>
          <span className="toast-text">
            <strong>{toast.original_filename} is ready</strong>
            <span>
              {pageCount(toast) > 0
                ? `${pageCount(toast)} page${pageCount(toast) === 1 ? '' : 's'} sorted`
                : 'Text read'}{' '}
              · ask anything now
            </span>
          </span>
          <button
            type="button"
            className="toast-action"
            onClick={() => {
              setSelectedId(toast.id)
              setToast(null)
            }}
          >
            View
          </button>
          <button type="button" className="toast-close" aria-label="Dismiss" onClick={() => setToast(null)}>
            <IconClose size={16} />
          </button>
        </div>
      )}
    </div>
  )
}

export default Documents
