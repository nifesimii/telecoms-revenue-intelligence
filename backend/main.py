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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import config
from backend.agent import prompts
from backend.api.routes import router as api_router

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — fail fast if the KB cannot be loaded
# ---------------------------------------------------------------------------


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
        "System prompt loaded (%d chars). USE_SAMPLE_DATA=%s.",
        len(system_prompt),
        config.USE_SAMPLE_DATA,
    )
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


# ---------------------------------------------------------------------------
# Health probe
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    """Lightweight liveness probe — also reports which data mode is active."""
    return {
        "status": "ok",
        "sample_data_mode": config.USE_SAMPLE_DATA,
    }


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(api_router)
