# Preview responsiveness

## Scope and acceptance criteria

Requested on 2026-09-30 after investigating lag on the Render preview. The
implementation follows the user's instruction to implement the recommendations
with parallel Herdr workers and commit locally. Baseline: `e0ecf96`.

- Reduce the measured sample-mode activation summary CPU work without changing
  any recorded amounts, denomination attribution, zero counts, source labels,
  filters, deterministic ordering, or bounded API responses.
- Load workspace JavaScript on demand. Keep a usable loading/error state while
  a workspace loads.
- Preserve a visited workspace's dealer selection, filters and investigation
  context. Hidden workspaces must not fetch new reporting-month data. Returning
  to one must show the current reporting month, with correct comparison and
  browser-history behavior.
- Open Atlas promptly and show immediate progress after submission. Reuse the
  existing structured explanation streaming; improve any remaining buffered
  interactive path without dropping tool evidence or the complete knowledge
  base. Preserve cancellation, retry and conversation scope isolation.
- Keep current hosting and model settings. No production writes, deployment,
  billed model probes, speculative Redis cache or new data infrastructure.

Verification uses the existing public query/API, conversation transport and
browser interaction boundaries. Financial equivalence is required before a
performance change is retained. Backend tests run in sample mode with mocked
providers. The project has no standalone JavaScript typecheck configured;
production builds and browser checks validate its JSX modules.

## Initial evidence

- Live `/health` reported `e0ecf96`, sample data, simulated payments and a ready
  service. One response took 0.454 seconds including network transport.
- The authenticated dashboard could not be measured from this session. Its
  login response took approximately 0.484 seconds; that is not dashboard latency.
- Local March-versus-February `/commissions` activation reads took 630–762 ms
  across six requests; subscriptions took 37–42 ms. Profiling attributed almost
  all activation processing to per-dealer operations in the sample summary.
- The initial production JavaScript bundle was 593.02 kB (171.84 kB gzip).
- `render.yaml` specifies Starter. Actual Render CPU/memory metrics and plan
  settings have not been inspected. A paid upgrade is not justified by the
  evidence collected so far.

## Results

### Commission aggregation

Seven-run medians using the same offline benchmark and source fixtures:

| Workload | Before | After |
| --- | ---: | ---: |
| March summary, warm CSV cache | 321.76 ms | 52.53 ms |
| March summary, cleared CSV cache | 360.10 ms | 114.68 ms |
| March API with February comparison, warm | 640.82 ms | 91.47 ms |
| March API with February comparison, cleared CSV cache | 788.55 ms | 183.34 ms |

The warm comparison API uses about 86% less time (7× faster). These are local
in-process HTTP measurements, not Render latency guarantees. CSV-cold means
clearing the parsed-CSV cache; it excludes interpreter startup and OS cache
eviction. No balance/result cache was added. Reproduce current measurements with
`.venv/bin/python -m backend.tests.benchmark_dealer_summary`.

Regression checks compare the original and optimized result exactly across all
six fixture periods, selected dealer filters, missing/empty results, first-row
null metadata, denomination order and the bounded collection API. The optimized
path retains the original floating-point reduction semantics for dealer totals.

### Browser navigation

An isolated Chrome probe visited Commission, switched to Payments, and changed
March to April. Previously hidden Commission generated two collection requests
under the development StrictMode build. After the change it generated zero;
only the active Payments collection and comparison-position reads remained.
Development request duplication is not claimed as a production measurement.
The warm Atlas opener took 73 ms before changes, so there is no measured reason
to attribute local panel-opening delay to model inference.

### Initial JavaScript

Workspaces load on demand, and the Commission page defers Atlas's Markdown
rendering dependencies until Atlas is needed. An isolated production-build
browser loaded about 285 kB of JavaScript for the initial Commission table,
compared with the original single 593 kB bundle (about 52% fewer bytes).
Separately gzipping those loaded assets totals about 92 kB versus the original
172 kB (about 46% less). These are asset-size measurements, not a promise about
network speed or evidence that Render currently compresses every asset.
Additional chunks load when the user opens Atlas or another workspace.

### Atlas delivery

Ordinary questions now use `/chat/stream`, sharing the existing conversation and
tool loop. `/chat` remains compatible with buffered callers. The browser shows
progress immediately, marks streamed text as an incomplete draft, clears
planning prose when a tool is selected, and retains tool provenance on completion.
The full KB, model, output budget and retry/deadline policy remain intact.
The existing structured `/chat/explain` path remains available.

No live provider speedup is claimed: first useful text still depends on provider
latency and necessary tool rounds. Streaming improves delivery while a response
is being generated; it does not make model generation itself faster.

The ordinary-chat loopback fixture observed opening at 56 ms, visible waiting at
88 ms, first provisional text at 47 ms after submission and completion at 311 ms.
The fixture deliberately controls byte delivery. These timings prove progressive
rendering; they do not estimate live model or Render response time.

## Verification

- Full sample backend suite: 353 passed, 28 skipped. The final cross-tool-round
  retry guard was additionally checked in the complete streaming test file:
  14 passed. No billed provider calls or live Presto access.
- Frontend unit/transport tests: 16 passed. Production build and Python module
  compilation passed; no standalone frontend typecheck is configured.
- Isolated Chrome checks: Commission dealer/filter continuity across page/month
  changes, browser history, earliest-month comparison, lazy workspaces, narrow
  layout, Atlas progressive delivery, Stop/Retry, reload interruption,
  provisional-history exclusion and scoped conversation preservation.
- Existing Findings/Inventory and Payment/Commission assistant browser
  regressions passed with mocked streams.
- Independent Standards and Spec reviews identified audit acknowledgement scope,
  Activation default comparison and Inventory selection-pagination issues. Their
  fixes passed focused browser checks and both reviewers cleared the final code.
  Audit acknowledgements reset on module/month changes; automatic Activation
  comparisons advance while explicit choices persist; Inventory scans bounded
  pages for the exact selected subject and cancels that lookup when hidden.

## Deployment and remaining measurements

The changes are local until deployed. No Render settings or model selection were
changed. After deployment, confirm the new revision through `/health`, measure
authenticated page/stream requests, and compare `Server-Timing` with browser
time-to-first-text and completion. Inspect Render CPU/memory around the same
requests before deciding whether more compute is needed. Do not interpret the
local sample benchmarks as live database capacity measurements.
