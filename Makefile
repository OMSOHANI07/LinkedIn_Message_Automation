.PHONY: install dev api web bot scheduler-check test build import-notes clean

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt
	cd web && npm install

# Runs the FastAPI API + the Vite dev server together. The Telegram bot is a
# separate long-running process (`make bot`) since it needs its own event loop.
dev:
	@trap 'kill 0' EXIT INT TERM; \
	( $(PY) -m uvicorn app.main:app --reload --port 8000 ) & \
	( cd web && npm run dev ) & \
	wait

api:
	$(PY) -m uvicorn app.main:app --reload --port 8000

web:
	cd web && npm run dev

bot:
	$(PY) -m app.bot.telegram_bot

test:
	$(PY) -m pytest -q

build:
	cd web && npm run build

import-notes:
	$(PY) -m app.cli import-notes

clean:
	rm -rf $(VENV) web/node_modules web/dist skinstinct.db
