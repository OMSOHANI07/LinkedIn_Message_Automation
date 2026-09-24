"""Long-polling Telegram bot entrypoint.

The chat is a channel (id starts with -100), so it only ever receives
`channel_post` updates for the notes Meera posts, plus `callback_query`
updates when she taps a draft's inline buttons. Regular `message` updates are
also handled so this works in a normal DM/group chat during testing.
"""

from __future__ import annotations

import logging

from telegram import BotCommand, Update
from telegram.ext import Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.bot.commands import (
    COMMAND_LIST,
    cmd_autoapprove,
    cmd_backlog,
    cmd_calibration,
    cmd_draft,
    cmd_scores,
    cmd_settings,
    cmd_start,
    cmd_status,
    cmd_threshold,
    cmd_week,
)
from app.bot import queue_worker
from app.bot.handlers import handle_callback, handle_incoming_note
from app.config import settings
from app.db.session import init_db
from app.scheduler import start_scheduler

logger = logging.getLogger(__name__)

# Both message and channel_post updates need handling - a channel (which is
# what TELEGRAM_CHAT_ID normally is) only ever produces channel_post.
_MESSAGE_OR_CHANNEL_POST = filters.UpdateType.MESSAGE | filters.UpdateType.CHANNEL_POST

# New posts only - excludes edited_message / edited_channel_post so an edit
# to an old note doesn't get re-ingested as a fresh one.
_NOTE_UPDATE_FILTER = (filters.TEXT | filters.CAPTION) & ~filters.COMMAND & _MESSAGE_OR_CHANNEL_POST


async def _on_startup(app: Application) -> None:
    start_scheduler(app.bot)
    queue_worker.start_worker()
    try:
        await app.bot.set_my_commands([BotCommand(name, desc) for name, desc in COMMAND_LIST])
    except Exception:
        logger.exception("Failed to register bot command menu (non-fatal)")


def build_application() -> Application:
    app = ApplicationBuilder().token(settings.telegram_bot_token).post_init(_on_startup).build()

    # CommandHandler defaults to filters.UpdateType.MESSAGES only, which
    # silently drops channel_post updates - every command needs the explicit
    # filter below or /commands typed into the channel are never dispatched.
    def cmd(name: str, callback) -> CommandHandler:
        return CommandHandler(name, callback, filters=_MESSAGE_OR_CHANNEL_POST)

    app.add_handler(cmd("start", cmd_start))
    app.add_handler(cmd("status", cmd_status))
    app.add_handler(cmd("draft", cmd_draft))
    app.add_handler(cmd("backlog", cmd_backlog))
    app.add_handler(cmd("autoapprove", cmd_autoapprove))
    app.add_handler(cmd("threshold", cmd_threshold))
    app.add_handler(cmd("settings", cmd_settings))
    app.add_handler(cmd("scores", cmd_scores))
    app.add_handler(cmd("week", cmd_week))
    app.add_handler(cmd("calibration", cmd_calibration))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(_NOTE_UPDATE_FILTER, handle_incoming_note))

    return app


def run_bot() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    app = build_application()
    logger.info("Starting Telegram bot (long polling) for chat %s", settings.telegram_chat_id)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run_bot()
