"""Extend bundled demo fixtures through June without changing February/March.

Run: python -m backend.data.generate_half_year_demo
All new records are synthetic; see data/samples/README.md.
"""
from datetime import datetime
from calendar import monthrange
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import csv

SAMPLES = Path(__file__).resolve().parents[2] / 'data' / 'samples'
# January uses February; later months use March. Volume factors are demo choices.
MONTHS = {'202601': ('202602', 90), '202604': ('202603', 95),
          '202605': ('202603', 105), '202606': ('202603', 110)}


def read(name):
    with (SAMPLES / name).open(newline='') as source:
        reader = csv.DictReader(source)
        return reader.fieldnames, list(reader)


def write(name, fields, rows):
    with (SAMPLES / name).open('w', newline='') as destination:
        writer = csv.DictWriter(destination, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def shift_dates(row, months):
    for field, fmt in [('invoice_date', '%Y-%m-%d'),
                       ('first_activation_date', '%Y%m%d %H:%M:%S'),
                       ('tbl_dt', '%Y%m%d')]:
        if row.get(field):
            date = datetime.strptime(row[field], fmt)
            year, month = divmod(date.year * 12 + date.month - 1 + months, 12)
            month += 1
            row[field] = date.replace(year=year, month=month,
                                      day=min(date.day, monthrange(year, month)[1])).strftime(fmt)


def main():
    for period, (base, volume) in MONTHS.items():
        months = int(period[-2:]) - int(base[-2:])
        fields, rows = read(f'fbb_comm_dev_act_{base}.csv')
        dealers = {}
        for row in rows:
            dealers.setdefault(row['distributor_code'], []).append(row)
        generated = []
        for records in dealers.values():
            # Keep every dealer, product mix and recorded per-device amount.
            count = max(1, round(len(records) * volume / 100))
            for index in range(count):
                row = records[index % len(records)].copy()
                shift_dates(row, months)
                # Unique synthetic device IDs, including duplicated volume rows.
                row['imei'] = f'99{period}{len(generated):07d}'
                row['mon_period'] = period
                generated.append(row)
        write(f'fbb_comm_dev_act_{period}.csv', fields, generated)

        source = 'fbb_comm_orsc_sample.csv' if base == '202602' else f'fbb_comm_orsc_{base}.csv'
        fields, rows = read(source)
        for index, row in enumerate(rows):
            if period == '202601':
                # January must not contain February activation dates.
                shift_dates(row, months)
                row['imei'] = f'98{period}{index:07d}'
            factor = Decimal(volume + index % 11 - 5) / 100
            row['data_subscription_amount'] = str(
                (Decimal(row['data_subscription_amount']) * factor)
                .quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
            row['mon_period'] = period
        write(f'fbb_comm_orsc_{period}.csv', fields, rows)
        print(f'{period}: {len(generated)} activations, {len(rows)} ORSC records')

    # Preserve existing payment rows verbatim and derive only the added months.
    from backend import config
    from backend.data import generate_payment_simulation as payments
    from backend.db.queries import _clear_csv_cache
    config.USE_SAMPLE_DATA = True
    _clear_csv_cache()
    fields, existing = read('payment_simulation.csv')
    existing = [row for row in existing if row['report_month'] not in MONTHS]
    generated = payments.generate(tuple(MONTHS)).fillna('').to_dict(orient='records')
    write('payment_simulation.csv', fields, existing + generated)


if __name__ == '__main__':
    main()
