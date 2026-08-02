# Dealer Data Connectors — access-model decision record

The goal: when finance approves, connect to dealers and pull their MoMo /
account data **immediately**. This document is the honest map of how that
actually works, what's already proven, and what each access model needs
before it can go live — so there are no surprises the day approval lands.

Code: `apdp/ingestion/connectors/`.

---

## The core fact (read this first)

"Connect to a dealer and fetch their MoMo data" is **not one thing**. There
are three legitimate access models, and they differ in what MTN/finance must
grant, how fast you can onboard dealers, and what you can actually read. The
MoMo **merchant** API you already had (`ingestion/pollers/mtn_momo.py`)
authenticates as *you* and sees *your* collections — it cannot read an
arbitrary dealer's wallet. So picking the right model matters more than the code.

| # | Model | How access is granted | Reads the dealer's own wallet? | Time to onboard a dealer | What it needs before go-live |
|---|-------|----------------------|-------------------------------|--------------------------|------------------------------|
| A | **MoMo merchant API** (`momo`) | You hold MoMo API keys | Only accounts you hold keys for — **not** an arbitrary dealer | Immediate for your own accounts | Production MoMo keys + a real statement/history endpoint |
| B | **Consent aggregation** (`consent`) | Each dealer authorizes (Mono/Okra widget) | **Yes** — the dealer's real account | Per-dealer (dealer must click "allow") | Aggregator contract + a consent-capture flow |
| C | **Internal MTN feed** (`internal`) | MTN grants access to its own MoMo/BSS ledger | **Yes** — MTN owns MoMo | Immediate for all dealers at once | An internal data-access grant + feed spec |
| — | **File drop** (`file`) | Dealer/DMS exports a CSV | N/A (whatever the export contains) | Immediate | A file spec + drop location (already built: `telecom_batch.py`) |
| — | **Simulated** (`simulated`) | none | N/A | Immediate | nothing — proof/demo source |

**Chosen direction (this build):** model-agnostic core + a live-mechanism
proof, with **consent aggregation (B)** as the first production target.
Model C (internal feed) is likely the fastest real path if MTN grants it —
and because everything sits behind one interface, activating it later is one
new connector class, not a rebuild.

---

## What was built — the model-proof architecture

Everything routes through **one interface** so the access model is a
swappable detail, not an architectural commitment.

```
dealer_connections (onboarding registry: "a dealer = a row")
        │
        ▼
runner.py  ──dispatch per dealer──►  DealerDataConnector.fetch()
        │                              ├─ SimulatedConnector   (proof, no creds)
        │                              ├─ MoMoConnector        (model A / sandbox proof)
        │                              ├─ MonoConsentConnector (model B / production target)
        │                              └─ [InternalFeedConnector — add when MTN grants model C]
        ▼
raw envelope  ──►  existing Flink normalizer  ──►  normalized.transactions  ──►  Postgres  ──►  FBB
   (unchanged)          (unchanged)                   (unchanged)              (unchanged)
```

The key property: **a connector returns the exact raw envelope the existing
normalizer already consumes.** Proven in tests — a `SimulatedConnector`
envelope flows through `normalize_event()` and comes out as a canonical
`_pipeline_version: 1.3.0` event with no downstream change.

### Files
| File | Role |
|---|---|
| `connectors/base.py` | `DealerConnection` (the config row) + `DealerDataConnector` protocol + registry. Defines the five connector types and the consent lifecycle. |
| `connectors/simulated.py` | Deterministic fake source. Proves the whole path end-to-end with zero credentials/infra — the demo source. |
| `connectors/momo.py` | MTN MoMo (model A). Against sandbox proves auth + connectivity + envelope emission; point at prod + swap the fetch endpoint when keys land. |
| `connectors/mono.py` | Mono consent aggregation (model B). Reads a dealer's authorized account. The production target. |
| `connectors/onboarding.py` | Loads the dealer registry from Postgres `dealer_connections` (prod) or a JSON file (zero-infra fallback). |
| `connectors/runner.py` | Orchestrator: pull every ready dealer, publish to Kafka. Per-dealer error isolation. `--dry-run` / `--dealer`. |
| `connectors/dealer_connections.sample.json` | Sample onboarding registry (the zero-infra source). |
| `infra/postgres/init.sql` → `public.dealer_connections` | The production onboarding table. |

---

## What's proven vs pending

**Proven now (no credentials, no infra):**
- The connector interface + registry (3 connectors register cleanly).
- Onboarding-as-config: dealers load from the registry; `ready` correctly
  gates consent-pending dealers.
- End-to-end mechanism: `runner --dry-run` pulls the ready dealers, the
  simulated connector emits envelopes, and those envelopes normalize through
  the existing pipeline unchanged.
- Per-dealer error isolation: a mis-configured MoMo dealer fails with a clean
  captured error while the other dealers still succeed (verified in tests).

**Pending — needs a real grant/credential (one connector each, no rebuild):**
- **Model A (MoMo prod):** production subscription key + API user/key, and the
  real transaction-history endpoint (sandbox only exposes balance). Swap the
  one `fetch` call in `momo.py`.
- **Model B (Mono consent):** an aggregator agreement + a consent-capture step
  (dealer runs the Mono Connect widget → we store their `account_id` as
  `account_ref` and set `consent_status='granted'`). The polling half is done.
- **Model C (internal feed):** the data-access grant + feed spec. Add an
  `InternalFeedConnector` implementing the same interface.

---

## The day approval lands — activation checklist

1. Confirm the model finance actually granted (A / B / C).
2. Put the credential in the secret store; set the dealer's `credentials_ref`
   to its name (never the secret itself).
3. Load the dealer roster into `public.dealer_connections` (one row per
   dealer: `dealer_code`, `connector_type`, `account_ref`, `consent_status`).
4. For consent (B): run each dealer through the consent widget; flip
   `consent_status` to `granted` as authorizations come in.
5. `python -m ingestion.connectors.runner --dealer <one>` to smoke-test a
   single dealer, then run the full batch on a schedule.
6. Data flows into `normalized.transactions` → FBB reads it via
   `PAYMENT_SOURCE=apdp`. No downstream changes.

Because every link except the specific credential is already proven, "connect
to the dealers immediately" becomes: load the roster, drop in the secret, run.

---

## Try it now (zero setup)

```bash
cd apdp
PYTHONPATH=. python -m ingestion.connectors.runner --dry-run
# → pulls the sample dealers, prints the raw envelopes + a per-dealer report.
# The consent dealer is skipped (pending); the MoMo dealer reports "credentials
# not configured"; the simulated dealers emit events. That's the whole
# mechanism working before any real access exists.

# Tests (no creds/infra):
PYTHONPATH=apdp:apdp/flink_jobs pytest apdp/tests/test_connectors.py -q
```

Keep this doc updated when a new access model is activated or a connector's
production endpoint is wired.
