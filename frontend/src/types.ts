export interface DocumentItem {
  id: number
  original_filename: string
  content_type: string
  size_bytes: number
  status: string
  created_at: string
  doc_type: string | null
  // Pages per category, e.g. {"medical": 2, "financial": 6}
  doc_type_scores: Record<string, number> | null
  // While processing: "reading" (OCR + search index) or "sorting" (page types)
  processing_step: string | null
}

export interface PageItem {
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

export interface TypeOption {
  value: string
  label: string
  category: string
}

export interface ClassificationOptions {
  categories: Record<string, string>
  types: TypeOption[]
}

export const FAILED = 'failed'

export const CATEGORY_LABELS: Record<string, string> = {
  insurance: 'Insurance',
  medical: 'Medical',
  financial: 'Financial',
  kyc: 'KYC',
  other: 'Other',
  failed: 'Unreadable',
}

// A first question to suggest for each kind of page in the document
export const SUGGESTED_QUESTIONS: Record<string, string> = {
  financial: 'What is the total bill amount?',
  medical: 'Which medicines were prescribed?',
  insurance: 'What does the policy cover?',
  kyc: 'Whose name is on the ID?',
  other: 'What is this document about?',
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function getFileLabel(contentType: string): string {
  if (contentType === 'application/pdf') return 'PDF'
  if (contentType.startsWith('image/')) return 'IMG'
  return 'DOC'
}

export function pageCount(document: DocumentItem): number {
  return Object.values(document.doc_type_scores ?? {}).reduce((sum, n) => sum + n, 0)
}

export const PROCESS_STEPS = ['Uploading', 'Reading text', 'Sorting pages', 'Ready']

// Which of PROCESS_STEPS a document on the server is at
export function processStepIndex(document: DocumentItem): number {
  return document.processing_step === 'sorting' ? 2 : 1
}
