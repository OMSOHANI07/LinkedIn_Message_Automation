"""Central config, loaded once from .env. No secret is ever hardcoded here."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


class Settings:
    """Lazily-validated settings. Required vars only raise when actually read,
    so `python -m app.cli import-notes` works without Telegram/Gemini keys set.
    """

    @property
    def telegram_bot_token(self) -> str:
        return _require("TELEGRAM_BOT_TOKEN")

    @property
    def telegram_chat_id(self) -> str:
        return _require("TELEGRAM_CHAT_ID")

    @property
    def gemini_api_key(self) -> str:
        return _require("GEMINI_API_KEY")

    @property
    def gemini_model(self) -> str:
        return os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    @property
    def triage_threshold(self) -> int:
        return int(os.getenv("TRIAGE_THRESHOLD", "7"))

    @property
    def min_note_chars(self) -> int:
        """Messages shorter than this are ignored (not queued for evaluation)."""
        return int(os.getenv("MIN_NOTE_CHARS", "40"))

    @property
    def admin_user_ids(self) -> set[int]:
        """Optional allow-list for button presses/settings commands. Empty
        (default) means any press in TELEGRAM_CHAT_ID is trusted, same as
        before this existed."""
        raw = os.getenv("ADMIN_USER_IDS", "").strip()
        if not raw:
            return set()
        return {int(part) for part in raw.split(",") if part.strip()}

    @property
    def news_enabled(self) -> bool:
        return os.getenv("NEWS_ENABLED", "true").strip().lower() not in ("false", "0", "no")

    @property
    def news_min_relevance(self) -> int:
        return int(os.getenv("NEWS_MIN_RELEVANCE", "6"))

    @property
    def news_lookback_days(self) -> int:
        return int(os.getenv("NEWS_LOOKBACK_DAYS", "30"))

    @property
    def news_max_items(self) -> int:
        return int(os.getenv("NEWS_MAX_ITEMS", "3"))

    @property
    def database_path(self) -> Path:
        """Overridable so a deployment can point this at a mounted persistent
        volume (e.g. Railway) instead of the container's ephemeral disk."""
        raw = os.getenv("DATABASE_PATH")
        return Path(raw) if raw else BASE_DIR / "skinstinct.db"

    @property
    def notes_import_dir(self) -> Path:
        return BASE_DIR / "notes"

    @property
    def web_dist_dir(self) -> Path:
        return BASE_DIR / "web" / "dist"

    @property
    def cors_origins(self) -> list[str]:
        """Comma-separated extra origins (e.g. a Vercel deployment URL) allowed
        to call the API, in addition to the local Vite dev server."""
        raw = os.getenv("CORS_ORIGINS", "").strip()
        extra = [origin.strip() for origin in raw.split(",") if origin.strip()]
        return ["http://localhost:5173", "http://127.0.0.1:5173", *extra]


settings = Settings()
