#!/bin/sh
# Runs the Telegram bot (long polling) and the FastAPI dashboard/API as two
# processes in one container, so they share this filesystem's SQLite file.
# The bot restarts on its own if it crashes; the API runs in the foreground
# so the container's health/restart policy is driven by it.
set -e

(
  while true; do
    python -m app.bot.telegram_bot
    echo "Telegram bot exited (code $?) - restarting in 5s" >&2
    sleep 5
  done
) &

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
