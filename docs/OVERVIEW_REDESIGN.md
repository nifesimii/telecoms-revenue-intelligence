# Finance Overview redesign

Accepted scope: the September 13 conversation and populated-app review.

- Lead with period-specific owed, settled, outstanding and explicit comparison.
- Count the full finding set and unique dealers; preview/pagination is never a total.
- Rank a bounded dealer queue by severity, outstanding amount, then dealer code.
  Outstanding is a payment-source amount, never summed across findings.
- Search/filter and aggregate before pagination; maximum page size 100.
- Export all period findings; do not label partial results as a complete export.
- Expose unavailable modules, missing invoice evidence and audit-not-run separately.
- Open module/dealer evidence with period preserved. Never run an audit on navigation.
- Remove Overview's eager whole-period dealer evidence and payment record payloads.
- Use query caching, explicit loading/error/empty states, and responsive navigation.
- Keep current read-only sources and existing business classification rules.

Design: MTN yellow accent, white surfaces on a neutral background; financial
headline followed by a primary investigation queue and compact supporting
assurance/audit coverage. No alerts, recalculation, or new production writes.

Verification: public API counts, paging, exports and missing-source cases;
browser journeys for repeated drill-downs, period changes, and small screens.
Review base: 848d92e94e8f0cbc2003d15b32ce189b3671dfdf.

## Verification and review

- Final backend suite: 232 passed, 28 skipped, using sample data.
- Vite production build passes. This JavaScript project has no standalone
  typecheck script; API response models are validated by the HTTP tests.
- Browser checks cover February/March totals and comparison, dealer search,
  repeated Payment Exceptions navigation, exact inventory-subject evidence,
  activation evidence, and returning keyboard focus after closing evidence.
- No horizontal overflow at 320, 768, 1024 and 1440 pixels; mobile workspace
  and period controls remain visible.
- The existing bundle-size warning remains; no dependencies were added.

### Standards review

Independent review identified eager audit fetching, an overly broad activation
evidence destination, and duplicate payment classification. These were resolved
with on-demand subject evidence, relevant activation verification and a shared
classifier. Follow-up caveat filtering and persisted-source labeling were fixed.

### Spec review

Independent review identified filtering after dealer grouping, which could show
an unrelated lead finding. Filtering now precedes grouping, with an inventory/LOW
regression test. APDP success and failure are covered; persisted evidence shows
its own source and date. No outstanding review blockers remain.

Live Presto behavior is not validated by sample-mode checks. The existing broad
Audit Trails workspace remains a whole-period view; Overview evidence and its
single-subject audit destination do not fetch that whole-period collection.
