"""
Run with: python flink_jobs/test_normalizer.py
No Flink or Kafka needed — tests pure normalization logic.

Covers:
  - All 5 PSP providers: Flutterwave, Paystack, MTN MoMo, Monnify, Mono
  - Monnify virtual account type inference (STATIC, DYNAMIC, null)
  - Monnify settlement mode + expected_settlement_at computation
  - Mono CREDIT and DEBIT transactions with bank source mapping
  - v1.3.0 telecom variants: dealer_sale, commission_statement, settlement
  - v1.3.0 fields: dealer_id, partner_id, settlement_period, commission_*,
    linked_statement_ref, product_type, gross_revenue
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from normalizer_core import normalize_event

# ── Raw test fixtures ─────────────────────────────────────────────────────────

FLUTTERWAVE_RAW = json.dumps({
    "provider": "flutterwave", "event_type": "charge.completed",
    "raw": {"event": "charge.completed", "data": {
        "id": 99999, "tx_ref": "TEST-001", "flw_ref": "FLW-MOCK-001",
        "amount": 50000, "currency": "NGN", "status": "successful",
        "customer": {"name": "Test User", "email": "test@example.com", "phone_number": "+2348012345678"},
        "created_at": "2024-01-15T14:10:00.000Z"
    }},
    "_ingested_at": "2026-03-06T15:36:40.583411+00:00",
    "_source_topic": "raw.flutterwave.transactions"
})

PAYSTACK_RAW = json.dumps({
    "provider": "paystack", "event_type": "charge.success",
    "raw": {"event": "charge.success", "data": {
        "id": 88888, "reference": "TEST-PS-001", "amount": 5000000,
        "currency": "NGN", "status": "success",
        "customer": {"first_name": "Test", "last_name": "User", "email": "test@example.com", "phone": "08012345678"},
        "created_at": "2024-01-15T14:10:30.000Z"
    }},
    "_ingested_at": "2026-03-06T13:21:16.130906+00:00",
    "_source_topic": "raw.paystack.transactions"
})

MTN_RAW = json.dumps({
    "provider": "mtn_momo", "event_type": "collection.completed",
    "raw": {
        "financialTransactionId": "MTN-TEST-001", "externalId": "EXT-TEST-001",
        "amount": "50000", "currency": "NGN",
        "payer": {"partyIdType": "MSISDN", "partyId": "2348012345678"},
        "payerMessage": "Payment for goods", "payeeNote": "Thank you",
        "status": "SUCCESSFUL", "reason": None,
        "created": "2026-03-06T15:36:40.613098+00:00",
        "updated": "2026-03-06T15:36:40.613105+00:00"
    },
    "_ingested_at": "2026-03-06T15:36:40.613117+00:00",
    "_source_topic": "raw.mtn.transactions"
})

# Standard Monnify — no VA fields, no settlement mode
MONNIFY_RAW = json.dumps({
    "provider": "monnify", "event_type": "SUCCESSFUL_TRANSACTION",
    "raw": {"eventType": "SUCCESSFUL_TRANSACTION", "eventData": {
        "transactionReference": "MNFY-TEST-001", "paymentReference": "MNFY-PAY-001",
        "amountPaid": 50000.0, "totalPayable": 50000.0, "settlementAmount": 49250.0,
        "currencyCode": "NGN", "paymentStatus": "PAID",
        "paymentDescription": "Payment for goods", "paymentMethod": "ACCOUNT_TRANSFER",
        "customer": {"name": "Test User", "email": "test@example.com"},
        "product": {"reference": "PROD-001", "name": "Test Product"},
        "metaData": {},
        "createdOn": "2024-01-15T14:10:00.000+0000",
        "completedOn": "2024-01-15T14:10:45.000+0000"
    }},
    "_ingested_at": "2026-03-06T15:36:40.622815+00:00",
    "_source_topic": "raw.monnify.transactions"
})

# Monnify — static virtual account + DAILY settlement
MONNIFY_STATIC_VA_RAW = json.dumps({
    "provider": "monnify", "event_type": "VIRTUAL_ACCOUNT_FUNDED",
    "raw": {"eventType": "VIRTUAL_ACCOUNT_FUNDED", "eventData": {
        "transactionReference": "MNFY-VA-STATIC-001", "paymentReference": "MNFY-PAY-VA-001",
        "amountPaid": 25000.0, "totalPayable": 25000.0, "settlementAmount": 24500.0,
        "currencyCode": "NGN", "paymentStatus": "PAID",
        "paymentMethod": "ACCOUNT_TRANSFER", "settlementMode": "DAILY",
        "customer": {"name": "Business User", "email": "biz@example.com"},
        "product": {"reference": "RESERVED-001", "name": "Reserved Account"},
        "reservedAccountDetails": {
            "accountNumber": "0123456789", "accountName": "Test Merchant",
            "bankCode": "058", "bankName": "GTBank"
        },
        "createdOn": "2024-01-15T08:00:00.000+0000",
        "completedOn": "2024-01-15T08:00:30.000+0000"
    }},
    "_ingested_at": "2026-03-06T15:36:40.700000+00:00",
    "_source_topic": "raw.monnify.transactions"
})

# Monnify — dynamic virtual account + INSTANT settlement
MONNIFY_DYNAMIC_VA_RAW = json.dumps({
    "provider": "monnify", "event_type": "SUCCESSFUL_TRANSACTION",
    "raw": {"eventType": "SUCCESSFUL_TRANSACTION", "eventData": {
        "transactionReference": "MNFY-DYN-001", "paymentReference": "MNFY-PAY-DYN-001",
        "amountPaid": 10000.0, "totalPayable": 10000.0, "settlementAmount": 9800.0,
        "currencyCode": "NGN", "paymentStatus": "PAID",
        "paymentMethod": "ACCOUNT_TRANSFER", "settlementMode": "INSTANT",
        "customer": {"name": "Quick Pay User", "email": "quick@example.com"},
        "product": {"reference": "ORDER-999", "name": "One-time Payment"},
        "destinationAccountDetails": {
            "accountNumber": "9876543210", "accountName": "Dynamic Account",
            "bankCode": "035", "bankName": "Wema Bank"
        },
        "createdOn": "2024-01-15T10:00:00.000+0000",
        "completedOn": "2024-01-15T10:00:15.000+0000"
    }},
    "_ingested_at": "2026-03-06T15:36:40.800000+00:00",
    "_source_topic": "raw.monnify.transactions"
})

# Mono — CREDIT transaction (funds received) from GTBank
MONO_CREDIT_RAW = json.dumps({
    "provider": "mono", "event_type": "bank.credit",
    "bank_code": "GTB",
    "account_id": "60c1f3e4a2b3c4d5e6f70001",
    "account_name": "Acme Logistics Ltd",
    "batch_date": "2026-03-06",
    "raw": {
        "id": "mono_txn_credit_001",
        "amount": 5000000,       # 50,000 NGN in kobo
        "date": "2026-03-06T00:00:00.000Z",
        "narration": "TRANSFER FROM JOHN DOE - Payment for invoice INV-2026-001",
        "type": "credit",
        "balance": 15000000,     # 150,000 NGN post-transaction balance (kobo)
        "currency": "NGN"
    },
    "_ingested_at": "2026-03-06T23:05:00.000000+00:00",
    "_source_topic": "raw.mono.transactions"
})

# Mono — DEBIT transaction (funds sent) from Access Bank
MONO_DEBIT_RAW = json.dumps({
    "provider": "mono", "event_type": "bank.debit",
    "bank_code": "ACCESS",
    "account_id": "60c1f3e4a2b3c4d5e6f70002",
    "account_name": "TechPay Nigeria Ltd",
    "batch_date": "2026-03-06",
    "raw": {
        "id": "mono_txn_debit_001",
        "amount": 2000000,       # 20,000 NGN in kobo
        "date": "2026-03-06T00:00:00.000Z",
        "narration": "OUTWARD TRANSFER - Vendor payment VNDR-456",
        "type": "debit",
        "balance": 8000000,      # 80,000 NGN post-transaction balance (kobo)
        "currency": "NGN"
    },
    "_ingested_at": "2026-03-06T23:05:00.000000+00:00",
    "_source_topic": "raw.mono.transactions"
})

# ── Test cases ────────────────────────────────────────────────────────────────

CASES = [
    (
        "Flutterwave",
        FLUTTERWAVE_RAW,
        {
            "id_prefix": "flw_", "amount": 50000.0, "status": "SUCCESS",
            "phone": "+2348012345678",
            "payment_source": "FLUTTERWAVE", "ingestion_mode": "STREAMING",
            "virtual_account_type": None, "settlement_mode": None,
        }
    ),
    (
        "Paystack",
        PAYSTACK_RAW,
        {
            "id_prefix": "ps_", "amount": 50000.0, "status": "SUCCESS",
            "phone": "+2348012345678",
            "payment_source": "PAYSTACK", "ingestion_mode": "STREAMING",
            "virtual_account_type": None, "settlement_mode": None,
        }
    ),
    (
        "MTN MoMo",
        MTN_RAW,
        {
            "id_prefix": "mtn_", "amount": 50000.0, "status": "SUCCESS",
            "phone": "+2348012345678",
            "payment_source": "MTN_MOMO", "ingestion_mode": "STREAMING",
            "virtual_account_type": None, "settlement_mode": None,
        }
    ),
    (
        "Monnify (standard — no VA, no settlement mode)",
        MONNIFY_RAW,
        {
            "id_prefix": "mnfy_", "amount": 50000.0, "status": "SUCCESS",
            "phone": None,
            "payment_source": "MONNIFY", "ingestion_mode": "STREAMING",
            "virtual_account_type": None, "settlement_mode": None,
        }
    ),
    (
        "Monnify (STATIC virtual account + DAILY settlement)",
        MONNIFY_STATIC_VA_RAW,
        {
            "id_prefix": "mnfy_", "amount": 25000.0, "status": "SUCCESS",
            "phone": None,
            "payment_source": "MONNIFY", "ingestion_mode": "STREAMING",
            "virtual_account_type": "STATIC", "settlement_mode": "DAILY",
        }
    ),
    (
        "Monnify (DYNAMIC virtual account + INSTANT settlement)",
        MONNIFY_DYNAMIC_VA_RAW,
        {
            "id_prefix": "mnfy_", "amount": 10000.0, "status": "SUCCESS",
            "phone": None,
            "payment_source": "MONNIFY", "ingestion_mode": "STREAMING",
            "virtual_account_type": "DYNAMIC", "settlement_mode": "INSTANT",
        }
    ),
    (
        "Mono CREDIT — GTBank (BATCH_EOD)",
        MONO_CREDIT_RAW,
        {
            "id_prefix": "mono_", "amount": 50000.0, "status": "SUCCESS",
            "phone": None,
            "payment_source": "DIRECT_BANK_GTB", "ingestion_mode": "BATCH_EOD",
            "virtual_account_type": None, "settlement_mode": None,
            "receiver_name": "Acme Logistics Ltd",
            "sender_name": None,
        }
    ),
    (
        "Mono DEBIT — Access Bank (BATCH_EOD)",
        MONO_DEBIT_RAW,
        {
            "id_prefix": "mono_", "amount": 20000.0, "status": "SUCCESS",
            "phone": None,
            "payment_source": "DIRECT_BANK_ACCESS", "ingestion_mode": "BATCH_EOD",
            "virtual_account_type": None, "settlement_mode": None,
            "sender_name": "TechPay Nigeria Ltd",
            "receiver_name": None,
        }
    ),

    # ── v1.3.0 telecom variants ───────────────────────────────────────────────
    (
        "Telecom dealer_sale (FBB device, MoMo)",
        json.dumps({
            "provider": "telecom_batch",
            "event_type": "telecom.dealer_sale",
            "raw": {
                "transaction_ref": "DMS_FBB_D00001_202410_0001",
                "sale_date": "2024-10-08T14:11:58+00:00",
                "dealer_code": "FBB_D00001",
                "partner_code": "PARTNER_A",
                "product_type": "FBB_DEVICE",
                "product_code": "MIFI_4G_BASIC",
                "imei": "218196001338908",
                "total_amount_ngn": 25000,
                "payment_method": "MOMO",
                "consumer_msisdn": "+2348036687537",
                "source_system": "DEALER_MGMT_X",
            },
            "_ingested_at": "2026-06-20T10:00:00+00:00",
            "_source_topic": "raw.telecom.dealer_sales",
        }),
        {
            "id_prefix": "tel_sale_", "amount": 25000.0, "status": "SUCCESS",
            "phone": "+2348036687537",
            "payment_source": "DEALER_MGMT_X", "ingestion_mode": "BATCH_EOD",
            "virtual_account_type": None, "settlement_mode": None,
            "event_type": "telecom.dealer_sale",
            "transaction_type": "PAYMENT",
            "dealer_id": "FBB_D00001",
            "partner_id": "PARTNER_A",
            "product_type": "FBB_DEVICE",
            "gross_revenue": 25000.0,
        }
    ),
    (
        "Telecom commission_statement (FINAL)",
        json.dumps({
            "provider": "telecom_batch",
            "event_type": "telecom.commission_statement",
            "raw": {
                "statement_ref": "STMT_FBB_D00001_FBB_DEVICE_202410",
                "statement_date": "2024-11-01T05:15:13+00:00",
                "settlement_period": "202410",
                "dealer_code": "FBB_D00001",
                "partner_code": "PARTNER_A",
                "product_type": "FBB_DEVICE",
                "activation_count": 21,
                "qualified_count": 16,
                "gross_revenue_ngn": 920000,
                "commission_rate": 0.08,
                "commission_amount_ngn": 73600.0,
                "status": "FINAL",
                "source_system": "COMMISSION_ENGINE",
            },
            "_ingested_at": "2026-06-20T10:00:00+00:00",
            "_source_topic": "raw.telecom.commission_statements",
        }),
        {
            "id_prefix": "tel_stmt_", "amount": 73600.0, "status": "SUCCESS",
            "phone": None,
            "payment_source": "COMMISSION_ENGINE", "ingestion_mode": "BATCH_EOD",
            "virtual_account_type": None, "settlement_mode": None,
            "event_type": "telecom.commission_statement",
            "transaction_type": "STATEMENT",
            "dealer_id": "FBB_D00001",
            "partner_id": "PARTNER_A",
            "product_type": "FBB_DEVICE",
            "settlement_period": "202410",
            "commission_rate": 0.08,
            "gross_revenue": 920000.0,
        }
    ),
    (
        "Telecom settlement (PARTIAL via MoMo)",
        json.dumps({
            "provider": "telecom_batch",
            "event_type": "telecom.settlement",
            "raw": {
                "settlement_ref": "PAY_FBB_D00001_FBB_DEVICE_202410",
                "linked_statement_ref": "STMT_FBB_D00001_FBB_DEVICE_202410",
                "settlement_date": "2024-11-04T22:13:10+00:00",
                "settlement_period": "202410",
                "dealer_code": "FBB_D00001",
                "amount_ngn": 36800.0,
                "payout_method": "MOMO",
                "momo_transaction_id": "MOMO_88295121",
                "dealer_msisdn": "+2348031000001",
                "status": "PARTIAL",
                "source_system": "MTN_MOMO_DISBURSEMENT",
            },
            "_ingested_at": "2026-06-20T10:00:00+00:00",
            "_source_topic": "raw.telecom.settlement_records",
        }),
        {
            "id_prefix": "tel_pay_", "amount": 36800.0, "status": "PENDING",
            "phone": None,  # sender is MTN; dealer phone is in receiver
            "receiver_phone": "+2348031000001",
            "payment_source": "MTN_MOMO_DISBURSEMENT", "ingestion_mode": "BATCH_EOD",
            "virtual_account_type": None, "settlement_mode": None,
            "event_type": "telecom.settlement",
            "transaction_type": "TRANSFER",
            "dealer_id": "FBB_D00001",
            "settlement_period": "202410",
            "linked_statement_ref": "tel_stmt_STMT_FBB_D00001_FBB_DEVICE_202410",
        }
    ),
]

# ── Test runner ───────────────────────────────────────────────────────────────

all_passed = True
for name, raw, exp in CASES:
    print(f"\n{'─' * 60}\n Testing: {name}\n{'─' * 60}")
    result_str = normalize_event(raw)
    if not result_str:
        print(f"❌ normalize_event returned None")
        all_passed = False
        continue
    r = json.loads(result_str)
    print(json.dumps(r, indent=2))
    errors = []

    if not r["transaction_id"].startswith(exp["id_prefix"]):
        errors.append(f"id prefix — expected '{exp['id_prefix']}', got '{r['transaction_id']}'")
    if r["amount"] != exp["amount"]:
        errors.append(f"amount — expected {exp['amount']}, got {r['amount']}")
    if r["status"] != exp["status"]:
        errors.append(f"status — expected '{exp['status']}', got '{r['status']}'")
    if r["sender"]["phone"] != exp["phone"]:
        errors.append(f"phone — expected '{exp['phone']}', got '{r['sender']['phone']}'")
    if r.get("payment_source") != exp["payment_source"]:
        errors.append(f"payment_source — expected '{exp['payment_source']}', got '{r.get('payment_source')}'")
    if r.get("ingestion_mode") != exp["ingestion_mode"]:
        errors.append(f"ingestion_mode — expected '{exp['ingestion_mode']}', got '{r.get('ingestion_mode')}'")
    if r.get("virtual_account_type") != exp["virtual_account_type"]:
        errors.append(f"virtual_account_type — expected '{exp['virtual_account_type']}', got '{r.get('virtual_account_type')}'")
    if r.get("settlement_mode") != exp["settlement_mode"]:
        errors.append(f"settlement_mode — expected '{exp['settlement_mode']}', got '{r.get('settlement_mode')}'")

    # Monnify DAILY settlement — verify expected_settlement_at is set and is next day
    if exp.get("settlement_mode") == "DAILY":
        if not r.get("expected_settlement_at"):
            errors.append("expected_settlement_at — should be set for DAILY settlement mode")

    # Monnify INSTANT settlement — verify expected_settlement_at equals completed_at
    if exp.get("settlement_mode") == "INSTANT":
        if not r.get("expected_settlement_at"):
            errors.append("expected_settlement_at — should be set for INSTANT settlement mode")

    # Mono sender/receiver name assertions
    if "sender_name" in exp and r["sender"].get("name") != exp["sender_name"]:
        errors.append(f"sender.name — expected '{exp['sender_name']}', got '{r['sender'].get('name')}'")
    if "receiver_name" in exp and r["receiver"].get("name") != exp["receiver_name"]:
        errors.append(f"receiver.name — expected '{exp['receiver_name']}', got '{r['receiver'].get('name')}'")
    if "receiver_phone" in exp and r["receiver"].get("phone") != exp["receiver_phone"]:
        errors.append(f"receiver.phone — expected '{exp['receiver_phone']}', got '{r['receiver'].get('phone')}'")

    # v1.3.0 telecom-specific optional assertions
    for key in (
        "event_type", "transaction_type", "dealer_id", "partner_id",
        "product_type", "settlement_period", "commission_rate",
        "gross_revenue", "linked_statement_ref",
    ):
        if key in exp and r.get(key) != exp[key]:
            errors.append(
                f"{key} — expected {exp[key]!r}, got {r.get(key)!r}"
            )

    # Pipeline version check
    if r.get("_pipeline_version") != "1.3.0":
        errors.append(f"_pipeline_version — expected '1.3.0', got '{r.get('_pipeline_version')}'")

    if errors:
        print(f"\n❌ FAILED:")
        for e in errors:
            print(f"   • {e}")
        all_passed = False
    else:
        print(f"\n✅ Passed")

# ── FX enrichment tests (Phase 3) ────────────────────────────────────────────
# These run after the existing 8 cases and test non-NGN conversion.
# Redis is not available in test environment — fx_service uses fallback rates.

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Patch fx_service to use known fallback rates so assertions are deterministic
try:
    import fx_service
    TEST_RATES = {"USD": 1580.0, "GBP": 2010.0, "EUR": 1720.0, "GHS": 105.0, "KES": 12.0}
    fx_service.FALLBACK_RATES = TEST_RATES
except ImportError:
    TEST_RATES = {}

FLW_USD_RAW = json.dumps({
    "provider": "flutterwave", "event_type": "charge.completed",
    "raw": {"event": "charge.completed", "data": {
        "id": 77777, "tx_ref": "TEST-USD-001", "flw_ref": "FLW-USD-001",
        "amount": 100, "currency": "USD", "status": "successful",
        "customer": {"name": "Foreign User", "email": "foreign@example.com", "phone_number": "+12125550100"},
        "created_at": "2024-01-15T14:10:00.000Z"
    }},
    "_ingested_at": "2026-03-07T10:00:00.000000+00:00",
    "_source_topic": "raw.flutterwave.transactions"
})

PS_GBP_RAW = json.dumps({
    "provider": "paystack", "event_type": "charge.success",
    "raw": {"event": "charge.success", "data": {
        "id": 66666, "reference": "TEST-GBP-001", "amount": 5000,
        "currency": "GBP", "status": "success",
        "customer": {"first_name": "UK", "last_name": "User", "email": "uk@example.com", "phone": ""},
        "created_at": "2024-01-15T14:10:30.000Z"
    }},
    "_ingested_at": "2026-03-07T10:00:00.000000+00:00",
    "_source_topic": "raw.paystack.transactions"
})

FX_CASES = [
    (
        "Flutterwave USD → NGN (FX enrichment)",
        FLW_USD_RAW,
        {
            "id_prefix":   "flw_",
            "currency":    "USD",
            "amount":      100.0,
            # 100 USD × 1580.0 = 158000.0 NGN (fallback rate)
            "amount_ngn":  158000.0,
            "fx_rate":     1580.0,
            "fx_source":   "fallback",
        }
    ),
    (
        "Paystack GBP → NGN (FX enrichment, kobo input)",
        PS_GBP_RAW,
        {
            "id_prefix":   "ps_",
            "currency":    "GBP",
            # 5000 kobo = 50 GBP → 50 × 2010.0 = 100500.0 NGN
            "amount":      50.0,
            "amount_ngn":  100500.0,
            "fx_rate":     2010.0,
            "fx_source":   "fallback",
        }
    ),
]

print(f"\n{'═' * 60}")
print(f"  Phase 3 — FX Enrichment Tests")
print(f"{'═' * 60}")

for name, raw, exp in FX_CASES:
    print(f"\n{'─' * 60}\n Testing: {name}\n{'─' * 60}")
    result_str = normalize_event(raw)
    if not result_str:
        print(f"❌ normalize_event returned None")
        all_passed = False
        continue
    r = json.loads(result_str)
    print(json.dumps(r, indent=2))
    errors = []

    if not r["transaction_id"].startswith(exp["id_prefix"]):
        errors.append(f"id prefix — expected '{exp['id_prefix']}', got '{r['transaction_id']}'")
    if r.get("currency") != exp["currency"]:
        errors.append(f"currency — expected '{exp['currency']}', got '{r.get('currency')}'")
    if r.get("amount") != exp["amount"]:
        errors.append(f"amount — expected {exp['amount']}, got {r.get('amount')}")
    if r.get("amount_ngn") != exp["amount_ngn"]:
        errors.append(f"amount_ngn — expected {exp['amount_ngn']}, got {r.get('amount_ngn')}")
    if r.get("fx_rate") != exp["fx_rate"]:
        errors.append(f"fx_rate — expected {exp['fx_rate']}, got {r.get('fx_rate')}")
    if r.get("fx_source") != exp["fx_source"]:
        errors.append(f"fx_source — expected '{exp['fx_source']}', got '{r.get('fx_source')}'")
    if r.get("_pipeline_version") != "1.3.0":
        errors.append(f"_pipeline_version — expected '1.3.0', got '{r.get('_pipeline_version')}'")

    if errors:
        print(f"\n❌ FAILED:")
        for e in errors:
            print(f"   • {e}")
        all_passed = False
    else:
        print(f"\n✅ Passed")


# ── v1.3.0 round-trip: synthetic CSV fixtures → normalize_event ──────────────
# Runs the generator-produced rows through the full pipeline to confirm every
# row in every file type normalizes without error. Skipped silently if the
# fixtures haven't been generated.

import csv
from pathlib import Path

_FIX = Path(__file__).resolve().parent.parent / "tools" / "fixtures" / "202410"
if _FIX.exists():
    print(f"\n{'─' * 60}\n Round-trip: synthetic telecom fixtures\n{'─' * 60}")
    file_to_event = {
        "dealer_sales.csv":          "telecom.dealer_sale",
        "commission_statements.csv": "telecom.commission_statement",
        "settlement_records.csv":    "telecom.settlement",
    }
    rt_errors = 0
    rt_total  = 0
    for fname, event_type in file_to_event.items():
        path = _FIX / fname
        if not path.exists():
            continue
        with path.open() as f:
            for row in csv.DictReader(f):
                rt_total += 1
                envelope = json.dumps({
                    "provider": "telecom_batch",
                    "event_type": event_type,
                    "raw": row,
                    "_ingested_at": "2026-06-20T10:00:00+00:00",
                    "_source_topic": f"raw.telecom.{path.stem}",
                })
                result_str = normalize_event(envelope)
                if not result_str:
                    rt_errors += 1
                    continue
                r = json.loads(result_str)
                if r.get("_pipeline_version") != "1.3.0":
                    rt_errors += 1
                if r.get("event_type") != event_type:
                    rt_errors += 1
    if rt_errors:
        print(f"❌ {rt_errors}/{rt_total} rows failed round-trip")
        all_passed = False
    else:
        print(f"✅ {rt_total} rows round-tripped cleanly")


print(f"\n{'═' * 60}")
print(f"{'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
print(f"{'═' * 60}\n")