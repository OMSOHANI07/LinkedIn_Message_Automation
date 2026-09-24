from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.db.models import NewsQueryCache
from app.pipeline import news
from app.pipeline.news import (
    NewsCandidate,
    _fetch_one_query,
    _get_cached,
    _normalise_title,
    _parse_feed_entries,
    _set_cache,
    build_search_queries,
    fetch_candidates,
    find_related_news,
    rank_candidates,
    resolve_redirect,
)
from app.pipeline.schemas import NewsQueries, NewsRankPick, NewsRanking

FIXTURES = Path(__file__).parent / "fixtures"
FEED_1 = (FIXTURES / "sample_feed_1.xml").read_text()
FEED_2 = (FIXTURES / "sample_feed_2.xml").read_text()


def _engine_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _candidates(n: int = 3) -> list[NewsCandidate]:
    return [
        NewsCandidate(f"Headline {i}", f"Publisher {i}", "Mon, 01 Sep 2026 00:00:00 GMT", f"https://news.google.com/rss/articles/X{i}", "q")
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# RSS parsing from a saved sample feed (no live network)
# ---------------------------------------------------------------------------


def test_parse_feed_entries_extracts_title_publisher_link():
    entries = _parse_feed_entries(FEED_1, "niacinamide skincare India")
    assert len(entries) == 2
    assert entries[0].title == "Niacinamide serums face scrutiny over labelling - The Hindu"
    assert entries[0].publisher == "The Hindu"
    assert entries[0].link == "https://news.google.com/rss/articles/CBMi1"
    assert entries[0].query == "niacinamide skincare India"


def test_parse_feed_entries_skips_items_missing_title_or_link():
    xml = "<rss><channel><item><title></title><link></link></item></channel></rss>"
    assert _parse_feed_entries(xml, "q") == []


# ---------------------------------------------------------------------------
# Deduplication across queries
# ---------------------------------------------------------------------------


def test_normalise_title_is_case_and_whitespace_insensitive():
    assert _normalise_title("  Some   Title  ") == _normalise_title("some title")


@pytest.mark.asyncio
async def test_fetch_candidates_dedupes_across_queries():
    responses = {"query one": FEED_1, "query two": FEED_2}

    async def fake_get(url, **kwargs):
        for q, body in responses.items():
            if q.replace(" ", "+") in url or q.replace(" ", "%20") in url:
                return MagicMock(text=body, raise_for_status=lambda: None)
        return MagicMock(text=FEED_1, raise_for_status=lambda: None)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch.object(news.httpx, "AsyncClient", return_value=mock_client):
        candidates = await fetch_candidates(["query one", "query two"])

    titles = [c.title for c in candidates]
    # the duplicate "Niacinamide..." title (present in both feeds) appears once
    assert titles.count("Niacinamide serums face scrutiny over labelling - The Hindu") == 1
    assert len(candidates) == 3  # 2 unique from feed 1 + 1 new from feed 2


# ---------------------------------------------------------------------------
# Query building: "when:30d" appended
# ---------------------------------------------------------------------------


def test_build_search_queries_appends_lookback_window(monkeypatch):
    monkeypatch.setattr(
        news,
        "generate_structured",
        lambda **kwargs: NewsQueries(queries=["niacinamide skincare India", "cosmetic labelling rules"]),
    )
    queries = build_search_queries("some approved post text")
    assert all(q.endswith("when:30d") for q in queries)
    assert "niacinamide skincare India when:30d" in queries


# ---------------------------------------------------------------------------
# Ranker: only real numbers from the list, never invented
# ---------------------------------------------------------------------------


def test_rank_candidates_rejects_out_of_list_numbers(monkeypatch):
    candidates = _candidates(3)
    monkeypatch.setattr(
        news,
        "generate_structured",
        lambda **kwargs: NewsRanking(
            picks=[
                NewsRankPick(number=2, relevance=8, reason="Relevant"),
                NewsRankPick(number=99, relevance=9, reason="Invented, out of range"),
                NewsRankPick(number=0, relevance=5, reason="Also invalid (1-indexed list)"),
            ]
        ),
    )
    picks = rank_candidates("post text", candidates)
    assert len(picks) == 1
    assert picks[0][0] is candidates[1]  # number=2 -> index 1


def test_rank_candidates_empty_when_no_candidates():
    assert rank_candidates("post text", []) == []


# ---------------------------------------------------------------------------
# Redirect resolution with fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_redirect_returns_resolved_url_on_success():
    mock_client = AsyncMock()
    mock_client.head = AsyncMock(return_value=MagicMock(url="https://real-publisher.example.com/article"))
    resolved = await resolve_redirect(mock_client, "https://news.google.com/rss/articles/X1")
    assert resolved == "https://real-publisher.example.com/article"


@pytest.mark.asyncio
async def test_resolve_redirect_falls_back_to_original_on_failure():
    mock_client = AsyncMock()
    mock_client.head = AsyncMock(side_effect=Exception("network error"))
    mock_client.get = AsyncMock(side_effect=Exception("network error too"))
    original = "https://news.google.com/rss/articles/X1"
    resolved = await resolve_redirect(mock_client, original)
    assert resolved == original


# ---------------------------------------------------------------------------
# Cache: hit on repeated / "Other news" fetches
# ---------------------------------------------------------------------------


def test_cache_round_trip():
    with _engine_session() as session:
        candidates = _candidates(2)
        _set_cache(session, "my query", candidates)
        cached = _get_cached(session, "my query")
        assert cached is not None
        assert [c.title for c in cached] == [c.title for c in candidates]


def test_cache_miss_when_absent():
    with _engine_session() as session:
        assert _get_cached(session, "never fetched") is None


@pytest.mark.asyncio
async def test_fetch_one_query_uses_cache_and_skips_http_call():
    with _engine_session() as session:
        _set_cache(session, "cached query", _candidates(1))

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=AssertionError("should not hit the network - cache should be used"))

        result = await _fetch_one_query(mock_client, session, "cached query")
        assert len(result) == 1
        mock_client.get.assert_not_called()


# ---------------------------------------------------------------------------
# End-to-end failure resilience
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_related_news_never_raises_on_query_generation_failure(monkeypatch):
    monkeypatch.setattr(news, "build_search_queries", MagicMock(side_effect=RuntimeError("Gemini down")))
    with _engine_session() as session:
        items, queries = await find_related_news(session, "post text")
    assert items == []


@pytest.mark.asyncio
async def test_find_related_news_returns_empty_when_disabled(monkeypatch):
    monkeypatch.setenv("NEWS_ENABLED", "false")
    with _engine_session() as session:
        items, queries = await find_related_news(session, "post text")
    assert items == []
