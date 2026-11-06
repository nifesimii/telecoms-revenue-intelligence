"""Fictional Partner Commission Account statements. Opening balances, dates and
references are authored fixture values, never derived from monthly totals. Orders,
invoices and collections never reach this module, so they cannot change a statement.

The server holds them so that each partner receives only their own. The rules that
read a statement (missing evidence versus a recorded zero, separate streams) stay
with the view that presents it.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from backend.sales.simulation import PARTNERS, SalesNotFound


def _entry(date: str, reference: str, stream: str, kind: str, amount_minor: int) -> dict:
    return {"date": date, "reference": reference, "stream": stream, "kind": kind, "amount_minor": amount_minor}


def _long_activity() -> list[dict]:
    """110 earnings of NGN 1,000.00 and 10 settlements of NGN 500.00, so paging has to
    span more than the largest page of 100 rows."""
    activity = []
    for index in range(120):
        sequence = f"{index + 1:04d}"
        date = f"2026-05-{index % 31 + 1:02d}"
        if index % 12 == 11:
            activity.append(_entry(date, f"SIM-SET-295083-{sequence}", "activation", "settlement", 50_000))
        else:
            activity.append(_entry(date, f"SIM-COM-295083-{sequence}", "activation", "earning", 100_000))
    return activity


# These reconcile to the same account's recorded sample statement
# (backend/tests/test_partner_commission_fixtures.py), so explanations can stand behind them.
_LINKED = json.loads(Path(__file__).with_name("linked_commission_statements.json").read_text())

# These do not, so they offer no explanation links.
_STANDALONE = [
    {"account_code": "74050", "period": "202605", "opening_minor": 2_000_000, "opening_reference": "SIM-OPEN-74050-202605",
     "subscription_recorded": True, "subscription_revenue_minor": 24_000_000, "activity": [
         _entry("2026-05-12", "SIM-COM-74050-0501", "activation", "earning", 900_000),
         _entry("2026-05-18", "SIM-SET-74050-0501", "activation", "settlement", 750_000),
         _entry("2026-05-25", "SIM-COM-74050-0502", "subscription", "earning", 600_000),
         _entry("2026-05-28", "SIM-SET-74050-0502", "subscription", "settlement", 250_000),
     ]},
    # A recorded zero settlement: evidence of nothing paid, unlike a missing settlement.
    {"account_code": "98052", "period": "202605", "opening_minor": 500_000, "opening_reference": "SIM-OPEN-98052-202605",
     "subscription_recorded": False, "subscription_revenue_minor": None, "activity": [
         _entry("2026-05-14", "SIM-COM-98052-0501", "activation", "earning", 1_200_000),
         _entry("2026-05-30", "SIM-SET-98052-0501", "activation", "settlement", 0),
     ]},
    # No subscription entries: activation alone would be a misleading partial total.
    {"account_code": "98052", "period": "202606", "opening_minor": 1_700_000, "opening_reference": "SIM-OPEN-98052-202606",
     "subscription_recorded": True, "subscription_revenue_minor": None, "activity": [
         _entry("2026-06-10", "SIM-COM-98052-0601", "activation", "earning", 800_000),
         _entry("2026-06-20", "SIM-SET-98052-0601", "activation", "settlement", 300_000),
     ]},
    {"account_code": "205044", "period": "202605", "opening_minor": 1_000_000, "opening_reference": "SIM-OPEN-205044-202605",
     "subscription_recorded": False, "subscription_revenue_minor": None, "activity": [
         _entry("2026-05-16", "SIM-COM-205044-0501", "activation", "earning", 3_000_000),
     ]},
    {"account_code": "295083", "period": "202605", "opening_minor": 100_000, "opening_reference": "SIM-OPEN-295083-202605",
     "subscription_recorded": False, "subscription_revenue_minor": None, "activity": _long_activity()},
]

_STATEMENTS = [{**statement, "linked": True} for statement in _LINKED] + [{**statement, "linked": False} for statement in _STANDALONE]


_PARTNER_CODES = {partner["code"] for partner in PARTNERS}


def statement_for(account_code: str | None, period: str) -> dict | None:
    """A copy, so no caller can change the fixture. None is a missing statement, never a zero one."""
    if account_code not in _PARTNER_CODES:
        raise SalesNotFound
    found = next((statement for statement in _STATEMENTS if statement["account_code"] == account_code and statement["period"] == period), None)
    return copy.deepcopy(found)


def statement_periods(account_code: str) -> list[str]:
    """The months with a statement for this exact account, newest first."""
    return sorted((statement["period"] for statement in _STATEMENTS if statement["account_code"] == account_code), reverse=True)


def own_statement(account_code: str | None, period: str) -> dict | None:
    """Without the link to recorded evidence: a partner has no explanation workspaces to follow."""
    found = statement_for(account_code, period)
    if found is not None:
        del found["linked"]
    return found
