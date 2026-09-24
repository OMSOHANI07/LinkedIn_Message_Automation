export type NoteStatus = 'new' | 'triaged' | 'drafted' | 'approved' | 'discarded'
export type NoteSource = 'telegram' | 'import' | 'manual'
export type Category = 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G'
export type DraftDecision = 'approved' | 'rejected'

export interface EditorScores {
  facts: number
  voice: number
  structure: number
  hook: number
  reader: number
}

export const CATEGORY_LABELS: Record<Category, string> = {
  A: 'Ingredient Deep-Dive',
  B: 'Founder Story',
  C: 'India-Specific Context',
  D: 'Industry Transparency',
  E: 'Formulation Science',
  F: 'Brand Philosophy',
  G: 'Consumer Education',
}

export const STATUS_LABELS: Record<NoteStatus, string> = {
  new: 'New',
  triaged: 'Triaged',
  drafted: 'Drafted',
  approved: 'Approved',
  discarded: 'Discarded',
}

export interface Note {
  id: number
  text: string
  source: NoteSource
  telegram_message_id: number | null
  received_at: string
  status: NoteStatus
  score: number | null
  publishable: boolean | null
  category: Category | null
  core_insight: string | null
  suggested_hook_type: string | null
  missing_facts: string[] | null
  triage_reason: string | null
  triaged_at: string | null
  current_draft: Draft | null
}

export interface Checklist {
  word_count: number
  word_count_in_range: boolean
  verify_count: number
  verify_items: string[]
  has_emojis: boolean
  has_hashtags: boolean
  has_bullets: boolean
  has_headers: boolean
  has_bold: boolean
  has_exclamation: boolean
  has_em_dash: boolean
  has_audience_question: boolean
  no_banned_formatting: boolean
  uses_spaced_hyphen_dashes: boolean
}

export interface DraftNews {
  id: number
  title: string
  publisher: string
  published_at: string | null
  url: string
  relevance: number
  reason: string
  query: string
  created_at: string
}

export interface Draft {
  id: number
  note_id: number
  version: number
  body: string
  category: Category | null
  word_count: number
  verify_count: number
  checklist: Checklist | null
  redraft_instruction: string | null
  created_at: string
  is_current: boolean
  human_edited: boolean
  editor_scores: EditorScores | null
  editor_issues: string[] | null
  unsupported_claims: string[] | null
  final_score: number | null
  evaluated_at: string | null
  decision: DraftDecision | null
  block_reasons: string[] | null
  auto_redraft_count: number
  decided_at: string | null
  news_checked_at: string | null
  news: DraftNews[]
}

export interface NoteWithDrafts extends Note {
  drafts: Draft[]
}

export interface WeekStats {
  approved_this_week: number
  target: number
  week_starts: string
  queued_drafts: Draft[]
}

export interface ImportResult {
  imported: number
  notes: Note[]
}
