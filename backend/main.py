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


def _seed_apdp_if_empty() -> None:
    """One-shot APDP seed loader.

    When ``PAYMENT_SOURCE=apdp`` and the target Postgres has an empty
    (or missing) ``normalized.transactions``, execute the packaged
    ``infra/postgres/apdp_seed.sql`` — which restores the raw + normalized
    schemas + the fixture data + the ``partner_settlements`` view.

    Idempotent: on subsequent boots the table already has rows, so this
    is a fast COUNT-and-skip. Deliberately non-fatal — if seeding fails
    the app still boots (Payment tab just returns empty results with a
    'Live · APDP' badge). Rendering an empty tab is a better demo
    posture than a 500 wall.
    """
    if config.PAYMENT_SOURCE != "apdp":
        return
    if not _APDP_SEED_PATH.is_file():
        logger.info("APDP seed file not present at %s — skipping.", _APDP_SEED_PATH)
        return
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=config.APDP_PG_HOST, port=config.APDP_PG_PORT,
            dbname=config.APDP_PG_DB, user=config.APDP_PG_USER,
            password=config.APDP_PG_PASSWORD, connect_timeout=10,
        )
    except Exception as exc:
        logger.warning("APDP seed skipped — Postgres unreachable: %s", exc)
        return

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass('normalized.transactions') IS NOT NULL"
            )
            has_table = bool(cur.fetchone()[0])
            row_count = 0
            if has_table:
                cur.execute("SELECT COUNT(*) FROM normalized.transactions")
                row_count = int(cur.fetchone()[0])
            if row_count > 0:
                logger.info(
                    "APDP seed skipped — normalized.transactions already "
                    "has %d rows.", row_count,
                )
                return
        # Empty (or table missing) — apply the seed.
        logger.info("Applying APDP seed from %s …", _APDP_SEED_PATH)
        sql = _APDP_SEED_PATH.read_text()
        # autocommit so pg_dump's own transaction directives don't nest.
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql)
        # Confirm.
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM normalized.transactions")
            n = int(cur.fetchone()[0])
        logger.info("APDP seed applied — %d transactions loaded.", n)
    except Exception:
        logger.exception("APDP seed failed — Payment tab will read empty results.")
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
    _seed_apdp_if_empty()
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

# Basic Auth gate for the GM preview deploy. No-op locally unless
# DEMO_USERNAME + DEMO_PASSWORD are set — production sets both as secrets.
if install_basic_auth(app):
    logger.info("Basic Auth middleware installed (DEMO_USERNAME/PASSWORD set).")


# ---------------------------------------------------------------------------
# Health probe
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    """Lightweight liveness probe — also reports which data mode is active."""
    return {
        "status": "ok",
        "sample_data_mode": config.USE_SAMPLE_DATA,
        "payment_source": config.PAYMENT_SOURCE,   # "simulated" | "apdp"
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
