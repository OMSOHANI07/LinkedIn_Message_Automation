"""Builds the Telegram HTML messages + inline keyboards for the 5-stage
pipeline: Draft (stage 2) -> Evaluating (stage 3 start) -> Decision (stage 4)
-> News (stage 5, approved only).

All AI-generated text is passed through html.escape before being embedded -
never trust it to already be HTML-safe. [VERIFY: ...] tags are bolded after
escaping (safe: html.escape doesn't touch square brackets).
"""

from __future__ import annotations

import html
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import AppSettings, AutoApproveMode, Draft, DraftDecision, DraftNews, Note, NoteStatus
from app.pipeline.schemas import CATEGORY_LABELS

MAX_MESSAGE_LEN = 4096
_VERIFY_PATTERN = re.compile(r"\[VERIFY[^\]]*\]", re.IGNORECASE)
_DIMENSIONS = ("facts", "voice", "structure", "hook", "reader")


def cb(action: str, entity_id: int) -> str:
    return f"act:{action}:{entity_id}"


def parse_cb(data: str) -> tuple[str, int] | None:
    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != "act":
        return None
    try:
        return parts[1], int(parts[2])
    except ValueError:
        return None


def _bold_verify_tags(escaped_body: str) -> str:
    return _VERIFY_PATTERN.sub(lambda m: f"<b>{m.group(0)}</b>", escaped_body)


def _score_line(draft: Draft) -> str:
    scores = draft.editor_scores or {}
    parts = [f"{dim.capitalize()} {scores.get(dim, '?')}/10" for dim in _DIMENSIONS]
    return " · ".join(parts)


def _category_label(category: str | None) -> str:
    return CATEGORY_LABELS.get(category or "", category or "uncategorised")


def _why_lines(draft: Draft, limit: int = 3) -> list[str]:
    """Hard block reasons first, then the lowest-scoring dimension's specific
    editor issue, then fill to `limit` with any remaining issues."""
    lines: list[str] = list((draft.block_reasons or [])[:limit])

    scores = draft.editor_scores or {}
    issues = draft.editor_issues or []
    if len(lines) < limit and scores:
        lowest_dim = min(scores, key=lambda k: scores[k])
        match = next((i for i in issues if i.lower().startswith(lowest_dim.lower())), None)
        if match and match not in lines:
            lines.append(match)

    for issue in issues:
        if len(lines) >= limit:
            break
        if issue not in lines:
            lines.append(issue)

    return lines[:limit]


def is_approved(draft: Draft, note: Note) -> bool:
    """Display state for THIS draft. Only the note's *current* draft can be
    overridden by note.status (a manual mode=off approve, or a discard) -
    note.status describes the note as a whole, which moves on to a later
    draft after a redraft, so an old superseded draft must always show its
    own original verdict regardless of what happened afterwards."""
    if draft.is_current:
        if note.status == NoteStatus.APPROVED:
            return True
        if note.status == NoteStatus.DISCARDED:
            return False
    return draft.decision == DraftDecision.APPROVED


def _safe_truncate_html(html_text: str, limit: int = MAX_MESSAGE_LEN) -> str:
    """Truncates on a whitespace boundary and closes a dangling <b> tag, so
    text that's still over the limit on its own (rare - checklist caps word
    count, but this is the last line of defense) never breaks Telegram's
    HTML parser or exceeds the hard 4096-char limit."""
    if len(html_text) <= limit:
        return html_text
    suffix = "\n\n[truncated - see dashboard]"
    truncated = html_text[: limit - len(suffix)].rsplit(" ", 1)[0]
    if truncated.count("<b>") > truncated.count("</b>"):
        truncated += "</b>"
    return truncated + suffix


# ---------------------------------------------------------------------------
# Stage 1: note received
# ---------------------------------------------------------------------------

NOTE_RECEIVED_TEXT = "📥 Note received · drafting…"


def queued_text(position: int) -> str:
    return NOTE_RECEIVED_TEXT if position <= 1 else f"Queued (#{position})"


# ---------------------------------------------------------------------------
# Stage 2: draft (no buttons, no news, no scores yet)
# ---------------------------------------------------------------------------


def build_draft_message(draft: Draft) -> str:
    header = f"📝 Draft #{draft.id} · {html.escape(_category_label(draft.category))}"
    body_html = _bold_verify_tags(html.escape(draft.body))
    text = f"{header}\n───\n{body_html}"
    return _safe_truncate_html(text)


# ---------------------------------------------------------------------------
# Stage 3: evaluating (transient) -> Stage 4: decision
# ---------------------------------------------------------------------------


def evaluating_text(draft_id: int) -> str:
    return f"🧪 Evaluating Draft #{draft_id}…"


def build_decision_message(draft: Draft, note: Note, settings: AppSettings) -> str:
    score = draft.final_score if draft.final_score is not None else 0.0
    threshold = settings.auto_approve_threshold

    if is_approved(draft, note):
        lines = [f"✅ Approved · {score:.0f}/100 (threshold {threshold})"]
    else:
        lines = [f"❌ Rejected · {score:.0f}/100 (threshold {threshold})", "Why:"]
        for item in _why_lines(draft):
            lines.append(f"• {html.escape(item)}")

    lines.append(f"see Draft #{draft.id} above")
    lines.append("")
    lines.append("📊 Scores")
    if draft.editor_scores:
        lines.append(_score_line(draft))
    if note.score is not None:
        lines.append(f"Note quality (triage): {round(note.score)}/10")

    return _safe_truncate_html("\n".join(lines))


def decision_keyboard(draft: Draft, note: Note, settings: AppSettings) -> InlineKeyboardMarkup:
    d = draft.id

    if draft.is_current and note.status == NoteStatus.DISCARDED:
        return InlineKeyboardMarkup([])

    # mode=off: verdict is shown but every still-pending draft always gets
    # the same manual [Approve][Discard] pair - nothing auto-applies.
    if draft.is_current and settings.mode == AutoApproveMode.OFF and note.status != NoteStatus.APPROVED:
        return InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("✅ Approve", callback_data=cb("approve", d)),
                InlineKeyboardButton("🗑 Discard", callback_data=cb("discard", d)),
            ]]
        )

    if is_approved(draft, note):
        return InlineKeyboardMarkup([])  # buttons live on the stage-5 news message instead

    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✏️ Redraft", callback_data=cb("redraft", d)),
            InlineKeyboardButton("🗑 Discard", callback_data=cb("discard", d)),
        ]]
    )


# ---------------------------------------------------------------------------
# Stage 5 (approved only): related news
# ---------------------------------------------------------------------------

NEWS_SEARCHING_TEXT = "📰 Finding related news…"


def build_news_message(draft: Draft, items: list[DraftNews]) -> str:
    if not items:
        return (
            "No relevant recent news found for this topic. "
            "The post stands on its own."
        )

    lines = [f"📰 Related news for Draft #{draft.id}"]
    for i, item in enumerate(items, start=1):
        title = html.escape(item.title)
        publisher = html.escape(item.publisher)
        date = html.escape(item.published_at or "date unknown")
        url = html.escape(item.url, quote=True)
        reason = html.escape(item.reason)
        lines.append(f"{i}. {title}")
        lines.append(f"   {publisher} · {date} · relevance {item.relevance}/10")
        lines.append(f"   Why: {reason}")
        lines.append(f"   {url}")  # preview shown only for the top item - see send call's link_preview_options
    return _safe_truncate_html("\n".join(lines))


def news_keyboard(draft_id: int, has_news: bool) -> InlineKeyboardMarkup:
    if has_news:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📋 Copy post", callback_data=cb("copy", draft_id))],
                [InlineKeyboardButton("📋 Copy post + reference", callback_data=cb("copy_ref", draft_id))],
                [InlineKeyboardButton("🔄 Other news", callback_data=cb("other_news", draft_id))],
            ]
        )
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("📋 Copy post", callback_data=cb("copy", draft_id)),
            InlineKeyboardButton("🔄 Try again", callback_data=cb("other_news", draft_id)),
        ]]
    )


# ---------------------------------------------------------------------------
# Shared: redraft prompt, retry
# ---------------------------------------------------------------------------


def redraft_prompt_keyboard(draft_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Skip", callback_data=cb("redraft_skip", draft_id))]])


def retry_keyboard(note_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Retry", callback_data=cb("retry", note_id))]])
