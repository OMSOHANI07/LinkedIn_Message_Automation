import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { CATEGORY_LABELS, STATUS_LABELS, type Category, type Note, type NoteStatus } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { NoteCard } from '../components/NoteCard'
import { NoteCardSkeleton } from '../components/Skeleton'

const STATUS_OPTIONS: (NoteStatus | 'all')[] = ['all', 'new', 'triaged', 'drafted', 'approved', 'discarded']
const CATEGORY_OPTIONS: (Category | 'all')[] = ['all', 'A', 'B', 'C', 'D', 'E', 'F', 'G']

export function Inbox() {
  const [notes, setNotes] = useState<Note[] | null>(null)
  const [status, setStatus] = useState<NoteStatus | 'all'>('all')
  const [category, setCategory] = useState<Category | 'all'>('all')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setNotes(null)
    api
      .listNotes({
        status: status === 'all' ? undefined : status,
        category: category === 'all' ? undefined : category,
      })
      .then((data) => !cancelled && setNotes(data))
      .catch((e) => !cancelled && setError(String(e)))
    return () => {
      cancelled = true
    }
  }, [status, category])

  const sorted = useMemo(
    () => (notes ?? []).slice().sort((a, b) => (b.score ?? -1) - (a.score ?? -1)),
    [notes],
  )

  return (
    <div>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-serif text-2xl font-semibold">Inbox</h1>
          <p className="text-sm text-ink-soft">Every note that's come in, triaged or not.</p>
        </div>
        <div className="flex gap-2">
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as NoteStatus | 'all')}
            className="rounded-md border border-hairline bg-paper-raised px-2.5 py-1.5 text-sm text-ink"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s === 'all' ? 'All statuses' : STATUS_LABELS[s]}
              </option>
            ))}
          </select>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as Category | 'all')}
            className="rounded-md border border-hairline bg-paper-raised px-2.5 py-1.5 text-sm text-ink"
          >
            {CATEGORY_OPTIONS.map((c) => (
              <option key={c} value={c}>
                {c === 'all' ? 'All categories' : `${c} · ${CATEGORY_LABELS[c]}`}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && <p className="mt-6 text-sm text-rose">{error}</p>}

      {notes === null && !error && (
        <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <NoteCardSkeleton key={i} />
          ))}
        </div>
      )}

      {notes !== null && sorted.length === 0 && (
        <div className="mt-6">
          <EmptyState
            title="No notes here yet"
            description="Drop a note into the Telegram channel, or import your backlog from the Backlog tab."
          />
        </div>
      )}

      {notes !== null && sorted.length > 0 && (
        <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {sorted.map((note) => (
            <NoteCard key={note.id} note={note} />
          ))}
        </div>
      )}
    </div>
  )
}
