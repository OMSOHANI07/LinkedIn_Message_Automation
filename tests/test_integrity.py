"""Section 5 integrity rule: the approved post text must never change after
approval, and news is attached to the draft record, never written into the
body. attach_news() must never touch body/body_hash."""

import hashlib
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.db.models import Draft, DraftDecision, Note, NoteStatus
from app.pipeline.orchestrator import attach_news, body_hash_matches


def _engine_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed_approved_draft(session: Session) -> Draft:
    note = Note(text="a note", status=NoteStatus.APPROVED, score=8.0)
    session.add(note)
    session.commit()
    session.refresh(note)

    body = "The approved post text, unchanged since evaluation."
    draft = Draft(
        note_id=note.id,
        version=1,
        body=body,
        body_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        decision=DraftDecision.APPROVED,
        final_score=90.0,
        is_current=True,
    )
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


def test_body_hash_matches_when_unmodified():
    with _engine_session() as session:
        draft = _seed_approved_draft(session)
        assert body_hash_matches(draft) is True


def test_body_hash_mismatch_when_body_edited_after_evaluation():
    with _engine_session() as session:
        draft = _seed_approved_draft(session)
        draft.body = "Someone edited the approved text after the fact."
        assert body_hash_matches(draft) is False


@pytest.mark.asyncio
async def test_attach_news_never_modifies_body_or_hash():
    with _engine_session() as session:
        draft = _seed_approved_draft(session)
        original_body = draft.body
        original_hash = draft.body_hash

        fake_items = (
            [
                {
                    "title": "Some real headline",
                    "publisher": "The Hindu",
                    "published_at": "Mon, 01 Sep 2026 00:00:00 GMT",
                    "url": "https://example.com/article",
                    "relevance": 8,
                    "reason": "Relevant",
                    "query": "topic when:30d",
                }
            ],
            ["topic when:30d"],
        )
        with patch("app.pipeline.orchestrator.find_related_news", AsyncMock(return_value=fake_items)):
            rows = await attach_news(session, draft)

        assert len(rows) == 1
        assert draft.body == original_body
        assert draft.body_hash == original_hash
        assert body_hash_matches(draft) is True
