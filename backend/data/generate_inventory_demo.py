"""Generate fictional shared purchase evidence without modifying source fixtures.

Run: python -m backend.data.generate_inventory_demo --output-dir /tmp/inventory-demo
The same fixed quantities apply to every reporting month; these are not invoices
for a particular month, replenishments, or verified stock balances.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"
PERIODS = tuple(f"2026{month:02d}" for month in range(1, 7))
FIELDS = ("dealer_id", "product_code", "scenario_id", "scenario_label",
          "total_units_purchased")
# dealer, product, June scenario, immutable purchase quantity, June activations.
# Fixed choices: never resize purchases to force a result after fixture drift.
COHORT = (
    ("74050", "1283279", "exact", 379, 379),
    ("296065", "1212360", "exact", 159, 159),
    ("98053", "1283280", "exact", 101, 101),
    ("69031", "1212360", "cushion", 300, 246),
    ("73037", "1186254", "cushion", 180, 152),
    ("74050", "1283281", "cushion", 100, 79),
    ("90032", "1283279", "one_unit_excess", 186, 187),
    ("19958", "1283280", "one_unit_excess", 98, 99),
    ("357063", "1229866", "one_unit_excess", 76, 77),
    ("98052", "1186254", "larger_excess", 200, 244),
    ("88031", "1212360", "larger_excess", 100, 129),
    ("357063", "1283281", "larger_excess", 50, 76),
    ("213044", "1283279", "missing_holdout", None, 208),
    ("205044", "1186254", "missing_holdout", None, 180),
    ("19477", "1212360", "missing_holdout", None, 136),
    ("98052", "1283280", "missing_holdout", None, 199),
)
LABELS = {
    "exact": "Synthetic shared purchase evidence - June exact match",
    "cushion": "Synthetic shared purchase evidence - June purchases exceed activations",
    "one_unit_excess": "Synthetic shared purchase evidence - June one-unit activation excess",
    "larger_excess": "Synthetic shared purchase evidence - June larger activation excess",
    "missing_holdout": "Synthetic demo control - retained missing invoice evidence",
}


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def _outcome(activations: int, purchased: float | None) -> dict:
    gap = None if purchased is None else activations - purchased
    return {
        "activation_count": activations,
        "total_units_purchased": purchased,
        "inventory_gap": gap,
        "gap_pct": None if purchased is None or purchased == 0 else round(gap / purchased * 100, 1),
        "finding_type": ("NO_INVOICE_RECORD" if purchased is None else
                         "CONFIRMED_MISMATCH" if activations > purchased else
                         "WITHIN_ALLOCATION"),
    }


def _summary(counts: Counter, purchases: dict) -> dict:
    outcomes = [_outcome(count, purchases.get(pair)) for pair, count in counts.items()]
    findings = Counter(row["finding_type"] for row in outcomes)
    return {
        "comparison_count": len(outcomes),
        "observed_mismatches": findings["CONFIRMED_MISMATCH"],
        "observed_excess_units": sum(row["inventory_gap"] for row in outcomes
                                     if row["finding_type"] == "CONFIRMED_MISMATCH"),
        "invoice_gaps": findings["NO_INVOICE_RECORD"],
        "within_purchases": findings["WITHIN_ALLOCATION"],
        "exact_matches": sum(row["inventory_gap"] == 0 for row in outcomes),
    }


def generate(output_dir: str | Path = SAMPLES) -> dict:
    """Validate inputs, write only the two demo artifacts, and return the manifest.

    Reads the repository's fixed source fixtures, independent of output_dir.
    No config import, database access, runtime query dependency, or random seed.
    Raises ValueError on cohort collisions, invalid quantities, or fixture drift
    before creating outputs. Source hashes make the input provenance reviewable.
    """
    invoice_path = SAMPLES / "ifs_invoice_history.csv"
    invoices = _read(invoice_path)
    base_pairs = {(r["customer_no"], r["part_no"]) for r in invoices}
    pairs = [(dealer, product) for dealer, product, *_ in COHORT]
    if len(set(pairs)) != len(pairs):
        raise ValueError("Duplicate dealer/product in synthetic cohort")
    for dealer, product, kind, quantity, _ in COHORT:
        if (dealer, product) in base_pairs:
            raise ValueError(f"Existing base invoice evidence for {dealer}/{product}")
        if kind not in LABELS or (quantity is None) != (kind == "missing_holdout"):
            raise ValueError(f"Invalid scenario or missing quantity for {dealer}/{product}")
        if quantity is not None and (
            isinstance(quantity, bool) or not math.isfinite(quantity) or quantity <= 0
        ):
            raise ValueError(f"Purchase quantity must be finite and positive: {dealer}/{product}")

    # Match existing pooled IFS natural-key deduplication for baseline reporting.
    purchases = defaultdict(float)
    dedup = set()
    for row in invoices:
        key = (row["customer_no"], row["part_no"], float(row["implied_units"]),
               row["actual_completion_date"])
        if key not in dedup:
            purchases[key[:2]] += key[2]
            dedup.add(key)
    enriched = dict(purchases)
    enriched.update({(d, p): quantity for d, p, _, quantity, _ in COHORT
                     if quantity is not None})
    counts_by_period, names = {}, {}
    source_paths = [invoice_path]
    for period in PERIODS:
        path = SAMPLES / f"fbb_comm_dev_act_{period}.csv"
        source_paths.append(path)
        rows = [r for r in _read(path) if r["mon_period"] == period]
        counts = Counter((r["distributor_code"], r["product_code"])
                         for r in rows if r["imei"])
        for row in rows:
            names.setdefault((row["distributor_code"], row["product_code"]),
                             (row["distributor_name"], row["product_name"]))
        for pair in pairs:
            if counts[pair] <= 0:
                raise ValueError(f"Cohort pair absent in {period}: {pair}")
        counts_by_period[period] = counts
    for dealer, product, _, _, expected in COHORT:
        if counts_by_period["202606"][(dealer, product)] != expected:
            raise ValueError(f"June activation fixture drift for {dealer}/{product}")

    scenarios, csv_rows = [], []
    for dealer, product, kind, quantity, _ in COHORT:
        pair = (dealer, product)
        scenario_id = f"synthetic_shared_{kind}_{dealer}_{product}"
        csv_rows.append(dict(zip(FIELDS, (dealer, product, scenario_id, LABELS[kind], quantity))))
        scenarios.append({
            "scenario_id": scenario_id, "scenario_label": LABELS[kind],
            "dealer_id": dealer, "dealer_name": names[pair][0],
            "product_code": product, "product_name": names[pair][1],
            "total_units_purchased": quantity,
            "monthly_expectations": {
                period: {"baseline": _outcome(counts[pair], None),
                         "enriched": _outcome(counts[pair], quantity)}
                for period, counts in counts_by_period.items()
            },
        })
    manifest = {
        "schema_version": 1,
        "dataset_id": "inventory_shared_synthetic_v1",
        "provenance": {
            "source": "Fictional purchase evidence for sample-mode demonstration only; not IFS source invoices.",
            "semantics": "Immutable shared dataset: identical purchase quantities apply across all reporting periods using existing pooled comparison semantics.",
            "limitations": "No monthly purchase window, replenishment, stock balance, carryover, alias resolution, or real-world invoice completeness is asserted.",
            "selection": "Fixed named cohort absent from base IFS in all six months; scenarios selected for June comparisons, not representative coverage.",
            "holdouts": "Blank CSV quantities and null manifest quantities retain unknown purchases, gaps, and percentages; they are not zero-quantity invoices.",
            "integration": "Sample-only exact dealer/product join; reject base evidence collisions; apply nonblank quantities only; preserve synthetic provenance in downstream displays and audit evidence.",
            "activation_sources": "January and April-June are existing synthetic extensions; February/March are preserved reference fixtures. This generator changes none of them.",
        },
        "periods": list(PERIODS),
        "cohort_size": len(COHORT),
        "synthetic_purchase_pairs": sum(q is not None for _, _, _, q, _ in COHORT),
        "retained_missing_pairs": sum(q is None for _, _, _, q, _ in COHORT),
        "source_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in source_paths},
        "monthly_outcomes": {
            period: {"baseline": _summary(counts, purchases),
                     "enriched": _summary(counts, enriched)}
            for period, counts in counts_by_period.items()
        },
        "scenarios": scenarios,
    }
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "inventory_demo_scenarios.csv").open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_rows)
    (output / "inventory_demo_manifest.json").write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=SAMPLES)
    args = parser.parse_args()
    result = generate(args.output_dir)
    print(f"Generated {result['cohort_size']} scenarios in {args.output_dir}")
