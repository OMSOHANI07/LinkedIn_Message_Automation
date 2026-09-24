"""Deterministic checks against the skill's Section 12 pre-publish checklist.

Kept separate from any AI call so it's cheap, fast and unit-testable: word
count and banned-formatting checks don't need a model, they need a regex.
"""

from __future__ import annotations

import re

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002700-\U000027BF"
    "]+",
    flags=re.UNICODE,
)
HASHTAG_PATTERN = re.compile(r"(?<!\w)#\w+")
BULLET_LINE_PATTERN = re.compile(r"^[ \t]*([-*••]|\d+[.)])[ \t]+", re.MULTILINE)
MARKDOWN_HEADER_PATTERN = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]", re.MULTILINE)
BOLD_PATTERN = re.compile(r"\*\*[^*]+\*\*")
VERIFY_PATTERN = re.compile(r"\[VERIFY[^\]]*\]", re.IGNORECASE)
EM_DASH_PATTERN = re.compile(r"[—–]")
AUDIENCE_QUESTION_PHRASES = (
    "thoughts?",
    "agree?",
    "what do you think",
    "unpopular opinion",
    "let that sink in",
    "here's the thing",
)
WORD_COUNT_MIN = 450
WORD_COUNT_MAX = 650


def validate_checklist(body: str) -> dict:
    """Returns a dict of deterministic checklist results for a draft body."""
    word_count = len(body.split())
    verify_matches = VERIFY_PATTERN.findall(body)
    has_emojis = bool(EMOJI_PATTERN.search(body))
    has_hashtags = bool(HASHTAG_PATTERN.search(body))
    has_bullets = bool(BULLET_LINE_PATTERN.search(body))
    has_headers = bool(MARKDOWN_HEADER_PATTERN.search(body))
    has_bold = bool(BOLD_PATTERN.search(body))
    has_exclamation = "!" in body
    has_em_dash = bool(EM_DASH_PATTERN.search(body))
    lowered = body.lower()
    has_audience_question = any(phrase in lowered for phrase in AUDIENCE_QUESTION_PHRASES)

    no_banned_formatting = not any(
        [
            has_emojis,
            has_hashtags,
            has_bullets,
            has_headers,
            has_bold,
            has_exclamation,
            has_audience_question,
        ]
    )

    return {
        "word_count": word_count,
        "word_count_in_range": WORD_COUNT_MIN <= word_count <= WORD_COUNT_MAX,
        "verify_count": len(verify_matches),
        "verify_items": verify_matches,
        "has_emojis": has_emojis,
        "has_hashtags": has_hashtags,
        "has_bullets": has_bullets,
        "has_headers": has_headers,
        "has_bold": has_bold,
        "has_exclamation": has_exclamation,
        "has_em_dash": has_em_dash,
        "has_audience_question": has_audience_question,
        "no_banned_formatting": no_banned_formatting,
        "uses_spaced_hyphen_dashes": not has_em_dash,
    }
