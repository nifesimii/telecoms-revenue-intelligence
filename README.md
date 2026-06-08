# fbb-trade-intel

FBB Trade Partner Revenue Intelligence Platform — a finance-facing
chat interface that explains, validates, and investigates Fixed
Broadband trade partner commissions (Device Activation and ORSC).

## Stack

- Backend: FastAPI + Anthropic Claude (tool use)
- Data: Presto (live) or pandas/CSV (sample mode)
- Frontend: React + Vite + Tailwind

## Quick start

1. Copy `.env.example` to `.env` and fill in values
2. Set `USE_SAMPLE_DATA=true` for local development
3. See `CLAUDE.md` for the full build order and architecture rules

This repo currently contains structure and stubs only.
Implementation follows the build order documented in `CLAUDE.md`.
