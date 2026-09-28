"""Offline illustrative policy generator. Runtime reads its recorded JSON only.

Run: python -m backend.data.generate_subscription_demo
Dates are calendar dates, with no clock/time-zone dependency. A PAID event
qualifies in [first activation, its 12-calendar-month anniversary); Feb 29
anniversaries clamp to Feb 28. Renewals never reset that original date. The
NGN 5,000 threshold is applied to each device's total qualifying monthly
revenue; 5% applies to the entire qualifying amount, rounded half-up to kobo.
All PAID monthly revenue is recorded, including purchases outside eligibility.
The due date is the final calendar day of the following month. Payment state
uses only supplied settlement evidence at fixed 2026-07-15, never today's date.
"""
import calendar
import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

POLICY_LABEL = 'Illustrative subscription commission policy—not confirmed MTN terms.'
EVIDENCE_AS_OF = '2026-07-15'
PERIODS = tuple(f'2026{month:02d}' for month in range(1, 7))
BOUNDARY = ('PAID purchase date >= first activation and < its 12-calendar-month '
            'anniversary; Feb 29 anniversary clamps to Feb 28. Renewals do not restart eligibility.')


def money(value):
    return float(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def calculate_record(*, mon_period, first_activation_date, purchases, dealer_expectation_ngn):
    """Produce a recorded policy example; only the offline generator calls this."""
    activation = date.fromisoformat(first_activation_date) if first_activation_date else None
    anniversary = (activation.replace(year=activation.year + 1,
                       day=min(activation.day, calendar.monthrange(activation.year + 1, activation.month)[1]))
                   if activation else None)
    paid = ([p for p in purchases if p['status'] == 'PAID'
             and p['date'].replace('-', '')[:6] == mon_period] if purchases is not None else None)
    amounts_known = paid is not None and all(p['amount_ngn'] is not None for p in paid)
    revenue = sum(Decimal(str(p['amount_ngn'])) for p in paid) if amounts_known else None
    qualifying = ([p for p in paid if activation <= date.fromisoformat(p['date']) < anniversary]
                  if activation and paid is not None else None)
    eligible = (sum(Decimal(str(p['amount_ngn'])) for p in qualifying)
                if qualifying is not None and amounts_known else None)
    reason = ('unknown_evidence' if eligible is None else 'eligible' if eligible >= 5000 else 'below_minimum')
    if eligible is not None and not qualifying and paid:
        reason = 'expired_eligibility'
    if paid == []:
        reason = 'no_paid_subscription'
    commission = (None if reason == 'unknown_evidence' else
                  money(eligible * Decimal('.05')) if reason == 'eligible' else 0.0)
    return {'mon_period': mon_period, 'first_activation_date': first_activation_date,
            'eligibility_end_exclusive': anniversary.isoformat() if anniversary else None, 'purchases': purchases or [],
            'paid_subscription_count': len(paid) if paid is not None else None,
            'recorded_subscription_revenue_ngn': money(revenue) if revenue is not None else None,
            'eligible_revenue_ngn': None if commission is None else money(eligible) if reason == 'eligible' else 0.0,
            'qualifying_revenue_ngn': money(eligible) if eligible is not None else None,
            'simulated_commission_ngn': commission, 'dealer_expectation_ngn': dealer_expectation_ngn,
            'variance_ngn': (money(Decimal(str(commission)) - Decimal(str(dealer_expectation_ngn)))
                             if commission is not None and dealer_expectation_ngn is not None else None),
            'reason': reason}


def paid_history(scenario, period):
    """One coherent fictional device history shared by every monthly snapshot.

    November/December are supplied historical controls. Missing-history devices
    have unknown pre-January activity; known reporting months progressively fill
    that gap. Renewal-gap devices last renewed in April, so May/June inactivity
    alone does not meet three consecutive months. Unknown activity stays unknown.
    """
    if scenario == 'unknown_activity':
        return None
    if scenario == 'missing_history':
        return None if period < '202601' else False
    if scenario == 'churn_context':
        return False
    if scenario == 'no_renewal':
        return period in {'202511', '202512', '202601', '202603', '202604'}
    return True


def generate_records(mon_period):
    """Return deterministic fictional evidence for one month (no source fixtures)."""
    if mon_period not in PERIODS:
        raise ValueError('Demo period unavailable')
    month = date(int(mon_period[:4]), int(mon_period[4:]), 1)
    next_month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    due = next_month.replace(day=calendar.monthrange(next_month.year, next_month.month)[1])
    scenarios = [
        ('eligible', 10000, 500, '2025-10-01', 'paid', [True, True, True]),
        ('threshold', 5000, 250, '2025-10-01', 'paid', [True, True, True]),
        ('below_minimum', 4000, 200, '2025-10-01', 'none', [True, True, True]),
        ('no_renewal', 0, 500, '2025-10-01', 'none', [True, True, False]),
        ('expired', 15000, 750, '2024-12-01', 'none', [True, True, True]),
        ('overdue', 12000, 600, '2025-10-01', 'unpaid', [True, True, True]),
        ('unknown_payment', 8000, 400, '2025-10-01', 'unknown', [True, True, True]),
        ('churn_context', 0, 500, '2025-10-01', 'none', [False, False, False]),
        ('missing_history', 0, 500, '2025-10-01', 'none', [None, None, False]),
        ('unknown_activity', None, None, '2025-10-01', 'unknown', [None, None, None]),
    ]
    explanations = {
        'eligible': 'Paid revenue qualifies; recorded commission agrees with the supplied dealer expectation.',
        'threshold': 'Exactly NGN 5,000.00 on this device qualifies; all qualifying revenue earns the illustrative rate.',
        'below_minimum': 'Dealer expected commission on NGN 4,000.00; this device is below the monthly minimum.',
        'no_renewal': 'Dealer expected a renewal; supplied monthly activity shows no paid subscription. This is not proof of churn.',
        'expired': 'Dealer expected commission on a renewal after the original eligibility anniversary. Renewals do not restart it.',
        'overdue': 'Earnings match expectation; supplied settlement evidence shows no payment as of the evidence date. Due date determines overdue versus not yet due.',
        'unknown_payment': 'Earnings match expectation; subscription settlement evidence is missing, so payment cannot be established.',
        'churn_context': 'Three complete consecutive months show no paid subscriptions. Churn is contextual; exclusion is no paid subscription this month.',
        'missing_history': 'No paid subscription this month. Prior history is incomplete, so churn is unknown.',
        'unknown_activity': 'Monthly activity evidence is missing. Revenue, eligibility result, earnings, expectation and payment amounts remain unknown.',
    }
    records = []
    for index, (scenario, amount, expectation, activated, settlement, history) in enumerate(scenarios):
        if scenario == 'no_renewal' and paid_history(scenario, mon_period):
            amount = 10000
        purchases = ([{'date': month.replace(day=10).isoformat(), 'status': 'PAID', 'amount_ngn': amount}]
                     if amount else [])
        if scenario == 'no_renewal' and not amount:
            purchases = [{'date': month.replace(day=10).isoformat(), 'status': 'FAILED', 'amount_ngn': 10000}]
        row = calculate_record(mon_period=mon_period, first_activation_date=activated,
                               purchases=purchases, dealer_expectation_ngn=expectation or 0)
        if amount is None:
            for key in ('paid_subscription_count', 'recorded_subscription_revenue_ngn',
                        'eligible_revenue_ngn', 'qualifying_revenue_ngn', 'simulated_commission_ngn',
                        'dealer_expectation_ngn', 'variance_ngn'):
                row[key] = None
            row['reason'] = 'unknown_evidence'
        commission = row['simulated_commission_ngn']
        paid = commission if settlement == 'paid' else (None if settlement == 'unknown' else 0.0)
        outstanding = money(commission - paid) if commission is not None and paid is not None else None
        status = ('unknown' if outstanding is None else 'not_applicable' if commission == 0
                  else 'paid' if outstanding == 0 else 'overdue' if due.isoformat() < EVIDENCE_AS_OF
                  else 'not_yet_due')
        history_rows = []
        for shift in (-2, -1, 0):
            month_index = month.year * 12 + month.month - 1 + shift
            history_period = f'{month_index // 12}{month_index % 12 + 1:02d}'
            history_rows.append({'mon_period': history_period,
                                 'has_paid_subscription': paid_history(scenario, history_period)})
        history = [h['has_paid_subscription'] for h in history_rows]
        # Pair threshold/below-minimum to prove the minimum is per device,
        # and pair missing history/churn to expose mixed evidence in one account.
        dealer_index = {0: 1, 1: 2, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 7, 9: 8}[index]
        names = ['Renewal Partners', 'Threshold Partners', 'Renewal Gap Partners', 'Expired Window Partners',
                 'Settlement Review Partners', 'Missing Payment Partners', 'History Review Partners', 'Evidence Gap Partners']
        records.append({**row, 'scenario': scenario, 'dealer_id': f'SYN-SUB-{dealer_index:03d}',
            'dealer_name': 'Synthetic ' + names[dealer_index - 1],
            'account_profile_class': None if scenario == 'unknown_activity' else 'FIXED BROADBAND',
            'imei': f'99000000000{index:04d}', 'product_name': 'Synthetic FBB Router',
            'selling_dealer_id': f'SYN-SUB-{dealer_index:03d}',
            'activity_evidence_complete': amount is not None,
            'eligibility_status': ('unknown' if amount is None else 'expired' if scenario == 'expired' else 'within_window'),
            'paid_subscription_dates': [p['date'] for p in purchases if p['status'] == 'PAID'] if amount is not None else None,
            'history': history_rows, 'history_complete': all(v is not None for v in history),
            'churn_indicator': None if any(v is None for v in history) else not any(history),
            'due_date': due.isoformat() if commission is not None and commission > 0 else None,
            'payment_status': status, 'amount_paid_ngn': paid, 'outstanding_ngn': outstanding,
            'payment_date': month.replace(day=20).isoformat() if settlement == 'paid' else None,
            'payment_evidence_reference': None if settlement == 'unknown' else f'SYN-SUB-SETTLEMENT-{mon_period}-{index:02d}',
            'expectation_reference': None if expectation is None else f'SYN-SUB-EXPECTATION-{mon_period}-{index:02d}',
            'variance_explanation': (
                'A paid renewal is recorded this month and the illustrative earnings match expectation.'
                if scenario == 'no_renewal' and amount else
                'Three supplied consecutive months show no paid subscriptions. Churn is contextual only.'
                if scenario == 'missing_history' and all(v is not None for v in history) else explanations[scenario]),
            'source': 'Synthetic subscription commission fixtures', 'synthetic': True,
            'policy_label': POLICY_LABEL, 'evidence_as_of': EVIDENCE_AS_OF,
            'eligibility_boundary': BOUNDARY})
    return records


def main():
    directory = Path(__file__).resolve().parents[2] / 'data' / 'samples'
    for period in PERIODS:
        payload = {'policy_label': POLICY_LABEL, 'synthetic': True, 'evidence_as_of': EVIDENCE_AS_OF,
                   'eligibility_boundary': BOUNDARY, 'mon_period': period, 'records': generate_records(period)}
        (directory / f'subscription_commission_demo_{period}.json').write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
