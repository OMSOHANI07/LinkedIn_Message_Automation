import { Link } from 'react-router-dom'
import type { Note } from '../api/types'
import { CategoryTag } from './CategoryTag'
import { DecisionBadge } from './DecisionBadge'
import { ScoreChip } from './ScoreChip'
import { StatusBadge } from './StatusBadge'

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).getTime()
  const mins = Math.round(diffMs / 60000)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return `${days}d ago`
}

export function NoteCard({ note }: { note: Note }) {
  return (
    <Link
      to={`/notes/${note.id}`}
      className="group block rounded-lg border border-hairline bg-paper-raised p-4 transition hover:border-sage/50 hover:shadow-[0_1px_0_0_var(--color-sage)]"
    >
      <div className="flex flex-wrap items-center gap-2">
        <ScoreChip score={note.score} size="sm" />
        <CategoryTag category={note.category} />
        {note.current_draft?.decision && (
          <DecisionBadge decision={note.current_draft.decision} finalScore={note.current_draft.final_score} size="sm" />
        )}
        <span className="ml-auto font-mono text-[11px] text-ink-faint">{timeAgo(note.received_at)}</span>
      </div>
      <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-ink">{note.text}</p>
      {note.current_draft?.decision === 'rejected' && note.current_draft.block_reasons?.[0] ? (
        <p className="mt-2.5 line-clamp-2 text-xs italic text-rose">{note.current_draft.block_reasons[0]}</p>
      ) : (
        note.triage_reason && (
          <p className="mt-2.5 line-clamp-2 text-xs italic text-ink-soft">{note.triage_reason}</p>
        )
      )}
      <div className="mt-3 flex items-center justify-between border-t border-hairline pt-2.5">
        <StatusBadge status={note.status} />
        <span className="text-xs text-ink-faint capitalize">{note.source}</span>
      </div>
    </Link>
  )
}
