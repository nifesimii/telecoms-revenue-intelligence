"""Connector runner — pull every onboarded dealer, publish to Kafka.

The orchestrator behind "connect to the dealers and fetch their data". For
each active dealer connection it dispatches to the right connector, fetches
activity since the last high-water mark, and publishes the returned raw
envelopes to the correct raw.* Kafka topic — from where the existing Flink
normalizer + Postgres sink take over unchanged.

Per-dealer error isolation: one dealer's auth/network failure is captured in
its RunReport entry and never aborts the batch.

Run modes:
    python -m ingestion.connectors.runner            # pull all, publish
    python -m ingestion.connectors.runner --dry-run  # pull all, print, no Kafka
    python -m ingestion.connectors.runner --dealer FBB_D00001
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ingestion.connectors.base import DealerConnection, get_connector
from ingestion.connectors.onboarding import active_connections, load_connections

# Provider → raw topic. Matches the topics the normalizer already reads.
_PROVIDER_TOPIC = {
    "mtn_momo": "raw.mtn.transactions",
    "mono": "raw.mono.transactions",
    "flutterwave": "raw.flutterwave.transactions",
    "paystack": "raw.paystack.transactions",
    "monnify": "raw.monnify.transactions",
}


@dataclass
class RunReport:
    started_at: str
    dealers_attempted: int = 0
    dealers_ok: int = 0
    dealers_failed: int = 0
    events_published: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)


def run(
    *,
    dry_run: bool = False,
    only_dealer: str | None = None,
    since: datetime | None = None,
) -> RunReport:
    report = RunReport(started_at=datetime.now(timezone.utc).isoformat())

    conns = active_connections()
    if only_dealer:
        # When a specific dealer is named, ignore readiness so you can probe
        # a not-yet-consented dealer and see the connector's error.
        conns = [c for c in load_connections() if c.dealer_code == only_dealer]

    for conn in conns:
        report.dealers_attempted += 1
        connector = get_connector(conn.connector_type)
        if connector is None:
            report.dealers_failed += 1
            report.details.append({
                "dealer": conn.dealer_code, "ok": False,
                "error": f"no connector registered for '{conn.connector_type}'",
            })
            continue

        result = connector.fetch(conn, since)
        if not result.ok:
            report.dealers_failed += 1
            report.details.append({
                "dealer": conn.dealer_code, "connector": conn.connector_type,
                "ok": False, "error": result.error,
            })
            continue

        published = _publish(result.envelopes, dry_run=dry_run)
        report.dealers_ok += 1
        report.events_published += published
        report.details.append({
            "dealer": conn.dealer_code, "connector": conn.connector_type,
            "ok": True, "events": published,
        })

    return report


def _publish(envelopes: list[dict[str, Any]], *, dry_run: bool) -> int:
    if dry_run:
        for e in envelopes:
            print(json.dumps(e))
        return len(envelopes)

    # Lazy import so --dry-run works with no Kafka libs / broker.
    from ingestion.kafka_client import publish_event

    count = 0
    for e in envelopes:
        provider = e.get("provider", "")
        topic = _PROVIDER_TOPIC.get(provider)
        if not topic:
            continue
        # publish_event stamps _ingested_at / _source_topic.
        if publish_event(topic, e, provider=provider, key=e.get("_dealer_code")):
            count += 1
    return count


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dry-run", action="store_true", help="Print envelopes; no Kafka.")
    p.add_argument("--dealer", help="Only this dealer_code (ignores readiness).")
    args = p.parse_args()

    report = run(dry_run=args.dry_run, only_dealer=args.dealer)
    print(json.dumps({
        "started_at": report.started_at,
        "dealers_attempted": report.dealers_attempted,
        "dealers_ok": report.dealers_ok,
        "dealers_failed": report.dealers_failed,
        "events_published": report.events_published,
        "details": report.details,
    }, indent=2))
    return 0 if report.dealers_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
