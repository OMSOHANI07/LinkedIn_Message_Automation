"""Binary decision: APPROVED if final_score >= threshold AND no hard blocks,
REJECTED otherwise. `mode` only controls whether APPROVED is applied
automatically (mode=on) or always left for a button press (mode=off) - the
verdict itself is computed identically either way.

Hard-block rule (deliberately conservative): any of these blocks approval
regardless of score, because they need Meera's input, not a better draft:
  - any unresolved [VERIFY] tag
  - any deterministic checklist failure (word count, banned formatting, dashes)
  - any unsupported claim the editor found
  - the draft names a competitor
  - the draft claims medical/dermatological authority
  - the editor's facts score is below FACT_INTEGRITY_MIN

News is not part of the decision at all - it's only looked up after a draft
is already APPROVED (see pipeline/news.py), so there is no "missing source"
block here.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.db.models import AppSettings, AutoApproveMode, DraftDecision
from app.db.settings_store import weights
from app.pipeline.schemas import EditorResult

FACT_INTEGRITY_MIN = 7


def compute_final_score(editor: EditorResult, w: dict[str, float]) -> float:
    """Each dimension is 0-10; weights sum to 1.0 -> final score is 0-100."""
    raw = (
        editor.facts * w["facts"]
        + editor.voice * w["voice"]
        + editor.structure * w["structure"]
        + editor.hook * w["hook"]
        + editor.reader * w["reader"]
    )
    return round(raw * 10, 1)


def compute_block_reasons(*, checklist: dict, verify_count: int, editor: EditorResult) -> list[str]:
    reasons: list[str] = []
    if verify_count > 0:
        reasons.append(f"{verify_count} unresolved [VERIFY] item(s)")
    if not checklist.get("word_count_in_range", True):
        reasons.append(f"word count {checklist.get('word_count')} outside 450-650")
    if not checklist.get("no_banned_formatting", True):
        reasons.append("banned formatting present (emoji/hashtag/bullet/bold/header/exclamation/audience question)")
    if not checklist.get("uses_spaced_hyphen_dashes", True):
        reasons.append("uses em dashes instead of spaced hyphens")
    if editor.unsupported_claims:
        reasons.append(f"{len(editor.unsupported_claims)} unsupported claim(s)")
    if editor.names_competitor:
        reasons.append("names a competitor brand")
    if editor.claims_medical_authority:
        reasons.append("claims medical/dermatological authority")
    if editor.facts < FACT_INTEGRITY_MIN:
        reasons.append(f"fact integrity {editor.facts}/10 below minimum {FACT_INTEGRITY_MIN}")
    return reasons


@dataclass
class DecisionResult:
    final_score: float
    block_reasons: list[str]
    verdict: DraftDecision  # the binary computed verdict, always present
    auto_applied: bool  # True only when mode=on and verdict=APPROVED


def decide(
    *,
    editor: EditorResult,
    checklist: dict,
    verify_count: int,
    settings: AppSettings,
) -> DecisionResult:
    w = weights(settings)
    final_score = compute_final_score(editor, w)
    block_reasons = compute_block_reasons(checklist=checklist, verify_count=verify_count, editor=editor)

    verdict = (
        DraftDecision.APPROVED
        if (not block_reasons and final_score >= settings.auto_approve_threshold)
        else DraftDecision.REJECTED
    )
    auto_applied = settings.mode == AutoApproveMode.ON and verdict == DraftDecision.APPROVED

    return DecisionResult(final_score=final_score, block_reasons=block_reasons, verdict=verdict, auto_applied=auto_applied)


def redraft_instruction_from_issues(issues: list[str], extra_instruction: str | None = None) -> str:
    parts = []
    if issues:
        parts.append("Fix these specific issues: " + "; ".join(issues[:5]))
    if extra_instruction:
        parts.append(f"Meera's instruction: {extra_instruction}")
    if not parts:
        return "Tighten the draft against the skill's checklist - it was rejected on the last pass."
    return " ".join(parts)
