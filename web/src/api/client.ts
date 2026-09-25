import type {
  Draft,
  ImportResult,
  Note,
  NoteStatus,
  NoteWithDrafts,
  WeekStats,
} from './types'

// In local dev this is empty and Vite's proxy forwards /api to the backend
// (see vite.config.ts). In production (e.g. a Vercel-hosted frontend calling
// a separately-hosted backend) set VITE_API_BASE_URL to that backend's origin.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      // ignore
    }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  listNotes: (params?: { status?: NoteStatus; category?: string }) => {
    const qs = new URLSearchParams()
    if (params?.status) qs.set('status', params.status)
    if (params?.category) qs.set('category', params.category)
    const suffix = qs.toString() ? `?${qs}` : ''
    return request<Note[]>(`/notes${suffix}`)
  },

  getNote: (id: number) => request<NoteWithDrafts>(`/notes/${id}`),

  draftNote: (id: number) => request<Draft>(`/notes/${id}/draft`, { method: 'POST' }),

  discardNote: (id: number) => request<Note>(`/notes/${id}/discard`, { method: 'POST' }),

  draftNext: () => request<Draft[]>('/drafts/next', { method: 'POST' }),

  approveDraft: (id: number) => request<Draft>(`/drafts/${id}/approve`, { method: 'POST' }),

  redraftDraft: (id: number, instruction?: string) =>
    request<Draft>(`/drafts/${id}/redraft`, {
      method: 'POST',
      body: JSON.stringify({ instruction: instruction || null }),
    }),

  editDraft: (id: number, body: string) =>
    request<Draft>(`/drafts/${id}`, { method: 'PATCH', body: JSON.stringify({ body }) }),

  backlog: (limit = 5) => request<Note[]>(`/backlog?limit=${limit}`),

  weekStats: () => request<WeekStats>('/week'),

  importFolder: () => request<ImportResult>('/import/folder', { method: 'POST' }),

  importUpload: async (files: File[]): Promise<ImportResult> => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    const res = await fetch('/api/import/upload', { method: 'POST', body: form })
    if (!res.ok) throw new Error(res.statusText)
    return res.json()
  },
}
