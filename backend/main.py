"""FastAPI app entry point.

Builds the FastAPI app, wires CORS using :data:`backend.config.CORS_ORIGINS`,
mounts the API router from :mod:`backend.api.routes`, and exposes a tiny
``GET /health`` probe.

The lifespan startup hook explicitly loads the knowledge base via
:func:`backend.agent.prompts.get_system_prompt` so the process fails fast at
boot — not on the first ``/chat`` request — if the KB file is missing or
empty.
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend import config
from backend.agent import prompts
from backend.api.routes import router as api_router
from backend.middleware.basic_auth import install_if_configured as install_basic_auth

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — fail fast if the KB cannot be loaded
# ---------------------------------------------------------------------------


_APDP_SEED_PATH = (
    Path(__file__).resolve().parent.parent / "infra" / "postgres" / "apdp_seed.sql"
)
_APDP_REPAIR_PATH = (
    Path(__file__).resolve().parent.parent
    / "infra"
    / "postgres"
    / "apdp_schema_repair.sql"
)
_PAYMENT_BOOTSTRAP_STAGE = "not_started"
_PAYMENT_BOOTSTRAP_ERROR: str | None = None


def _record_bootstrap_error(stage: str, exc: Exception) -> None:
    """Record a credential-free diagnostic for the public readiness probe."""
    global _PAYMENT_BOOTSTRAP_STAGE, _PAYMENT_BOOTSTRAP_ERROR
    _PAYMENT_BOOTSTRAP_STAGE = stage
    pgcode = getattr(exc, "pgcode", None) or "none"
    primary = getattr(getattr(exc, "diag", None), "message_primary", None)
    message = primary or str(exc).splitlines()[0]
    _PAYMENT_BOOTSTRAP_ERROR = (
        f"{type(exc).__name__} pgcode={pgcode}: {message[:240]}"
    )


def _seed_apdp_if_empty() -> bool:
    """One-shot APDP seed loader.

    When ``PAYMENT_SOURCE=apdp`` and the target Postgres has an empty
    (or missing) ``normalized.transactions``, execute the packaged
    ``infra/postgres/apdp_seed.sql`` — which restores the raw + normalized
    schemas + the fixture data + the ``partner_settlements`` view.

    Idempotent: on subsequent boots both the table and settlement view exist,
    so this is a fast metadata-check-and-skip. A partially initialised database
    (transactions present, view absent) gets a non-destructive schema repair.
    Deliberately non-fatal — if seeding fails
    the app still boots (Payment tab just returns empty results with a
    'Live · APDP' badge). Rendering an empty tab is a better demo
    posture than a 500 wall.
    """
    global _PAYMENT_BOOTSTRAP_STAGE, _PAYMENT_BOOTSTRAP_ERROR
    _PAYMENT_BOOTSTRAP_STAGE = "disabled"
    _PAYMENT_BOOTSTRAP_ERROR = None
    if config.PAYMENT_SOURCE != "apdp":
        return True
    if not _APDP_SEED_PATH.is_file():
        _PAYMENT_BOOTSTRAP_STAGE = "seed_file_missing"
        logger.info("APDP seed file not present at %s — skipping.", _APDP_SEED_PATH)
        return False
    try:
        _PAYMENT_BOOTSTRAP_STAGE = "connecting"
        import psycopg2
        conn = psycopg2.connect(
            host=config.APDP_PG_HOST, port=config.APDP_PG_PORT,
            dbname=config.APDP_PG_DB, user=config.APDP_PG_USER,
            password=config.APDP_PG_PASSWORD, connect_timeout=10,
        )
    except Exception as exc:
        _record_bootstrap_error("connect_failed", exc)
        logger.warning("APDP seed skipped — Postgres unreachable: %s", exc)
        return False

    try:
        # Enable autocommit before the first statement. psycopg2 starts a
        # transaction even for SELECTs; changing autocommit after the metadata
        # checks raises ProgrammingError and previously prevented both the
        # seed and partial-schema repair from ever running on Render.
        conn.autocommit = True
        _PAYMENT_BOOTSTRAP_STAGE = "inspecting"
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass('normalized.transactions') IS NOT NULL"
            )
            has_table = bool(cur.fetchone()[0])
            cur.execute(
                "SELECT to_regclass('normalized.partner_settlements') "
                "IS NOT NULL"
            )
            has_view = bool(cur.fetchone()[0])
            row_count = 0
            if has_table:
                cur.execute("SELECT COUNT(*) FROM normalized.transactions")
                row_count = int(cur.fetchone()[0])
            if row_count > 0 and has_view:
                _PAYMENT_BOOTSTRAP_STAGE = "ready"
                logger.info(
                    "APDP bootstrap skipped — normalized.transactions has "
                    "%d rows and partner_settlements exists.", row_count,
                )
                return True
            if row_count > 0 and not has_view:
                if not _APDP_REPAIR_PATH.is_file():
                    _PAYMENT_BOOTSTRAP_STAGE = "repair_file_missing"
                    logger.warning(
                        "APDP schema repair file not present at %s.",
                        _APDP_REPAIR_PATH,
                    )
                    return False
                logger.warning(
                    "APDP database is partially initialised: %d transactions "
                    "exist but partner_settlements is missing. Repairing schema.",
                    row_count,
                )
                _PAYMENT_BOOTSTRAP_STAGE = "repairing"
                with conn.cursor() as repair_cur:
                    repair_cur.execute(_APDP_REPAIR_PATH.read_text())
                    repair_cur.execute(
                        "SELECT to_regclass('normalized.partner_settlements') "
                        "IS NOT NULL"
                    )
                    if not bool(repair_cur.fetchone()[0]):
                        raise RuntimeError(
                            "APDP schema repair completed without creating "
                            "normalized.partner_settlements"
                        )
                logger.info("APDP partner_settlements view repaired.")
                _PAYMENT_BOOTSTRAP_STAGE = "ready_after_repair"
                return True
        # Empty (or table missing) — apply the seed.
        logger.info("Applying APDP seed from %s …", _APDP_SEED_PATH)
        _PAYMENT_BOOTSTRAP_STAGE = "seeding"
        sql = _APDP_SEED_PATH.read_text()
        with conn.cursor() as cur:
            cur.execute(sql)
        # Confirm.
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM normalized.transactions")
            n = int(cur.fetchone()[0])
        logger.info("APDP seed applied — %d transactions loaded.", n)
        _PAYMENT_BOOTSTRAP_STAGE = "ready_after_seed"
        return True
    except Exception as exc:
        _record_bootstrap_error(f"{_PAYMENT_BOOTSTRAP_STAGE}_failed", exc)
        logger.exception("APDP seed failed — Payment tab will read empty results.")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Verify the system prompt loads cleanly before serving traffic."""
    system_prompt = prompts.get_system_prompt()
    if not system_prompt or len(system_prompt) < 500:
        raise RuntimeError(
            "System prompt failed to load or is suspiciously short — "
            "expected the FBB commission KB to be injected. Check "
            "backend/knowledge_base/fbb_commission_kb.md."
        )
    logger.info(
        "System prompt loaded (%d chars). USE_SAMPLE_DATA=%s PAYMENT_SOURCE=%s.",
        len(system_prompt),
        config.USE_SAMPLE_DATA,
        config.PAYMENT_SOURCE,
    )
    # APDP seed happens after KB load so the app is definitely usable
    # even if seeding fails. Runs synchronously in the startup phase —
    # ~30-60s on first Render boot, ~50ms on subsequent boots (idempotent).
    app.state.payment_ready = _seed_apdp_if_empty()
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


app = FastAPI(
    title="FBB Trade Partner Intelligence API",
    description=(
        "Finance intelligence backend for MTN Nigeria's Fixed Broadband "
        "trade partner commission programme."
    ),
    version="0.1.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def performance_observability(request, call_next):
    """Expose and log request duration without logging financial payloads."""
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"
    logger.info(
        "http_request method=%s path=%s status=%s duration_ms=%.1f content_length=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        response.headers.get("content-length", "streamed"),
    )
    return response

# Basic Auth gate for the GM preview deploy. No-op locally unless
# DEMO_USERNAME + DEMO_PASSWORD are set — production sets both as secrets.
if install_basic_auth(app):
    logger.info("Basic Auth middleware installed (DEMO_USERNAME/PASSWORD set).")


# ---------------------------------------------------------------------------
# Health probe
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    """Liveness plus deploy identity and Payment-source readiness."""
    return {
        "status": "ok",
        "sample_data_mode": config.USE_SAMPLE_DATA,
        "payment_source": config.PAYMENT_SOURCE,   # "simulated" | "apdp"
        "payment_ready": getattr(
            app.state, "payment_ready", config.PAYMENT_SOURCE != "apdp"
        ),
        "revision": os.getenv("RENDER_GIT_COMMIT", "local")[:7],
        "payment_bootstrap_stage": _PAYMENT_BOOTSTRAP_STAGE,
        "payment_bootstrap_error": _PAYMENT_BOOTSTRAP_ERROR,
    }


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(api_router)


# ---------------------------------------------------------------------------
# Static SPA — serve the built frontend under `/` (deployed single-service).
# ---------------------------------------------------------------------------
# In the deploy image the Vite build lands at ./frontend/dist. Mount LAST so
# any real API route (registered above) wins over the SPA catch-all.
# `html=True` makes /some/path fall back to /index.html for client-side routes.
_spa_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _spa_dir.is_dir():
    app.mount("/", StaticFiles(directory=_spa_dir, html=True), name="spa")
    logger.info("Serving SPA from %s", _spa_dir)
else:
    logger.info("No SPA build at %s — API-only mode.", _spa_dir)
