#!/bin/bash
set -e

echo "Waiting for Kafka to be ready..."
sleep 10

BOOTSTRAP="kafka:29092"

echo "Creating topics..."

kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP --topic raw.flutterwave.transactions --partitions 3 --replication-factor 1
kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP --topic raw.paystack.transactions --partitions 3 --replication-factor 1
kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP --topic raw.mtn.transactions --partitions 3 --replication-factor 1
# v1.3.0 telecom trade partner topics (consumed by Flink normalizer)
kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP --topic raw.telecom.dealer_sales --partitions 3 --replication-factor 1
kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP --topic raw.telecom.commission_statements --partitions 3 --replication-factor 1
kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP --topic raw.telecom.settlement_records --partitions 3 --replication-factor 1
kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP --topic normalized.transactions --partitions 6 --replication-factor 1
kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP --topic reconciled.transactions --partitions 6 --replication-factor 1
kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP --topic cbn.reports.daily --partitions 1 --replication-factor 1
kafka-topics --create --if-not-exists --bootstrap-server $BOOTSTRAP --topic dead.letter.queue --partitions 3 --replication-factor 1

echo "Topics created successfully!"
echo ""
echo "Topic list:"
kafka-topics --list --bootstrap-server $BOOTSTRAP
