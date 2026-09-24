from app.bot.formatting import (
    build_decision_message,
    build_draft_message,
    build_news_message,
    cb,
    decision_keyboard,
    is_approved,
    news_keyboard,
    parse_cb,
    queued_text,
)
from app.db.models import AppSettings, AutoApproveMode, Draft, DraftDecision, DraftNews, Note, NoteStatus


def _note(**overrides) -> Note:
    base = dict(id=1, text="a note", status=NoteStatus.DRAFTED, category="A", score=8.0)
    base.update(overrides)
    return Note(**base)


def _draft(**overrides) -> Draft:
    base = dict(
        id=42,
        note_id=1,
        version=1,
        body="This is the drafted post body.",
        category="A",
        decision=DraftDecision.REJECTED,
        final_score=62.0,
        editor_scores={"facts": 6, "voice": 7, "structure": 6, "hook": 5, "reader": 7},
        editor_issues=["Hook: line 1 has no concrete number, year or place."],
        block_reasons=[],
        verify_count=0,
        auto_redraft_count=0,
    )
    base.update(overrides)
    return Draft(**base)


def _settings(**overrides) -> AppSettings:
    base = dict(mode=AutoApproveMode.ON, auto_approve_threshold=85)
    base.update(overrides)
    return AppSettings(**base)


def _news_item(**overrides) -> DraftNews:
    base = dict(
        id=1,
        draft_id=42,
        title="Study finds rising humidity affects skincare formulation",
        publisher="The Hindu",
        published_at="Mon, 01 Sep 2026 00:00:00 GMT",
        url="https://example.com/article",
        relevance=8,
        reason="Directly discusses the same humidity mechanism as the post.",
        query="skincare humidity India when:30d",
    )
    base.update(overrides)
    return DraftNews(**base)


# ---------------------------------------------------------------------------
# cb / parse_cb
# ---------------------------------------------------------------------------


def test_cb_roundtrip():
    assert parse_cb(cb("approve", 42)) == ("approve", 42)


def test_parse_cb_rejects_malformed():
    assert parse_cb("garbage") is None
    assert parse_cb("act:approve:notanumber") is None


def test_queued_text_first_in_line_says_received():
    assert "received" in queued_text(1).lower()


def test_queued_text_shows_position_when_backed_up():
    assert "#3" in queued_text(3)


# ---------------------------------------------------------------------------
# is_approved (display-state regression coverage)
# ---------------------------------------------------------------------------


def test_is_approved_follows_note_status_over_verdict():
    draft = _draft(decision=DraftDecision.REJECTED)
    note = _note(status=NoteStatus.APPROVED)
    assert is_approved(draft, note) is True


def test_is_approved_false_when_discarded_even_if_verdict_approved():
    draft = _draft(decision=DraftDecision.APPROVED)
    note = _note(status=NoteStatus.DISCARDED)
    assert is_approved(draft, note) is False


def test_superseded_draft_keeps_its_own_verdict_even_if_note_later_approved():
    old_rejected_draft = _draft(id=4, decision=DraftDecision.REJECTED, is_current=False)
    note = _note(status=NoteStatus.APPROVED)  # approved via a *different*, newer draft
    assert is_approved(old_rejected_draft, note) is False


# ---------------------------------------------------------------------------
# Stage 2: draft message
# ---------------------------------------------------------------------------


def test_draft_message_has_id_category_and_body():
    draft = _draft(id=7, category="C", body="The post text goes here.")
    text = build_draft_message(draft)
    assert "Draft #7" in text
    assert "India-Specific Context" in text
    assert "The post text goes here." in text


def test_draft_message_bolds_verify_and_escapes_html():
    draft = _draft(body="A claim [VERIFY: source needed] and <script>bad</script>.")
    text = build_draft_message(draft)
    assert "<b>[VERIFY: source needed]</b>" in text
    assert "<script>bad</script>" not in text
    assert "&lt;script&gt;" in text


def test_draft_message_truncates_very_long_body():
    draft = _draft(body="word " * 1500)
    text = build_draft_message(draft)
    assert len(text) <= 4096


# ---------------------------------------------------------------------------
# Stage 4: decision message + keyboard
# ---------------------------------------------------------------------------


def test_decision_message_approved_shows_verdict_and_scores():
    draft = _draft(decision=DraftDecision.APPROVED, final_score=88.0)
    note = _note(status=NoteStatus.APPROVED)
    text = build_decision_message(draft, note, _settings())
    assert "✅ Approved" in text
    assert "88/100" in text
    assert "see Draft #42 above" in text
    assert "Facts 6/10" in text


def test_decision_message_rejected_shows_why():
    draft = _draft(
        decision=DraftDecision.REJECTED, final_score=62.0, block_reasons=["1 unresolved [VERIFY] item(s)"]
    )
    note = _note(status=NoteStatus.DRAFTED)
    text = build_decision_message(draft, note, _settings())
    assert "❌ Rejected" in text
    assert "Why:" in text
    assert "unresolved [VERIFY]" in text


def test_decision_message_never_repeats_the_post_body():
    draft = _draft(body="This exact sentence must not reappear in the decision message.")
    note = _note()
    text = build_decision_message(draft, note, _settings())
    assert "must not reappear" not in text


def test_decision_keyboard_rejected_shows_redraft_and_discard():
    draft = _draft(decision=DraftDecision.REJECTED)
    note = _note(status=NoteStatus.DRAFTED)
    keyboard = decision_keyboard(draft, note, _settings())
    labels = [b.text for row in keyboard.inline_keyboard for b in row]
    assert "✏️ Redraft" in labels
    assert "🗑 Discard" in labels


def test_decision_keyboard_approved_has_no_buttons_mode_on():
    draft = _draft(decision=DraftDecision.APPROVED)
    note = _note(status=NoteStatus.APPROVED)
    keyboard = decision_keyboard(draft, note, _settings(mode=AutoApproveMode.ON))
    assert len(keyboard.inline_keyboard) == 0  # buttons live on the news message instead


def test_decision_keyboard_mode_off_always_shows_approve_and_discard():
    draft = _draft(decision=DraftDecision.APPROVED)  # verdict says approved
    note = _note(status=NoteStatus.DRAFTED)  # but not yet actually approved
    keyboard = decision_keyboard(draft, note, _settings(mode=AutoApproveMode.OFF))
    labels = [b.text for row in keyboard.inline_keyboard for b in row]
    assert labels == ["✅ Approve", "🗑 Discard"]


def test_decision_keyboard_discarded_has_no_buttons():
    draft = _draft()
    note = _note(status=NoteStatus.DISCARDED)
    keyboard = decision_keyboard(draft, note, _settings())
    assert len(keyboard.inline_keyboard) == 0


# ---------------------------------------------------------------------------
# Stage 5: news message + keyboard
# ---------------------------------------------------------------------------


def test_news_message_lists_items_with_relevance_and_link():
    draft = _draft(id=9)
    item = _news_item(draft_id=9)
    text = build_news_message(draft, [item])
    assert "Draft #9" in text
    assert "The Hindu" in text
    assert "relevance 8/10" in text
    assert item.url in text


def test_news_message_empty_says_stands_on_its_own():
    draft = _draft()
    text = build_news_message(draft, [])
    assert "stands on its own" in text


def test_news_message_escapes_html_in_title_and_reason():
    draft = _draft()
    item = _news_item(title="<b>Injected</b> headline", reason="<script>bad</script>")
    text = build_news_message(draft, [item])
    assert "<script>bad</script>" not in text
    assert "&lt;script&gt;" in text


def test_news_keyboard_with_items_has_copy_and_other_news():
    keyboard = news_keyboard(9, has_news=True)
    labels = [b.text for row in keyboard.inline_keyboard for b in row]
    assert "📋 Copy post" in labels
    assert "📋 Copy post + reference" in labels
    assert "🔄 Other news" in labels


def test_news_keyboard_without_items_has_try_again():
    keyboard = news_keyboard(9, has_news=False)
    labels = [b.text for row in keyboard.inline_keyboard for b in row]
    assert "📋 Copy post" in labels
    assert "🔄 Try again" in labels
    assert "📋 Copy post + reference" not in labels
