from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Chat, Message, MessageEntity, Update

from app.bot import handlers, queue_worker
from app.bot.telegram_bot import _NOTE_UPDATE_FILTER

CHAT_ID = -1004380024074


@pytest.fixture(autouse=True)
def _authorized_chat(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(CHAT_ID))


def _channel_message(text: str, message_id: int = 1, entities=None) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=Chat(id=CHAT_ID, type="channel"),
        text=text,
        entities=entities or [],
    )


# ---------------------------------------------------------------------------
# Routing filter: commands never reach handle_incoming_note
# ---------------------------------------------------------------------------


def test_note_filter_excludes_commands():
    message = _channel_message(
        "/draft", entities=[MessageEntity(type=MessageEntity.BOT_COMMAND, offset=0, length=6)]
    )
    update = Update(update_id=1, channel_post=message)
    assert not _NOTE_UPDATE_FILTER.check_update(update)


def test_note_filter_matches_plain_text():
    message = _channel_message("just a regular observation about pH and niacinamide")
    update = Update(update_id=2, channel_post=message)
    assert _NOTE_UPDATE_FILTER.check_update(update)


# ---------------------------------------------------------------------------
# handle_incoming_note: short messages are rejected, valid ones are queued
# ---------------------------------------------------------------------------


def _mock_update(text: str, message_id: int = 1, reply_to=None) -> MagicMock:
    update = MagicMock()
    update.effective_chat.id = CHAT_ID
    update.effective_message.text = text
    update.effective_message.caption = None
    update.effective_message.message_id = message_id
    update.effective_message.reply_to_message = reply_to
    return update


@contextmanager
def _fake_session_scope():
    yield MagicMock()


@pytest.mark.asyncio
async def test_short_message_is_rejected_without_enqueueing(monkeypatch):
    monkeypatch.setenv("MIN_NOTE_CHARS", "40")
    enqueue_mock = AsyncMock()
    monkeypatch.setattr(queue_worker, "enqueue", enqueue_mock)

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    update = _mock_update("too short")
    await handlers.handle_incoming_note(update, context)

    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert "Too short" in kwargs["text"]
    enqueue_mock.assert_not_called()


@pytest.mark.asyncio
async def test_valid_note_is_queued_for_evaluation(monkeypatch):
    monkeypatch.setenv("MIN_NOTE_CHARS", "10")
    enqueue_mock = AsyncMock()
    monkeypatch.setattr(queue_worker, "enqueue", enqueue_mock)
    monkeypatch.setattr(queue_worker, "queue_position", lambda: 1)
    monkeypatch.setattr(handlers, "session_scope", _fake_session_scope)
    monkeypatch.setattr(handlers, "import_note_text", MagicMock(return_value=MagicMock(id=42)))

    context = MagicMock()
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=999))

    update = _mock_update("A sufficiently long note about niacinamide pH and delivery base for evaluation.")
    await handlers.handle_incoming_note(update, context)

    enqueue_mock.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert "received" in kwargs["text"].lower()


@pytest.mark.asyncio
async def test_duplicate_note_is_not_queued(monkeypatch):
    monkeypatch.setenv("MIN_NOTE_CHARS", "10")
    enqueue_mock = AsyncMock()
    monkeypatch.setattr(queue_worker, "enqueue", enqueue_mock)
    monkeypatch.setattr(handlers, "session_scope", _fake_session_scope)
    monkeypatch.setattr(handlers, "import_note_text", MagicMock(return_value=None))  # duplicate

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    update = _mock_update("A sufficiently long note that happens to already exist in the database.")
    await handlers.handle_incoming_note(update, context)

    enqueue_mock.assert_not_called()
    context.bot.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# Redraft flow: old message gets edited once the new draft exists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redraft_edits_old_message_and_uses_the_new_draft_id(monkeypatch):
    old_draft = MagicMock(id=10, note_id=5, telegram_chat_id=CHAT_ID, decision_message_id=111)
    new_draft = MagicMock(id=11)

    session = MagicMock()
    session.get.return_value = old_draft
    monkeypatch.setattr(handlers, "session_scope", lambda: _session_yielding(session))

    run_pipeline_mock = AsyncMock(return_value=new_draft)
    monkeypatch.setattr(handlers, "_run_pipeline", run_pipeline_mock)

    context = MagicMock()
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=222))
    context.bot.edit_message_text = AsyncMock()
    context.bot.edit_message_reply_markup = AsyncMock()

    await handlers._run_redraft(context, CHAT_ID, old_draft_id=10, instruction="make it shorter")

    run_pipeline_mock.assert_awaited_once()
    _, kwargs = run_pipeline_mock.call_args
    assert kwargs["is_redraft"] is True
    assert kwargs["redraft_instruction"] == "make it shorter"

    context.bot.edit_message_text.assert_awaited_once()
    _, edit_kwargs = context.bot.edit_message_text.call_args
    assert edit_kwargs["chat_id"] == CHAT_ID
    assert edit_kwargs["message_id"] == 111  # the OLD message, not the new status message
    assert "Draft #11" in edit_kwargs["text"]


@pytest.mark.asyncio
async def test_redraft_does_not_edit_old_message_when_pipeline_fails(monkeypatch):
    old_draft = MagicMock(id=10, note_id=5, telegram_chat_id=CHAT_ID, decision_message_id=111)

    session = MagicMock()
    session.get.return_value = old_draft
    monkeypatch.setattr(handlers, "session_scope", lambda: _session_yielding(session))
    monkeypatch.setattr(handlers, "_run_pipeline", AsyncMock(return_value=None))  # pipeline failed

    context = MagicMock()
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=222))
    context.bot.edit_message_text = AsyncMock()

    await handlers._run_redraft(context, CHAT_ID, old_draft_id=10, instruction=None)

    context.bot.edit_message_text.assert_not_awaited()


@contextmanager
def _session_yielding(session):
    yield session


# ---------------------------------------------------------------------------
# Stage ordering: evaluation (a new message) never starts before the draft
# message (an edit of the stage-1 message) has been sent successfully.
# ---------------------------------------------------------------------------


def _patch_pipeline_stages(monkeypatch, *, auto_applied: bool):
    session = MagicMock()
    session.get.return_value = MagicMock(id=1, score=8.0)
    monkeypatch.setattr(handlers, "session_scope", lambda: _session_yielding(session))

    fake_draft = MagicMock(id=5, decision="rejected" if not auto_applied else "approved")
    monkeypatch.setattr(handlers, "draft_only", MagicMock(return_value=fake_draft))
    monkeypatch.setattr(handlers, "evaluate_draft", MagicMock(return_value=MagicMock()))
    outcome = MagicMock(auto_applied=auto_applied)
    monkeypatch.setattr(handlers, "decide_draft", MagicMock(return_value=outcome))
    monkeypatch.setattr(handlers, "get_settings", MagicMock(return_value=MagicMock(auto_approve_threshold=85)))
    monkeypatch.setattr(handlers, "build_draft_message", MagicMock(return_value="DRAFT TEXT"))
    monkeypatch.setattr(handlers, "build_decision_message", MagicMock(return_value="DECISION TEXT"))
    monkeypatch.setattr(handlers, "decision_keyboard", MagicMock(return_value=MagicMock()))
    return fake_draft


@pytest.mark.asyncio
async def test_evaluation_message_sent_only_after_draft_edit_completes(monkeypatch):
    _patch_pipeline_stages(monkeypatch, auto_applied=False)

    bot = MagicMock()
    bot.edit_message_text = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=777))
    bot.send_chat_action = AsyncMock()

    await handlers._run_pipeline(bot, CHAT_ID, note_id=1, initial_message_id=100)

    # Every call on `bot` is recorded on its shared mock_calls in real order,
    # since edit_message_text and send_message are both children of `bot`.
    call_names = [c[0] for c in bot.mock_calls if c[0] in ("edit_message_text", "send_message")]
    first_edit_index = call_names.index("edit_message_text")
    first_send_index = call_names.index("send_message")
    assert first_edit_index < first_send_index  # stage 2 (edit) precedes stage 3 (new message)

    # And that edit specifically targeted the stage-1 message with the draft text.
    first_edit_call = [c for c in bot.mock_calls if c[0] == "edit_message_text"][0]
    assert first_edit_call.kwargs["message_id"] == 100
    assert first_edit_call.kwargs["text"] == "DRAFT TEXT"


@pytest.mark.asyncio
async def test_rejected_draft_never_triggers_news_fetch(monkeypatch):
    _patch_pipeline_stages(monkeypatch, auto_applied=False)
    news_stage_mock = AsyncMock()
    monkeypatch.setattr(handlers, "_run_news_stage", news_stage_mock)

    bot = MagicMock()
    bot.edit_message_text = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=777))
    bot.send_chat_action = AsyncMock()

    await handlers._run_pipeline(bot, CHAT_ID, note_id=1, initial_message_id=100)

    news_stage_mock.assert_not_called()


@pytest.mark.asyncio
async def test_approved_draft_triggers_news_fetch(monkeypatch):
    _patch_pipeline_stages(monkeypatch, auto_applied=True)
    news_stage_mock = AsyncMock()
    monkeypatch.setattr(handlers, "_run_news_stage", news_stage_mock)

    bot = MagicMock()
    bot.edit_message_text = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=777))
    bot.send_chat_action = AsyncMock()

    await handlers._run_pipeline(bot, CHAT_ID, note_id=1, initial_message_id=100)

    news_stage_mock.assert_awaited_once()
