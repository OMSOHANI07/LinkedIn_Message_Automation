"""Dashboard-facing REST API. No route here ever touches LinkedIn - approve
just marks a note ready for Meera to copy and post herself."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlmodel import Session, select

from app.api.schemas import (
    DraftNewsOut,
    DraftOut,
    EditDraftRequest,
    ImportResult,
    NoteOut,
    NoteWithDraftsOut,
    RedraftRequest,
    WeekStatsOut,
)
from app.config import settings
from app.db.models import Draft, DraftDecision, Note, NoteSource, NoteStatus
from app.db.session import get_session
from app.pipeline.orchestrator import (
    approve_current_draft,
    attach_news,
    discard_note,
    draft_for_note,
    draft_top_notes,
    get_draft_news,
    import_note_text,
    import_notes_from_folder,
    mark_human_edited,
    rank_backlog,
    undo_draft,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

IST = ZoneInfo("Asia/Kolkata")


def _draft_out(session: Session, draft: Draft) -> DraftOut:
    out = DraftOut.model_validate(draft)
    out.news = [DraftNewsOut.model_validate(n) for n in get_draft_news(session, draft.id)]
    return out


async def _draft_and_attach_news(session: Session, note: Note, **kwargs) -> Draft:
    """Runs the sync draft pipeline in a thread, then fetches news if the
    result was approved - used by every dashboard route that can produce an
    approved draft, so the dashboard sees news without a separate step."""
    draft = await asyncio.to_thread(draft_for_note, session, note, **kwargs)
    if draft.decision == DraftDecision.APPROVED:
        try:
            await attach_news(session, draft)
        except Exception:
            logger.exception("Dashboard news attachment failed for draft %s", draft.id)
    return draft


def _note_out(session: Session, note: Note) -> NoteOut:
    out = NoteOut.model_validate(note)
    current = session.exec(
        select(Draft).where(Draft.note_id == note.id, Draft.is_current == True)  # noqa: E712
    ).first()
    if current is not None:
        out.current_draft = _draft_out(session, current)
    return out


@router.get("/notes", response_model=list[NoteOut])
def list_notes(
    status: NoteStatus | None = None,
    category: str | None = None,
    session: Session = Depends(get_session),
) -> list[NoteOut]:
    statement = select(Note)
    if status is not None:
        statement = statement.where(Note.status == status)
    if category is not None:
        statement = statement.where(Note.category == category)
    statement = statement.order_by(Note.received_at.desc())
    notes = session.exec(statement).all()
    return [_note_out(session, n) for n in notes]


@router.get("/notes/{note_id}", response_model=NoteWithDraftsOut)
def get_note(note_id: int, session: Session = Depends(get_session)) -> NoteWithDraftsOut:
    note = session.get(Note, note_id)
    if note is None:
        raise HTTPException(404, "Note not found")
    drafts = session.exec(
        select(Draft).where(Draft.note_id == note_id).order_by(Draft.version.desc())
    ).all()
    draft_outs = [_draft_out(session, d) for d in drafts]
    out = NoteWithDraftsOut.model_validate(note)
    out.drafts = draft_outs
    out.current_draft = next((d for d in draft_outs if d.is_current), None)
    return out


@router.post("/notes/{note_id}/draft", response_model=DraftOut)
async def draft_note(note_id: int, session: Session = Depends(get_session)) -> DraftOut:
    note = session.get(Note, note_id)
    if note is None:
        raise HTTPException(404, "Note not found")
    draft = await _draft_and_attach_news(session, note)
    return _draft_out(session, draft)


@router.post("/notes/{note_id}/discard", response_model=NoteOut)
def discard(note_id: int, session: Session = Depends(get_session)) -> Note:
    note = discard_note(session, note_id)
    if note is None:
        raise HTTPException(404, "Note not found")
    return note


@router.post("/drafts/next", response_model=list[DraftOut])
async def draft_next_best(session: Session = Depends(get_session)) -> list[DraftOut]:
    drafts = await asyncio.to_thread(draft_top_notes, session, 1)
    for d in drafts:
        if d.decision == DraftDecision.APPROVED:
            try:
                await attach_news(session, d)
            except Exception:
                logger.exception("Dashboard news attachment failed for draft %s", d.id)
    return [_draft_out(session, d) for d in drafts]


@router.post("/drafts/{draft_id}/approve", response_model=DraftOut)
async def approve(draft_id: int, session: Session = Depends(get_session)) -> DraftOut:
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise HTTPException(404, "Draft not found")
    approve_current_draft(session, draft.note_id)
    session.refresh(draft)
    if not get_draft_news(session, draft.id):
        try:
            await attach_news(session, draft)
        except Exception:
            logger.exception("Dashboard news attachment failed for draft %s", draft.id)
    return _draft_out(session, draft)


@router.post("/drafts/{draft_id}/redraft", response_model=DraftOut)
async def redraft(draft_id: int, body: RedraftRequest, session: Session = Depends(get_session)) -> DraftOut:
    old_draft = session.get(Draft, draft_id)
    if old_draft is None:
        raise HTTPException(404, "Draft not found")
    note = session.get(Note, old_draft.note_id)
    if note is None:
        raise HTTPException(404, "Note not found")
    new_draft = await _draft_and_attach_news(session, note, redraft_instruction=body.instruction, is_redraft=True)
    return _draft_out(session, new_draft)


@router.post("/drafts/{draft_id}/undo", response_model=DraftOut)
def undo(draft_id: int, session: Session = Depends(get_session)) -> DraftOut:
    draft = undo_draft(session, draft_id)
    if draft is None:
        raise HTTPException(404, "Draft not found")
    return _draft_out(session, draft)


@router.patch("/drafts/{draft_id}", response_model=DraftOut)
def edit_draft(draft_id: int, body: EditDraftRequest, session: Session = Depends(get_session)) -> DraftOut:
    """Inline manual edits from the Draft Studio - does not call the model."""
    draft = mark_human_edited(session, draft_id, body.body)
    if draft is None:
        raise HTTPException(404, "Draft not found")
    return _draft_out(session, draft)


@router.get("/backlog", response_model=list[NoteOut])
def backlog(limit: int = 5, session: Session = Depends(get_session)) -> list[NoteOut]:
    notes = rank_backlog(session, limit=limit, triage_first=True)
    return [_note_out(session, n) for n in notes]


@router.get("/week", response_model=WeekStatsOut)
def week_stats(session: Session = Depends(get_session)) -> WeekStatsOut:
    now_ist = datetime.now(IST)
    week_start_ist = (now_ist - timedelta(days=now_ist.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_start_utc = week_start_ist.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    approved_notes = session.exec(select(Note).where(Note.status == NoteStatus.APPROVED)).all()
    approved_this_week = 0
    for note in approved_notes:
        latest = session.exec(
            select(Draft)
            .where(Draft.note_id == note.id, Draft.is_current == True)  # noqa: E712
        ).first()
        if latest and latest.created_at.replace(tzinfo=None) >= week_start_utc:
            approved_this_week += 1

    queued_notes = session.exec(select(Note).where(Note.status == NoteStatus.DRAFTED)).all()
    queued_drafts = []
    for note in queued_notes:
        d = session.exec(
            select(Draft).where(Draft.note_id == note.id, Draft.is_current == True)  # noqa: E712
        ).first()
        if d:
            queued_drafts.append(_draft_out(session, d))
    queued_drafts.sort(key=lambda d: d.created_at, reverse=True)

    return WeekStatsOut(
        approved_this_week=approved_this_week,
        week_starts=week_start_ist,
        queued_drafts=queued_drafts,
    )


@router.post("/import/folder", response_model=ImportResult)
def import_folder(session: Session = Depends(get_session)) -> ImportResult:
    imported = import_notes_from_folder(session, settings.notes_import_dir)
    return ImportResult(imported=len(imported), notes=imported)


@router.post("/import/upload", response_model=ImportResult)
async def import_upload(files: list[UploadFile], session: Session = Depends(get_session)) -> ImportResult:
    imported: list[Note] = []
    for f in files:
        if not (f.filename or "").lower().endswith((".txt", ".md")):
            continue
        raw = (await f.read()).decode("utf-8", errors="ignore")
        note = import_note_text(session, raw, source=NoteSource.IMPORT)
        if note:
            imported.append(note)
    return ImportResult(imported=len(imported), notes=imported)
