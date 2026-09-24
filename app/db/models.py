"""SQLModel tables for notes, drafts and news angles."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlmodel import JSON, Column, Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NoteStatus(str, enum.Enum):
    NEW = "new"
    TRIAGED = "triaged"
    DRAFTED = "drafted"
    APPROVED = "approved"
    DISCARDED = "discarded"


class NoteSource(str, enum.Enum):
    TELEGRAM = "telegram"
    IMPORT = "import"
    MANUAL = "manual"


class DraftDecision(str, enum.Enum):
    """Binary verdict: score >= threshold AND no hard blocks -> APPROVED,
    otherwise REJECTED. Always computed regardless of mode; `mode` only
    controls whether APPROVED is applied automatically or left for a button
    press (see AutoApproveMode)."""

    APPROVED = "approved"
    REJECTED = "rejected"


class AutoApproveMode(str, enum.Enum):
    OFF = "off"  # verdict still shown, but always requires a button press
    ON = "on"  # APPROVED verdicts are applied automatically


class DecisionActor(str, enum.Enum):
    SYSTEM = "system"
    MEERA = "meera"


class Note(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    text: str
    source: NoteSource = Field(default=NoteSource.TELEGRAM)
    telegram_message_id: int | None = Field(default=None, index=True)
    received_at: datetime = Field(default_factory=_utcnow)
    status: NoteStatus = Field(default=NoteStatus.NEW, index=True)

    # Triage output (AI call #1) — flattened onto the note, one triage per note.
    score: float | None = None
    publishable: bool | None = None
    category: str | None = None
    core_insight: str | None = None
    suggested_hook_type: str | None = None
    missing_facts: list[str] | None = Field(default=None, sa_column=Column(JSON))
    triage_reason: str | None = None
    triaged_at: datetime | None = None


class Draft(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    note_id: int = Field(foreign_key="note.id", index=True)
    version: int = Field(default=1)
    body: str
    body_hash: str | None = Field(default=None, index=True)  # set at evaluation; checked before any Copy action
    category: str | None = None  # the draft's own self-classification (A-G), set when drafted
    word_count: int = 0
    verify_count: int = 0
    checklist: dict | None = Field(default=None, sa_column=Column(JSON))
    redraft_instruction: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)  # = "drafted" timestamp, stage 2
    is_current: bool = Field(default=True, index=True)
    human_edited: bool = Field(default=False)

    # Editor scoring (AI call #3) - five dimensions, 0-10 each. Set at stage 3.
    editor_scores: dict | None = Field(default=None, sa_column=Column(JSON))
    editor_issues: list[str] | None = Field(default=None, sa_column=Column(JSON))
    unsupported_claims: list[str] | None = Field(default=None, sa_column=Column(JSON))
    final_score: float | None = None
    evaluated_at: datetime | None = None  # stage 3 completion

    # Decision engine output. Set at stage 4.
    decision: DraftDecision | None = Field(default=None, index=True)
    block_reasons: list[str] | None = Field(default=None, sa_column=Column(JSON))
    # Repurposed: no more automatic redraft loop, so this now just counts how
    # many times this note's draft chain was manually redrafted via the button.
    auto_redraft_count: int = Field(default=0)

    # Who last decided this draft's fate, and when (SYSTEM = the initial
    # computed verdict at stage 4; MEERA = a later button press).
    decided_by: DecisionActor | None = None
    decided_at: datetime | None = None

    # Stage 5 (approved only) - see DraftNews for the actual items.
    news_checked_at: datetime | None = None  # set once stage 5 finishes, found or not
    news_queries: list[str] | None = Field(default=None, sa_column=Column(JSON))  # reused by "Other news"

    # Telegram message ids for this draft's three messages, so buttons can
    # edit the right one in place instead of sending a new message each time.
    telegram_chat_id: int | None = None
    draft_message_id: int | None = None  # stage 2
    decision_message_id: int | None = None  # stage 3/4, edited in place through both
    news_message_id: int | None = None  # stage 5


class DraftNews(SQLModel, table=True):
    """A related-news item attached to an approved draft (stage 5). Only
    headline/publisher/date/link are stored - never article text, per
    copyright: this is a citation, not a reproduction."""

    id: int | None = Field(default=None, primary_key=True)
    draft_id: int = Field(foreign_key="draft.id", index=True)
    title: str
    publisher: str
    published_at: str | None = None  # RSS date string, kept as-is (formats vary by publisher)
    url: str
    relevance: int = Field(ge=0, le=10)
    reason: str
    query: str
    created_at: datetime = Field(default_factory=_utcnow)


class NewsQueryCache(SQLModel, table=True):
    """Caches Google News RSS results per query for NEWS_CACHE_HOURS, so a
    redraft or "Other news" doesn't refetch the same query."""

    id: int | None = Field(default=None, primary_key=True)
    query: str = Field(index=True, unique=True)
    fetched_at: datetime = Field(default_factory=_utcnow)
    items_json: str  # JSON list of {title, publisher, published_at, link}


class AppSettings(SQLModel, table=True):
    """Single-row runtime-mutable settings, controlled via /autoapprove,
    /threshold and /settings. id is always 1."""

    id: int | None = Field(default=1, primary_key=True)
    mode: AutoApproveMode = Field(default=AutoApproveMode.ON)
    auto_approve_threshold: int = Field(default=85)
    weekly_cap: int = Field(default=3)  # informational only, for /week and /settings - doesn't gate the decision

    weight_facts: float = Field(default=0.2)
    weight_voice: float = Field(default=0.2)
    weight_structure: float = Field(default=0.2)
    weight_hook: float = Field(default=0.2)
    weight_reader: float = Field(default=0.2)

    nudge_enabled: bool = Field(default=True)
    nudge_hour_ist: int = Field(default=19)
    last_nudge_date: str | None = None


class DecisionLog(SQLModel, table=True):
    """Audit trail: every system or Meera decision on a draft."""

    id: int | None = Field(default=None, primary_key=True)
    draft_id: int = Field(foreign_key="draft.id", index=True)
    actor: DecisionActor
    action: str
    previous_decision: str | None = None
    new_decision: str | None = None
    final_score: float | None = None
    at: datetime = Field(default_factory=_utcnow)
