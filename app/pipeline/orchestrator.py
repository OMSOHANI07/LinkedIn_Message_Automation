"""Ties triage -> draft -> evaluate -> decide -> (approved) news together and
persists results. Shared by the Telegram bot, the API and the scheduler.

The pipeline is deliberately staged as separate functions (draft_only,
evaluate_draft, decide_draft, attach_news) rather than one monolithic call:
the bot shows/edits a Telegram message between each stage, and non-Telegram
callers (API/CLI/scheduler) just run them back to back via draft_for_note().
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from app.db.models import (
    DecisionActor,
    DecisionLog,
    Draft,
    DraftDecision,
    DraftNews,
    Note,
    NoteSource,
    NoteStatus,
)
from app.db.settings_store import get_settings
from app.pipeline.checklist import validate_checklist
from app.pipeline.decision import DecisionResult, decide, redraft_instruction_from_issues
from app.pipeline.draft import draft_post
from app.pipeline.editor import score_draft
from app.pipeline.news import find_related_news
from app.pipeline.schemas import EditorResult
from app.pipeline.triage import triage_note
from app.pipeline.week import week_start_utc

logger = logging.getLogger(__name__)

IMPORTABLE_SUFFIXES = {".txt", ".md"}


def get_recent_approved_topics(session: Session, limit: int = 5) -> list[str]:
    statement = (
        select(Note)
        .where(Note.status == NoteStatus.APPROVED)
        .order_by(Note.received_at.desc())
        .limit(limit)
    )
    notes = session.exec(statement).all()
    return [note.core_insight for note in notes if note.core_insight]


def triage_and_save(session: Session, note: Note) -> Note:
    recent_topics = get_recent_approved_topics(session)
    result = triage_note(note.text, recent_topics)
    note.score = result.score
    note.publishable = result.publishable
    note.category = result.category
    note.core_insight = result.core_insight
    note.suggested_hook_type = result.suggested_hook_type
    note.missing_facts = result.missing_facts
    note.triage_reason = result.reason
    note.triaged_at = datetime.now(timezone.utc)
    note.status = NoteStatus.TRIAGED
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def ensure_all_triaged(session: Session) -> None:
    new_notes = session.exec(select(Note).where(Note.status == NoteStatus.NEW)).all()
    for note in new_notes:
        try:
            triage_and_save(session, note)
        except Exception:
            logger.exception("Failed to triage note %s", note.id)


def rank_backlog(session: Session, limit: int = 5, triage_first: bool = True) -> list[Note]:
    if triage_first:
        ensure_all_triaged(session)
    statement = select(Note).where(
        Note.status.in_([NoteStatus.NEW, NoteStatus.TRIAGED])  # type: ignore[attr-defined]
    )
    notes = list(session.exec(statement).all())
    notes.sort(key=lambda n: (n.score is None, -(n.score or 0.0)))
    return notes[:limit]


# ---------------------------------------------------------------------------
# Weekly auto-approval cap (informational only, see AppSettings.weekly_cap)
# ---------------------------------------------------------------------------


def count_weekly_auto_approvals(session: Session) -> int:
    week_start = week_start_utc()
    statement = select(Draft).where(
        Draft.is_current == True,  # noqa: E712
        Draft.decision == DraftDecision.APPROVED,
        Draft.decided_by == DecisionActor.SYSTEM,
        Draft.created_at >= week_start,
    )
    return len(session.exec(statement).all())


def _log_decision(
    session: Session,
    *,
    draft_id: int,
    actor: DecisionActor,
    action: str,
    previous_decision: str | None,
    new_decision: str | None,
    final_score: float | None,
) -> None:
    session.add(
        DecisionLog(
            draft_id=draft_id,
            actor=actor,
            action=action,
            previous_decision=previous_decision,
            new_decision=new_decision,
            final_score=final_score,
        )
    )
    session.commit()


# ---------------------------------------------------------------------------
# Stage 2: draft only - no research, no scoring, no decision. Self-classifies.
# ---------------------------------------------------------------------------


def draft_only(
    session: Session, note: Note, redraft_instruction: str | None = None, is_redraft: bool = False
) -> Draft:
    prior_current = session.exec(
        select(Draft).where(Draft.note_id == note.id, Draft.is_current == True)  # noqa: E712
    ).first()

    previous_draft_body: str | None = None
    combined_instruction = redraft_instruction
    if is_redraft and prior_current:
        previous_draft_body = prior_current.body
        combined_instruction = redraft_instruction_from_issues(prior_current.editor_issues or [], redraft_instruction)

    if prior_current:
        prior_current.is_current = False
        session.add(prior_current)
        session.commit()

    approved_topics = get_recent_approved_topics(session)
    result, checklist = draft_post(
        note_text=note.text,
        approved_topics=approved_topics,
        redraft_instruction=combined_instruction,
        previous_draft=previous_draft_body,
    )

    previous_redraft_count = session.exec(
        select(Draft.auto_redraft_count).where(Draft.note_id == note.id).order_by(Draft.version.desc()).limit(1)
    ).first()
    redraft_count = (previous_redraft_count or 0) + 1 if is_redraft else 0

    version = len(session.exec(select(Draft).where(Draft.note_id == note.id)).all()) + 1

    draft = Draft(
        note_id=note.id,
        version=version,
        body=result.body,
        category=result.category,
        word_count=checklist["word_count"],
        verify_count=checklist["verify_count"],
        checklist=checklist,
        redraft_instruction=combined_instruction,
        is_current=True,
        auto_redraft_count=redraft_count,
    )
    session.add(draft)
    note.status = NoteStatus.DRAFTED
    session.add(note)
    session.commit()
    session.refresh(draft)
    return draft


# ---------------------------------------------------------------------------
# Stage 3: evaluate - triage the raw note (quality score) + editor-score the
# draft. Both run on the finished draft text shown at stage 2.
# ---------------------------------------------------------------------------


def evaluate_draft(session: Session, draft: Draft, note: Note) -> EditorResult:
    if note.score is None:
        note = triage_and_save(session, note)

    editor = score_draft(note_text=note.text, draft_body=draft.body)

    draft.editor_scores = {
        "facts": editor.facts,
        "voice": editor.voice,
        "structure": editor.structure,
        "hook": editor.hook,
        "reader": editor.reader,
    }
    draft.editor_issues = editor.issues
    draft.unsupported_claims = editor.unsupported_claims
    draft.body_hash = hashlib.sha256(draft.body.encode("utf-8")).hexdigest()
    draft.evaluated_at = datetime.now(timezone.utc)
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return editor


# ---------------------------------------------------------------------------
# Stage 4: decide - binary verdict from the editor score + checklist.
# ---------------------------------------------------------------------------


def decide_draft(session: Session, draft: Draft, note: Note, editor: EditorResult) -> DecisionResult:
    settings = get_settings(session)
    outcome = decide(
        editor=editor,
        checklist=draft.checklist or {},
        verify_count=draft.verify_count,
        settings=settings,
    )

    draft.final_score = outcome.final_score
    draft.block_reasons = outcome.block_reasons
    draft.decision = outcome.verdict
    draft.decided_by = DecisionActor.SYSTEM
    draft.decided_at = datetime.now(timezone.utc)
    session.add(draft)

    note.status = NoteStatus.APPROVED if outcome.auto_applied else NoteStatus.DRAFTED
    session.add(note)
    session.commit()
    session.refresh(draft)

    _log_decision(
        session,
        draft_id=draft.id,
        actor=DecisionActor.SYSTEM,
        action=outcome.verdict.value,
        previous_decision=None,
        new_decision=outcome.verdict.value,
        final_score=outcome.final_score,
    )
    return outcome


def draft_for_note(
    session: Session, note: Note, redraft_instruction: str | None = None, is_redraft: bool = False
) -> Draft:
    """Runs stages 2-4 back to back (no news). For the API/CLI/scheduler; the
    bot calls draft_only()/evaluate_draft()/decide_draft() directly so it can
    show a message between each stage."""
    draft = draft_only(session, note, redraft_instruction, is_redraft)
    editor = evaluate_draft(session, draft, note)
    decide_draft(session, draft, note, editor)
    session.refresh(draft)
    return draft


def draft_top_notes(session: Session, count: int = 3) -> list[Draft]:
    ranked = rank_backlog(session, limit=max(count * 3, count), triage_first=True)
    publishable = [n for n in ranked if n.publishable]
    chosen = publishable[:count] if publishable else ranked[:count]
    drafts: list[Draft] = []
    for note in chosen:
        try:
            drafts.append(draft_for_note(session, note))
        except Exception:
            logger.exception("Failed to draft note %s", note.id)
    return drafts


# ---------------------------------------------------------------------------
# Stage 5 (approved only): related news via Google News RSS
# ---------------------------------------------------------------------------


async def attach_news(session: Session, draft: Draft, other_news: bool = False) -> list[DraftNews]:
    """Finds and stores related news for an APPROVED draft. Never runs for a
    rejected draft (callers must check draft.decision themselves - this
    function doesn't re-check, to keep it testable in isolation)."""
    exclude_titles = None
    queries = draft.news_queries  # reused if already set (e.g. a redraft, or "Other news" below)
    if other_news:
        existing = session.exec(select(DraftNews).where(DraftNews.draft_id == draft.id)).all()
        exclude_titles = {e.title.strip().lower() for e in existing}
        for e in existing:
            session.delete(e)
        session.commit()

    items, used_queries = await find_related_news(session, draft.body, queries=queries, exclude_titles=exclude_titles)

    draft.news_queries = used_queries
    draft.news_checked_at = datetime.now(timezone.utc)
    session.add(draft)

    news_rows = []
    for item in items:
        row = DraftNews(
            draft_id=draft.id,
            title=item["title"],
            publisher=item["publisher"],
            published_at=item.get("published_at"),
            url=item["url"],
            relevance=item["relevance"],
            reason=item["reason"],
            query=item["query"],
        )
        session.add(row)
        news_rows.append(row)
    session.commit()
    for row in news_rows:
        session.refresh(row)
    return news_rows


def get_draft_news(session: Session, draft_id: int) -> list[DraftNews]:
    return list(
        session.exec(
            select(DraftNews).where(DraftNews.draft_id == draft_id).order_by(DraftNews.relevance.desc())
        ).all()
    )


def body_hash_matches(draft: Draft) -> bool:
    """Integrity check before any Copy action: the approved text must not
    have changed since it was evaluated."""
    if draft.body_hash is None:
        return True  # nothing to check against yet
    return hashlib.sha256(draft.body.encode("utf-8")).hexdigest() == draft.body_hash


# ---------------------------------------------------------------------------
# Human decisions: approve / undo / discard / redraft
# ---------------------------------------------------------------------------


def approve_current_draft(session: Session, note_id: int) -> Draft | None:
    note = session.get(Note, note_id)
    if note is None:
        return None
    draft = session.exec(
        select(Draft).where(Draft.note_id == note_id, Draft.is_current == True)  # noqa: E712
    ).first()
    previous = draft.decision.value if draft and draft.decision else None
    note.status = NoteStatus.APPROVED
    session.add(note)
    if draft:
        draft.decided_by = DecisionActor.MEERA
        draft.decided_at = datetime.now(timezone.utc)
        session.add(draft)
    session.commit()
    if draft:
        _log_decision(
            session,
            draft_id=draft.id,
            actor=DecisionActor.MEERA,
            action="approved",
            previous_decision=previous,
            new_decision=previous,
            final_score=draft.final_score,
        )
    return draft


def undo_draft(session: Session, draft_id: int) -> Draft | None:
    """Moves an auto-approved draft back to review. Does not change the
    historical `decision` field or refund the weekly cap slot."""
    draft = session.get(Draft, draft_id)
    if draft is None:
        return None
    note = session.get(Note, draft.note_id)
    if note is None:
        return None
    previous = draft.decision.value if draft.decision else None
    note.status = NoteStatus.DRAFTED
    draft.decided_by = DecisionActor.MEERA
    draft.decided_at = datetime.now(timezone.utc)
    session.add(note)
    session.add(draft)
    session.commit()
    _log_decision(
        session,
        draft_id=draft.id,
        actor=DecisionActor.MEERA,
        action="undone",
        previous_decision=previous,
        new_decision=previous,
        final_score=draft.final_score,
    )
    return draft


def discard_note(session: Session, note_id: int) -> Note | None:
    note = session.get(Note, note_id)
    if note is None:
        return None
    draft = session.exec(
        select(Draft).where(Draft.note_id == note_id, Draft.is_current == True)  # noqa: E712
    ).first()
    note.status = NoteStatus.DISCARDED
    session.add(note)
    if draft:
        draft.decided_by = DecisionActor.MEERA
        draft.decided_at = datetime.now(timezone.utc)
        session.add(draft)
    session.commit()
    session.refresh(note)
    if draft:
        _log_decision(
            session,
            draft_id=draft.id,
            actor=DecisionActor.MEERA,
            action="discarded",
            previous_decision=draft.decision.value if draft.decision else None,
            new_decision=draft.decision.value if draft.decision else None,
            final_score=draft.final_score,
        )
    return note


def mark_human_edited(session: Session, draft_id: int, body: str) -> Draft | None:
    draft = session.get(Draft, draft_id)
    if draft is None:
        return None
    draft.body = body
    draft.human_edited = True
    checklist = validate_checklist(body)
    draft.checklist = checklist
    draft.word_count = checklist["word_count"]
    draft.verify_count = checklist["verify_count"]
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


# ---------------------------------------------------------------------------
# Pending review / calibration
# ---------------------------------------------------------------------------


def get_pending_review_count(session: Session) -> int:
    return len(session.exec(select(Note).where(Note.status == NoteStatus.DRAFTED)).all())


def get_calibration_pairs(session: Session, limit: int = 30) -> list[tuple[Draft, Note]]:
    statement = (
        select(Draft, Note)
        .where(Draft.note_id == Note.id)
        .where(Draft.is_current == True)  # noqa: E712
        .where(Note.status.in_([NoteStatus.APPROVED, NoteStatus.DISCARDED]))  # type: ignore[attr-defined]
    )
    rows = list(session.exec(statement).all())
    rows.sort(key=lambda pair: pair[0].decided_at or pair[0].created_at, reverse=True)
    return rows[:limit]


def compute_calibration_stats(session: Session, pairs: list[tuple[Draft, Note]]) -> dict:
    scored = [(d, n) for d, n in pairs if d.final_score is not None]
    if len(scored) < 15:
        return {"insufficient_data": True, "count": len(scored)}

    auto_approved = [(d, n) for d, n in scored if d.decided_by == DecisionActor.SYSTEM]
    undone_ids: set[int] = set()
    if auto_approved:
        draft_ids = [d.id for d, _ in auto_approved]
        logs = session.exec(
            select(DecisionLog.draft_id).where(
                DecisionLog.draft_id.in_(draft_ids),  # type: ignore[attr-defined]
                DecisionLog.action == "undone",
            )
        ).all()
        undone_ids = set(logs)

    undo_rate = (len(undone_ids) / len(auto_approved)) if auto_approved else None
    agreement_rate = (1 - undo_rate) if undo_rate is not None else None

    approved_clean = [(d, n) for d, n in scored if n.status == NoteStatus.APPROVED and not d.human_edited]

    candidate_scores = sorted({d.final_score for d, _ in scored})
    suggested_threshold = None
    for s in candidate_scores:
        at_or_above = [pair for pair in scored if pair[0].final_score >= s]
        clean_at_or_above = [pair for pair in approved_clean if pair[0].final_score >= s]
        if at_or_above and len(clean_at_or_above) / len(at_or_above) >= 0.95:
            suggested_threshold = s
            break

    return {
        "insufficient_data": False,
        "count": len(scored),
        "auto_approved_count": len(auto_approved),
        "undo_rate": undo_rate,
        "agreement_rate": agreement_rate,
        "suggested_threshold": suggested_threshold,
    }


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def note_exists(session: Session, text: str) -> bool:
    statement = select(Note).where(Note.text == text.strip())
    return session.exec(statement).first() is not None


def import_note_text(
    session: Session,
    text: str,
    source: NoteSource = NoteSource.IMPORT,
    telegram_message_id: int | None = None,
) -> Note | None:
    text = text.strip()
    if not text or note_exists(session, text):
        return None
    note = Note(text=text, source=source, telegram_message_id=telegram_message_id)
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def import_notes_from_folder(session: Session, folder: Path) -> list[Note]:
    imported: list[Note] = []
    if not folder.exists():
        return imported
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in IMPORTABLE_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8").strip()
        note = import_note_text(session, text)
        if note:
            imported.append(note)
            logger.info("Imported note from %s (id=%s)", path.name, note.id)
    return imported
