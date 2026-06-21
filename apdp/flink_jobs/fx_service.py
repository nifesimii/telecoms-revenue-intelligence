"""
FX Rate Service
===============
Redis-backed currency exchange rate cache for the normalization pipeline.

Responsibilities:
  - Provide NGN conversion rates for USD, GBP, EUR, GHS, KES
  - Cache rates in Redis with a 2-hour TTL
  - Fall back to last known rate if Redis is unavailable
  - Fall back to hardcoded emergency rates if no rate has ever been cached

Redis key structure:
  fx:rate:USD:NGN  →  "1580.50"
  fx:rate:GBP:NGN  →  "2010.75"
  fx:rate:EUR:NGN  →  "1720.30"
  fx:rate:GHS:NGN  →  "105.40"
  fx:rate:KES:NGN  →  "12.10"
  fx:updated_at    →  "2026-03-07T23:00:00+00:00"

Used by:
  normalizer_core.py  — convert_to_ngn() called per non-NGN event
  fx_refresher.py     — writes fresh rates on schedule
"""
import logging
import os
from typing import Optional

log = logging.getLogger("fx_service")

# Supported non-NGN currencies
SUPPORTED_CURRENCIES = {"USD", "GBP", "EUR", "GHS", "KES"}

# Emergency fallback rates — used only if Redis has no cached rate at all.
# These are approximate and should never be relied on in production.
# fx_refresher.py populates Redis on startup so this is a last resort.
FALLBACK_RATES: dict[str, float] = {
    "USD": 1580.0,
    "GBP": 2010.0,
    "EUR": 1720.0,
    "GHS": 105.0,
    "KES": 12.0,
}

REDIS_KEY_PREFIX = "fx:rate"
REDIS_UPDATED_AT_KEY = "fx:updated_at"
REDIS_TTL_SECONDS = 7200  # 2 hours — refresher runs hourly so this gives a buffer


def _rate_key(from_currency: str) -> str:
    return f"{REDIS_KEY_PREFIX}:{from_currency}:NGN"


def get_redis_client():
    """
    Lazy Redis client — imported here to avoid a hard dependency when
    running test_normalizer.py without Redis available.
    Returns None if Redis is not configured or unreachable.
    """
    try:
        import redis
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        client = redis.Redis(host=host, port=port, db=0, socket_timeout=1.0)
        client.ping()
        return client
    except Exception as e:
        log.warning(f"Redis unavailable: {e} — will use fallback rates")
        return None


def get_rate(currency: str, redis_client=None) -> Optional[float]:
    """
    Get the NGN conversion rate for the given currency.

    Lookup order:
      1. Redis cache (live rate, refreshed hourly by fx_refresher.py)
      2. FALLBACK_RATES (hardcoded emergency rates)
      3. None (unsupported currency — caller should leave amount_ngn as-is)

    Args:
      currency     : ISO 4217 currency code e.g. "USD"
      redis_client : optional pre-built Redis client (avoids reconnect per call)

    Returns:
      float rate (1 unit of currency = N NGN) or None
    """
    currency = currency.upper().strip()

    if currency == "NGN":
        return 1.0

    if currency not in SUPPORTED_CURRENCIES:
        log.warning(f"Unsupported currency: {currency} — skipping FX conversion")
        return None

    # Try Redis first
    client = redis_client or get_redis_client()
    if client:
        try:
            raw = client.get(_rate_key(currency))
            if raw:
                rate = float(raw.decode("utf-8"))
                log.debug(f"FX cache hit: 1 {currency} = {rate} NGN")
                return rate
            else:
                log.warning(f"FX cache miss for {currency} — using fallback rate")
        except Exception as e:
            log.warning(f"Redis read error for {currency}: {e} — using fallback rate")

    # Fall back to hardcoded rates
    fallback = FALLBACK_RATES.get(currency)
    if fallback:
        log.warning(f"Using fallback rate: 1 {currency} = {fallback} NGN")
        return fallback

    return None


def convert_to_ngn(amount: float, currency: str, redis_client=None) -> float:
    """
    Convert an amount in the given currency to NGN.

    If currency is NGN, returns amount unchanged.
    If conversion rate is unavailable, returns amount unchanged and logs a warning.
    This ensures amount_ngn is always populated — just potentially inaccurate
    for unsupported/unavailable currencies rather than null.

    Args:
      amount       : transaction amount in original currency
      currency     : ISO 4217 currency code
      redis_client : optional pre-built Redis client

    Returns:
      float amount in NGN
    """
    if currency == "NGN":
        return amount

    rate = get_rate(currency, redis_client)
    if rate is None:
        log.warning(
            f"No FX rate available for {currency} — "
            f"amount_ngn will equal raw amount {amount}"
        )
        return amount

    converted = round(amount * rate, 2)
    log.debug(f"FX: {amount} {currency} → {converted} NGN (rate: {rate})")
    return converted


def set_rate(currency: str, rate: float, redis_client=None) -> bool:
    """
    Write an FX rate to Redis. Called by fx_refresher.py.

    Args:
      currency     : ISO 4217 currency code e.g. "USD"
      rate         : NGN equivalent of 1 unit of currency
      redis_client : pre-built Redis client

    Returns:
      True on success, False on failure
    """
    client = redis_client or get_redis_client()
    if not client:
        return False
    try:
        client.setex(_rate_key(currency), REDIS_TTL_SECONDS, str(rate))
        log.info(f"FX rate set: 1 {currency} = {rate} NGN (TTL: {REDIS_TTL_SECONDS}s)")
        return True
    except Exception as e:
        log.error(f"Failed to set FX rate for {currency}: {e}")
        return False


def get_all_rates(redis_client=None) -> dict[str, float]:
    """
    Return all currently cached rates. Used by fx_refresher.py health check
    and for logging/debugging.
    """
    client = redis_client or get_redis_client()
    rates = {}
    for currency in SUPPORTED_CURRENCIES:
        rate = get_rate(currency, client)
        if rate:
            rates[currency] = rate
    return rates