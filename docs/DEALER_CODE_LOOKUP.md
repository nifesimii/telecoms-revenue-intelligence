# Dealer name to code lookup

Finance can ask Atlas to list distinct dealer codes recorded against a selected
dealer name. The lookup covers activation and subscription revenue records in
the available reporting months, independent of the currently selected month.

## Contract

- `get_dealer_codes` accepts `dealer_name` and optional inclusive `start_period`
  and `end_period` (YYYYMM). Omitted bounds use available source coverage.
- Match the complete name, ignoring letter case and surrounding whitespace.
  Do not merge punctuation, spelling variations, or partial names.
- Return one row per distinct code, all recorded name variants, first and last
  observed months within the search, and the contributing sources.
- Report months searched per source, including for no-match results. A missing
  configured file is an error, not silently omitted evidence.
- Results are deterministically ordered and paginated, at most 100 codes per
  page, with a total count. Atlas must fetch remaining pages to list all codes.
- These are recorded name–code associations, not verified branches or legal
  entities. Observation endpoints do not establish continuity between months.

## Scope and validation

No financial consolidation, reverse lookup, fuzzy matching, branch mapping,
source-data modification, or frontend redesign. Existing sample records already
contain multiple codes for the same name; no artificial mapping is required.

Validate through the public data query and tool executor using small known
fixtures, then exercise the bundled demo data. The live Presto executor remains
unimplemented project-wide; parameterized SQL belongs only in `db/queries.py`.

## Live connection limitation

The existing Presto executor is a stub. Before enabling this tool in live mode,
its adapter must resolve omitted bounds from available source coverage, apply
bounded pagination to the grouped SQL result, and supply the same coverage and
count metadata as sample mode. The authored SQL supplies the association rows;
it is not a complete live implementation of the tool contract.
