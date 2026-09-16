"""Public report terminology must not change internal stream identifiers or amounts."""
import csv
import io

from backend.api.commission_routes import export_accounts


def test_subscription_export_uses_public_name_and_preserves_revenue():
    data = {'stream': 'orsc', 'mon_period': '202603',
            'source': 'Sample CSVs · synthetic March 2026 ORSC demo data',
            'items': [{'dealer_id': 'demo', 'amount_ngn': 123.45}]}
    response = export_accounts(data)
    row = next(csv.DictReader(io.StringIO(response.body.decode())))
    assert row['stream'] == 'Subscription commission'
    assert 'ORSC' not in row['source']
    assert 'synthetic' in row['source']
    assert row['amount_ngn'] == '123.45'
    assert row['amount_basis'] == 'Recorded subscription revenue; not confirmed commission payable'
    assert 'orsc' not in response.headers['content-disposition']
    assert data['stream'] == 'orsc'


def test_activation_export_retains_existing_stream():
    response = export_accounts({'stream': 'activation', 'mon_period': '202603',
                                'items': [{'dealer_id': 'demo', 'amount_ngn': 50}]})
    row = next(csv.DictReader(io.StringIO(response.body.decode())))
    assert row['stream'] == 'activation'
    assert row['amount_ngn'] == '50'
