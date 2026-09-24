import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { Note } from '../api/types'
import { CategoryTag } from '../components/CategoryTag'
import { EmptyState } from '../components/EmptyState'
import { ScoreChip } from '../components/ScoreChip'
import { Skeleton } from '../components/Skeleton'

export function Backlog() {
  const [notes, setNotes] = useState<Note[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [drafting, setDrafting] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importMessage, setImportMessage] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const navigate = useNavigate()

  const load = useCallback(() => {
    setNotes(null)
    api
      .backlog(20)
      .then(setNotes)
      .catch((e) => setError(String(e)))
  }, [])

  useEffect(load, [load])

  async function handleDraftNext() {
    setDrafting(true)
    setError(null)
    try {
      const drafts = await api.draftNext()
      if (drafts.length > 0) {
        navigate(`/notes/${drafts[0].note_id}`)
      } else {
        setImportMessage('Nothing publishable in the backlog right now.')
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setDrafting(false)
    }
  }

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return
    setImporting(true)
    setImportMessage(null)
    try {
      const result = await api.importUpload(Array.from(files))
      setImportMessage(`Imported ${result.imported} new note(s).`)
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setImporting(false)
    }
  }

  async function handleImportFolder() {
    setImporting(true)
    setImportMessage(null)
    try {
      const result = await api.importFolder()
      setImportMessage(`Imported ${result.imported} new note(s) from notes/.`)
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setImporting(false)
    }
  }

  return (
    <div>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-serif text-2xl font-semibold">Backlog</h1>
          <p className="text-sm text-ink-soft">Ranked, unused notes - highest score first.</p>
        </div>
        <button
          type="button"
          onClick={handleDraftNext}
          disabled={drafting}
          className="rounded-md bg-sage px-3.5 py-2 text-sm font-medium text-paper-raised transition hover:bg-sage-strong disabled:opacity-50"
        >
          {drafting ? 'Drafting...' : 'Draft next best note'}
        </button>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          handleFiles(e.dataTransfer.files)
        }}
        className={`mt-6 flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center transition ${
          dragOver ? 'border-sage bg-sage-soft' : 'border-hairline'
        }`}
      >
        <p className="text-sm text-ink-soft">Drag .txt or .md notes here to import your backlog</p>
        <div className="flex items-center gap-3">
          <label className="cursor-pointer rounded-md border border-hairline bg-paper-raised px-3 py-1.5 text-xs text-ink hover:border-sage">
            Choose files
            <input
              type="file"
              multiple
              accept=".txt,.md"
              className="hidden"
              onChange={(e) => handleFiles(e.target.files)}
            />
          </label>
          <button
            type="button"
            onClick={handleImportFolder}
            disabled={importing}
            className="rounded-md border border-hairline bg-paper-raised px-3 py-1.5 text-xs text-ink hover:border-sage disabled:opacity-50"
          >
            Import notes/ folder
          </button>
        </div>
        {importMessage && <p className="font-mono text-xs text-sage-strong">{importMessage}</p>}
      </div>

      {error && <p className="mt-6 text-sm text-rose">{error}</p>}

      {notes === null && !error && (
        <div className="mt-6 space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      )}

      {notes !== null && notes.length === 0 && (
        <div className="mt-6">
          <EmptyState title="Backlog is empty" description="Every note has been used or discarded." />
        </div>
      )}

      {notes !== null && notes.length > 0 && (
        <ol className="mt-6 divide-y divide-hairline rounded-lg border border-hairline bg-paper-raised">
          {notes.map((note, i) => (
            <li key={note.id}>
              <button
                type="button"
                onClick={() => navigate(`/notes/${note.id}`)}
                className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-paper-sunken/60"
              >
                <span className="font-mono text-xs text-ink-faint">{String(i + 1).padStart(2, '0')}</span>
                <ScoreChip score={note.score} size="sm" />
                <CategoryTag category={note.category} />
                <p className="ml-1 line-clamp-1 flex-1 text-sm text-ink">{note.text}</p>
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
