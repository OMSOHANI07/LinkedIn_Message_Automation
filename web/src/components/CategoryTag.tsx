import { CATEGORY_LABELS, type Category } from '../api/types'

export function CategoryTag({ category }: { category: Category | null }) {
  if (!category) {
    return <span className="text-xs text-ink-faint font-mono">unscored</span>
  }
  const label = CATEGORY_LABELS[category] ?? category
  return (
    <span className="inline-flex items-center gap-1.5 rounded border border-hairline bg-paper-sunken px-2 py-0.5 text-xs text-ink-soft">
      <span className="font-mono font-semibold text-ink">{category}</span>
      <span className="hidden sm:inline">{label}</span>
    </span>
  )
}
