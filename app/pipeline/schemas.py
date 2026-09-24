"""Pydantic schemas for structured AI output. Shared by triage/research/draft."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["A", "B", "C", "D", "E", "F", "G"]

CATEGORY_LABELS: dict[str, str] = {
    "A": "Ingredient Deep-Dive",
    "B": "Founder Story",
    "C": "India-Specific Context",
    "D": "Industry Transparency",
    "E": "Formulation Science",
    "F": "Brand Philosophy",
    "G": "Consumer Education",
}


class TriageResult(BaseModel):
    score: float = Field(ge=0, le=10, description="0-10, how strong this note is as a post seed")
    publishable: bool
    category: Category
    core_insight: str = Field(description="The single thesis this note could become")
    suggested_hook_type: str = Field(description="Which of the skill's 4 hook types fits best")
    missing_facts: list[str] = Field(
        default_factory=list,
        description="Specific facts/numbers Meera would need to supply to make this credible",
    )
    reason: str = Field(description="One or two sentences on why this score, for the 'not now' log")


class DraftResult(BaseModel):
    """AI call #2: draft the post AND self-classify it - no separate upstream
    triage call feeds this anymore, so the draft determines its own category
    and thesis directly from the note and the skill."""

    category: Category = Field(description="Which of the skill's categories A-G this post falls into")
    core_insight: str = Field(description="The single thesis this post argues")
    body: str = Field(description="The full LinkedIn post text, 450-650 words")
    verify_items: list[str] = Field(
        default_factory=list,
        description="Every [VERIFY: ...] tag used in the body, listed plainly for Meera",
    )


class EditorResult(BaseModel):
    """AI call #3: an independent editor pass, scored against SKILL.md."""

    facts: int = Field(ge=0, le=10, description="Fact integrity: no invented data/citations, everything unverifiable is [VERIFY]-tagged")
    voice: int = Field(ge=0, le=10, description="Matches Meera's voice: hedging, vocabulary, sentence rhythm, no marketing language")
    structure: int = Field(ge=0, le=10, description="Follows the 6-beat arc in order, correct paragraph count and shape")
    hook: int = Field(ge=0, le=10, description="Line 1 has a concrete specific; hook type fits the content")
    reader: int = Field(ge=0, le=10, description="Ends with a concrete question to ask any brand and a calm, non-salesy close")
    issues: list[str] = Field(
        default_factory=list,
        description="Specific, actionable problems found, one per item, each prefixed with the dimension it "
        "belongs to, e.g. 'Hook: line 1 is a generic observation with no number, year or place.' "
        "Never generic phrasing like 'could be better' - name exactly what's missing or wrong.",
    )
    unsupported_claims: list[str] = Field(
        default_factory=list,
        description="Any claim stated as fact that isn't in the canonical fact sheet, the note, or already [VERIFY]-tagged",
    )
    names_competitor: bool = Field(
        default=False, description="True if the draft names or clearly identifies a specific competitor brand"
    )
    claims_medical_authority: bool = Field(
        default=False,
        description="True if the draft claims or implies medical/dermatological authority or makes a diagnosis - "
        "Meera is ex-pharma formulation, not a dermatologist, and never claims otherwise",
    )


class NewsQueries(BaseModel):
    """AI call #4a (approved drafts only): 2-5 word search queries for Google
    News, built from the finished post - never runs before approval."""

    queries: list[str] = Field(
        min_length=1,
        max_length=3,
        description="Exactly 3 short (2-5 word) Google News search queries about the post's core "
        "topic - the ingredient, regulation, India market angle, or consumer issue it discusses",
    )


class NewsRankPick(BaseModel):
    number: int = Field(description="The candidate's number from the numbered list - never invented")
    relevance: int = Field(ge=0, le=10)
    reason: str = Field(description="One line on why this candidate is relevant to the post")


class NewsRanking(BaseModel):
    """AI call #4b: ranks real RSS candidates by number only - titles and URLs
    are never model output, only an index into the list it was given."""

    picks: list[NewsRankPick] = Field(
        default_factory=list,
        max_length=3,
        description="Up to 3 picks, most relevant first. Empty if nothing is genuinely relevant.",
    )
