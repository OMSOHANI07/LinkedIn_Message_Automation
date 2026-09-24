import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { WeekStats } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { Skeleton } from '../components/Skeleton'

export function ThisWeek() {
  const [stats, setStats] = useState<WeekStats | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.weekStats().then(setStats).catch((e) => setError(String(e)))
  }, [])

  return (
    <div>
      <h1 className="font-serif text-2xl font-semibold">This Week</h1>
      <p className="text-sm text-ink-soft">Progress toward three posts, and what's waiting on you.</p>

      {error && <p className="mt-6 text-sm text-rose">{error}</p>}

      {!stats && !error && (
        <div className="mt-6 rounded-lg border border-hairline bg-paper-raised p-6">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="mt-4 h-3 w-full" />
        </div>
      )}

      {stats && (
        <>
          <div className="mt-6 rounded-lg border border-hairline bg-paper-raised p-6">
            <div className="flex items-end justify-between">
              <span className="font-mono text-3xl font-semibold text-ink">
                {stats.approved_this_week}
                <span className="text-lg text-ink-faint">/{stats.target}</span>
              </span>
              <span className="text-sm text-ink-soft">approved this week</span>
            </div>
            <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-paper-sunken">
              <div
                className="h-full rounded-full bg-sage transition-all"
                style={{
                  width: `${Math.min(100, (stats.approved_this_week / stats.target) * 100)}%`,
                }}
              />
            </div>
          </div>

          <h2 className="mt-8 font-serif text-lg font-semibold">Queued for review</h2>
          {stats.queued_drafts.length === 0 ? (
            <div className="mt-3">
              <EmptyState
                title="Nothing waiting on you"
                description="Drafted posts you haven't approved or discarded yet will show up here."
              />
            </div>
          ) : (
            <ul className="mt-3 divide-y divide-hairline rounded-lg border border-hairline bg-paper-raised">
              {stats.queued_drafts.map((draft) => (
                <li key={draft.id}>
                  <Link
                    to={`/notes/${draft.note_id}`}
                    className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-paper-sunken/60"
                  >
                    <p className="line-clamp-1 text-sm text-ink">{draft.body}</p>
                    <span className="whitespace-nowrap font-mono text-xs text-ink-faint">
                      {draft.word_count}w
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}
