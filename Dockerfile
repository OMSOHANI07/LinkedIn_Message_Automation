# Builds the React dashboard, then runs it inside the same FastAPI process
# that also serves the API (see app/main.py) - and starts the Telegram bot
# as a second process in the same container, so both share one filesystem
# and therefore one SQLite database file (mount a volume at DATABASE_PATH's
# directory so it survives redeploys).

FROM node:22-slim AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY --from=web-build /web/dist/ ./web/dist/
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["./docker-entrypoint.sh"]
