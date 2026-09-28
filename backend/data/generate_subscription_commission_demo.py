"""Create fictional upstream statement amounts, never an MTN commission formula.

Run: python -m backend.data.generate_subscription_commission_demo
Source revenue and device/dealer attribution are preserved. Amounts below are
arbitrary scenario values capped below source revenue for demo plausibility.
The cap is a fixture consistency guard, never a commission rate or policy.
"""
import csv
import hashlib
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

SAMPLES = Path(__file__).resolve().parents[2] / 'data' / 'samples'
FIELDS = ['mon_period', 'dealer_id', 'imei', 'subscription_commission_ngn',
          'subscription_settled_ngn', 'statement_reference', 'settlement_reference']


def generate_rows(samples: Path = SAMPLES) -> list[dict]:
    revenues = {}
    for path in sorted(samples.glob('fbb_comm_orsc*.csv')):
        with path.open(newline='') as source:
            for row in csv.DictReader(source):
                key = (row['mon_period'], row['distributor_code'], row['imei'])
                revenues[key] = revenues.get(key, Decimal(0)) + Decimal(row['data_subscription_amount'] or '0')
    rows = []
    for period, dealer, imei in sorted(revenues):
        seed = int(hashlib.sha256(f'{period}:{dealer}:{imei}'.encode()).hexdigest()[:8], 16)
        # Arbitrary statement amounts; a revenue cap only keeps the demo plausible.
        # Zero-revenue records use a recorded-zero demo scenario, not an eligibility rule.
        revenue = revenues[(period, dealer, imei)]
        cap = revenue.quantize(Decimal('1') if revenue >= 1 else Decimal('0.01'), rounding=ROUND_DOWN)
        commission = min(Decimal(250 + seed % 1751), max(cap, Decimal(0)))
        scenario = int(hashlib.sha256(f'{period}:{dealer}'.encode()).hexdigest()[:8], 16) % 3
        settled = commission if scenario == 0 else commission / 2 if scenario == 1 else Decimal(0)
        rows.append(dict(zip(FIELDS, [period, dealer, imei, f'{commission:.2f}',
            f'{settled:.2f}', f'DEMO-SUB-{period}-{dealer}',
            f'DEMO-PAY-{period}-{dealer}' if settled else ''])))
    return rows


def main() -> None:
    target = SAMPLES / 'subscription_commission_demo.csv'
    with target.open('w', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator='\n')
        writer.writeheader()
        writer.writerows(generate_rows())


if __name__ == '__main__':
    main()
