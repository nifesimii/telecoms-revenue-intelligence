# ORSC demo data

`fbb_comm_orsc_sample.csv` is the existing February 2026 reference sample.
`fbb_comm_orsc_202603.csv` is **synthetic March 2026 demo data**, not a March
source extract, validated revenue or a commission-payable figure.

The March fixture retains February's 200 device records, 157 dealer accounts,
dealer identities, products, invoice dates and first activation dates. Continued
subscription activity in March is a demo assumption. Historical invoice and
activation dates are deliberately unchanged.

For input row index `i` (starting at zero), the fictional March amount equals
the February amount multiplied by `(90 + i % 31) / 100`, rounded half-up to two
decimal places. This creates repeatable increases and decreases for comparison.
The 69 zero amounts remain zero; no business root cause is asserted for them.
These factors are fixture-generation choices, not commission rules.

Regenerate from the repository root:

```sh
python -m backend.data.generate_orsc_demo
```

The sample-mode configuration loads each month separately. Commission workspace
summary, detail and CSV export identify March ORSC as synthetic. February remains
unchanged; an absent month still has no source records. Live Presto reads are
unaffected. Restart an already-running backend after changing bundled fixtures
because sample CSVs are cached in memory.
