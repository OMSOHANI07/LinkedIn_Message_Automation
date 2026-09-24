import type { Checklist } from '../api/types'

const ITEMS: { key: keyof Checklist; label: string; pass: (c: Checklist) => boolean }[] = [
  { key: 'word_count_in_range', label: '450-650 words', pass: (c) => c.word_count_in_range },
  { key: 'no_banned_formatting', label: 'No emoji/hashtags/bullets/bold/headers', pass: (c) => c.no_banned_formatting },
  {
    key: 'uses_spaced_hyphen_dashes',
    label: 'Spaced hyphens, not em dashes',
    pass: (c) => c.uses_spaced_hyphen_dashes,
  },
  { key: 'has_audience_question', label: 'No audience-question close', pass: (c) => !c.has_audience_question },
]

export function ChecklistTicks({ checklist }: { checklist: Checklist | null }) {
  if (!checklist) return null
  return (
    <ul className="space-y-1.5">
      {ITEMS.map((item) => {
        const ok = item.pass(checklist)
        return (
          <li key={item.key} className="flex items-center gap-2 text-xs">
            <span
              className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] ${
                ok ? 'bg-sage-soft text-sage-strong' : 'bg-rose-soft text-rose'
              }`}
            >
              {ok ? '✓' : '!'}
            </span>
            <span className={ok ? 'text-ink-soft' : 'text-rose'}>{item.label}</span>
          </li>
        )
      })}
      <li className="flex items-center gap-2 text-xs">
        <span
          className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] ${
            checklist.verify_count === 0 ? 'bg-sage-soft text-sage-strong' : 'bg-clay-soft text-clay-strong'
          }`}
        >
          {checklist.verify_count === 0 ? '✓' : checklist.verify_count}
        </span>
        <span className="text-ink-soft">
          {checklist.verify_count === 0
            ? 'No [VERIFY] items'
            : `${checklist.verify_count} item(s) need Meera's facts`}
        </span>
      </li>
    </ul>
  )
}
