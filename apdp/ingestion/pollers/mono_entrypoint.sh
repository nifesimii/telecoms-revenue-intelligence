#!/bin/sh
# Entrypoint for the mono-batch Docker service.
# Writes the crontab and starts supercronic.
# Using /bin/sh (not bash) for maximum compatibility across slim images.

set -e

CRONTAB_FILE="/tmp/mono-crontab"

echo "0 23 * * * python /app/ingestion/pollers/mono_batch.py" > "$CRONTAB_FILE"

echo "[mono-batch] Cron schedule: daily at 23:00 UTC"
echo "[mono-batch] Starting supercronic..."

exec supercronic "$CRONTAB_FILE"