"""FastAPI app: the dashboard API, plus the built frontend in production.

This process never talks to Telegram - that's app.bot.telegram_bot, run as
its own process. See Makefile / dev.sh for running both together.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.config import settings
from app.db.session import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database ready at %s", settings.database_path)
    yield


app = FastAPI(title="Skinstinct LinkedIn Drafting Assistant", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


_dist = settings.web_dist_dir
if _dist.exists():
    assets_dir = _dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> FileResponse:
        candidate = _dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_dist / "index.html")
else:
    logger.warning("web/dist not built yet - run `npm run build` in web/, or use the Vite dev server")
