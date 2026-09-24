import type { DraftDecision } from '../api/types'

export function DecisionBadge({
  decision,
  finalScore,
  size = 'md',
}: {
  decision: DraftDecision
  finalScore: number | null
  size?: 'sm' | 'md'
}) {
  const approved = decision === 'approved'
  const padding = size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs'
  const scoreLabel = finalScore !== null ? ` · ${Math.round(finalScore)}/100` : ''
  return (
    <span
      className={`inline-flex items-center rounded-full border font-mono font-medium ${padding} ${
        approved
          ? 'border-sage/40 bg-sage-soft text-sage-strong'
          : 'border-rose/30 bg-rose-soft text-rose'
      }`}
      title={approved ? 'AI verdict: approved' : 'AI verdict: rejected'}
    >
      {approved ? '✅ Approved' : '❌ Rejected'}
      {scoreLabel}
    </span>
  )
}
