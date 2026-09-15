# Fictional dealer names

The bundled activation, ORSC, payment and invoice CSVs use randomly assigned
fictional business names. Assignments are fixed in the files, so names remain
stable across restarts, periods, searches, statements, exports and agent tools.
Accounts linked by a shared name or account code share one fictional name;
account codes still distinguish separate accounts. Blank source names remain blank.

`data/samples/dealer_aliases.json` contains only account codes and fictional
names. It supports masking names in older saved audit evidence when
`USE_SAMPLE_DATA=true`, including name references in evidence text. Masking
happens on read; saved audit records are not rewritten. Live-mode audit reads
retain their recorded names.

Restart the backend after updating the CSVs to clear the in-process data cache.
Reload the browser and start a new chat before presenting. Existing chat messages,
previously downloaded reports, slide decks and Git history are not rewritten.
A hosted demo must receive this change through its normal deployment process.

This change replaces dealer names only. Account codes, device identifiers,
financial figures, dates, products and other evidence remain unchanged; the
result is not a fully anonymized dataset. Future sample imports must use the
same aliases (and assign fictional names to new accounts) before being shared.
