"""Serializes note evaluation through a single asyncio worker so several
Telegram messages sent quickly never trigger parallel Gemini calls (rate
limits, cost, and out-of-order replies).

Jobs are plain zero-arg async callables; the worker just awaits them one at a
time. `queue_position()` gives the 1-based slot a new job would take right
now, including one currently in flight, so the caller can show "Queued (#N)".
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

Job = Callable[[], Awaitable[None]]

_queue: asyncio.Queue[Job] = asyncio.Queue()
_worker_busy = False
_worker_task: asyncio.Task | None = None


def queue_position() -> int:
    return (1 if _worker_busy else 0) + _queue.qsize() + 1


async def enqueue(job: Job) -> None:
    await _queue.put(job)


def start_worker() -> None:
    global _worker_task
    if _worker_task is None:
        _worker_task = asyncio.create_task(_worker_loop())


async def _worker_loop() -> None:
    global _worker_busy
    while True:
        job = await _queue.get()
        _worker_busy = True
        try:
            await job()
        except Exception:
            logger.exception("Note evaluation job failed")
        finally:
            _worker_busy = False
            _queue.task_done()
