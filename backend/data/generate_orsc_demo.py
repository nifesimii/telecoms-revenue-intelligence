"""Generate synthetic March ORSC revenue; never an upstream extract or payable.

Run from the repository root: python -m backend.data.generate_orsc_demo
The February input is preserved. See data/samples/README.md for assumptions.
"""
import csv
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def main() -> None:
    samples = Path(__file__).resolve().parents[2] / 'data' / 'samples'
    with (samples / 'fbb_comm_orsc_sample.csv').open(newline='') as source:
        reader = csv.DictReader(source)
        fields = reader.fieldnames
        rows = list(reader)

    for index, row in enumerate(rows):
        if row['mon_period'] != '202602':
            raise ValueError('Expected February 2026 ORSC input only')
        # Repeatable -10% to +20% changes; retained zeros have no inferred cause.
        factor = Decimal(90 + index % 31) / Decimal(100)
        amount = Decimal(row['data_subscription_amount']) * factor
        row['data_subscription_amount'] = str(amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        row['mon_period'] = '202603'

    target = samples / 'fbb_comm_orsc_202603.csv'
    with target.open('w', newline='') as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f'Generated {len(rows)} synthetic March ORSC records: {target.name}')


if __name__ == '__main__':
    main()
