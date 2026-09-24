import type { Draft } from '../api/types'

export function RelatedNewsCard({ draft }: { draft: Draft }) {
  if (!draft.news_checked_at) {
    return null // stage 5 hasn't run yet (not approved, or not checked)
  }

  if (draft.news.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-hairline p-4">
        <p className="font-mono text-[11px] uppercase tracking-wide text-ink-faint">Related news</p>
        <p className="mt-1.5 text-sm text-ink-soft">
          No relevant recent news found for this topic. The post stands on its own.
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-hairline bg-clay-soft p-4">
      <p className="font-mono text-[11px] uppercase tracking-wide text-clay-strong">Related news</p>
      <ul className="mt-2 space-y-3">
        {draft.news.map((item) => (
          <li key={item.id} className="border-t border-clay/20 pt-2.5 first:border-t-0 first:pt-0">
            <p className="text-sm font-medium text-ink">{item.title}</p>
            <p className="mt-0.5 font-mono text-[11px] text-clay-strong">
              {item.publisher}
              {item.published_at ? ` · ${item.published_at}` : ''} · relevance {item.relevance}/10
            </p>
            <p className="mt-1 text-xs italic text-ink-soft">{item.reason}</p>
            <a
              href={item.url}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-block text-xs text-clay-strong underline decoration-clay/40 underline-offset-2 hover:decoration-clay"
            >
              Read source ↗
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}
