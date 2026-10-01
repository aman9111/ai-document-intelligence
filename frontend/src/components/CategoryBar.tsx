import { CATEGORY_LABELS } from '../types'

// One coloured bar split by how many pages each category has
function CategoryBar({ scores, size = 'md' }: { scores: Record<string, number> | null; size?: 'sm' | 'md' }) {
  const entries = Object.entries(scores ?? {}).filter(([, count]) => count > 0)

  if (entries.length === 0) return <span className={`cat-bar cat-bar-${size} cat-bar-empty`} />

  return (
    <span
      className={`cat-bar cat-bar-${size}`}
      role="img"
      aria-label={entries.map(([key, count]) => `${CATEGORY_LABELS[key] ?? key} ${count}`).join(', ')}
    >
      {entries.map(([key, count]) => (
        <span key={key} className={`cat-seg cat-${key}`} style={{ flexGrow: count }} />
      ))}
    </span>
  )
}

export default CategoryBar
