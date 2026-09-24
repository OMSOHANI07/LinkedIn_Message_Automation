from app.db.models import AppSettings, AutoApproveMode, DraftDecision
from app.pipeline.decision import FACT_INTEGRITY_MIN, compute_block_reasons, compute_final_score, decide
from app.pipeline.schemas import EditorResult

CLEAN_CHECKLIST = {
    "word_count": 550,
    "word_count_in_range": True,
    "no_banned_formatting": True,
    "uses_spaced_hyphen_dashes": True,
}

BAD_CHECKLIST = {
    "word_count": 300,
    "word_count_in_range": False,
    "no_banned_formatting": False,
    "uses_spaced_hyphen_dashes": False,
}


def _editor(**overrides) -> EditorResult:
    base = dict(
        facts=9,
        voice=9,
        structure=9,
        hook=9,
        reader=9,
        issues=[],
        unsupported_claims=[],
        names_competitor=False,
        claims_medical_authority=False,
    )
    base.update(overrides)
    return EditorResult(**base)


def _settings(**overrides) -> AppSettings:
    base = dict(mode=AutoApproveMode.ON, auto_approve_threshold=85, weekly_cap=3)
    base.update(overrides)
    return AppSettings(**base)


EQUAL_WEIGHTS = {"facts": 0.2, "voice": 0.2, "structure": 0.2, "hook": 0.2, "reader": 0.2}


def test_compute_final_score_equal_weights():
    editor = _editor(facts=8, voice=8, structure=8, hook=8, reader=8)
    assert compute_final_score(editor, EQUAL_WEIGHTS) == 80.0


def test_compute_final_score_mixed_scores():
    editor = _editor(facts=10, voice=8, structure=6, hook=9, reader=7)
    assert compute_final_score(editor, EQUAL_WEIGHTS) == 80.0


def test_block_reasons_empty_when_clean():
    editor = _editor()
    assert compute_block_reasons(checklist=CLEAN_CHECKLIST, verify_count=0, editor=editor) == []


def test_block_reasons_flags_verify_tags():
    editor = _editor()
    reasons = compute_block_reasons(checklist=CLEAN_CHECKLIST, verify_count=2, editor=editor)
    assert any("VERIFY" in r for r in reasons)


def test_block_reasons_flags_checklist_failures():
    editor = _editor()
    reasons = compute_block_reasons(checklist=BAD_CHECKLIST, verify_count=0, editor=editor)
    assert len(reasons) >= 3


def test_block_reasons_flags_unsupported_claims():
    editor = _editor(unsupported_claims=["23% return rate claimed without source"])
    reasons = compute_block_reasons(checklist=CLEAN_CHECKLIST, verify_count=0, editor=editor)
    assert any("unsupported claim" in r for r in reasons)


def test_block_reasons_flags_competitor_naming():
    editor = _editor(names_competitor=True)
    reasons = compute_block_reasons(checklist=CLEAN_CHECKLIST, verify_count=0, editor=editor)
    assert any("competitor" in r for r in reasons)


def test_block_reasons_flags_medical_authority_claim():
    editor = _editor(claims_medical_authority=True)
    reasons = compute_block_reasons(checklist=CLEAN_CHECKLIST, verify_count=0, editor=editor)
    assert any("medical" in r for r in reasons)


def test_block_reasons_flags_low_fact_integrity():
    editor = _editor(facts=FACT_INTEGRITY_MIN - 1)
    reasons = compute_block_reasons(checklist=CLEAN_CHECKLIST, verify_count=0, editor=editor)
    assert any("fact integrity" in r for r in reasons)


def test_decide_approved_at_or_above_threshold_no_blocks():
    editor = _editor()  # all 9s -> 90/100
    settings = _settings(auto_approve_threshold=85)
    outcome = decide(editor=editor, checklist=CLEAN_CHECKLIST, verify_count=0, settings=settings)
    assert outcome.final_score == 90.0
    assert outcome.verdict == DraftDecision.APPROVED
    assert outcome.auto_applied is True


def test_decide_rejected_just_below_threshold():
    # 84/100 average -> reject
    editor = _editor(facts=8, voice=8, structure=8, hook=9, reader=9)  # 84.0
    settings = _settings(auto_approve_threshold=85)
    outcome = decide(editor=editor, checklist=CLEAN_CHECKLIST, verify_count=0, settings=settings)
    assert outcome.final_score == 84.0
    assert outcome.verdict == DraftDecision.REJECTED
    assert outcome.auto_applied is False


def test_decide_rejected_with_verify_tag_even_at_high_score():
    editor = _editor()  # all 9s -> 90/100
    settings = _settings(auto_approve_threshold=85)
    outcome = decide(editor=editor, checklist=CLEAN_CHECKLIST, verify_count=1, settings=settings)
    assert outcome.final_score == 90.0
    assert outcome.verdict == DraftDecision.REJECTED
    assert outcome.block_reasons  # the block is listed
    assert outcome.auto_applied is False


def test_decide_mode_off_never_auto_applies_even_when_approved():
    editor = _editor()  # 90/100, clean
    settings = _settings(mode=AutoApproveMode.OFF)
    outcome = decide(editor=editor, checklist=CLEAN_CHECKLIST, verify_count=0, settings=settings)
    assert outcome.verdict == DraftDecision.APPROVED  # verdict still computed
    assert outcome.auto_applied is False  # but never applied automatically


def test_decide_mode_off_still_computes_rejected_verdict():
    editor = _editor(facts=5, voice=5, structure=5, hook=5, reader=5)
    settings = _settings(mode=AutoApproveMode.OFF)
    outcome = decide(editor=editor, checklist=CLEAN_CHECKLIST, verify_count=0, settings=settings)
    assert outcome.verdict == DraftDecision.REJECTED
    assert outcome.auto_applied is False
