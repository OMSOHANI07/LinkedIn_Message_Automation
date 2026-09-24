interface Props {
  score: number | null
  size?: 'sm' | 'md'
}

function tier(score: number): 'high' | 'mid' | 'low' {
  if (score >= 7.5) return 'high'
  if (score >= 5) return 'mid'
  return 'low'
}

const TIER_CLASSES: Record<string, string> = {
  high: 'border-sage/40 bg-sage-soft text-sage-strong dark:text-sage-strong',
  mid: 'border-clay/40 bg-clay-soft text-clay-strong',
  low: 'border-rose/30 bg-rose-soft text-rose',
}

export function ScoreChip({ score, size = 'md' }: Props) {
  if (score === null) {
    return (
      <span className="inline-flex items-center rounded-full border border-hairline px-2 py-0.5 font-mono text-xs text-ink-faint">
        —/10
      </span>
    )
  }
  const t = tier(score)
  const padding = size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs'
  return (
    <span
      className={`inline-flex items-center rounded-full border font-mono font-medium ${padding} ${TIER_CLASSES[t]}`}
      title={`Triage score: ${score.toFixed(1)} / 10`}
    >
      {score.toFixed(1)}/10
    </span>
  )
}
