#!/bin/bash
set -e

echo "Waiting for Kafka to be ready..."
sleep 10

BOOTSTRAP="kafka:29092"

echo "Creating topics..."

# ── PSP streaming topics ──────────────────────────────────────────────────────
kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP \
  --topic raw.flutterwave.transactions --partitions 3 --replication-factor 1

kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP \
  --topic raw.paystack.transactions --partitions 3 --replication-factor 1

kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP \
  --topic raw.mtn.transactions --partitions 3 --replication-factor 1

kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP \
  --topic raw.monnify.transactions --partitions 3 --replication-factor 1

# ── Open-banking batch topic ──────────────────────────────────────────────────
# Mono bank statement events arrive in nightly batches.
# 3 partitions allows parallelism across multiple connected bank accounts.
kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP \
  --topic raw.mono.transactions --partitions 3 --replication-factor 1

# ── Downstream topics ─────────────────────────────────────────────────────────
kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP \
  --topic normalized.transactions --partitions 6 --replication-factor 1

kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP \
  --topic reconciled.transactions --partitions 6 --replication-factor 1

kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP \
  --topic cbn.reports.daily --partitions 1 --replication-factor 1

kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP \
  --topic dead.letter.queue --partitions 3 --replication-factor 1

echo ""
echo "Topics created successfully!"
echo ""
echo "Topic list:"
kafka-topics --list --bootstrap-server $BOOTSTRAP