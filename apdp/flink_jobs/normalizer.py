"""
Flink Normalization Job — imports core logic and wires up Kafka I/O.
"""
import logging
import os

from pyflink.common import WatermarkStrategy, Types
from pyflink.common.serialization import SimpleStringSchema
from pyflink.datastream import StreamExecutionEnvironment, RuntimeExecutionMode
from pyflink.datastream.connectors.kafka import (
    KafkaSource, KafkaSink,
    KafkaRecordSerializationSchema,
    KafkaOffsetsInitializer,
    DeliveryGuarantee,
)
from normalizer_core import normalize_event

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("normalizer")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
OUTPUT_TOPIC    = "normalized.transactions"
RAW_TOPICS      = [
    "raw.flutterwave.transactions",
    "raw.paystack.transactions",
    "raw.mtn.transactions",
    "raw.monnify.transactions",
    "raw.mono.transactions",        # Mono open-banking batch (BATCH_EOD)
]


def build_pipeline():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_runtime_mode(RuntimeExecutionMode.STREAMING)
    env.set_parallelism(1)
    env.add_jars("file:///opt/flink/lib/flink-sql-connector-kafka.jar")

    source = (
        KafkaSource.builder()
        .set_bootstrap_servers(KAFKA_BOOTSTRAP)
        .set_topics(*RAW_TOPICS)
        .set_group_id("flink-normalizer")
        .set_starting_offsets(KafkaOffsetsInitializer.earliest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )

    sink = (
        KafkaSink.builder()
        .set_bootstrap_servers(KAFKA_BOOTSTRAP)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(OUTPUT_TOPIC)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .set_delivery_guarantee(DeliveryGuarantee.AT_LEAST_ONCE)
        .build()
    )

    (
        env
        .from_source(source, WatermarkStrategy.no_watermarks(), "raw-payment-events")
        .map(normalize_event, output_type=Types.STRING())
        .filter(lambda x: x is not None)
        .sink_to(sink)
    )

    log.info(f"Starting normalizer | {RAW_TOPICS} → {OUTPUT_TOPIC}")
    env.execute("african-payment-normalizer")


if __name__ == "__main__":
    build_pipeline()