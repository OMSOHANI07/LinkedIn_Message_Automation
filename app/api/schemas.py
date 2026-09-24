"""Request/response shapes for the dashboard API (kept separate from the
AI-facing pipeline schemas in app.pipeline.schemas)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import DecisionActor, DraftDecision, NoteSource, NoteStatus


class _ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DraftNewsOut(_ORMBase):
    id: int
    title: str
    publisher: str
    published_at: str | None
    url: str
    relevance: int
    reason: str
    query: str
    created_at: datetime


class DraftOut(_ORMBase):
    id: int
    note_id: int
    version: int
    body: str
    category: str | None = None
    word_count: int
    verify_count: int
    checklist: dict | None
    redraft_instruction: str | None
    created_at: datetime
    is_current: bool
    human_edited: bool = False
    editor_scores: dict | None = None
    editor_issues: list[str] | None = None
    unsupported_claims: list[str] | None = None
    final_score: float | None = None
    evaluated_at: datetime | None = None
    decision: DraftDecision | None = None
    block_reasons: list[str] | None = None
    auto_redraft_count: int = 0
    decided_by: DecisionActor | None = None
    decided_at: datetime | None = None
    news_checked_at: datetime | None = None
    news: list[DraftNewsOut] = []


class NoteOut(_ORMBase):
    id: int
    text: str
    source: NoteSource
    telegram_message_id: int | None
    received_at: datetime
    status: NoteStatus
    score: float | None
    publishable: bool | None
    category: str | None
    core_insight: str | None
    suggested_hook_type: str | None
    missing_facts: list[str] | None
    triage_reason: str | None
    triaged_at: datetime | None
    current_draft: DraftOut | None = None


class NoteWithDraftsOut(NoteOut):
    drafts: list[DraftOut] = []


class RedraftRequest(BaseModel):
    instruction: str | None = None


class EditDraftRequest(BaseModel):
    body: str


class WeekStatsOut(BaseModel):
    approved_this_week: int
    target: int = 3
    week_starts: datetime
    queued_drafts: list[DraftOut]


class ImportResult(BaseModel):
    imported: int
    notes: list[NoteOut]
