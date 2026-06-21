FROM python:3.11-slim

WORKDIR /app

# ── System deps ───────────────────────────────────────────────────────────────
# supercronic: reliable cron runner for Docker containers.
# Used by the mono-batch service (cron 23:00 daily bank statement pull).
# curl + ca-certificates needed to download the supercronic binary.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && SUPERCRONIC_URL="https://github.com/aptible/supercronic/releases/download/v0.2.29/supercronic-linux-amd64" \
    && curl -fsSL "$SUPERCRONIC_URL" -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Python deps ───────────────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000