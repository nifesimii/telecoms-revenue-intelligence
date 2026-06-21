"""
African Payment Data Platform — Ingestion Service

Webhook receivers:
  POST /webhooks/flutterwave   — Flutterwave charge events
  POST /webhooks/paystack      — Paystack charge events
  POST /webhooks/monnify       — Monnify transaction events

Simulation endpoints (dev):
  GET /webhooks/flutterwave/test
  GET /webhooks/paystack/test
  GET /webhooks/mtn/test
  GET /webhooks/monnify/test

Pollers:
  MTN MoMo — polls every 30s via asyncio background task
  Mono      — runs as separate mono-batch Docker service (cron 23:00 daily)
              not started here; see ingestion/pollers/mono_batch.py
"""
import asyncio
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from prometheus_client import make_asgi_app

from ingestion.receivers.flutterwave import router as flw_router
from ingestion.receivers.paystack import router as ps_router
from ingestion.receivers.mtn_momo import router as mtn_router
from ingestion.receivers.monnify import router as monnify_router
from ingestion.kafka_client import get_producer

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting African Payment Platform ingestion service")

    # Initialize Kafka producer
    producer = get_producer()
    app.state.kafka_producer = producer

    # Start MTN MoMo background poller
    from ingestion.pollers.mtn_momo import run_mtn_poller
    poller_task = asyncio.create_task(run_mtn_poller())
    app.state.mtn_poller_task = poller_task
    log.info("MTN MoMo poller started as background task")

    yield

    # Shutdown
    log.info("Shutting down ingestion service")
    poller_task.cancel()
    try:
        await poller_task
    except asyncio.CancelledError:
        pass
    producer.flush()
    log.info("Shutdown complete")


app = FastAPI(
    title="African Payment Platform — Ingestion",
    description="""
Real-time payment event ingestion across Nigerian payment providers.

**Streaming providers (webhook/poll):**
- 🟡 MTN MoMo (polling-based, every 30s)
- 🟢 Flutterwave (webhook)
- 🔵 Paystack (webhook)
- 🟠 Monnify (webhook — supports static & dynamic virtual accounts)

**Batch providers (EOD):**
- 🏦 Mono open banking (bank statement pull at 23:00 daily)
  — GTBank, Access Bank, Zenith Bank, UBA, and others
  — Runs as a separate `mono-batch` service (see docker-compose.yml)
  — Real-time reconciliation not available for direct bank connections

All events are normalized into a canonical schema and published to Apache Kafka
for downstream Flink processing, reconciliation, and CBN regulatory reporting.
    """,
    version="0.2.0",
    lifespan=lifespan
)

# Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Provider routers
app.include_router(flw_router,     prefix="/webhooks/flutterwave", tags=["Flutterwave"])
app.include_router(ps_router,      prefix="/webhooks/paystack",    tags=["Paystack"])
app.include_router(mtn_router,     prefix="/webhooks/mtn",         tags=["MTN MoMo"])
app.include_router(monnify_router, prefix="/webhooks/monnify",     tags=["Monnify"])


@app.get("/health", tags=["System"])
async def health():
    return {
        "status": "ok",
        "service": "ingestion",
        "version": "0.2.0",
        "streaming_providers": ["flutterwave", "paystack", "mtn_momo", "monnify"],
        "batch_providers": ["mono"],
        "notes": {
            "mono": "Batch EOD only — runs via mono-batch service at 23:00 daily"
        }
    }