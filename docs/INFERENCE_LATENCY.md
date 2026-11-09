# Explain Findings latency

Ordinary chat and Explain Findings now share prepared evidence and complete-answer
validation before publication. Findings retains its deterministic evidence lookup;
ordinary chat resolves a bounded scope first. Progress may be shown while either
path works, but provider drafts are withheld until validated. The September 29
measurements below describe the earlier direct-streaming implementation and must
not be interpreted as latency measurements of this publication contract.

## Request and response

`POST /chat/explain` accepts:

```json
{
  "dealer_id": "74050",
  "mon_period": "202606",
  "finding": {"module": "commission", "type": "ZERO_COMMISSION_ACTIVATION"}
}
```

`finding.product_code` is required for inventory and rejected for other modules. No
client-supplied amount or finding description is accepted as evidence. The
server revalidates the finding against the selected source, dealer and month.
Unknown/stale findings do not invoke the model. Payment evidence uses the same
source and status projection as the Payments API, including APDP record counts.

The `application/x-ndjson` response emits one JSON object per line:

- `{"type":"status", ...}`: application-owned progress before answer publication.
- `{"type":"text","text":"..."}`: validated rendered answer text only.
- `{"type":"complete","response":"...","tools_called":[],"raw_data":{},"error":null}`:
  final answer with the existing chat metadata.
- `{"type":"error","error":"deadline_exceeded","message":"..."}`:
  sanitized failure; never followed by successful completion.

Other failure codes are `invalid_evidence` and `explanation_failed`. Invalid
request schemas return HTTP 422 before streaming. Clients must treat EOF without
completion as interrupted, retain any partial text as incomplete, and exclude
incomplete answers from subsequent model history. Provisional or rejected model
prose is never sent as answer text. No retry replays a published answer.
Disconnects cancel provider work, including waits before publication. A read already running in a worker thread may finish
after the waiting request is cancelled; cooperative checks prevent the next
evidence operation from starting.

## Provider policy and observation

`compose_answer()` receives an application-created `PreparedAnswer` containing
validated scope, source-referenced facts and supported claims, permitted actions,
mandatory caveats and structured attachments. Python prepares arithmetic using
`Decimal`; model input uses decimal strings. Missing evidence is not zero, and
paid, owed, outstanding and subscription revenue retain distinct meanings.
Findings inventory evidence is projected to the exact selected product.

The model returns a forced-tool `AnswerDraft` with a nullable headline,
explanation blocks (`text`, `claim_ids`) and `next_step_ids`. Complete local
validation checks references, scope, financial meaning, population, causality and
unsafe content before rendering. Each placeholder must belong to a cited claim;
claim IDs alone do not establish prose truth. Python renders selected action
wording and appends mandatory source-specific disclosures even if omitted by the
model. The limits remain 12,000 answer characters and 180 KB of model input.
Refusals, truncation and invalid drafts are never published as partial prose.

The static provider schemas are adapted using the installed SDK's schema
transformer through `inference.strict_tool()`, with `strict: true` and existing
forced tool selection. The original local schemas retain constraints and
cross-field checks. See the provider's [strict tool documentation](https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use).
The full core KB and stable tool/system prefixes retain provider prompt caching;
local Python prompt caching alone does not establish a provider cache hit. See
[prompt-caching documentation](https://platform.claude.com/docs/en/build-with-claude/prompt-caching).

The SDK has `max_retries=0`. A single recovery allowance is shared by provider
retry, scope repair and answer repair. Recovery honors provider Retry-After
guidance and rejects waits exceeding the remaining 90-second request deadline.
There is no extra Findings retry budget or automatic evidence-only fallback. HTTP timeouts are connect 5s, read 30s, write 10s, pool 5s.
These limits bound failures; they are not a claim of faster healthy inference.

Inference logs carry an opaque request ID and contain timing/count/status fields,
not questions, dealer identities, financial records or provider exception bodies.
They report model-call duration/count, evidence/tool duration, retry waits/count,
provider timing, validated answer readiness, overall duration and
input/output/cache token counts. Existing
HTTP middleware timing measures response setup; use inference completion events
for full request duration. Historical provider-first-text timing is distinct from
validated publication and browser render timing. Time to first answer text now
includes retrieval, composition and complete validation (plus scope resolution in
ordinary chat); progress-event timing should be measured separately. The browser keeps local performance entries with opaque request
IDs for first rendered text, network completion and rendered completion. A
rendered-completion measurement can include time spent away from the thread;
network completion is recorded independently. See `frontend/tests/README.md`.

## Historical local measurements

All measurements below use sample data or mocked HTTP, with no live Presto or
billed model requests. They do not reproduce the user's production latency.

An identical persistent-429 SDK MockTransport probe at the original commit
`87c0dc3` and the new runtime, with sleep replaced by a recorder, produced:

| Policy | HTTP attempts | Simulated total waits | Fixed 20-second waits |
| --- | ---: | ---: | ---: |
| Original stacked retries | 12 | 65.019s | 3 |
| Shared request retry policy | 2 | 1.000s | 0 |

The original SDK jitter varies the exact baseline. These are recorded intended
waits, not elapsed end-to-end inference timings.

Three repeated scoped-evidence calls for the first available finding in each
module in January 2026 (`202601`), with sample mode and simulated payments:

| Module | Evidence retrieval seconds (three observations) |
| --- | --- |
| Activation | 0.157, 0.156, 0.156 |
| Commission | 0.043, 0.044, 0.044 |
| Inventory | 0.410, 0.399, 0.445 |
| Payment | 0.404, 0.392, 0.382 |

These use an already-running Python process and local CSV cache; they are not
provider cold/warm cache measurements or a production-query benchmark. The earlier
handoff measured a different composite dossier at 0.511, 0.487, 0.469 seconds;
the differing scopes are not an apples-to-apples speedup comparison.

A controlled loopback HTTP/browser fixture showed first text at 47ms, network
completion at 318ms and rendered completion at 330ms in one run. The fixture
deliberately holds the terminal event back to prove progressive rendering. These
numbers are test-harness timings, not model latency estimates.

## Remaining operational validation

### Historical live provider check — September 29, 2026

After implementation QA, a bounded live check used the configured Anthropic
provider with one synthetic June 2026 commission finding. It made one original
buffered request from commit `87c0dc3` and two successive current structured
requests. No production source or hosted deployment was involved. Only timing
and token metrics were recorded; prompts, generated financial text and credentials
were not included in the measurement output.

| Path | Model calls | First streamed text | Return/completion | Cache creation tokens | Cache read tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original buffered path | 3 | Buffered | 59.992s | Not recorded | Not recorded |
| Structured, first observation | 1 | 2.033s | 22.179s | 8,425 | 0 |
| Structured, repeat observation | 1 | 1.597s | 21.817s | 0 | 8,425 |

Both structured runs received confirmed successful provider completion, with
941 and 869 output tokens respectively, and no retries. Their uncached input was
3,135 tokens each. The original request's final model call produced 2,048 output
tokens, exhausting its configured budget; its stop reason was not captured, so
the buffered return time does not establish answer completeness. The original
three calls consumed 14,593, 17,910 and 30,455 input tokens respectively.

This confirms real provider streaming and prompt-cache reuse. It does not isolate
the latency contribution of caching: output lengths differ and the two completion
times are close. One baseline and two new-path observations on one synthetic
finding are insufficient to estimate typical or tail latency. First text here is
observed at the backend generator, not measured as live browser-visible text.

### Target-environment follow-up

Live-provider evaluations are opt-in. Mocked tests establish validation and
transport behavior, not real-provider semantic accuracy or latency improvements.
With explicit opt-in, run the same representative dealer/finding requests
repeatedly in the target environment using the current validated-publication path. Separate healthy calls, rate-limit failures and timeouts. Record
browser first-visible-text and complete-answer duration independently. Compare
cold requests with subsequent requests showing nonzero `cache_read_input_tokens`;
cache configuration alone does not prove cache hits or a latency reduction.
Check proxy buffering and hosting startup/network effects if browser latency
exceeds server/provider timings. No model substitution, history truncation,
Redis, production writes or new collection APIs are introduced here.
