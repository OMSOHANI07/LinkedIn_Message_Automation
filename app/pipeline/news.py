"""AI call #4 (approved drafts only): finds real, related news via Google
News RSS. Runs strictly after a draft is APPROVED - never before, never
feeds into drafting or the decision. A failure here never breaks the
pipeline: it just means no news gets attached.

Fact-integrity mirrors the rest of the app: the model NEVER invents a title
or URL. It only picks numbers out of a list of real RSS candidates; the
titles/publishers/links stored are always the RSS feed's own data.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import feedparser
import httpx
from sqlmodel import Session, select

from app.config import settings
from app.db.models import NewsQueryCache
from app.pipeline.gemini_client import generate_structured
from app.pipeline.schemas import NewsQueries, NewsRanking

logger = logging.getLogger(__name__)

RSS_URL = "https://news.google.com/rss/search"
USER_AGENT = (
    "SkinstinctDraftingAssistant/1.0 "
    "(+https://github.com/OMSOHANI07/LinkedIn_Message_Automation)"
)
CACHE_TTL = timedelta(hours=6)
FETCH_TIMEOUT = 10.0
REDIRECT_TIMEOUT = 5.0


class NewsCandidate:
    __slots__ = ("title", "publisher", "published_at", "link", "query")

    def __init__(self, title: str, publisher: str, published_at: str | None, link: str, query: str):
        self.title = title
        self.publisher = publisher
        self.published_at = published_at
        self.link = link
        self.query = query

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "publisher": self.publisher,
            "published_at": self.published_at,
            "link": self.link,
        }

    @classmethod
    def from_dict(cls, d: dict, query: str) -> "NewsCandidate":
        return cls(d["title"], d["publisher"], d.get("published_at"), d["link"], query)


def _normalise_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().lower())


def build_search_queries(post_text: str) -> list[str]:
    """AI call #4a: 2-5 word queries from the finished, approved post."""
    result = generate_structured(
        system_instruction=(
            "Given a finished LinkedIn post, return exactly 3 short Google News search "
            "queries (2-5 words each) about its core topic - the ingredient, regulation, "
            "India market angle, or consumer issue it discusses. Queries only, no punctuation "
            "beyond what a normal search query would have."
        ),
        contents=post_text,
        schema=NewsQueries,
    )
    lookback = f"when:{settings.news_lookback_days}d"
    return [f"{q.strip()} {lookback}" for q in result.queries[:3] if q.strip()]


def _parse_feed_entries(xml_text: str, query: str) -> list[NewsCandidate]:
    feed = feedparser.parse(xml_text)
    candidates: list[NewsCandidate] = []
    for entry in feed.entries:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        if not title or not link:
            continue
        publisher = ""
        source = getattr(entry, "source", None)
        if source is not None:
            publisher = (getattr(source, "title", "") or getattr(source, "href", "") or "").strip()
        published_at = getattr(entry, "published", None)
        candidates.append(NewsCandidate(title, publisher, published_at, link, query))
    return candidates


def _get_cached(session: Session, query: str) -> list[NewsCandidate] | None:
    row = session.exec(select(NewsQueryCache).where(NewsQueryCache.query == query)).first()
    if row is None:
        return None
    fetched_at = row.fetched_at if row.fetched_at.tzinfo else row.fetched_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - fetched_at > CACHE_TTL:
        return None
    try:
        items = json.loads(row.items_json)
    except (json.JSONDecodeError, TypeError):
        return None
    return [NewsCandidate.from_dict(item, query) for item in items]


def _set_cache(session: Session, query: str, candidates: list[NewsCandidate]) -> None:
    items_json = json.dumps([c.to_dict() for c in candidates])
    row = session.exec(select(NewsQueryCache).where(NewsQueryCache.query == query)).first()
    if row is None:
        row = NewsQueryCache(query=query, items_json=items_json)
    else:
        row.items_json = items_json
        row.fetched_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()


async def _fetch_one_query(client: httpx.AsyncClient, session: Session | None, query: str) -> list[NewsCandidate]:
    if session is not None:
        cached = _get_cached(session, query)
        if cached is not None:
            return cached

    url = f"{RSS_URL}?q={quote_plus(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        response = await client.get(url, timeout=FETCH_TIMEOUT, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
    except Exception:
        logger.exception("News RSS fetch failed for query %r", query)
        return []

    candidates = _parse_feed_entries(response.text, query)
    if session is not None:
        _set_cache(session, query, candidates)
    return candidates


async def fetch_candidates(queries: list[str], session: Session | None = None) -> list[NewsCandidate]:
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_fetch_one_query(client, session, q) for q in queries])

    seen: set[str] = set()
    deduped: list[NewsCandidate] = []
    for group in results:
        for c in group:
            key = _normalise_title(c.title)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(c)
    return deduped[:15]


def rank_candidates(post_text: str, candidates: list[NewsCandidate]) -> list[tuple[NewsCandidate, int, str]]:
    """AI call #4b: picks by NUMBER only from the real candidate list -
    any number outside the list is dropped, never trusted as a new item."""
    if not candidates:
        return []
    listing = "\n".join(
        f"{i + 1}. {c.title} - {c.publisher or 'unknown publisher'} - {c.published_at or 'date unknown'}"
        for i, c in enumerate(candidates)
    )
    contents = f"Post:\n{post_text}\n\nCandidates:\n{listing}"
    result = generate_structured(
        system_instruction=(
            "You are ranking real news candidates for relevance to a LinkedIn post. "
            "Pick up to 3 candidates STRICTLY by their number from the numbered list - "
            "never invent a number, title or URL of your own. If nothing is genuinely "
            "relevant, return an empty list. Score relevance 0-10 and give a one-line "
            "reason for each pick."
        ),
        contents=contents,
        schema=NewsRanking,
    )
    picks: list[tuple[NewsCandidate, int, str]] = []
    for pick in result.picks:
        idx = pick.number - 1
        if 0 <= idx < len(candidates):
            picks.append((candidates[idx], pick.relevance, pick.reason))
        else:
            logger.warning("Ranker returned out-of-list candidate number %s; dropped", pick.number)
    return picks


async def resolve_redirect(client: httpx.AsyncClient, url: str) -> str:
    """Google News RSS links are redirect URLs - try to resolve to the real
    publisher URL. Falls back to the original link on any failure; never
    constructs a URL of its own."""
    for method in (client.head, client.get):
        try:
            response = await method(url, timeout=REDIRECT_TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT})
            resolved = str(response.url)
            if resolved:
                return resolved
        except Exception:
            continue
    logger.warning("Could not resolve redirect for %s; keeping the Google News link", url)
    return url


async def find_related_news(
    session: Session,
    post_text: str,
    queries: list[str] | None = None,
    exclude_titles: set[str] | None = None,
) -> tuple[list[dict], list[str]]:
    """Returns (items, queries_used). `items` is up to NEWS_MAX_ITEMS dicts:
    title, publisher, published_at, url, relevance, reason, query. Never
    raises - any failure just means an empty result.
    """
    if not settings.news_enabled:
        return [], queries or []

    try:
        used_queries = queries or await asyncio.to_thread(build_search_queries, post_text)
        candidates = await fetch_candidates(used_queries, session=session)

        if exclude_titles:
            candidates = [c for c in candidates if _normalise_title(c.title) not in exclude_titles]

        ranked = await asyncio.to_thread(rank_candidates, post_text, candidates)
        ranked = [p for p in ranked if p[1] >= settings.news_min_relevance]
        ranked.sort(key=lambda p: p[1], reverse=True)
        ranked = ranked[: settings.news_max_items]

        if not ranked:
            return [], used_queries

        async with httpx.AsyncClient() as client:
            resolved_links = await asyncio.gather(*[resolve_redirect(client, c.link) for c, _, _ in ranked])

        items = [
            {
                "title": candidate.title,
                "publisher": candidate.publisher or "unknown publisher",
                "published_at": candidate.published_at,
                "url": link,
                "relevance": relevance,
                "reason": reason,
                "query": candidate.query,
            }
            for (candidate, relevance, reason), link in zip(ranked, resolved_links)
        ]
        return items, used_queries
    except Exception:
        logger.exception("News lookup failed; continuing without news")
        return [], queries or []
