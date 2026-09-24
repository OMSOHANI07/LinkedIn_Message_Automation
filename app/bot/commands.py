"""Bot commands: /start, /status, /draft, /backlog, /autoapprove, /threshold,
/settings, /scores, /calibration, /week."""

from __future__ import annotations

import logging

from sqlmodel import func, select
from telegram import Update
from telegram.ext import ContextTypes

from app.bot.handlers import (
    _is_authorized_chat,
    _is_authorized_user,
    _run_pipeline,
    build_details_text,
)
from app.config import settings
from app.db.models import AutoApproveMode, DecisionActor, Draft, Note, NoteStatus
from app.db.session import session_scope
from app.db.settings_store import get_settings, update_settings, weights
from app.pipeline.orchestrator import (
    compute_calibration_stats,
    count_weekly_auto_approvals,
    get_calibration_pairs,
    get_pending_review_count,
    rank_backlog,
)
from app.pipeline.schemas import CATEGORY_LABELS
from app.pipeline.week import week_start_ist, week_start_utc

logger = logging.getLogger(__name__)

COMMAND_LIST = [
    ("start", "what this bot does"),
    ("status", "note counts by status"),
    ("draft", "draft the best note in the backlog"),
    ("backlog", "top 5 unused notes with scores"),
    ("autoapprove", "show/set mode: on (auto-decide) or off (always manual)"),
    ("threshold", "set the auto-approve score threshold (50-100)"),
    ("settings", "current mode, thresholds, weights, weekly usage"),
    ("scores", "score breakdown for a draft: /scores <draft_id>"),
    ("week", "this week's approvals, auto vs manual, pending review"),
    ("calibration", "how well auto-approval matches your actual decisions"),
]

START_MESSAGE = (
    "Skinstinct drafting assistant is live.\n\n"
    "Drop a note here and I'll evaluate it instantly - triage, draft, score, "
    "and approve or reject it against the threshold. I never post to "
    "LinkedIn - I only prepare drafts for you to copy and publish yourself.\n\n"
    "Commands:\n" + "\n".join(f"/{name} - {desc}" for name, desc in COMMAND_LIST)
)


def _reject_unauthorized(chat, user=None, require_admin: bool = False) -> bool:
    """Returns True (and logs) if this update should be ignored."""
    if chat is None:
        return True
    if not _is_authorized_chat(chat.id):
        logger.warning(
            "Ignoring command from unauthorized chat %s (configured chat is %s)",
            chat.id,
            settings.telegram_chat_id,
        )
        return True
    if require_admin:
        user_id = user.id if user else None
        if not _is_authorized_user(user_id):
            logger.warning("Ignoring admin command from non-admin user %s", user_id)
            return True
    return False


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if _reject_unauthorized(chat):
        return
    await context.bot.send_message(chat_id=chat.id, text=START_MESSAGE)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if _reject_unauthorized(chat):
        return
    with session_scope() as session:
        statement = select(Note.status, func.count(Note.id)).group_by(Note.status)
        rows = session.exec(statement).all()
    counts = {status.value: 0 for status in NoteStatus}
    for status, count in rows:
        key = status.value if hasattr(status, "value") else status
        counts[key] = count
    lines = [f"{status}: {count}" for status, count in counts.items()]
    await context.bot.send_message(chat_id=chat.id, text="Note counts by status:\n" + "\n".join(lines))


async def cmd_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Optional - live notes evaluate instantly without this. Runs the best
    backlog note through the same 5-stage flow as a live message."""
    chat = update.effective_chat
    if _reject_unauthorized(chat):
        return
    with session_scope() as session:
        top = rank_backlog(session, limit=1, triage_first=True)
    if not top:
        await context.bot.send_message(chat_id=chat.id, text="Backlog is empty. Nothing to draft.")
        return
    note_id = top[0].id
    status = await context.bot.send_message(chat_id=chat.id, text="📥 Note received · drafting…")
    await _run_pipeline(context.bot, chat.id, note_id, status.message_id)


async def cmd_backlog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if _reject_unauthorized(chat):
        return
    with session_scope() as session:
        top = rank_backlog(session, limit=5, triage_first=True)
    if not top:
        await context.bot.send_message(chat_id=chat.id, text="Backlog is empty.")
        return
    lines = ["Top 5 unused notes:"]
    for note in top:
        label = CATEGORY_LABELS.get(note.category or "", note.category or "unscored")
        score = f"{note.score:.1f}" if note.score is not None else "?"
        preview = note.text[:80] + ("..." if len(note.text) > 80 else "")
        lines.append(f"[{score}/10 · {label}] {preview}")
    await context.bot.send_message(chat_id=chat.id, text="\n".join(lines))


async def cmd_autoapprove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    args = context.args or []

    if not args:
        if _reject_unauthorized(chat):
            return
        with session_scope() as session:
            current = get_settings(session).mode.value
        await context.bot.send_message(chat_id=chat.id, text=f"Auto-approve mode is currently: {current}")
        return

    if _reject_unauthorized(chat, user, require_admin=True):
        return

    choice = args[0].strip().lower()
    try:
        mode = AutoApproveMode(choice)
    except ValueError:
        await context.bot.send_message(chat_id=chat.id, text="Usage: /autoapprove on|off")
        return

    with session_scope() as session:
        update_settings(session, mode=mode)
    await context.bot.send_message(chat_id=chat.id, text=f"Auto-approve mode set to: {mode.value}")


async def cmd_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    args = context.args or []

    if not args:
        if _reject_unauthorized(chat):
            return
        with session_scope() as session:
            current = get_settings(session).auto_approve_threshold
        await context.bot.send_message(chat_id=chat.id, text=f"Auto-approve threshold is currently: {current}")
        return

    if _reject_unauthorized(chat, user, require_admin=True):
        return

    try:
        value = int(args[0])
    except ValueError:
        await context.bot.send_message(chat_id=chat.id, text="Usage: /threshold <number 50-100>")
        return

    if not (50 <= value <= 100):
        await context.bot.send_message(chat_id=chat.id, text="Threshold must be between 50 and 100.")
        return

    with session_scope() as session:
        update_settings(session, auto_approve_threshold=value)
    await context.bot.send_message(chat_id=chat.id, text=f"Auto-approve threshold set to: {value}")


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if _reject_unauthorized(chat):
        return
    with session_scope() as session:
        s = get_settings(session)
        used = count_weekly_auto_approvals(session)
        w = weights(s)

    weight_line = " · ".join(f"{k}:{v:.0%}" for k, v in w.items())
    lines = [
        f"Mode: {s.mode.value}",
        f"Auto-approve threshold: {s.auto_approve_threshold}/100",
        f"Weekly cap: {used}/{s.weekly_cap} used (informational only)",
        f"Weights: {weight_line}",
        f"Daily nudge: {'on' if s.nudge_enabled else 'off'} at {s.nudge_hour_ist:02d}:00 IST",
    ]
    await context.bot.send_message(chat_id=chat.id, text="\n".join(lines))


async def cmd_scores(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if _reject_unauthorized(chat):
        return
    args = context.args or []
    if not args or not args[0].isdigit():
        await context.bot.send_message(chat_id=chat.id, text="Usage: /scores <draft_id>")
        return
    draft_id = int(args[0])
    with session_scope() as session:
        text = build_details_text(session, draft_id)
    if text is None:
        await context.bot.send_message(chat_id=chat.id, text=f"No draft with id {draft_id}.")
        return
    await context.bot.send_message(chat_id=chat.id, text=text, parse_mode="HTML")


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if _reject_unauthorized(chat):
        return
    with session_scope() as session:
        s = get_settings(session)
        week_start_ist_dt = week_start_ist()
        cutoff_utc = week_start_utc()

        decided_this_week = session.exec(
            select(Draft).where(
                Draft.is_current == True,  # noqa: E712
                Draft.decided_at != None,  # noqa: E711
                Draft.decided_at >= cutoff_utc,
            )
        ).all()

        auto_count = 0
        manual_count = 0
        for d in decided_this_week:
            note = session.get(Note, d.note_id)
            if note is None or note.status != NoteStatus.APPROVED:
                continue
            if d.decided_by == DecisionActor.SYSTEM:
                auto_count += 1
            elif d.decided_by == DecisionActor.MEERA:
                manual_count += 1

        pending = get_pending_review_count(session)

    total = auto_count + manual_count
    lines = [
        f"This week (since {week_start_ist_dt.strftime('%a %d %b')}):",
        f"Approved: {total}/{s.weekly_cap}",
        f"  auto: {auto_count} · manual: {manual_count}",
        f"Pending review: {pending}",
    ]
    await context.bot.send_message(chat_id=chat.id, text="\n".join(lines))


async def cmd_calibration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if _reject_unauthorized(chat):
        return
    with session_scope() as session:
        pairs = get_calibration_pairs(session, limit=30)
        stats = compute_calibration_stats(session, pairs)

    if stats["insufficient_data"]:
        await context.bot.send_message(
            chat_id=chat.id,
            text=f"Not enough data yet ({stats['count']} decided drafts, need at least 15).",
        )
        return

    lines = [f"Last {stats['count']} decided drafts:"]
    if stats["agreement_rate"] is not None:
        lines.append(f"Agreement with auto decision: {stats['agreement_rate']:.0%}")
        lines.append(f"Undo rate (of {stats['auto_approved_count']} auto-approved): {stats['undo_rate']:.0%}")
    else:
        lines.append("No auto-approved drafts yet to measure agreement/undo rate.")
    if stats["suggested_threshold"] is not None:
        lines.append(f"Suggested threshold: {stats['suggested_threshold']:.0f} (95%+ approved without edits above this)")
    else:
        lines.append("Not enough consistency yet to suggest a threshold.")
    await context.bot.send_message(chat_id=chat.id, text="\n".join(lines))
