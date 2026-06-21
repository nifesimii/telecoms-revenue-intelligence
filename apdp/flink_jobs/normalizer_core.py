"""
Core normalization logic — pure Python, no Flink dependency.
Imported by both normalizer.py (Flink job) and tests.

Canonical schema version: 1.3.0

New fields (v1.3.0 — telecom trade partner extension):
  See flink_jobs/SCHEMA_v1.3.0.md for the full spec.

  Additive over v1.2.0. Existing PSP events keep the v1.2.0 shape; the new
  fields are populated only on telecom events (provider="telecom_batch").

  Added canonical fields (nullable):
    - partner_id, dealer_id
    - product_type, gross_revenue
    - commission_amount, commission_rate
    - settlement_period            (YYYYMM — joins to FBB project's mon_period)
    - linked_statement_ref         (settlement events → commission_statement)

  Three new event types share provider "telecom_batch":
    - telecom.dealer_sale          (Consumer → Dealer)
    - telecom.commission_statement (MTN ledger entry, no money movement)
    - telecom.settlement           (MTN → Dealer)

  transaction_type "STATEMENT" is new in v1.3.0 — represents a ledger entry
  rather than a money movement.

Prior fields (v1.2.0):
  - fx_rate, fx_source

Prior fields (v1.1.0):
  - payment_source, ingestion_mode, virtual_account_type,
    settlement_mode, expected_settlement_at
"""
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

log = logging.getLogger("normalizer_core")

# ── FX service — lazy import so tests work without Redis ─────────────────────
# fx_service.py lives alongside normalizer_core.py in flink_jobs/.
# If Redis is unavailable, fx_service falls back to hardcoded rates silently.
try:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from fx_service import convert_to_ngn, get_rate, get_redis_client, FALLBACK_RATES
    _FX_AVAILABLE = True
except ImportError:
    log.warning("fx_service not found — FX conversion disabled, amount_ngn = raw amount")
    _FX_AVAILABLE = False
    FALLBACK_RATES: dict = {}

    def convert_to_ngn(amount, currency, redis_client=None):
        return amount

    def get_rate(currency, redis_client=None):
        return None

    def get_redis_client():
        return None


# Module-level Redis client shared across all normalize_* calls in this
# Flink task slot — avoids a new connection per event.
_redis_client = None


def _get_shared_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = get_redis_client()
    return _redis_client


def _fx_enrich(amount: float, currency: str) -> tuple:
    """
    Convert amount to NGN and return enrichment metadata.

    Returns:
      (amount_ngn, fx_rate, fx_source)
      amount_ngn : converted NGN value
      fx_rate    : rate used (None when currency is already NGN)
      fx_source  : "live" | "fallback" | None
    """
    if currency == "NGN":
        return amount, None, None

    redis_client = _get_shared_redis()
    rate = get_rate(currency, redis_client)

    if rate is None:
        return amount, None, None

    is_fallback = (rate == FALLBACK_RATES.get(currency))
    fx_source = "fallback" if is_fallback else "live"
    amount_ngn = round(amount * rate, 2)
    return amount_ngn, rate, fx_source


# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize_phone(phone: Optional[str], country: str = "NG") -> Optional[str]:
    if not phone:
        return None
    digits = re.sub(r"\D", "", str(phone))
    country_codes = {"NG": "234", "GH": "233", "KE": "254"}
    if digits.startswith("0") and len(digits) == 11:
        code = country_codes.get(country, "234")
        digits = code + digits[1:]
    return f"+{digits}" if digits else None


def normalize_status(provider: str, raw_status: str) -> str:
    status = str(raw_status).upper().strip()
    mappings = {
        "SUCCESSFUL":     "SUCCESS",
        "SUCCESS":        "SUCCESS",
        "FAILED":         "FAILED",
        "FAILURE":        "FAILED",
        "PENDING":        "PENDING",
        "PROCESSING":     "PENDING",
        "PAID":           "SUCCESS",
        "OVERPAID":       "SUCCESS",
        "PARTIALLY_PAID": "PENDING",
        "PARTIAL":        "PENDING",
        "EXPIRED":        "FAILED",
        "CANCELLED":      "FAILED",
        "CREDIT":         "SUCCESS",
        "DEBIT":          "SUCCESS",
        # v1.3.0 telecom statuses
        "FINAL":          "SUCCESS",
        "DRAFT":          "PENDING",
        "DISPUTED":       "FAILED",
    }
    return mappings.get(status, "UNKNOWN")


# ── Telecom (v1.3.0) helpers ──────────────────────────────────────────────────

_EMPTY_PARTY = {"name": None, "email": None, "phone": None, "bank": None}


def _telecom_base(raw: dict, event_type: str) -> dict:
    """Common v1.3.0 telecom envelope fields. Caller overrides as needed."""
    currency = raw.get("currency") or "NGN"
    return {
        "provider":              "telecom_batch",
        "event_type":            event_type,
        "currency":              currency,
        "fx_rate":               None,
        "fx_source":             None,
        "payment_source":        raw.get("source_system"),
        "ingestion_mode":        "BATCH_EOD",
        "virtual_account_type":  None,
        "settlement_mode":       None,
        "expected_settlement_at": None,
        # v1.3.0 additions
        "partner_id":            raw.get("partner_code"),
        "dealer_id":             raw.get("dealer_code"),
        "settlement_period":     raw.get("settlement_period"),
        "product_type":          raw.get("product_type"),
        "gross_revenue":         None,
        "commission_amount":     None,
        "commission_rate":       None,
        "linked_statement_ref":  None,
    }


def normalize_telecom_dealer_sale(envelope: dict) -> dict:
    raw = envelope["raw"]
    amount = float(raw.get("total_amount_ngn", 0))
    currency = raw.get("currency") or "NGN"
    amount_ngn, fx_rate, fx_source = _fx_enrich(amount, currency)

    base = _telecom_base(raw, "telecom.dealer_sale")
    base.update(
        {
            "transaction_id":   f"tel_sale_{raw.get('transaction_ref', 'unknown')}",
            "amount":           amount,
            "amount_ngn":       amount_ngn,
            "fx_rate":          fx_rate,
            "fx_source":        fx_source,
            "status":           "SUCCESS",
            "transaction_type": "PAYMENT",
            "gross_revenue":    amount_ngn,
            "sender": {
                "name":  None,
                "email": None,
                "phone": normalize_phone(raw.get("consumer_msisdn")),
                "bank":  None,
            },
            "receiver":     dict(_EMPTY_PARTY),
            "initiated_at": raw.get("sale_date"),
            "completed_at": raw.get("sale_date"),
            "metadata": {
                "imei":           raw.get("imei") or None,
                "product_code":   raw.get("product_code"),
                "payment_method": str(raw.get("payment_method", "")).upper() or None,
            },
        }
    )
    return base


def normalize_telecom_commission_statement(envelope: dict) -> dict:
    raw = envelope["raw"]
    commission = float(raw.get("commission_amount_ngn", 0))
    gross = float(raw.get("gross_revenue_ngn", 0))
    currency = raw.get("currency") or "NGN"
    amount_ngn, fx_rate, fx_source = _fx_enrich(commission, currency)
    raw_status = str(raw.get("status", ""))

    base = _telecom_base(raw, "telecom.commission_statement")
    base.update(
        {
            "transaction_id":   f"tel_stmt_{raw.get('statement_ref', 'unknown')}",
            "amount":           commission,
            "amount_ngn":       amount_ngn,
            "fx_rate":          fx_rate,
            "fx_source":        fx_source,
            "status":           normalize_status("telecom", raw_status),
            "transaction_type": "STATEMENT",
            "gross_revenue":    gross,
            "commission_amount": amount_ngn,
            "commission_rate":  float(raw.get("commission_rate", 0)) or None,
            "sender":           dict(_EMPTY_PARTY),
            "receiver":         dict(_EMPTY_PARTY),
            "initiated_at":     raw.get("statement_date"),
            "completed_at":     raw.get("statement_date"),
            "metadata": {
                "activation_count": int(raw.get("activation_count", 0)),
                "qualified_count":  int(raw.get("qualified_count", 0))
                                    if raw.get("qualified_count") not in (None, "") else None,
                "statement_status": raw_status.upper() or None,
            },
        }
    )
    return base


def normalize_telecom_settlement(envelope: dict) -> dict:
    raw = envelope["raw"]
    amount = float(raw.get("amount_ngn", 0))
    currency = raw.get("currency") or "NGN"
    amount_ngn, fx_rate, fx_source = _fx_enrich(amount, currency)
    payout_method = str(raw.get("payout_method", "")).upper() or None
    linked = raw.get("linked_statement_ref") or None

    base = _telecom_base(raw, "telecom.settlement")
    base.update(
        {
            "transaction_id":      f"tel_pay_{raw.get('settlement_ref', 'unknown')}",
            "amount":              amount,
            "amount_ngn":          amount_ngn,
            "fx_rate":             fx_rate,
            "fx_source":           fx_source,
            "status":              normalize_status("telecom", raw.get("status", "")),
            "transaction_type":    "TRANSFER",
            "commission_amount":   amount_ngn,
            "linked_statement_ref": f"tel_stmt_{linked}" if linked else None,
            "sender":              dict(_EMPTY_PARTY),
            "receiver": {
                "name":  None,
                "email": None,
                "phone": normalize_phone(raw.get("dealer_msisdn")),
                "bank":  None,
            },
            "initiated_at": raw.get("settlement_date"),
            "completed_at": raw.get("settlement_date"),
            "metadata": {
                "payout_method":       payout_method,
                "momo_transaction_id": raw.get("momo_transaction_id") or None,
                "dealer_msisdn":       raw.get("dealer_msisdn") or None,
                "settlement_status":   str(raw.get("status", "")).upper() or None,
            },
        }
    )
    return base


def infer_transaction_type(provider: str, raw: dict) -> str:
    if provider == "mtn_momo":
        return "TRANSFER"
    if provider == "monnify":
        method = raw.get("eventData", {}).get("paymentMethod", "")
        return "TRANSFER" if "TRANSFER" in method.upper() else "PAYMENT"
    if provider == "flutterwave":
        tx_type = raw.get("data", {}).get("tx_type", "")
        return "TRANSFER" if "transfer" in tx_type.lower() else "PAYMENT"
    if provider == "mono":
        return "TRANSFER"
    return "PAYMENT"


def compute_expected_settlement(
    completed_at: Optional[str],
    settlement_mode: Optional[str],
) -> Optional[str]:
    if not completed_at or not settlement_mode:
        return None
    try:
        ts_str = completed_at.replace("+0000", "+00:00")
        completed = datetime.fromisoformat(ts_str)
        mode = settlement_mode.upper()
        if mode == "INSTANT":
            return completed.isoformat()
        if mode == "DAILY":
            next_day = (completed + timedelta(days=1)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
            return next_day.isoformat()
        if mode == "BI_DAILY":
            same_day_afternoon = completed.replace(
                hour=15, minute=0, second=0, microsecond=0
            )
            if completed < same_day_afternoon:
                return same_day_afternoon.isoformat()
            next_morning = (completed + timedelta(days=1)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
            return next_morning.isoformat()
    except Exception:
        pass
    return None


# ── Provider normalizers ──────────────────────────────────────────────────────

def normalize_flutterwave(envelope: dict) -> dict:
    raw = envelope["raw"]
    data = raw.get("data", {})
    customer = data.get("customer", {})
    amount = float(data.get("amount", 0))
    currency = data.get("currency", "NGN")
    amount_ngn, fx_rate, fx_source = _fx_enrich(amount, currency)

    return {
        "transaction_id":        f"flw_{data.get('id', 'unknown')}",
        "provider":              "flutterwave",
        "event_type":            envelope.get("event_type", ""),
        "amount":                amount,
        "currency":              currency,
        "amount_ngn":            amount_ngn,
        "fx_rate":               fx_rate,
        "fx_source":             fx_source,
        "status":                normalize_status("flutterwave", data.get("status", "")),
        "transaction_type":      infer_transaction_type("flutterwave", raw),
        "payment_source":        "FLUTTERWAVE",
        "ingestion_mode":        "STREAMING",
        "virtual_account_type":  None,
        "settlement_mode":       None,
        "expected_settlement_at": None,
        "sender": {
            "name":  customer.get("name"),
            "email": customer.get("email"),
            "phone": normalize_phone(customer.get("phone_number")),
            "bank":  data.get("card", {}).get("issuer"),
        },
        "receiver": {"name": None, "email": None, "phone": None, "bank": None},
        "initiated_at": data.get("created_at"),
        "completed_at": data.get("created_at"),
        "metadata": {
            "tx_ref":  data.get("tx_ref"),
            "flw_ref": data.get("flw_ref"),
        },
    }


def normalize_paystack(envelope: dict) -> dict:
    raw = envelope["raw"]
    data = raw.get("data", {})
    customer = data.get("customer", {})
    currency = data.get("currency", "NGN")
    # Paystack amounts are in kobo — divide by 100 first, then convert
    amount = float(data.get("amount", 0)) / 100
    amount_ngn, fx_rate, fx_source = _fx_enrich(amount, currency)
    sender_name = " ".join(filter(None, [
        customer.get("first_name"), customer.get("last_name")
    ])) or None

    return {
        "transaction_id":        f"ps_{data.get('reference', data.get('id', 'unknown'))}",
        "provider":              "paystack",
        "event_type":            envelope.get("event_type", ""),
        "amount":                amount,
        "currency":              currency,
        "amount_ngn":            amount_ngn,
        "fx_rate":               fx_rate,
        "fx_source":             fx_source,
        "status":                normalize_status("paystack", data.get("status", "")),
        "transaction_type":      infer_transaction_type("paystack", raw),
        "payment_source":        "PAYSTACK",
        "ingestion_mode":        "STREAMING",
        "virtual_account_type":  None,
        "settlement_mode":       None,
        "expected_settlement_at": None,
        "sender": {
            "name":  sender_name,
            "email": customer.get("email"),
            "phone": normalize_phone(customer.get("phone")),
            "bank":  data.get("authorization", {}).get("bank"),
        },
        "receiver": {"name": None, "email": None, "phone": None, "bank": None},
        "initiated_at": data.get("created_at"),
        "completed_at": data.get("paid_at"),
        "metadata": {
            "reference":        data.get("reference"),
            "gateway_response": data.get("gateway_response"),
            "channel":          data.get("channel"),
        },
    }


def normalize_mtn(envelope: dict) -> dict:
    raw = envelope["raw"]
    payer = raw.get("payer", {})
    currency = raw.get("currency", "NGN")
    amount = float(raw.get("amount", 0))
    amount_ngn, fx_rate, fx_source = _fx_enrich(amount, currency)

    return {
        "transaction_id":        f"mtn_{raw.get('financialTransactionId', raw.get('externalId', 'unknown'))}",
        "provider":              "mtn_momo",
        "event_type":            envelope.get("event_type", ""),
        "amount":                amount,
        "currency":              currency,
        "amount_ngn":            amount_ngn,
        "fx_rate":               fx_rate,
        "fx_source":             fx_source,
        "status":                normalize_status("mtn_momo", raw.get("status", "")),
        "transaction_type":      "TRANSFER",
        "payment_source":        "MTN_MOMO",
        "ingestion_mode":        "STREAMING",
        "virtual_account_type":  None,
        "settlement_mode":       None,
        "expected_settlement_at": None,
        "sender": {
            "name":  None,
            "email": None,
            "phone": normalize_phone(payer.get("partyId")),
            "bank":  None,
        },
        "receiver": {"name": None, "email": None, "phone": None, "bank": None},
        "initiated_at": raw.get("created"),
        "completed_at": raw.get("updated"),
        "metadata": {
            "external_id":   raw.get("externalId"),
            "payer_message": raw.get("payerMessage"),
            "payee_note":    raw.get("payeeNote"),
            "party_id_type": payer.get("partyIdType"),
        },
    }


def normalize_monnify(envelope: dict) -> dict:
    raw = envelope["raw"]
    data = raw.get("eventData", {})
    customer = data.get("customer", {})
    currency = data.get("currencyCode", "NGN")
    amount = float(data.get("amountPaid", data.get("totalPayable", 0)))
    amount_ngn, fx_rate, fx_source = _fx_enrich(amount, currency)

    if "reservedAccountDetails" in data:
        va_type = "STATIC"
    elif "destinationAccountDetails" in data:
        va_type = "DYNAMIC"
    else:
        va_type = None

    raw_settlement = data.get("settlementMode", "")
    settlement_map = {
        "INSTANT":  "INSTANT",
        "DAILY":    "DAILY",
        "BI_DAILY": "BI_DAILY",
        "BIDAILY":  "BI_DAILY",
        "BI-DAILY": "BI_DAILY",
    }
    settlement_mode = settlement_map.get(str(raw_settlement).upper()) if raw_settlement else None
    completed_at = data.get("completedOn")

    return {
        "transaction_id":        f"mnfy_{data.get('transactionReference', 'unknown')}",
        "provider":              "monnify",
        "event_type":            envelope.get("event_type", ""),
        "amount":                amount,
        "currency":              currency,
        "amount_ngn":            amount_ngn,
        "fx_rate":               fx_rate,
        "fx_source":             fx_source,
        "status":                normalize_status("monnify", data.get("paymentStatus", "")),
        "transaction_type":      infer_transaction_type("monnify", raw),
        "payment_source":        "MONNIFY",
        "ingestion_mode":        "STREAMING",
        "virtual_account_type":  va_type,
        "settlement_mode":       settlement_mode,
        "expected_settlement_at": compute_expected_settlement(completed_at, settlement_mode),
        "sender": {
            "name":  customer.get("name"),
            "email": customer.get("email"),
            "phone": normalize_phone(customer.get("phoneNumber")),
            "bank":  None,
        },
        "receiver": {
            "name":  data.get("product", {}).get("name"),
            "email": None, "phone": None, "bank": None,
        },
        "initiated_at": data.get("createdOn"),
        "completed_at": completed_at,
        "metadata": {
            "payment_reference":   data.get("paymentReference"),
            "settlement_amount":   data.get("settlementAmount"),
            "payment_method":      data.get("paymentMethod"),
            "payment_description": data.get("paymentDescription"),
        },
    }


def normalize_mono(envelope: dict) -> dict:
    raw = envelope["raw"]
    currency = raw.get("currency", "NGN")
    # Mono amounts are in kobo
    amount = float(raw.get("amount", 0)) / 100
    amount_ngn, fx_rate, fx_source = _fx_enrich(amount, currency)
    tx_type = raw.get("type", "credit").upper()

    bank_code = envelope.get("bank_code", "OTHER").upper()
    bank_source_map = {
        "GTB":    "DIRECT_BANK_GTB",
        "ACCESS": "DIRECT_BANK_ACCESS",
        "ZENITH": "DIRECT_BANK_ZENITH",
        "UBA":    "DIRECT_BANK_UBA",
    }
    payment_source = bank_source_map.get(bank_code, "DIRECT_BANK_OTHER")
    account_name = envelope.get("account_name")

    return {
        "transaction_id":        f"mono_{raw.get('id', 'unknown')}",
        "provider":              "mono",
        "event_type":            f"bank.{tx_type.lower()}",
        "amount":                amount,
        "currency":              currency,
        "amount_ngn":            amount_ngn,
        "fx_rate":               fx_rate,
        "fx_source":             fx_source,
        "status":                "SUCCESS",
        "transaction_type":      "TRANSFER",
        "payment_source":        payment_source,
        "ingestion_mode":        "BATCH_EOD",
        "virtual_account_type":  None,
        "settlement_mode":       None,
        "expected_settlement_at": None,
        "sender": {
            "name":  account_name if tx_type == "DEBIT" else None,
            "email": None,
            "phone": None,
            "bank":  bank_code,
        },
        "receiver": {
            "name":  account_name if tx_type == "CREDIT" else None,
            "email": None,
            "phone": None,
            "bank":  bank_code,
        },
        "initiated_at": raw.get("date"),
        "completed_at": raw.get("date"),
        "metadata": {
            "narration":  raw.get("narration"),
            "balance":    raw.get("balance"),
            "type":       tx_type,
            "account_id": envelope.get("account_id"),
            "batch_date": envelope.get("batch_date"),
        },
    }


# ── Router ────────────────────────────────────────────────────────────────────

NORMALIZERS = {
    "flutterwave": normalize_flutterwave,
    "paystack":    normalize_paystack,
    "mtn_momo":    normalize_mtn,
    "monnify":     normalize_monnify,
    "mono":        normalize_mono,
}

# Telecom batch uses event_type as a secondary dispatch key — all three telecom
# variants share provider "telecom_batch" but produce different canonical shapes.
TELECOM_NORMALIZERS = {
    "telecom.dealer_sale":          normalize_telecom_dealer_sale,
    "telecom.commission_statement": normalize_telecom_commission_statement,
    "telecom.settlement":           normalize_telecom_settlement,
}


def normalize_event(raw_message: str) -> Optional[str]:
    try:
        envelope = json.loads(raw_message)
        provider = envelope.get("provider")

        if provider == "telecom_batch":
            event_type = envelope.get("event_type")
            fn = TELECOM_NORMALIZERS.get(event_type)
            if fn is None:
                log.warning(f"Unknown telecom event_type: {event_type}")
                return None
            normalized = fn(envelope)
        elif provider in NORMALIZERS:
            normalized = NORMALIZERS[provider](envelope)
        else:
            log.warning(f"Unknown provider: {provider}")
            return None

        normalized["_normalized_at"]    = datetime.now(timezone.utc).isoformat()
        normalized["_ingested_at"]      = envelope.get("_ingested_at")
        normalized["_raw_topic"]        = envelope.get("_source_topic")
        normalized["_pipeline_version"] = "1.3.0"
        return json.dumps(normalized)
    except Exception as e:
        log.error(f"Failed to normalize event: {e} | raw: {raw_message[:200]}")
        return None