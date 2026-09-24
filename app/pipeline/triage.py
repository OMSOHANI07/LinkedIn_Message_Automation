"""AI call #1: is a raw note worth developing into a post?"""

from __future__ import annotations

import logging

from app.pipeline.gemini_client import generate_structured
from app.pipeline.schemas import CATEGORY_LABELS, TriageResult

logger = logging.getLogger(__name__)

_CATEGORY_BLOCK = "\n".join(f"  {code}. {label}" for code, label in CATEGORY_LABELS.items())

TRIAGE_SYSTEM_INSTRUCTION = f"""
You are triaging raw notes for Meera Pillai, founder of Skinstinct (an Indian
D2C skincare brand; she is ex-pharmaceutical formulation, not a dermatologist).
Notes arrive as short observations, two-liners, or voice-note transcriptions.
Decide whether each is worth developing into a 450-650 word LinkedIn post in
her voice: precise, evidence-first, quietly sceptical of marketing claims,
never hype-driven.

Score 0-10 on:
  - Does it contain a specific fact, number, or a dated/located scene, rather
    than a vague generality?
  - Is there a clear single thesis that could anchor a post ("the label/claim
    is the beginning of the question, not the answer")?
  - Does it fit one of the categories below and Meera's established positions?
  - Is there enough substance to sustain 450-650 words without padding?

Categories (pick exactly one):
{_CATEGORY_BLOCK}

Be honest and specific in `reason` - this is kept even for notes that score
low, so Meera can see why a note was set aside. Notes are never deleted for
scoring low, so there is no need to be generous.

List in `missing_facts` any concrete numbers or details she would need to
supply to make a post credible. Never invent facts, numbers or citations
yourself - that is her job to supply later.
""".strip()


def triage_note(note_text: str, recent_topics: list[str] | None = None) -> TriageResult:
    recent_block = ""
    if recent_topics:
        joined = "\n".join(f"- {topic}" for topic in recent_topics)
        recent_block = (
            f"\n\nTopics covered in recently approved posts (avoid repeating these):\n{joined}"
        )

    contents = f"Note:\n{note_text}{recent_block}"
    result = generate_structured(
        system_instruction=TRIAGE_SYSTEM_INSTRUCTION,
        contents=contents,
        schema=TriageResult,
    )
    logger.info(
        "Triaged note: score=%.1f publishable=%s category=%s",
        result.score,
        result.publishable,
        result.category,
    )
    return result
