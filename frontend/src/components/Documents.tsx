import { useCallback, useEffect, useRef, useState } from 'react'
import type { ChangeEvent, DragEvent } from 'react'
import { API_BASE_URL, getErrorMessage } from '../api'
import DocumentSearch from './DocumentSearch'
import DocumentText from './DocumentText'

interface DocumentItem {
  id: number
  original_filename: string
  content_type: string
  size_bytes: number
  status: string
  created_at: string
}

interface DocumentsProps {
  token: string
  onUnauthorized: () => void
}

const ACCEPTED_FILES = '.pdf,.docx,.png,.jpg,.jpeg'
const POLL_INTERVAL_MS = 3000

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function getFileLabel(contentType: string): string {
  if (contentType === 'application/pdf') return 'PDF'
  if (contentType.startsWith('image/')) return 'IMG'
  return 'DOC'
}

function Documents({ token, onUnauthorized }: DocumentsProps) {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isUploading, setIsUploading] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [viewingDocument, setViewingDocument] = useState<DocumentItem | null>(null)
  const [searchingDocument, setSearchingDocument] = useState<DocumentItem | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

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
        if (data) setDocuments(data)
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

  async function uploadFile(file: File) {
    setError(null)
    setIsUploading(true)

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
        setError(getErrorMessage(data.detail, 'Upload failed'))
        return
      }

      setDocuments((current) => [data as DocumentItem, ...current])
    } catch {
      setError('Could not reach the server')
    } finally {
      setIsUploading(false)
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (file) uploadFile(file)
    event.target.value = ''
  }

  function handleDrop(event: DragEvent) {
    event.preventDefault()
    setIsDragging(false)
    const file = event.dataTransfer.files[0]
    if (file) uploadFile(file)
  }

  async function handleOpen(document: DocumentItem) {
    // The file needs the auth header, so a plain <a href> won't work.
    // Open the tab first (so popup blockers allow it), then load the file.
    const newTab = window.open('', '_blank')

    try {
      const response = await fetch(`${API_BASE_URL}/documents/${document.id}/file`, {
        headers: authHeader,
      })

      if (!response.ok) throw new Error()

      const blob = await response.blob()
      const url = URL.createObjectURL(blob)

      if (newTab) newTab.location.href = url
      else window.open(url, '_blank')
    } catch {
      newTab?.close()
      setError('Could not open the file')
    }
  }

  async function handleProcess(document: DocumentItem) {
    setError(null)

    try {
      const response = await fetch(`${API_BASE_URL}/documents/${document.id}/process`, {
        method: 'POST',
        headers: authHeader,
      })

      if (response.status === 401) return onUnauthorized()

      const data = await response.json()

      if (!response.ok) {
        setError(getErrorMessage(data.detail, 'Could not process the file'))
        return
      }

      setDocuments((current) =>
        current.map((d) => (d.id === document.id ? (data as DocumentItem) : d)),
      )
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

  return (
    <section className="documents">
      <div
        className={`dropzone${isDragging ? ' dropzone-active' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
      >
        <span className="dropzone-icon" aria-hidden="true">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 16V4M7 9l5-5 5 5" />
            <path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
          </svg>
        </span>
        <p className="dropzone-title">
          {isUploading ? 'Uploading...' : 'Drag & drop a file here'}
        </p>
        <p className="dropzone-hint">PDF, DOCX, PNG or JPG · up to 10 MB</p>

        <button
          type="button"
          className="btn btn-primary"
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
        >
          Choose file
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_FILES}
          onChange={handleFileChange}
          hidden
        />
      </div>

      {error && <p className="login-error">{error}</p>}

      <h2 className="section-title">
        My documents <span className="count-badge">{documents.length}</span>
      </h2>

      {isLoading ? (
        <p className="subtitle">Loading...</p>
      ) : documents.length === 0 ? (
        <div className="empty-state">
          <strong>No documents yet</strong>
          Upload your first file to get started.
        </div>
      ) : (
        <ul className="doc-list">
          {documents.map((document) => (
            <li key={document.id} className="doc-item">
              <span className={`doc-icon doc-icon-${getFileLabel(document.content_type).toLowerCase()}`}>
                {getFileLabel(document.content_type)}
              </span>
              <div className="doc-info">
                <p className="doc-name" title={document.original_filename}>
                  {document.original_filename}
                </p>
                <p className="doc-meta">
                  {formatSize(document.size_bytes)} ·{' '}
                  {new Date(document.created_at).toLocaleDateString()} ·{' '}
                  <span className={`status-pill status-${document.status}`}>
                    {document.status}
                  </span>
                </p>
              </div>
              <div className="doc-actions">
                {document.status === 'ready' && (
                  <>
                    <button type="button" className="btn-icon" onClick={() => setSearchingDocument(document)}>
                      Search
                    </button>
                    <button type="button" className="btn-icon" onClick={() => setViewingDocument(document)}>
                      View text
                    </button>
                  </>
                )}
                {(document.status === 'uploaded' || document.status === 'failed') && (
                  <button type="button" className="btn-icon" onClick={() => handleProcess(document)}>
                    {document.status === 'failed' ? 'Retry' : 'Extract text'}
                  </button>
                )}
                <button type="button" className="btn-icon" onClick={() => handleOpen(document)}>
                  Open
                </button>
                <button type="button" className="btn-icon btn-icon-danger" onClick={() => handleDelete(document)}>
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {searchingDocument && (
        <DocumentSearch
          documentId={searchingDocument.id}
          filename={searchingDocument.original_filename}
          token={token}
          onClose={() => setSearchingDocument(null)}
          onReprocess={() => {
            handleProcess(searchingDocument)
            setSearchingDocument(null)
          }}
        />
      )}

      {viewingDocument && (
        <DocumentText
          documentId={viewingDocument.id}
          filename={viewingDocument.original_filename}
          token={token}
          onClose={() => setViewingDocument(null)}
        />
      )}
    </section>
  )
}

export default Documents
