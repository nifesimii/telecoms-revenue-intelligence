# Deploy — GM Preview on Render

Getting a shareable link for the FBB Trade Partner Intelligence Platform.
Single Render web service (Docker) that serves both the FastAPI backend and
the built React SPA on one origin, plus one managed Postgres for the Audit
Trails feature. Everything runs on sample data — no MTN systems touched.

**Cost:** ~$14/mo (Starter web $7 + Basic-256mb Postgres $7). Free tiers work
too but the web service cold-starts after 15 min idle — not great for a demo.

---

## 1. Prereqs

- Repo pushed to GitHub with these files:
  - `render.yaml` (blueprint at repo root)
  - `backend/Dockerfile` + `.dockerignore` at repo root
  - `backend/middleware/basic_auth.py`
- Render account (free to create). No card needed until you upgrade off free.
- An Anthropic API key with budget for the demo window.

## 2. Provision

1. Render dashboard → **New** → **Blueprint**.
2. Connect the GitHub repo. Render reads `render.yaml` and shows a plan:
   - Web service `fbb-preview` (Docker, Frankfurt, Starter)
   - Postgres `fbb-audit-pg` (Basic-256mb, Frankfurt)
3. Click **Apply**. Postgres provisions first (~1 min); the web service
   builds after (~4–6 min for the first Docker build).

## 3. Set the three secrets

The blueprint declares three env vars as `sync: false`, meaning Render leaves
them blank for you to fill in the dashboard (never commit them to the repo).

Go to the web service → **Environment** → set:

| Key              | Value                                                   |
|------------------|---------------------------------------------------------|
| `ANTHROPIC_API_KEY` | Your Anthropic key                                   |
| `DEMO_USERNAME`     | Chosen username (e.g. `mtn-gm`)                      |
| `DEMO_PASSWORD`     | Strong random string — this gates the whole preview  |

Save. Render redeploys automatically.

**If either `DEMO_*` is blank the gate is disabled and the app is public.**
Both must be set.

The Blueprint also links `FBB_AUDIT_PG_*` and `APDP_PG_*` to the managed
`fbb-audit-pg` database automatically. If the web service was created manually
instead of through the Blueprint, verify those variables under **Environment**.
An Audit Trails error mentioning `localhost:5544` means the database binding
is missing—not that Postgres should be running inside the web container.
For the demo, the backend can fall back from missing `FBB_AUDIT_PG_*` values to
explicit `APDP_PG_*` values because both schemas intentionally share one DB.

## 4. Smoke test

Once the deploy shows **Live**:

```bash
# Health probe — no auth required, confirms the process is up.
curl -i https://fbb-preview.onrender.com/health
# → 200 {"status":"ok","sample_data_mode":true,"payment_source":"simulated",...}
# The Render preview intentionally matches localhost and reads the packaged
# payment_simulation.csv fixture. Use PAYMENT_SOURCE=apdp only in a dedicated
# APDP integration environment.

# Anything else — 401 without creds, 200 with them.
curl -i https://fbb-preview.onrender.com/
curl -i -u "mtn-gm:<password>" https://fbb-preview.onrender.com/periods
```

In a browser: open the site, browser prompts for the basic-auth credentials,
enter them once, the SPA loads. Click **Audit Trails** → **Run** → confirm
trails come back (proves the managed Postgres is wired end-to-end;
`ensure_schema()` bootstraps the schema on first write).

## 5. Share

Grab the Render URL, share with the GM alongside the credentials **out of
band** (WhatsApp, not the same email as the URL).

## Operations

**Rotate the password.** Dashboard → Environment → change `DEMO_PASSWORD` →
Save. Render redeploys; browsers with the old creds cached get a 401 and
re-prompt.

**Redeploy after code changes.** Push to the tracked branch — `autoDeploy:
true` in `render.yaml` picks it up. Or dashboard → **Manual Deploy**.

**Reset the audit DB.** Dashboard → Postgres → **Reset**. Next time
someone opens the Audit Trails tab, `ensure_schema()` recreates the tables
from `infra/postgres/audit_init.sql`; running an audit repopulates them.
Note: this also empties `normalized.transactions`. The next backend boot
does not reload APDP while the preview uses `PAYMENT_SOURCE=simulated`.
If a dedicated APDP environment is enabled later, its next boot will
re-apply `infra/postgres/apdp_seed.sql` automatically (~60s).

**Reload the APDP seed manually.** Delete the rows and restart the
backend service, e.g. from a psql shell:
```sql
TRUNCATE normalized.transactions;
```
Render → **Manual Deploy** on the web service — the lifespan hook
notices the empty table and re-applies the seed. Useful if you've been
poking at data and want a fresh known-good state.

**Downgrade to free.** Change `plan: starter` → `plan: free` in
`render.yaml`. Accept ~30s cold starts on the first request after idle.

## Known limits (deliberately not fixed)

- **Sample data only on the FBB side.** `USE_SAMPLE_DATA=true`. Live
  Presto still `NotImplementedError` (the query strings in
  `backend/db/queries.py` exist for that future path). Payment also uses
  the deterministic simulated CSV so Render matches localhost.
- **APDP data comes from a packaged seed, not live ingestion.**
  `infra/postgres/apdp_seed.sql` is a fixture pg_dump baked into the
  Docker image (~23 MB). The backend applies it on first boot via
  `main.py`'s lifespan hook when `normalized.transactions` is empty.
  Real streaming ingestion via Kafka/Flink is out of scope for the
  demo (the Flink Docker build is broken — see `apdp/CLAUDE.md`).
- **One shared credential.** Basic Auth is a gate, not a user system. Anyone
  with the URL + password gets full access to every endpoint.
- **Frankfurt region.** Latency from Lagos is ~150–200 ms; acceptable for a
  demo. If it feels sluggish, Fly.io in JNB is the next step (needs a
  separate blueprint — not covered here).
- **No HTTPS-only redirect config needed.** Render terminates TLS and always
  serves the site over HTTPS.
