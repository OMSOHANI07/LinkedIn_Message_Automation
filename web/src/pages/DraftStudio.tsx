import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { CATEGORY_LABELS, type Draft, type NoteWithDrafts } from '../api/types'
import { CategoryTag } from '../components/CategoryTag'
import { ChecklistTicks } from '../components/ChecklistTicks'
import { DecisionBadge } from '../components/DecisionBadge'
import { EmptyState } from '../components/EmptyState'
import { RelatedNewsCard } from '../components/RelatedNewsCard'
import { ScoreChip } from '../components/ScoreChip'
import { Skeleton } from '../components/Skeleton'
import { StageTimeline } from '../components/StageTimeline'
import { StatusBadge } from '../components/StatusBadge'
import { VerifyHighlightedBody } from '../components/VerifyHighlightedBody'

function wordCount(text: string): number {
  return text.trim().length === 0 ? 0 : text.trim().split(/\s+/).length
}

export function DraftStudio() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const noteId = Number(id)

  const [note, setNote] = useState<NoteWithDrafts | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [draftText, setDraftText] = useState('')
  const [redrafting, setRedrafting] = useState(false)
  const [instruction, setInstruction] = useState('')
  const [copied, setCopied] = useState(false);

  const currentDraft: Draft | undefined = note?.drafts.find((d) => d.is_current) ?? note?.drafts[0]

  const load = () => {
    api
      .getNote(noteId)
      .then((n) => {
        setNote(n)
        const d = n.drafts.find((x) => x.is_current) ?? n.drafts[0]
        setDraftText(d?.body ?? '')
      })
      .catch((e) => setError(String(e)))
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [noteId])

  const liveWordCount = useMemo(() => wordCount(draftText), [draftText])

  async function handleDraftThis() {
    setBusy('draft')
    try {
      await api.draftNote(noteId)
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(null)
    }
  }

  async function handleSaveEdit() {
    if (!currentDraft) return
    setBusy('save')
    try {
      await api.editDraft(currentDraft.id, draftText)
      setEditing(false)
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(null)
    }
  }

  async function handleApprove() {
    if (!currentDraft) return
    setBusy('approve')
    try {
      await api.approveDraft(currentDraft.id)
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(null)
    }
  }

  async function handleDiscard() {
    setBusy('discard')
    try {
      await api.discardNote(noteId)
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(null)
    }
  }

  async function handleRedraft() {
    if (!currentDraft) return
    setBusy('redraft')
    try {
      await api.redraftDraft(currentDraft.id, instruction || undefined)
      setInstruction('')
      setRedrafting(false)
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(null)
    }
  }

  function handleCopy() {
    navigator.clipboard.writeText(draftText).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    })
  }

  if (error) return <p className="text-sm text-rose">{error}</p>
  if (!note) {
    return (
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    )
  }

  const isFinal = note.status === 'approved' || note.status === 'discarded'

  return (
    <div>
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="mb-4 text-sm text-ink-soft hover:text-ink"
      >
        ← Back
      </button>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 lg:items-start">
        {/* LEFT: source material */}
        <div className="space-y-4">
          <div className="rounded-lg border border-hairline bg-paper-raised p-5">
            <div className="flex items-center justify-between">
              <p className="font-mono text-[11px] uppercase tracking-wide text-ink-faint">Original note</p>
              <StatusBadge status={note.status} />
            </div>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-ink">{note.text}</p>
          </div>

          <div className="rounded-lg border border-hairline bg-paper-raised p-5">
            <p className="font-mono text-[11px] uppercase tracking-wide text-ink-faint">Triage</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <ScoreChip score={note.score} />
              <CategoryTag category={note.category} />
              {note.publishable !== null && (
                <span className="text-xs text-ink-soft">{note.publishable ? 'publishable' : 'not now'}</span>
              )}
            </div>
            {note.core_insight && (
              <p className="mt-3 text-sm text-ink">
                <span className="font-mono text-[11px] text-ink-faint">thesis · </span>
                {note.core_insight}
              </p>
            )}
            {note.triage_reason && <p className="mt-2 text-xs italic text-ink-soft">{note.triage_reason}</p>}
            {note.missing_facts && note.missing_facts.length > 0 && (
              <ul className="mt-3 space-y-1 border-t border-hairline pt-2.5">
                {note.missing_facts.map((f, i) => (
                  <li key={i} className="text-xs text-clay-strong">
                    · {f}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {currentDraft && (
            <div className="rounded-lg border border-hairline bg-paper-raised p-5">
              <p className="mb-3 font-mono text-[11px] uppercase tracking-wide text-ink-faint">Pipeline stages</p>
              <StageTimeline draft={currentDraft} />
            </div>
          )}

          {currentDraft?.decision && (
            <div className="rounded-lg border border-hairline bg-paper-raised p-5">
              <div className="flex items-center justify-between">
                <p className="font-mono text-[11px] uppercase tracking-wide text-ink-faint">AI verdict</p>
                <DecisionBadge decision={currentDraft.decision} finalScore={currentDraft.final_score} />
              </div>
              {currentDraft.editor_scores && (
                <div className="mt-3 grid grid-cols-5 gap-2 font-mono text-[11px]">
                  {(['facts', 'voice', 'structure', 'hook', 'reader'] as const).map((dim) => (
                    <div key={dim} className="rounded border border-hairline bg-paper-sunken px-1.5 py-1 text-center">
                      <div className="text-ink-faint capitalize">{dim}</div>
                      <div className="text-ink">{currentDraft.editor_scores![dim]}/10</div>
                    </div>
                  ))}
                </div>
              )}
              {currentDraft.decision === 'rejected' && (
                <ul className="mt-3 space-y-1 border-t border-hairline pt-2.5">
                  {(currentDraft.block_reasons ?? []).map((r, i) => (
                    <li key={`b${i}`} className="text-xs text-rose">
                      · {r}
                    </li>
                  ))}
                  {(currentDraft.editor_issues ?? []).slice(0, 3).map((r, i) => (
                    <li key={`i${i}`} className="text-xs text-ink-soft">
                      · {r}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {currentDraft && <RelatedNewsCard draft={currentDraft} />}
        </div>

        {/* RIGHT: draft studio */}
        <div className="space-y-4">
          {!currentDraft ? (
            <EmptyState
              title="Not drafted yet"
              description="Run the drafting pipeline for this note to see a LinkedIn-ready draft here."
              action={
                <button
                  type="button"
                  onClick={handleDraftThis}
                  disabled={busy === 'draft'}
                  className="rounded-md bg-sage px-3.5 py-2 text-sm font-medium text-paper-raised hover:bg-sage-strong disabled:opacity-50"
                >
                  {busy === 'draft' ? 'Drafting...' : 'Draft this note'}
                </button>
              }
            />
          ) : (
            <div className="rounded-lg border border-hairline bg-paper-raised shadow-sm">
              <div className="flex items-center gap-3 border-b border-hairline p-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-sage-soft font-serif text-sm font-semibold text-sage-strong">
                  MP
                </div>
                <div>
                  <p className="text-sm font-medium text-ink">Meera Pillai</p>
                  <p className="text-xs text-ink-faint">Founder, Skinstinct</p>
                </div>
                <span className="ml-auto font-mono text-[11px] text-ink-faint">v{currentDraft.version}</span>
              </div>

              <div className="p-4">
                {editing ? (
                  <textarea
                    value={draftText}
                    onChange={(e) => setDraftText(e.target.value)}
                    rows={18}
                    className="w-full resize-y rounded-md border border-hairline bg-paper p-3 text-sm leading-relaxed text-ink focus:border-sage focus:outline-none"
                  />
                ) : (
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">
                    <VerifyHighlightedBody text={draftText} />
                  </p>
                )}
                <div className="mt-3 flex items-center justify-between font-mono text-xs text-ink-faint">
                  <span>{liveWordCount} words</span>
                </div>
              </div>

              <div className="border-t border-hairline p-4">
                <p className="mb-2 font-mono text-[11px] uppercase tracking-wide text-ink-faint">
                  Pre-publish checklist
                </p>
                <ChecklistTicks checklist={currentDraft.checklist} />
              </div>

              {!isFinal && (
                <div className="flex flex-wrap gap-2 border-t border-hairline p-4">
                  <button
                    type="button"
                    onClick={handleCopy}
                    className="rounded-md border border-hairline px-3 py-1.5 text-xs text-ink hover:border-sage"
                  >
                    {copied ? 'Copied ✓' : 'Copy to clipboard'}
                  </button>
                  {editing ? (
                    <button
                      type="button"
                      onClick={handleSaveEdit}
                      disabled={busy === 'save'}
                      className="rounded-md border border-hairline px-3 py-1.5 text-xs text-ink hover:border-sage disabled:opacity-50"
                    >
                      {busy === 'save' ? 'Saving...' : 'Save edit'}
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setEditing(true)}
                      className="rounded-md border border-hairline px-3 py-1.5 text-xs text-ink hover:border-sage"
                    >
                      Edit inline
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setRedrafting((v) => !v)}
                    className="rounded-md border border-hairline px-3 py-1.5 text-xs text-ink hover:border-sage"
                  >
                    Redraft
                  </button>
                  <button
                    type="button"
                    onClick={handleApprove}
                    disabled={busy === 'approve'}
                    className="rounded-md bg-sage px-3 py-1.5 text-xs font-medium text-paper-raised hover:bg-sage-strong disabled:opacity-50"
                  >
                    ✅ Approve
                  </button>
                  <button
                    type="button"
                    onClick={handleDiscard}
                    disabled={busy === 'discard'}
                    className="rounded-md border border-rose/40 px-3 py-1.5 text-xs text-rose hover:bg-rose-soft disabled:opacity-50"
                  >
                    🗑 Discard
                  </button>
                </div>
              )}

              {isFinal && (
                <div className="border-t border-hairline p-4">
                  <p className="text-xs text-ink-soft">
                    {note.status === 'approved'
                      ? 'Approved - ready for Meera to copy and post herself. Nothing was sent to LinkedIn.'
                      : 'Discarded - kept in the archive, will not be suggested again.'}
                  </p>
                </div>
              )}

              {redrafting && !isFinal && (
                <div className="border-t border-hairline bg-paper-sunken/50 p-4">
                  <label className="text-xs text-ink-soft" htmlFor="redraft-instruction">
                    One-line instruction for this redraft (optional)
                  </label>
                  <div className="mt-2 flex gap-2">
                    <input
                      id="redraft-instruction"
                      value={instruction}
                      onChange={(e) => setInstruction(e.target.value)}
                      placeholder="e.g. lead with the humidity data instead"
                      className="flex-1 rounded-md border border-hairline bg-paper px-3 py-1.5 text-sm text-ink focus:border-sage focus:outline-none"
                    />
                    <button
                      type="button"
                      onClick={handleRedraft}
                      disabled={busy === 'redraft'}
                      className="rounded-md bg-sage px-3 py-1.5 text-xs font-medium text-paper-raised hover:bg-sage-strong disabled:opacity-50"
                    >
                      {busy === 'redraft' ? 'Regenerating...' : 'Regenerate'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      {note.category && (
        <p className="mt-6 text-center font-mono text-[11px] text-ink-faint">
          {note.category} · {CATEGORY_LABELS[note.category]}
        </p>
      )}
    </div>
  )
}
