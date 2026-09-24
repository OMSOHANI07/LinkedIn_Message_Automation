"""One-off data migrations that plain `create_all()` can't express - it only
creates missing tables, never rewrites existing data. Idempotent: safe to run
on every startup, including against a brand-new (empty) database.

Context: the 3-band decision model (auto_approved/needs_review/low_quality)
and shadow mode were replaced with a binary approved/rejected model. Existing
rows still hold the old values and must be rewritten so the app (which now
only knows APPROVED/REJECTED) can read them.

Note: SQLAlchemy's default Enum column stores the Python enum *member name*
(e.g. "NEEDS_REVIEW"), not its `.value` ("needs_review") - confirmed by
inspecting a live dev database. The raw SQL below matches on those names.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlmodel import Session

logger = logging.getLogger(__name__)

_DECISION_RENAMES = {
    "AUTO_APPROVED": "APPROVED",
    "NEEDS_REVIEW": "REJECTED",
    "LOW_QUALITY": "REJECTED",
}
_MODE_RENAMES = {"SHADOW": "ON"}


def _table_exists(session: Session, name: str) -> bool:
    row = session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"), {"name": name}
    ).first()
    return row is not None


def _column_exists(session: Session, table: str, column: str) -> bool:
    rows = session.execute(text(f"PRAGMA table_info({table})")).all()
    return any(r[1] == column for r in rows)


def migrate_binary_decision(session: Session) -> None:
    if _table_exists(session, "draft"):
        for old, new in _DECISION_RENAMES.items():
            session.execute(text("UPDATE draft SET decision = :new WHERE decision = :old"), {"new": new, "old": old})
        # shadow_decision is retired (no longer a mapped column) - clear any
        # stale 3-band values if the column is still physically present.
        if _column_exists(session, "draft", "shadow_decision"):
            session.execute(text("UPDATE draft SET shadow_decision = NULL WHERE shadow_decision IS NOT NULL"))

    if _table_exists(session, "appsettings"):
        for old, new in _MODE_RENAMES.items():
            session.execute(text("UPDATE appsettings SET mode = :new WHERE mode = :old"), {"new": new, "old": old})

    session.commit()


def run_all_migrations(session: Session) -> None:
    migrate_binary_decision(session)
    logger.info("Data migrations complete")
