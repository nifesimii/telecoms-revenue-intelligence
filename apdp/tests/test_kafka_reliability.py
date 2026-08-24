"""Regression tests for durable APDP ingestion behaviour."""
from __future__ import annotations

import json
import sys
from pathlib import Path

APDP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APDP))

from ingestion import kafka_client  # noqa: E402
from ingestion.pollers import telecom_batch  # noqa: E402
from ingestion.receivers import flutterwave  # noqa: E402
from services.postgres_sink import main as sink  # noqa: E402


class _Producer:
    def __init__(self, delivery_error=None):
        self.delivery_error = delivery_error
        self.callback = None
        self.records = []

    def produce(self, *args, **kwargs):
        self.records.append((args, kwargs))
        self.callback = kwargs["callback"]

    def poll(self, _timeout):
        return 0

    def flush(self, _timeout):
        self.callback(self.delivery_error, _DeliveredMessage())
        return 0


class _DeliveredMessage:
    def topic(self): return "test-topic"
    def partition(self): return 0
    def offset(self): return 0


def test_confirmed_publish_fails_when_kafka_rejects_delivery(monkeypatch):
    monkeypatch.setattr(kafka_client, "_producer", _Producer(Exception("rejected")))

    assert not kafka_client.publish_event(
        "raw.telecom.dealer_sales",
        {"id": "sale-1"},
        "test",
        wait_for_delivery=True,
    )


def test_batch_keeps_file_when_delivery_is_not_confirmed(tmp_path, monkeypatch):
    source = tmp_path / "dealer_sales_202602.csv"
    source.write_text(
        "transaction_ref,sale_date,dealer_code,product_type,total_amount_ngn,payment_method,source_system\n"
        "sale-1,2026-02-01,19472,FBB_DEVICE,10000,CASH,DMS\n"
    )
    archive = tmp_path / "archive"
    quarantine = tmp_path / "quarantine"
    calls = []

    def rejected_publish(**kwargs):
        calls.append(kwargs)
        return False

    monkeypatch.setattr(telecom_batch, "publish_event", rejected_publish)
    route = telecom_batch._route_for(source.name)

    assert not telecom_batch._process_file(source, route, archive, quarantine, False)
    assert source.exists()
    assert calls[0]["wait_for_delivery"] is True


def test_batch_quarantines_file_with_invalid_rows(tmp_path, monkeypatch):
    source = tmp_path / "dealer_sales_202602.csv"
    source.write_text(
        "transaction_ref,sale_date,dealer_code,product_type,total_amount_ngn,payment_method,source_system\n"
        "sale-1,2026-02-01,19472,FBB_DEVICE,10000,CASH,DMS\n"
        ",2026-02-01,19472,FBB_DEVICE,10000,CASH,DMS\n"
    )
    archive = tmp_path / "archive"
    quarantine = tmp_path / "quarantine"
    calls = []

    def record_publish(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(telecom_batch, "publish_event", record_publish)
    route = telecom_batch._route_for(source.name)

    assert not telecom_batch._process_file(source, route, archive, quarantine, False)
    assert not source.exists()
    assert len(list(quarantine.glob("*.csv"))) == 1
    assert not archive.exists()
    assert calls == []


class _Message:
    def topic(self): return "normalized.transactions"
    def partition(self): return 2
    def offset(self): return 17


def test_dlq_record_contains_source_metadata(monkeypatch):
    producer = _Producer()
    monkeypatch.setattr(sink, "_build_dlq_producer", lambda: producer)

    assert sink._publish_to_dlq(_Message(), b"{bad json", "bad_json")
    payload = json.loads(producer.records[0][1]["value"])
    assert payload == {
        "reason": "bad_json",
        "source_topic": "normalized.transactions",
        "source_partition": 2,
        "source_offset": 17,
        "raw_value": "{bad json",
    }


def test_flutterwave_rejects_when_webhook_hash_is_not_configured(monkeypatch):
    monkeypatch.setattr(flutterwave.settings, "FLUTTERWAVE_WEBHOOK_HASH", "")

    assert not flutterwave.verify_signature(None)
    assert not flutterwave.verify_signature("attacker-value")
