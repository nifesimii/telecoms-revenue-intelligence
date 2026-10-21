"""Persist fictional upstream evidence; runtime only reads these fixtures.

Existing activation/commission/payment amounts are never changed. Historical profile
and product-master decisions are separate evidence, not edits to current extracts.
"""
import csv
from pathlib import Path

import pandas as pd

from backend import config
from backend.db import queries
from backend.db.investigation_evidence import fingerprint, gap_days


def generate(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    calculation = []
    for period, path in sorted(config.SAMPLE_DATA_PATHS['fbb_comm_dev_act'].items()):
        frame = pd.read_csv(path)
        zeros = frame[frame.commission_rate.fillna(0) == 0]
        for index, row in enumerate(zeros.to_dict('records')):
            dealer = str(row['distributor_code'])
            gap = gap_days(row)
            reason = 'USP_SNAPSHOT_MISS'
            if gap is None or gap < 0:
                reason = ''
            elif gap > 180:
                reason = 'OUTSIDE_6_MONTH_WINDOW'
            elif dealer != '296065':
                if index % 41 == 0:
                    reason = ''  # Deliberately unresolved control; no invented diagnosis.
                elif index % 17 == 0:
                    reason = 'NULL_PROFILE_CLASS'
                elif str(row['product_code']) == '1283281':
                    reason = 'HYNEX_DENOMINATION_SPLIT'
            calculation.append(dict(mon_period=period, dealer_id=dealer, imei=str(row['imei']),
                source_fingerprint=fingerprint(row), evidence_ref=f'CALC-{period}-{index:06d}',
                rule_version='activation-180d-v1', recorded_reason=reason,
                usp_snapshot_period=period, usp_lookup='NO_MATCH' if reason in (
                    'USP_SNAPSHOT_MISS', 'OUTSIDE_6_MONTH_WINDOW') else 'MATCH',
                profile_at_calculation='' if reason == 'NULL_PROFILE_CLASS' else str(row['account_profile_class']),
                profile_lookup='NO_MATCH' if reason == 'NULL_PROFILE_CLASS' else 'MATCH',
                calculation_denomination='Hynex_1' if reason == 'HYNEX_DENOMINATION_SPLIT' else '',
                canonical_denomination='Hynex' if reason == 'HYNEX_DENOMINATION_SPLIT' else '',
                product_mapping_ref=f'MASTER-{period}-1283281' if reason == 'HYNEX_DENOMINATION_SPLIT' else ''))
    payments = []
    source = pd.read_csv(config.PROJECT_ROOT / 'data/samples/payment_simulation.csv', dtype=str).fillna('')
    for index, row in enumerate(source.to_dict('records')):
        owed, paid = float(row['commission_owed']), float(row['amount_paid'])
        balance = round(owed-paid, 2)
        state = ('SETTLED' if balance == 0 else 'EXCESS_REVIEW' if balance < 0 else
                 'DISPUTE_REVIEW' if row['payment_status'] == 'DISPUTED' else 'AWAITING_RELEASE')
        # Evidence of a queue event, distinct from inferring a cause from status.
        payments.append(dict(mon_period=row['report_month'], dealer_id=row['distributor_code'],
            evidence_ref=f'SET-{row["report_month"]}-{index:06d}',
            recorded_owed=f'{owed:.2f}', recorded_paid=f'{paid:.2f}',
            remaining_amount=f'{balance:.2f}', recorded_status=row['payment_status'],
            process_state=state, batch_reference=f'FBB-{row["report_month"]}-B{index % 7 + 1:02d}',
            owner='Finance reconciliation' if state in ('DISPUTE_REVIEW', 'EXCESS_REVIEW') else 'Payment Operations'))
    for name, rows in [('commission_calculation_evidence', calculation), ('settlement_process_evidence', payments)]:
        with (output / f'{name}.csv').open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        print(name, len(rows))


if __name__ == '__main__':
    generate(config.PROJECT_ROOT / 'data/samples')
