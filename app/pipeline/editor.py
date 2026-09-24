"""AI call #3: an independent editor pass, scored against SKILL.md.

Deliberately a separate call from drafting itself - grading your own homework
is weaker than a second, focused pass whose only job is to find problems.
"""

from __future__ import annotations

import logging

from app.pipeline.draft import load_skill_text
from app.pipeline.gemini_client import generate_structured
from app.pipeline.schemas import EditorResult

logger = logging.getLogger(__name__)

EDITOR_SYSTEM_INSTRUCTION_SUFFIX = """

====================================================================
YOUR TASK: SCORE THIS DRAFT AGAINST THE SKILL ABOVE
====================================================================

You are the editor, not the writer. Score the draft on five dimensions,
0-10 each:

  facts     - Every number/claim is from the canonical fact sheet, supplied
              by Meera, or marked [VERIFY]. No invented Skinstinct data or
              study citations. 0 if anything is stated as fact that should
              have been [VERIFY]-tagged and wasn't.
  voice     - Matches section 0, 5, 7 and 8 of the skill: hedging calibrated
              not vague, signature constructions used naturally, banned
              marketing vocabulary avoided, British spelling, spaced hyphens.
  structure - Follows the 6-beat arc in section 3, in order, with the
              mandatory caveat paragraph and Skinstinct-as-proof-not-pitch
              paragraph both present.
  hook      - Line 1 has a concrete specific (number/year/place/claim); the
              hook type used fits the content and category.
  reader    - Ends with a concrete question to ask ANY brand, not just
              Skinstinct, and a calm close - not a sales CTA or audience
              question.

List every specific, actionable issue you find in `issues` - one per item,
prefixed with the dimension it belongs to (e.g. "Hook: ..."), short and
concrete. Never write a generic complaint like "could be better" - name
exactly what's missing or wrong, and where. List every claim stated as
established fact that is not in the canonical fact sheet, not supplied in the
note, and not already [VERIFY]-tagged, in `unsupported_claims`.

Also flag two hard-line conditions, independent of the scores:
  names_competitor        - true if the draft names or clearly identifies a
                             specific competitor brand (section 7: she never
                             names competitors, problems are framed as
                             systemic).
  claims_medical_authority - true if the draft claims or implies medical or
                             dermatological authority, or makes a diagnosis.
                             She is ex-pharma formulation, not a
                             dermatologist, and never claims otherwise.

Be a harsh, precise editor. A draft that would embarrass Meera if posted
as-is should score low, even if it reads well.
""".strip()


def score_draft(*, note_text: str, draft_body: str) -> EditorResult:
    system_instruction = load_skill_text() + "\n" + EDITOR_SYSTEM_INSTRUCTION_SUFFIX
    contents = f"Original note:\n{note_text}\n\nDraft to score:\n{draft_body}"
    result = generate_structured(
        system_instruction=system_instruction,
        contents=contents,
        schema=EditorResult,
    )
    logger.info(
        "Editor scores: facts=%d voice=%d structure=%d hook=%d reader=%d, %d issue(s)",
        result.facts,
        result.voice,
        result.structure,
        result.hook,
        result.reader,
        len(result.issues),
    )
    return result
