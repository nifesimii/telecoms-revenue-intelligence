"""Regression tests for the Render APDP startup bootstrap."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import patch

from backend import main


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql):
        self.connection.statement_started = True
        self.connection.statements.append(sql)
        if "apdp_schema_repair" in sql or "ALTER TABLE normalized.transactions" in sql:
            self.connection.view_exists = True
        elif "to_regclass('normalized.transactions')" in sql:
            self.result = (True,)
        elif "to_regclass('normalized.partner_settlements')" in sql:
            self.result = (self.connection.view_exists,)
        elif "COUNT(*) FROM normalized.transactions" in sql:
            self.result = (self.connection.row_count,)

    def fetchone(self):
        return self.result


class _Connection:
    def __init__(self, *, row_count=12, view_exists=False):
        self.row_count = row_count
        self.view_exists = view_exists
        self.statements = []
        self._autocommit = False
        self.statement_started = False
        self.closed = False

    @property
    def autocommit(self):
        return self._autocommit

    @autocommit.setter
    def autocommit(self, value):
        # Mirror psycopg2: session characteristics cannot be changed once a
        # transaction has begun. This catches the Render startup regression.
        if value and self.statement_started:
            raise RuntimeError("set_session cannot be used inside a transaction")
        self._autocommit = value

    def cursor(self):
        return _Cursor(self)

    def close(self):
        self.closed = True


def test_bootstrap_repairs_missing_settlement_view_without_reseeding():
    connection = _Connection(row_count=12, view_exists=False)
    fake_psycopg2 = SimpleNamespace(connect=lambda **_kwargs: connection)

    with (
        patch.object(main.config, "PAYMENT_SOURCE", "apdp"),
        patch.dict(sys.modules, {"psycopg2": fake_psycopg2}),
    ):
        main._seed_apdp_if_empty()

    assert connection.view_exists is True
    assert connection.autocommit is True
    assert connection.closed is True
    assert any(
        "CREATE OR REPLACE VIEW normalized.partner_settlements" in statement
        for statement in connection.statements
    )
    assert not any(
        "DROP TABLE IF EXISTS normalized.transactions" in statement
        for statement in connection.statements
    )


def test_bootstrap_skips_complete_apdp_schema():
    connection = _Connection(row_count=12, view_exists=True)
    fake_psycopg2 = SimpleNamespace(connect=lambda **_kwargs: connection)

    with (
        patch.object(main.config, "PAYMENT_SOURCE", "apdp"),
        patch.dict(sys.modules, {"psycopg2": fake_psycopg2}),
    ):
        main._seed_apdp_if_empty()

    assert connection.autocommit is True
    assert connection.closed is True
    assert not any(
        "ALTER TABLE normalized.transactions" in statement
        for statement in connection.statements
    )
