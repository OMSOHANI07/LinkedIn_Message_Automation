"""Two scheduled jobs, both running inside the bot process since they need a
live Bot instance to send output to Telegram:

- Weekly: every Monday 09:00 IST, rank the backlog and draft the top 3.
- Daily nudge: at settings.nudge_hour_ist (default 19:00), if any drafts are
  waiting for review, send one reminder - never more than one per day.
"""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot

from app.config import settings
from app.db.models import Note
from app.db.session import session_scope
from app.db.settings_store import get_settings, update_settings
from app.pipeline.orchestrator import draft_top_notes, get_pending_review_count
from app.pipeline.week import today_ist_key

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


async def weekly_draft_job(bot: Bot) -> None:
    from app.bot.handlers import send_draft_message  # avoid import cycle at module load

    logger.info("Running weekly draft job: ranking backlog, drafting top 3")
    chat_id = int(settings.telegram_chat_id)
    with session_scope() as session:
        drafts = draft_top_notes(session, count=3)
        if not drafts:
            await bot.send_message(
                chat_id=chat_id, text="Weekly run: nothing publishable in the backlog this week."
            )
            return
        await bot.send_message(chat_id=chat_id, text=f"Weekly run: {len(drafts)} draft(s) ready for review.")
        for draft in drafts:
            note = session.get(Note, draft.note_id)
            if note is not None:
                await send_draft_message(bot, chat_id, draft, note)


async def daily_nudge_job(bot: Bot) -> None:
    chat_id = int(settings.telegram_chat_id)
    with session_scope() as session:
        app_settings = get_settings(session)
        if not app_settings.nudge_enabled:
            return
        today_key = today_ist_key()
        if app_settings.last_nudge_date == today_key:
            return  # already nudged today

        pending = get_pending_review_count(session)
        if pending == 0:
            return

        update_settings(session, last_nudge_date=today_key)

    plural = "s" if pending != 1 else ""
    await bot.send_message(chat_id=chat_id, text=f"{pending} draft{plural} waiting for review.")


def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=IST)
    scheduler.add_job(
        weekly_draft_job,
        trigger=CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=IST),
        args=[bot],
        id="weekly_draft_job",
        replace_existing=True,
    )
    # Fixed at 19:00 IST as the trigger time; settings.nudge_enabled/nudge_hour_ist
    # are read inside the job so /settings changes take effect without a restart -
    # nudge_hour_ist changes require a bot restart to move the actual trigger time.
    scheduler.add_job(
        daily_nudge_job,
        trigger=CronTrigger(hour=19, minute=0, timezone=IST),
        args=[bot],
        id="daily_nudge_job",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started: weekly draft job Monday 09:00 IST, daily nudge check 19:00 IST")
    return scheduler
