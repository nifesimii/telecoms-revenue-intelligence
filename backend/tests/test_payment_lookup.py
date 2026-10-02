"""The audit payment lookup must read the frame the query layer actually returns."""
from backend import config
from backend.audit.payment_data import extract_payment
from backend.db.connection import execute_query
from backend.db.dealer_statement import compose_dealer_statement


def test_simulated_payment_frame_is_found_by_dealer_code(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)
    frame = execute_query("get_payment_summary", {"mon_period": "202606"})
    paid, found, status = extract_payment(frame, "296065", "simulated")
    assert (round(paid, 2), found, status) == (396434.72, True, "DISPUTED")


def test_statement_payment_matches_the_payments_screen(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)
    monkeypatch.setattr(config, "PAYMENT_SOURCE", "simulated")
    payment = compose_dealer_statement("296065", "202606")["payment"]
    assert payment["payment_found"] is True
    assert round(payment["amount_paid_ngn"], 2) == 396434.72
