# Explain Findings latency

The September 29 implementation removes model-selected evidence retrieval from
the Overview Explain Findings path, streams the answer, and bounds provider
failure recovery. General questions retain the existing tool loop and model.

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

- `{"type":"text","text":"..."}`: answer text only.
- `{"type":"complete","response":"...","tools_called":[],"raw_data":{},"error":null}`:
  final answer with the existing chat metadata.
- `{"type":"error","error":"deadline_exceeded","message":"..."}`:
  sanitized failure; never followed by successful completion.

Other failure codes are `invalid_evidence` and `explanation_failed`. Invalid
request schemas return HTTP 422 before streaming. Clients must treat EOF without
completion as interrupted, retain any partial text as incomplete, and exclude
incomplete answers from subsequent model history. No retry replays a stream
after its first answer text. Disconnects cancel provider work, including waits
before the first token. A read already running in a worker thread may finish
after the waiting request is cancelled; cooperative checks prevent the next
evidence operation from starting.

## Provider policy and observation

The model remains `claude-sonnet-4-5`, with the existing 2048-token output limit.
The explanation prompt requests a concise headline, supporting evidence,
uncertainty and next action. Truncated streamed generations fail explicitly;
completion requires the provider's terminal event and a successful stop reason.
The unchanged full core KB receives an ephemeral provider cache breakpoint.
With tool-enabled general chat, the preceding stable tool definitions are also
inside that prefix. Caching the local Python prompt string alone would not do
this. See the provider's [prompt-caching documentation](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
and [streaming documentation](https://platform.claude.com/docs/en/build-with-claude/streaming).

The SDK has `max_retries=0`. Application recovery allows one retry per request,
honors provider Retry-After guidance, and rejects waits exceeding the remaining
90-second deadline. HTTP timeouts are connect 5s, read 30s, write 10s, pool 5s.
These limits bound failures; they are not a claim of faster healthy inference.

Inference logs carry an opaque request ID and contain timing/count/status fields,
not questions, dealer identities, financial records or provider exception bodies.
They report model-call duration/count, evidence/tool duration, retry waits/count,
first provider text (streaming), buffered answer readiness, overall duration and
input/output/cache token counts. Existing
HTTP middleware timing measures response setup; use inference completion events
for streamed full duration. Provider-first-text timing is distinct from browser
render timing. The browser keeps local performance entries with opaque request
IDs for first rendered text, network completion and rendered completion. A
rendered-completion measurement can include time spent away from the thread;
network completion is recorded independently. See `frontend/tests/README.md`.

## Local measurements

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

Run the same representative dealer/finding requests repeatedly in the target
environment. Separate healthy calls, rate-limit failures and timeouts. Record
browser first-visible-text and complete-answer duration independently. Compare
cold requests with subsequent requests showing nonzero `cache_read_input_tokens`;
cache configuration alone does not prove cache hits or a latency reduction.
Check proxy buffering and hosting startup/network effects if browser latency
exceeds server/provider timings. No model substitution, history truncation,
Redis, production writes or new collection APIs are introduced here.
