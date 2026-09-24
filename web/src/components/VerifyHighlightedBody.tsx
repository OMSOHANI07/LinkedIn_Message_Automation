const VERIFY_SPLIT = /(\[VERIFY[^\]]*\])/gi

export function VerifyHighlightedBody({ text }: { text: string }) {
  const parts = text.split(VERIFY_SPLIT)
  return (
    <>
      {parts.map((part, i) =>
        /^\[VERIFY/i.test(part) ? (
          <mark
            key={i}
            className="rounded bg-clay-soft px-1 py-0.5 font-medium text-clay-strong not-italic"
          >
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  )
}
