"""IST week boundary helpers - the weekly rhythm (Monday drafting job, the
auto-approve cap, /week, the once-a-day cap notice) all key off this."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")


def week_start_ist(now_ist: datetime | None = None) -> datetime:
    now_ist = now_ist or datetime.now(IST)
    return (now_ist - timedelta(days=now_ist.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def week_start_utc(now_ist: datetime | None = None) -> datetime:
    """Timezone-aware UTC - SQLModel's datetime columns reject naive
    datetimes even as query bind parameters, so this must stay aware."""
    return week_start_ist(now_ist).astimezone(UTC)


def iso_week_key(now_ist: datetime | None = None) -> str:
    """A stable per-week string, e.g. '2026-W39' - used to cap "one notice/nudge
    per day or week" without a cron-precise scheduler."""
    now_ist = now_ist or datetime.now(IST)
    year, week, _ = now_ist.isocalendar()
    return f"{year}-W{week:02d}"


def today_ist_key(now_ist: datetime | None = None) -> str:
    now_ist = now_ist or datetime.now(IST)
    return now_ist.date().isoformat()
