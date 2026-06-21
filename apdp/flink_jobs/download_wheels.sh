#!/usr/bin/env bash
# Pre-download apache-flink + transitive wheels into flink_jobs/wheels/ so the
# Docker build can install offline. Run this once if the in-build PyPI install
# keeps timing out on your network.
#
#   ./flink_jobs/download_wheels.sh
#   docker compose build flink-normalizer
#
# The Dockerfile detects the wheels/ cache automatically — no flag needed.
# Re-running is safe (pip skips already-downloaded files).

set -euo pipefail
cd "$(dirname "$0")"

mkdir -p wheels

echo "==> Downloading apache-flink 1.18.1 + deps to $(pwd)/wheels/"
echo "    ~800MB total. 5-10 min on a typical home connection."
echo

# Target the Python runtime inside apache/flink:1.18.1-scala_2.12-java11
# (python3 from Debian Bullseye = cp39). Adjust --python-version/--abi if the
# base image changes.
pip3 download \
  --dest wheels/ \
  --prefer-binary \
  --only-binary=:all: \
  --platform manylinux2014_x86_64 \
  --python-version 3.9 \
  --implementation cp \
  --abi cp39 \
  "apache-flink==1.18.1"

echo
echo "==> Done. $(ls wheels/*.whl 2>/dev/null | wc -l | tr -d ' ') wheels staged."
echo "    Next: docker compose build flink-normalizer"
