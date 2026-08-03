# FBB Revenue Intelligence — deployable image.
#
# Multi-stage: build the frontend once, then ship a slim Python image that
# serves both the FastAPI backend and the built SPA. Single service, single
# origin — see docs/DEPLOY.md.
#
# Build context is the REPO ROOT (so both backend/ and frontend/ are visible).
#   docker build -f backend/Dockerfile -t fbb-preview .

# ── Stage 1: build the frontend ─────────────────────────────────────────────
FROM node:22-alpine AS frontend

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# Same-origin deploy: leave VITE_API_URL empty so axios calls the current host.
ENV VITE_API_URL=""
RUN npm run build

# ── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# psycopg2-binary ships wheels, but keep libpq available for safety.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install -r backend/requirements.txt

# Backend source + assets read at boot (KB) or query time (sample CSVs).
COPY backend/ ./backend/
COPY data/ ./data/
COPY infra/ ./infra/

# Built SPA from stage 1 — mounted as static files by backend/main.py.
COPY --from=frontend /app/dist ./frontend/dist

EXPOSE 8000

# Render (and most PaaS) inject $PORT; default to 8000 for local runs.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
