# Zero-Commission Audit Trail (Phase 1)

Structured, persisted verification chain behind every "Partner X was not
paid commission for period Y" claim.

**Scope:** zero-commission flagging only. Inventory mismatch trails are a
later phase once this pattern is validated.

## Two purposes
1. **Audit** — every claim is backed by an inspectable, logged chain: an
   auditor can see exactly what was checked and why the conclusion was
   reached.
2. **Evaluation** — the same trail is the substrate for reviewing the
   agent's judgment quality over time (e.g. "across all runs, how often
   did we mislabel a data gap as 'not paid'?"). Trails are structured so
   they aggregate/query cleanly, not just display.

## The verification chain (per partner, per period)
| # | Step (`name`) | What it checks |
|---|---|---|
| 1 | `qualifying_activity` | Did the partner have activation records this period? (source table + counts) |
| 2 | `applicable_rate` | Valid rate/eligibility? No contract table exists — assessed from `account_profile_class` presence + whether zero-comm products exist in the USP rate card (`usp_dimension.item_no`) + KB 6-month window |
| 3 | `expected_commission` | Computed entitlement + inputs |
| 4 | `payment_record_search` | Search the payment dataset for this partner/period (source recorded) |
| 5 | `near_match` | Before concluding "not paid": adjacent-period payments + partial-amount matches |
| 6 | `upstream_completeness` | Does the payment dataset fully cover this period, or is it a known ingestion gap? |
| 7 | conclusion + confidence | `NOT_PAID` / `PAID` / `INSUFFICIENT_DATA` + `HIGH` / `MEDIUM` / `LOW` |

**Confidence rule:** `HIGH` if steps 1-6 all clean; `MEDIUM` if exactly one
non-step-6 caveat; `LOW` if step 6 caveats (upstream gap undermines
everything), if there are 2+ caveats, or if the conclusion is
`INSUFFICIENT_DATA`. An upstream gap (step 6) or no activity (step 1) forces
`INSUFFICIENT_DATA` — we never assert "not paid" when we can't distinguish it
from "not yet ingested".

## Decisions taken (from the requirements clarification)
- **Dedicated FBB Postgres** — separate DB (`fbb_audit`) from APDP's
  `payment_platform`. FBB owns its own audit datastore lifecycle.
- **Payment source recorded, not gated** — each trail carries
  `payment_source` (`simulated` | `apdp`). Simulated trails are persisted
  alongside real ones; the reader decides how much to trust each.
- **One trail per (partner, period)** — matches the claim shape "Partner X
  not paid for period Y".
- **Explicit run job** — `POST /assurance/zero-commission/run?mon_period=X`
  generates + persists. Writes are never triggered by a page view.
  Idempotent: re-running a period atomically replaces its trails.

## Where things live
| Path | Role |
|---|---|
| `backend/audit/trail.py` | `TrailStep` / `VerificationTrail` dataclasses + JSON sanitizer |
| `backend/audit/zero_commission_audit.py` | pure 6-step `build_trail` + `gather_inputs` + `run_period` orchestrator |
| `backend/db/audit_store.py` | persistence (idempotent per-period replace) + evaluation query helpers |
| `infra/postgres/audit_init.sql` | `audit.zero_commission_trail` + `audit.assurance_run` schema |
| `docker-compose.yml` | dedicated `fbb-postgres` + `fbb-postgres-backup` sidecar |
| `infra/postgres/backup.sh` | scheduled `pg_dump` → host `./backups/` |

## API
- `POST /assurance/zero-commission/run?mon_period=YYYYMM` → generate + persist
- `GET  /assurance/zero-commission/trails?mon_period=YYYYMM[&caveat_step=…]`
  — all trails, or filtered to a caveat step (evaluation surface)
- `GET  /assurance/zero-commission/trails/{partner_code}?mon_period=YYYYMM`
  — the full chain for one partner (auditor view)
- `GET  /assurance/zero-commission/breakdown?mon_period=YYYYMM`
  — counts by (conclusion, confidence)

## Evaluation query example
"Show me all trails where step 6 raised a caveat":
```sql
SELECT partner_code, mon_period, conclusion, confidence
FROM   audit.zero_commission_trail
WHERE  'upstream_completeness' = ANY(caveat_steps);
```
`caveat_steps` is a GIN-indexed `TEXT[]`; the full chain is in the `steps`
JSONB (also GIN-indexed) for deeper drill-downs.

## Data safety
- **Persistent volume:** ✅ `fbb_audit_data` named volume — survives
  container recreation and `docker compose down`.
- **Backup:** ✅ `fbb-postgres-backup` sidecar runs `pg_dump` daily to the
  host `./backups/` directory (outside any volume), keeping the last 14
  snapshots. This is the safety net against `docker volume rm` / `down -v`.
- **Restore:**
  ```
  gunzip -c backups/fbb_audit_YYYYMMDDTHHMMSSZ.sql.gz \
    | docker exec -i fbb_audit_postgres psql -U fbb_audit -d fbb_audit
  ```

## Pending verification
The live end-to-end write path (schema load + real insert/query against the
running `fbb-postgres`) was not exercised because the Docker daemon was down
during the build. Everything else is verified: pure builder (12 unit tests),
`run_period` against real sample data (487 trails, all serialize), row
mapping, graceful 503 on DB-down, and the endpoint happy path with mocked
persistence. To close the gap when Docker is up:
```
docker compose up -d fbb-postgres
docker exec fbb_audit_postgres psql -U fbb_audit -d fbb_audit -c "\dt audit.*"
# then, with the FBB backend running:
curl -X POST "localhost:8000/assurance/zero-commission/run?mon_period=202602"
curl "localhost:8000/assurance/zero-commission/breakdown?mon_period=202602"
```
