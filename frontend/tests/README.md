# Browser and explanation regression checks

Run transport checks and the production build without a backend or provider:

```sh
node --test frontend/tests/*.test.mjs
npm --prefix frontend run build
```

With sample-mode servers on localhost:5173 and localhost:8000:

```sh
PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs node frontend/tests/findings-streaming.mjs
PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs node frontend/tests/payment-explanation.mjs
PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs node frontend/tests/chat-streaming.mjs
PLAYWRIGHT_MODULE=/path/to/playwright/index.js node frontend/tests/workspace-navigation.cjs
PLAYWRIGHT_MODULE=/path/to/playwright/index.js node frontend/tests/workspace-scope-regressions.cjs
```

The findings test launches isolated Chrome and a temporary loopback HTTP server.
It intercepts both chat endpoints; real NDJSON bytes arrive in controlled chunks,
without provider calls. It checks the production Overview opener, then public
queue/assistant components at `tests/findings-fixture.html` for deterministic scope
permutations. The fixture is test-only and is not part of the production entrypoint.

Coverage: explicit Send, repeated structured intent, edited/general chat routing,
progressive text, metadata, dealer/period/module/type/product isolation, comparison
and stream independence, unmounted completion, Stop and disconnect, exact Retry,
server error, partial-history exclusion, reload interruption, narrow composer,
and existing Inventory/Payment/Commission behavior.

Local `performance` entries use `explanation:<opaque UUID>:<phase>` names only:

- `first-visible-text`: committed assistant text measured with a guarded animation frame.
- `network-complete`: terminal completion received, independent of navigation.
- `rendered-complete`: completed answer rendered in a visible presentation; may include time away.

No request content or account identity is placed in timing entries. Measures remain
local to the page; they are not telemetry. The test prints separate fixture timings.
These establish progressive rendering, not provider performance or cache speedup.

The navigation check uses isolated Chrome and sample-data reads; provider/write
paths are blocked. It covers the initial period/comparison gate, suppression of
hidden workspace reads, retained dealer/filter state, month changes, browser
history, lazy loading and failure states, and cross-workspace investigation
handoffs. `FRONTEND_URL` can override its default Vite origin.
The scope regression additionally verifies month/module-specific audit
acknowledgement without writes, automatic versus explicit comparison choices,
and exact Inventory selection beyond the first bounded page or absent entirely.

The ordinary-chat streaming test uses a temporary loopback NDJSON server rather
than a model provider. It checks visible waiting/provisional text before terminal
completion, tool-planning reset and provenance, cancellation/disconnect, exact
retry, exclusion of incomplete history and account/period isolation.
