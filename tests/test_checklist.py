from app.pipeline.checklist import validate_checklist

GOOD_BODY = " ".join(["word"] * 500) + " [VERIFY: pH source]"

BAD_BODY_WITH_EMOJI = "This is a post about niacinamide 🙂 and pH."
BAD_BODY_WITH_HASHTAG = "This is a post about #skincare and formulation."
BAD_BODY_WITH_BULLETS = "Intro paragraph.\n- first point\n- second point\n"
BAD_BODY_WITH_NUMBERED_LIST = "Intro paragraph.\n1. first point\n2. second point\n"
BAD_BODY_WITH_BOLD = "This is **very** important."
BAD_BODY_WITH_HEADER = "# A big header\n\nSome text."
BAD_BODY_WITH_EXCLAMATION = "This is exciting!"
BAD_BODY_WITH_QUESTION = "What do you think about this?"
BAD_BODY_WITH_EM_DASH = "The pH was low—that mattered."


def test_word_count_in_range():
    result = validate_checklist(GOOD_BODY)
    assert result["word_count"] == 503
    assert result["word_count_in_range"] is True


def test_word_count_out_of_range_too_short():
    result = validate_checklist("Too short.")
    assert result["word_count_in_range"] is False


def test_verify_tags_are_counted():
    body = "Some claim [VERIFY: sample size] and another [VERIFY: source]."
    result = validate_checklist(body)
    assert result["verify_count"] == 2
    assert result["verify_items"] == ["[VERIFY: sample size]", "[VERIFY: source]"]


def test_detects_emoji():
    result = validate_checklist(BAD_BODY_WITH_EMOJI)
    assert result["has_emojis"] is True
    assert result["no_banned_formatting"] is False


def test_detects_hashtag():
    result = validate_checklist(BAD_BODY_WITH_HASHTAG)
    assert result["has_hashtags"] is True
    assert result["no_banned_formatting"] is False


def test_detects_bullet_points():
    result = validate_checklist(BAD_BODY_WITH_BULLETS)
    assert result["has_bullets"] is True
    assert result["no_banned_formatting"] is False


def test_detects_numbered_list_as_bullets():
    result = validate_checklist(BAD_BODY_WITH_NUMBERED_LIST)
    assert result["has_bullets"] is True


def test_detects_bold():
    result = validate_checklist(BAD_BODY_WITH_BOLD)
    assert result["has_bold"] is True
    assert result["no_banned_formatting"] is False


def test_detects_markdown_header():
    result = validate_checklist(BAD_BODY_WITH_HEADER)
    assert result["has_headers"] is True


def test_detects_exclamation():
    result = validate_checklist(BAD_BODY_WITH_EXCLAMATION)
    assert result["has_exclamation"] is True


def test_detects_audience_question():
    result = validate_checklist(BAD_BODY_WITH_QUESTION)
    assert result["has_audience_question"] is True


def test_detects_em_dash_instead_of_spaced_hyphen():
    result = validate_checklist(BAD_BODY_WITH_EM_DASH)
    assert result["has_em_dash"] is True
    assert result["uses_spaced_hyphen_dashes"] is False


def test_clean_body_passes_formatting_checks():
    body = "It is X. It is also Y. Not from us specifically - from any brand."
    result = validate_checklist(body)
    assert result["no_banned_formatting"] is True
    assert result["uses_spaced_hyphen_dashes"] is True
