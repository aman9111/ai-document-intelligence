export const API_BASE_URL = 'http://localhost:8000'

export function getErrorMessage(detail: unknown, fallback: string): string {
  // FastAPI sends a string for our own errors
  // and a list of field errors for validation failures (422)
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
  return fallback
}
