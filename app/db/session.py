"""SQLite engine + session helpers."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

engine = create_engine(
    f"sqlite:///{settings.database_path}",
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    from app.db.migrations import run_all_migrations

    with Session(engine) as session:
        run_all_migrations(session)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency.

    expire_on_commit=False: several call sites (import loops, backlog ranking)
    read attributes off objects after an earlier commit in the same session -
    the default would mark them expired and raise DetachedInstanceError once
    the session/request is done.
    """
    with Session(engine, expire_on_commit=False) as session:
        yield session


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """For use outside request handlers (bot, scheduler, CLI)."""
    with Session(engine, expire_on_commit=False) as session:
        yield session
