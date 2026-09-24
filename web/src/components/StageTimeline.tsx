import type { Draft } from '../api/types'

function formatTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso.endsWith('Z') ? iso : `${iso}Z`)
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function StageTimeline({ draft }: { draft: Draft }) {
  const isApproved = draft.decision === 'approved'
  const isRejected = draft.decision === 'rejected'

  const stages = [
    { label: 'Drafted', timestamp: draft.created_at },
    { label: 'Evaluated', timestamp: draft.evaluated_at },
    {
      label: isApproved ? 'Approved' : isRejected ? 'Rejected' : 'Decided',
      timestamp: draft.decided_at,
    },
    ...(isRejected ? [] : [{ label: 'News attached', timestamp: draft.news_checked_at }]),
  ]

  return (
    <ol className="space-y-0">
      {stages.map((stage, i) => {
        const done = Boolean(stage.timestamp)
        const isLast = i === stages.length - 1
        return (
          <li key={stage.label} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span
                className={`mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full ${
                  done ? 'bg-sage' : 'border border-hairline bg-paper'
                }`}
              />
              {!isLast && <span className="w-px flex-1 bg-hairline" />}
            </div>
            <div className="pb-3">
              <p className={`text-sm ${done ? 'text-ink' : 'text-ink-faint'}`}>{stage.label}</p>
              <p className="font-mono text-[11px] text-ink-faint">
                {done ? formatTime(stage.timestamp) : 'pending'}
              </p>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
