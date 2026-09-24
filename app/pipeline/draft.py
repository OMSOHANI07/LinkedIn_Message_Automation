"""AI call #2: draft the post in Meera's voice, self-classifying it, then
self-check it. No research or news feeds into this step - news is attached
only after approval (see pipeline/news.py)."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from app.config import BASE_DIR
from app.pipeline.checklist import validate_checklist
from app.pipeline.gemini_client import generate_structured
from app.pipeline.schemas import DraftResult

logger = logging.getLogger(__name__)

SKILL_PATH = BASE_DIR / "skills" / "SKILL.md"


@lru_cache(maxsize=1)
def load_skill_text() -> str:
    """The full, unmodified skill file, used verbatim as the system instruction.
    Never paraphrase or summarise this - it is the fact-integrity contract too.
    """
    return SKILL_PATH.read_text(encoding="utf-8")


def _build_prompt(
    *,
    note_text: str,
    approved_topics: list[str] | None,
    redraft_instruction: str | None,
    previous_draft: str | None,
) -> str:
    parts = [
        "Draft a LinkedIn post following the skill above exactly: pick the category "
        "(A-G) and the single thesis yourself, then follow its hooks, 6-beat "
        "structure, tone, vocabulary, length and fact-integrity rules.",
        f"\nRaw note from Meera:\n{note_text}",
    ]
    if approved_topics:
        joined = "\n".join(f"- {topic}" for topic in approved_topics)
        parts.append(f"\nRecently approved post topics (do not repeat these):\n{joined}")
    if previous_draft and redraft_instruction:
        parts.append(
            f"\nThis is a redraft. Previous draft:\n{previous_draft}\n\n"
            f"Meera's instruction for this redraft: {redraft_instruction}"
        )
    return "\n".join(p for p in parts if p)


def draft_post(
    *,
    note_text: str,
    approved_topics: list[str] | None = None,
    redraft_instruction: str | None = None,
    previous_draft: str | None = None,
) -> tuple[DraftResult, dict]:
    """Returns (draft_result, checklist_dict). checklist_dict is deterministic,
    computed in code against Section 12 - not asked of the model.
    """
    prompt = _build_prompt(
        note_text=note_text,
        approved_topics=approved_topics,
        redraft_instruction=redraft_instruction,
        previous_draft=previous_draft,
    )
    result = generate_structured(
        system_instruction=load_skill_text(),
        contents=prompt,
        schema=DraftResult,
    )
    checklist = validate_checklist(result.body)
    logger.info(
        "Drafted post: category=%s %d words, %d [VERIFY] tags, in_range=%s",
        result.category,
        checklist["word_count"],
        checklist["verify_count"],
        checklist["word_count_in_range"],
    )
    return result, checklist
