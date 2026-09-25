"""Message + callback-query handlers for the 5-stage pipeline:

  Stage 1  Note received            (this message is reused as Stage 2)
  Stage 2  Draft shown               (edits the stage-1 message)
  Stage 3  Evaluating…                (a NEW message, sent only after stage 2)
  Stage 4  Decision                   (edits the stage-3 message)
  Stage 5  Related news (approved)     (a NEW message, sent only after stage 4)

Note on ForceReply: the Bot API's `reply_markup` is one-of ForceReply OR an
inline keyboard, never both on the same message - so the redraft prompt uses
an inline [Skip] button instead, and any plain text reply to that prompt is
read as the instruction.
"""

from __future__ import annotations

import asyncio
import html as html_module
import logging

from sqlmodel import select
from telegram import LinkPreviewOptions, Update
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.bot import queue_worker
from app.bot.formatting import (
    NEWS_SEARCHING_TEXT,
    build_decision_message,
    build_draft_message,
    build_news_message,
    decision_keyboard,
    evaluating_text,
    news_keyboard,
    parse_cb,
    queued_text,
    redraft_prompt_keyboard,
    retry_keyboard,
)
from app.config import settings
from app.db.models import Draft, DraftNews, Note, NoteSource, NoteStatus
from app.db.session import session_scope
from app.db.settings_store import get_settings, weights
from app.pipeline.orchestrator import (
    approve_current_draft,
    attach_news,
    body_hash_matches,
    decide_draft,
    discard_note,
    draft_only,
    evaluate_draft,
    get_draft_news,
    import_note_text,
)

logger = logging.getLogger(__name__)

# prompt message_id -> draft_id being redrafted, for the "any instruction?" flow.
_pending_redraft_prompts: dict[int, int] = {}


def _is_authorized_chat(chat_id: int) -> bool:
    return str(chat_id) == settings.telegram_chat_id


async def _safe_edit_message_text(bot, **kwargs) -> None:
    """edit_message_text, but treats Telegram's "message is not modified"
    error as a no-op instead of a failure - this happens harmlessly when a
    retry (e.g. a repeated Gemini outage) produces identical content to
    what's already shown. Any other error still propagates normally."""
    try:
        await bot.edit_message_text(**kwargs)
    except BadRequest as exc:
        if "message is not modified" in str(exc).lower():
            logger.debug("Skipped no-op edit for message %s", kwargs.get("message_id"))
            return
        raise


def _is_authorized_user(user_id: int | None) -> bool:
    """Empty ADMIN_USER_IDS means anyone in the authorized chat is trusted -
    same behaviour as before this allow-list existed."""
    admins = settings.admin_user_ids
    if not admins:
        return True
    return user_id in admins


# ---------------------------------------------------------------------------
# The core pipeline: stages 2-4, then stage 5 if actually approved
# ---------------------------------------------------------------------------


async def _run_pipeline(
    bot,
    chat_id: int,
    note_id: int,
    initial_message_id: int,
    *,
    is_redraft: bool = False,
    redraft_instruction: str | None = None,
) -> Draft | None:
    """Runs stage 2 (edits `initial_message_id` into the draft), then stage 3
    (a NEW message, sent only once stage 2's edit has completed), then stage
    4 (edits that same message into the decision), then stage 5 if the draft
    was actually approved. Returns the Draft, or None on failure.
    """
    try:
        with session_scope() as session:
            note = session.get(Note, note_id)
            if note is None:
                await _safe_edit_message_text(bot,
                    chat_id=chat_id, message_id=initial_message_id, text="Couldn't find that note anymore."
                )
                return None

            # --- Stage 2: draft ---
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            draft = await asyncio.to_thread(draft_only, session, note, redraft_instruction, is_redraft)
            draft.telegram_chat_id = chat_id
            draft.draft_message_id = initial_message_id
            session.add(draft)
            session.commit()

            await _safe_edit_message_text(bot,
                chat_id=chat_id, message_id=initial_message_id, text=build_draft_message(draft), parse_mode="HTML"
            )

            # --- Stage 3: evaluating (a NEW message - only sent now that
            # stage 2's edit above has been awaited successfully) ---
            eval_message = await bot.send_message(chat_id=chat_id, text=evaluating_text(draft.id))
            draft.decision_message_id = eval_message.message_id
            session.add(draft)
            session.commit()

            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            editor = await asyncio.to_thread(evaluate_draft, session, draft, note)

            # --- Stage 4: decision ---
            outcome = await asyncio.to_thread(decide_draft, session, draft, note, editor)
            session.refresh(note)
            app_settings = get_settings(session)

            await _safe_edit_message_text(bot,
                chat_id=chat_id,
                message_id=eval_message.message_id,
                text=build_decision_message(draft, note, app_settings),
                parse_mode="HTML",
                reply_markup=decision_keyboard(draft, note, app_settings),
            )

        # --- Stage 5: news, only if this pass actually applied APPROVED ---
        if outcome.auto_applied:
            await _run_news_stage(bot, chat_id, draft.id)

        return draft
    except Exception:
        logger.exception("Pipeline failed for note %s", note_id)
        try:
            await _safe_edit_message_text(bot,
                chat_id=chat_id,
                message_id=initial_message_id,
                text="⚠️ Couldn't evaluate this note. Tap Retry.",
                reply_markup=retry_keyboard(note_id),
            )
        except Exception:
            logger.exception("Also failed to edit status message into an error state")
        return None


async def _run_news_stage(bot, chat_id: int, draft_id: int, other_news: bool = False) -> None:
    with session_scope() as session:
        draft = session.get(Draft, draft_id)
        if draft is None:
            return

        if other_news:
            message_id = draft.news_message_id
        else:
            msg = await bot.send_message(chat_id=chat_id, text=NEWS_SEARCHING_TEXT)
            draft.telegram_chat_id = chat_id
            draft.news_message_id = msg.message_id
            session.add(draft)
            session.commit()
            message_id = msg.message_id

        news_rows = await attach_news(session, draft, other_news=other_news)
        text = build_news_message(draft, news_rows)
        keyboard = news_keyboard(draft.id, has_news=bool(news_rows))
        preview = LinkPreviewOptions(url=news_rows[0].url) if news_rows else LinkPreviewOptions(is_disabled=True)

        try:
            await _safe_edit_message_text(bot,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
                link_preview_options=preview,
            )
        except Exception:
            logger.exception("Failed to edit news message for draft %s", draft_id)


# ---------------------------------------------------------------------------
# Note intake: stage 1, queued one-at-a-time
# ---------------------------------------------------------------------------


async def handle_incoming_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if chat is None or message is None or not _is_authorized_chat(chat.id):
        if chat is not None:
            logger.warning("Ignoring message from unauthorized chat %s", chat.id)
        return

    text = (message.text or message.caption or "").strip()
    if not text:
        return

    # A reply to a "any instruction?" redraft prompt takes priority over
    # being treated as a brand new note.
    reply_to = message.reply_to_message
    if reply_to is not None and reply_to.message_id in _pending_redraft_prompts:
        draft_id = _pending_redraft_prompts.pop(reply_to.message_id)
        await _run_redraft(context, chat.id, draft_id, instruction=text, prompt_message_id=reply_to.message_id)
        return

    if len(text) < settings.min_note_chars:
        await context.bot.send_message(
            chat_id=chat.id,
            text="Too short to evaluate. Send a bit more detail.",
            reply_to_message_id=message.message_id,
        )
        return

    with session_scope() as session:
        note = import_note_text(
            session, text, source=NoteSource.TELEGRAM, telegram_message_id=message.message_id
        )
    if note is None:
        return  # duplicate note, silently skip

    position = queue_worker.queue_position()
    status = await context.bot.send_message(
        chat_id=chat.id, text=queued_text(position), reply_to_message_id=message.message_id
    )

    async def job() -> None:
        if position > 1:
            try:
                await _safe_edit_message_text(context.bot,
                    chat_id=chat.id, message_id=status.message_id, text=queued_text(1)
                )
            except Exception:
                pass
        await _run_pipeline(context.bot, chat.id, note.id, status.message_id)

    await queue_worker.enqueue(job)


# ---------------------------------------------------------------------------
# Redraft flow
# ---------------------------------------------------------------------------


async def _run_redraft(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    old_draft_id: int,
    instruction: str | None,
    prompt_message_id: int | None = None,
) -> None:
    if prompt_message_id is not None:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=prompt_message_id, reply_markup=None
            )
        except Exception:
            pass  # prompt message may already be gone/edited; not fatal

    with session_scope() as session:
        old_draft = session.get(Draft, old_draft_id)
        if old_draft is None:
            await context.bot.send_message(chat_id=chat_id, text="That draft no longer exists.")
            return
        note_id = old_draft.note_id
        old_chat_id = old_draft.telegram_chat_id
        old_decision_message_id = old_draft.decision_message_id

    status = await context.bot.send_message(chat_id=chat_id, text="📥 Redrafting…")
    new_draft = await _run_pipeline(
        context.bot, chat_id, note_id, status.message_id, is_redraft=True, redraft_instruction=instruction
    )

    if new_draft is not None and old_chat_id and old_decision_message_id:
        try:
            await _safe_edit_message_text(context.bot,
                chat_id=old_chat_id,
                message_id=old_decision_message_id,
                text=f"↪️ Redrafted → see Draft #{new_draft.id}",
            )
        except Exception:
            logger.exception("Failed to edit the superseded draft message after redraft")


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat = update.effective_chat
    if query is None or chat is None or not _is_authorized_chat(chat.id):
        if chat is not None:
            logger.warning("Ignoring callback from unauthorized chat %s", chat.id)
        if query is not None:
            await query.answer()
        return

    user = query.from_user
    if not _is_authorized_user(user.id if user else None):
        logger.warning("Ignoring callback from non-admin user %s", user.id if user else None)
        await query.answer("You're not authorized to do that.", show_alert=True)
        return

    parsed = parse_cb(query.data or "")
    if parsed is None:
        await query.answer()
        return
    action, entity_id = parsed

    if action == "approve":
        await _handle_approve(query, context, entity_id)
    elif action == "discard":
        await _handle_discard(query, context, entity_id)
    elif action == "redraft":
        await _handle_redraft_prompt(query, context, entity_id)
    elif action == "redraft_skip":
        await query.answer("Redrafting with no instruction…")
        await _run_redraft(
            context,
            chat.id,
            entity_id,
            instruction=None,
            prompt_message_id=query.message.message_id if query.message else None,
        )
    elif action == "copy":
        await _handle_copy(query, context, entity_id)
    elif action == "copy_ref":
        await _handle_copy_with_reference(query, context, entity_id)
    elif action == "other_news":
        await _handle_other_news(query, context, entity_id)
    elif action == "retry":
        await _handle_retry(query, context, entity_id)
    else:
        await query.answer()


async def _refresh_decision_message(context, draft: Draft, note: Note) -> None:
    """Re-renders a draft's decision message in place from current state."""
    if not draft.telegram_chat_id or not draft.decision_message_id:
        return
    with session_scope() as session:
        app_settings = get_settings(session)
        text = build_decision_message(draft, note, app_settings)
        keyboard = decision_keyboard(draft, note, app_settings)

    try:
        await _safe_edit_message_text(context.bot,
            chat_id=draft.telegram_chat_id,
            message_id=draft.decision_message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception:
        logger.exception("Failed to refresh decision message for draft %s", draft.id)


async def _handle_approve(query, context, draft_id: int) -> None:
    with session_scope() as session:
        draft = session.get(Draft, draft_id)
        if draft is None:
            await query.answer("Draft not found.", show_alert=True)
            return
        note = session.get(Note, draft.note_id)
        if note is None:
            await query.answer("Note not found.", show_alert=True)
            return
        if note.status == NoteStatus.APPROVED:
            await query.answer("Already approved.")
            await _refresh_decision_message(context, draft, note)
            return
        approve_current_draft(session, note.id)
        session.refresh(draft)
        session.refresh(note)
        chat_id = draft.telegram_chat_id

    await query.answer("Approved.")
    await _refresh_decision_message(context, draft, note)
    if chat_id:
        await _run_news_stage(context.bot, chat_id, draft.id)


async def _handle_discard(query, context, draft_id: int) -> None:
    with session_scope() as session:
        draft = session.get(Draft, draft_id)
        if draft is None:
            await query.answer("Draft not found.", show_alert=True)
            return
        note = session.get(Note, draft.note_id)
        if note is None:
            await query.answer("Note not found.", show_alert=True)
            return
        if note.status == NoteStatus.DISCARDED:
            await query.answer("Already discarded.")
            return
        discard_note(session, note.id)
        session.refresh(draft)

    await query.answer("Discarded.")
    if draft.telegram_chat_id and draft.decision_message_id:
        try:
            await _safe_edit_message_text(context.bot,
                chat_id=draft.telegram_chat_id, message_id=draft.decision_message_id, text="🗑 Discarded"
            )
        except Exception:
            logger.exception("Failed to edit message to Discarded for draft %s", draft.id)


async def _handle_redraft_prompt(query, context, draft_id: int) -> None:
    await query.answer()
    chat_id = query.message.chat_id if query.message else None
    if chat_id is None:
        return
    prompt = await context.bot.send_message(
        chat_id=chat_id,
        text="Any instruction? Reply, or tap Skip.",
        reply_markup=redraft_prompt_keyboard(draft_id),
        reply_to_message_id=query.message.message_id if query.message else None,
    )
    _pending_redraft_prompts[prompt.message_id] = draft_id


async def _handle_copy(query, context, draft_id: int) -> None:
    with session_scope() as session:
        draft = session.get(Draft, draft_id)
        if draft is None:
            await query.answer("Draft not found.", show_alert=True)
            return
        if not body_hash_matches(draft):
            await query.answer("This draft changed since it was evaluated - redraft or re-approve first.", show_alert=True)
            return
        body = draft.body
        chat_id = draft.telegram_chat_id or (query.message.chat_id if query.message else None)
    await query.answer("Sent as plain text.")
    if chat_id:
        await context.bot.send_message(chat_id=chat_id, text=body)


async def _handle_copy_with_reference(query, context, draft_id: int) -> None:
    with session_scope() as session:
        draft = session.get(Draft, draft_id)
        if draft is None:
            await query.answer("Draft not found.", show_alert=True)
            return
        if not body_hash_matches(draft):
            await query.answer("This draft changed since it was evaluated - redraft or re-approve first.", show_alert=True)
            return
        top = session.exec(
            select(DraftNews).where(DraftNews.draft_id == draft_id).order_by(DraftNews.relevance.desc())
        ).first()
        body = draft.body
        chat_id = draft.telegram_chat_id or (query.message.chat_id if query.message else None)

    if top is None:
        await query.answer("No reference available for this draft.", show_alert=True)
        return

    text = f"{body}\n\nReference: {top.title} - {top.publisher} {top.url}"
    await query.answer("Sent with reference.")
    if chat_id:
        await context.bot.send_message(chat_id=chat_id, text=text)


async def _handle_other_news(query, context, draft_id: int) -> None:
    await query.answer("Looking for other news…")
    with session_scope() as session:
        draft = session.get(Draft, draft_id)
        chat_id = draft.telegram_chat_id if draft else None
    if chat_id:
        await _run_news_stage(context.bot, chat_id, draft_id, other_news=True)


async def _handle_retry(query, context, note_id: int) -> None:
    await query.answer("Retrying…")
    chat_id = query.message.chat_id if query.message else None
    status_message_id = query.message.message_id if query.message else None
    if chat_id is None or status_message_id is None:
        return
    await _run_pipeline(context.bot, chat_id, note_id, status_message_id)


# ---------------------------------------------------------------------------
# /scores - full breakdown for a draft
# ---------------------------------------------------------------------------


def build_details_text(session, draft_id: int) -> str | None:
    """All 5 scores with weights, the final-score formula, every block
    reason, the editor's issues and unsupported_claims, the triage score,
    redraft count and any attached news. Used by the /scores command."""
    draft = session.get(Draft, draft_id)
    if draft is None:
        return None
    note = session.get(Note, draft.note_id)
    app_settings = get_settings(session)
    w = weights(app_settings)

    scores = draft.editor_scores or {}
    dims = ("facts", "voice", "structure", "hook", "reader")
    lines = ["<b>Score breakdown</b>"]
    for dim in dims:
        lines.append(f"{dim.capitalize()}: {scores.get(dim, '?')}/10 (weight {w.get(dim, 0):.0%})")
    formula = " + ".join(f"{dim}×{w.get(dim, 0):.2f}" for dim in dims)
    lines.append(f"Formula: ({formula}) × 10 = {draft.final_score}")

    if draft.block_reasons:
        lines.append("\n<b>Block reasons</b>")
        lines.extend(f"- {html_module.escape(r)}" for r in draft.block_reasons)

    if draft.editor_issues:
        lines.append("\n<b>Editor issues</b>")
        lines.extend(f"- {html_module.escape(i)}" for i in draft.editor_issues)

    if draft.unsupported_claims:
        lines.append("\n<b>Unsupported claims</b>")
        lines.extend(f"- {html_module.escape(c)}" for c in draft.unsupported_claims)

    lines.append(f"\nTriage score: {note.score if note else '?'}/10")
    lines.append(f"Redraft attempts: {draft.auto_redraft_count}")

    news_items = get_draft_news(session, draft_id)
    if news_items:
        lines.append("\n<b>Related news</b>")
        for item in news_items:
            lines.append(f"- {html_module.escape(item.title)} ({html_module.escape(item.url)})")

    return "\n".join(lines)
