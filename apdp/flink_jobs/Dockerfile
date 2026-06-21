FROM apache/flink:1.18.1-scala_2.12-java11

USER root

RUN apt-get update -y && \
    apt-get install -y python3 python3-pip python3-dev && \
    ln -sf /usr/bin/python3 /usr/bin/python && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install --upgrade pip setuptools wheel --quiet

# apache-flink is ~800MB and frequently times out on flaky networks during
# `docker build`. Two install paths handled by the script below:
#
#   1. If wheels/ contains pre-downloaded .whl files (populated by running
#      ./download_wheels.sh on the host), install offline from local cache —
#      fast and immune to network failures.
#   2. Else, pull from PyPI with extended timeout + retry settings. Will
#      still fail on truly broken networks; rerun download_wheels.sh.
#
# The wheels/ directory is always present (kept by .gitkeep) so this COPY
# never errors. Cache cleared after install to keep the final image lean.
COPY wheels/ /tmp/wheels/
RUN if ls /tmp/wheels/*.whl >/dev/null 2>&1; then \
        echo ">> Installing apache-flink from local wheels cache"; \
        pip3 install --no-index --find-links /tmp/wheels "apache-flink==1.18.1"; \
    else \
        echo ">> No local wheels cache — pulling apache-flink from PyPI"; \
        pip3 install \
          --timeout 900 \
          --retries 30 \
          --no-cache-dir \
          --prefer-binary \
          --progress-bar off \
          "apache-flink==1.18.1"; \
    fi && \
    rm -rf /tmp/wheels

WORKDIR /opt/flink/jobs

# Copy Kafka connector JAR from local machine (pre-downloaded)
COPY flink-sql-connector-kafka-3.1.0-1.18.jar /opt/flink/lib/flink-sql-connector-kafka.jar

COPY normalizer_core.py .
COPY normalizer.py .

ENV KAFKA_BOOTSTRAP_SERVERS=kafka:29092

USER flink
