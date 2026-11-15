# syntax=docker/dockerfile:1

FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# time.tzset() in juliabot/config.py needs the zoneinfo database for named zones.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first so code edits do not invalidate the installed layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# client.setup_hook() resolves cogs relative to the working directory, so the
# package has to live at /app/juliabot.
COPY juliabot/ ./juliabot/

RUN useradd --uid 10001 --create-home \
    --home-dir /home/juliabot --shell /usr/sbin/nologin juliabot
USER 10001:10001

# Exec form: SIGTERM reaches the bot so the heartbeat row is cleaned up.
CMD ["python", "-m", "juliabot"]
