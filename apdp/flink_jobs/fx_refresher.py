"""
FX Rate Refresher
=================
Fetches live exchange rates from ExchangeRate API and writes them to Redis.
Runs as a Docker service (fx-refresher) on a 1-hour cron schedule.

Also runs once immediately on startup to ensure rates are available
before the Flink normalizer processes its first non-NGN event.

ExchangeRate API:
  Endpoint : GET https://v6.exchangerate-api.com/v6/{key}/latest/NGN
  Response : { "conversion_rates": { "USD": 0.000633, "GBP": 0.000497, ... } }
  Note     : Rates are NGN → foreign, so we invert to get foreign → NGN

Environment variables:
  EXCHANGE_RATE_API_KEY  — ExchangeRate API key (from .env)
  REDIS_HOST             — Redis hostname (default: localhost)
  REDIS_PORT             — Redis port (default: 6379)
"""
import logging
import os
import sys
import time
from datetime import datetime, timezone

import httpx
import redis

# fx_service is in the same directory (flink_jobs/ or ingestion/pollers/)
sys.path.insert(0, os.path.dirname(__file__))
from fx_service import set_rate, SUPPORTED_CURRENCIES, REDIS_UPDATED_AT_KEY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("fx_refresher")

EXCHANGE_RATE_API_KEY  = os.getenv("EXCHANGE_RATE_API_KEY", "")
EXCHANGE_RATE_BASE_URL = os.getenv("EXCHANGE_RATE_BASE_URL", "https://v6.exchangerate-api.com/v6")
REDIS_HOST             = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT             = int(os.getenv("REDIS_PORT", "6379"))

# How long to wait between refresh attempts when running in loop mode
REFRESH_INTERVAL_SECONDS = 3600  # 1 hour


def build_redis_client() -> redis.Redis:
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=0,
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
    )


def fetch_rates_from_api() -> dict[str, float]:
    """
    Fetch NGN-based rates from ExchangeRate API.

    The API returns rates relative to NGN as base currency:
      { "USD": 0.000633 } means 1 NGN = 0.000633 USD
    We invert each rate to get: 1 USD = X NGN

    Returns dict of { "USD": 1580.5, "GBP": 2010.3, ... }
    """
    if not EXCHANGE_RATE_API_KEY:
        log.error("EXCHANGE_RATE_API_KEY is not set — cannot fetch live rates")
        return {}

    url = f"{EXCHANGE_RATE_BASE_URL}/{EXCHANGE_RATE_API_KEY}/latest/NGN"
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()

        if data.get("result") != "success":
            log.error(f"ExchangeRate API returned non-success: {data.get('result')}")
            return {}

        conversion_rates = data.get("conversion_rates", {})
        rates = {}
        for currency in SUPPORTED_CURRENCIES:
            raw_rate = conversion_rates.get(currency)
            if raw_rate and raw_rate > 0:
                # Invert: 1 NGN = 0.000633 USD → 1 USD = 1/0.000633 = 1580.5 NGN
                ngn_rate = round(1.0 / raw_rate, 4)
                rates[currency] = ngn_rate
                log.info(f"  1 {currency} = {ngn_rate:,.2f} NGN")
            else:
                log.warning(f"  No rate returned for {currency}")

        return rates

    except httpx.HTTPStatusError as e:
        log.error(f"ExchangeRate API HTTP error: {e.response.status_code} — {e.response.text}")
        return {}
    except Exception as e:
        log.error(f"Failed to fetch FX rates: {e}")
        return {}


def refresh_rates(redis_client: redis.Redis) -> bool:
    """
    Fetch live rates and write them to Redis.
    Returns True if at least one rate was successfully written.
    """
    log.info("Fetching FX rates from ExchangeRate API...")
    rates = fetch_rates_from_api()

    if not rates:
        log.warning("No rates fetched — Redis cache will retain previous values")
        return False

    success_count = 0
    for currency, rate in rates.items():
        if set_rate(currency, rate, redis_client):
            success_count += 1

    # Write last-updated timestamp
    try:
        updated_at = datetime.now(timezone.utc).isoformat()
        redis_client.set(REDIS_UPDATED_AT_KEY, updated_at)
    except Exception as e:
        log.warning(f"Could not write fx:updated_at: {e}")

    log.info(f"FX refresh complete — {success_count}/{len(rates)} rates written to Redis")
    return success_count > 0


def run_once():
    """Single refresh — used by cron or manual trigger."""
    try:
        r = build_redis_client()
        r.ping()
    except Exception as e:
        log.error(f"Cannot connect to Redis at {REDIS_HOST}:{REDIS_PORT}: {e}")
        sys.exit(1)

    success = refresh_rates(r)
    sys.exit(0 if success else 1)


def run_loop():
    """
    Continuous refresh loop — runs refresh immediately on startup,
    then every REFRESH_INTERVAL_SECONDS.
    Used when the service is started without supercronic (dev mode).
    """
    log.info(f"Starting FX refresher loop (interval: {REFRESH_INTERVAL_SECONDS}s)")

    try:
        r = build_redis_client()
        r.ping()
        log.info(f"Redis connected at {REDIS_HOST}:{REDIS_PORT}")
    except Exception as e:
        log.error(f"Cannot connect to Redis: {e}")
        sys.exit(1)

    while True:
        refresh_rates(r)
        log.info(f"Next refresh in {REFRESH_INTERVAL_SECONDS // 60} minutes")
        time.sleep(REFRESH_INTERVAL_SECONDS)


if __name__ == "__main__":
    # If called with --once, do a single refresh and exit (for cron)
    # Otherwise run the continuous loop
    if "--once" in sys.argv:
        run_once()
    else:
        run_loop()
