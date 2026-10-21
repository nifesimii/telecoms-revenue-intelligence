"""
Telecom trade partner batch file ingestor.

Telecom data does NOT arrive via webhook — it lands as CSV drops from
dealer management systems, commission engines, and AP systems. This
ingestor watches an inbox directory, routes each file to the right
Kafka topic based on filename, and publishes one envelope per row in
the v1.3.0 canonical shape (see flink_jobs/SCHEMA_v1.3.0.md).

File-to-topic routing (by filename prefix):
    dealer_sales*.csv          → raw.telecom.dealer_sales
    commission_statements*.csv → raw.telecom.commission_statements
    settlement_records*.csv    → raw.telecom.settlement_records

Lifecycle:
    inbox/      → file lands here (mounted volume in compose)
    archive/    → moved here on full success
    quarantine/ → moved here when filename is unrecognised, any row
                  fails validation, or no rows are valid. Quarantine
                  means the file was not published.

Idempotency:
    * File-level: a file in archive/ is never re-processed.
    * Mid-file crash recovery: a file stays in inbox/ until ALL rows
      publish successfully. On restart it re-processes from the top;
      downstream postgres_sink dedupes on transaction_id (PK).

Run modes:
    Continuous (default):  poll inbox/ every TELECOM_POLL_INTERVAL_SECONDS
    One-shot:              `python telecom_batch.py --once`
    Dry-run:               `python telecom_batch.py --once --dry-run`
                           (logs what would be published; does NOT touch
                           Kafka or move files — useful for fixture testing)

Env vars (sensible compose defaults):
    TELECOM_INBOX_DIR              default /data/telecom/inbox
    TELECOM_ARCHIVE_DIR            default /data/telecom/archive
    TELECOM_QUARANTINE_DIR         default /data/telecom/quarantine
    TELECOM_POLL_INTERVAL_SECONDS  default 30
    KAFKA_BOOTSTRAP_SERVERS        (inherited from ingestion.config)
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from prometheus_client import Counter, start_http_server

from ingestion.kafka_client import publish_event

log = structlog.get_logger("telecom_batch")

# ── File-to-topic routing ────────────────────────────────────────────────────
# Filename prefix → (topic, event_type, required columns, dedup key column).
# A file whose name doesn't start with one of these keys is quarantined.

FILE_ROUTING: dict[str, dict[str, Any]] = {
    "dealer_sales": {
        "topic":      "raw.telecom.dealer_sales",
        "event_type": "telecom.dealer_sale",
        "required":   [
            "transaction_ref", "sale_date", "dealer_code",
            "product_type", "total_amount_ngn", "payment_method",
            "source_system",
        ],
        "key_col":    "transaction_ref",
    },
    "commission_statements": {
        "topic":      "raw.telecom.commission_statements",
        "event_type": "telecom.commission_statement",
        "required":   [
            "statement_ref", "statement_date", "settlement_period",
            "dealer_code", "product_type", "activation_count",
            "gross_revenue_ngn", "commission_rate", "commission_amount_ngn",
            "status", "source_system",
        ],
        "key_col":    "statement_ref",
    },
    "settlement_records": {
        "topic":      "raw.telecom.settlement_records",
        "event_type": "telecom.settlement",
        "required":   [
            "settlement_ref", "linked_statement_ref", "settlement_date",
            "settlement_period", "dealer_code", "amount_ngn",
            "payout_method", "status", "source_system",
        ],
        "key_col":    "settlement_ref",
    },
}

PROVIDER = "telecom_batch"

# ── Prometheus metrics ───────────────────────────────────────────────────────
rows_published = Counter(
    "telecom_batch_rows_published_total",
    "CSV rows successfully published to a raw.telecom.* topic",
    ["event_type"],
)
rows_failed = Counter(
    "telecom_batch_rows_failed_total",
    "CSV rows skipped (missing columns / publish error)",
    ["event_type", "reason"],
)
files_processed = Counter(
    "telecom_batch_files_processed_total",
    "Files moved to archive after successful processing",
    ["event_type"],
)
files_quarantined = Counter(
    "telecom_batch_files_quarantined_total",
    "Files moved to quarantine (unrouted or all rows failed)",
    ["reason"],
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _route_for(filename: str) -> dict[str, Any] | None:
    """Find the routing entry that matches the file's prefix."""
    name = filename.lower()
    for prefix, route in FILE_ROUTING.items():
        if name.startswith(prefix):
            return route
    return None


def _validate_row(row: dict[str, str], required: list[str]) -> str | None:
    """Return None if row OK, else a reason string."""
    missing = [c for c in required if not row.get(c)]
    if missing:
        return f"missing:{','.join(missing)}"
    return None


def _process_file(
    path: Path,
    route: dict[str, Any],
    archive_dir: Path,
    quarantine_dir: Path,
    dry_run: bool,
) -> bool:
    """Publish all rows of one file. Returns True on full success.

    Validation runs before any Kafka publish. One invalid row quarantines
    the file with nothing sent, so quarantine never means "partially
    ingested". On publish failure the file stays in inbox/ for retry.
    """
    event_type = route["event_type"]
    topic      = route["topic"]
    required   = route["required"]
    key_col    = route["key_col"]

    log.info("Processing file", file=path.name, event_type=event_type, dry_run=dry_run)

    skipped = 0
    row_count = 0
    with path.open(newline="") as f:
        for idx, row in enumerate(csv.DictReader(f)):
            row_count += 1
            reason = _validate_row(row, required)
            if reason:
                rows_failed.labels(event_type=event_type, reason="validation").inc()
                skipped += 1
                log.warning(
                    "Row failed validation",
                    file=path.name, row_index=idx, reason=reason,
                )

    if skipped > 0:
        _move(path, quarantine_dir, dry_run)
        files_quarantined.labels(reason="validation").inc()
        log.error(
            "File quarantined — one or more rows failed validation",
            file=path.name,
            published=0,
            skipped=skipped,
        )
        return False

    if row_count == 0:
        _move(path, quarantine_dir, dry_run)
        files_quarantined.labels(reason="no_valid_rows").inc()
        log.error("File quarantined — no valid rows", file=path.name)
        return False

    published = 0
    publish_errors = 0
    with path.open(newline="") as f:
        for idx, row in enumerate(csv.DictReader(f)):
            payload = {
                "provider":     PROVIDER,
                "event_type":   event_type,
                "raw":          dict(row),
                "_source_file": path.name,
                "_row_index":   idx,
            }
            key = row.get(key_col) or None

            if dry_run:
                log.debug(
                    "DRY-RUN would publish",
                    topic=topic, key=key, row_index=idx,
                )
                published += 1
                continue

            ok = publish_event(
                topic=topic,
                payload=payload,
                provider=PROVIDER,
                key=key,
                wait_for_delivery=True,
            )
            if ok:
                rows_published.labels(event_type=event_type).inc()
                published += 1
            else:
                rows_failed.labels(event_type=event_type, reason="publish").inc()
                publish_errors += 1

    # If we hit any publish errors, leave the file in inbox/ for retry.
    if publish_errors > 0:
        log.error(
            "File left in inbox/ for retry (publish errors)",
            file=path.name, published=published, errors=publish_errors,
        )
        return False

    _move(path, archive_dir, dry_run)
    files_processed.labels(event_type=event_type).inc()
    log.info(
        "File processed",
        file=path.name, published=published, skipped=skipped,
    )
    return True


def _move(path: Path, target_dir: Path, dry_run: bool) -> None:
    if dry_run:
        return
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp  = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    dest   = target_dir / f"{stamp}_{path.name}"
    shutil.move(str(path), str(dest))


def _scan_inbox(
    inbox: Path,
    archive: Path,
    quarantine: Path,
    dry_run: bool,
) -> int:
    """One pass over inbox/. Returns number of files processed."""
    inbox.mkdir(parents=True, exist_ok=True)
    candidates = sorted(p for p in inbox.iterdir() if p.is_file() and p.suffix == ".csv")
    if not candidates:
        return 0

    processed = 0
    for path in candidates:
        route = _route_for(path.name)
        if route is None:
            log.warning("Unrouted filename — quarantining", file=path.name)
            _move(path, quarantine, dry_run)
            files_quarantined.labels(reason="unrouted_filename").inc()
            continue
        if _process_file(path, route, archive, quarantine, dry_run):
            processed += 1
    return processed


# ── Run modes ────────────────────────────────────────────────────────────────

_shutdown = False


def _on_sigterm(_signum, _frame):
    global _shutdown
    log.info("Shutdown signal received — finishing current scan")
    _shutdown = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--once", action="store_true",
                        help="Process pending files and exit (default: loop)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't publish to Kafka or move files; log only")
    parser.add_argument("--inbox",      default=os.getenv("TELECOM_INBOX_DIR",      "/data/telecom/inbox"))
    parser.add_argument("--archive",    default=os.getenv("TELECOM_ARCHIVE_DIR",    "/data/telecom/archive"))
    parser.add_argument("--quarantine", default=os.getenv("TELECOM_QUARANTINE_DIR", "/data/telecom/quarantine"))
    parser.add_argument("--interval",   type=int,
                        default=int(os.getenv("TELECOM_POLL_INTERVAL_SECONDS", "30")))
    parser.add_argument("--metrics-port", type=int,
                        default=int(os.getenv("METRICS_PORT", "9101")))
    args = parser.parse_args()

    inbox      = Path(args.inbox)
    archive    = Path(args.archive)
    quarantine = Path(args.quarantine)

    log.info(
        "Telecom batch ingestor starting",
        inbox=str(inbox), archive=str(archive), quarantine=str(quarantine),
        once=args.once, dry_run=args.dry_run, interval=args.interval,
    )

    if not args.dry_run and not args.once:
        try:
            start_http_server(args.metrics_port)
            log.info("Prometheus metrics server started", port=args.metrics_port)
        except OSError as e:
            log.warning("Metrics server failed to start", error=str(e))

    signal.signal(signal.SIGTERM, _on_sigterm)
    signal.signal(signal.SIGINT,  _on_sigterm)

    if args.once:
        n = _scan_inbox(inbox, archive, quarantine, args.dry_run)
        log.info("One-shot scan complete", files_processed=n)
        return 0

    while not _shutdown:
        try:
            _scan_inbox(inbox, archive, quarantine, args.dry_run)
        except Exception as e:
            log.error("Scan failed", error=str(e), exc_info=True)
        # Sleep in small ticks so SIGTERM is responsive
        for _ in range(args.interval):
            if _shutdown:
                break
            time.sleep(1)

    log.info("Shutdown complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
