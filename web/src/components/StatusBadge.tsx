import { STATUS_LABELS, type NoteStatus } from '../api/types'

const DOT_CLASSES: Record<NoteStatus, string> = {
  new: 'bg-ink-faint',
  triaged: 'bg-clay',
  drafted: 'bg-sage',
  approved: 'bg-sage-strong',
  discarded: 'bg-rose',
}

export function StatusBadge({ status }: { status: NoteStatus }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-ink-soft">
      <span className={`h-1.5 w-1.5 rounded-full ${DOT_CLASSES[status]}`} />
      {STATUS_LABELS[status]}
    </span>
  )
}
