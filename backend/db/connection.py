"""Data layer entry point.

Exposes a single function, ``execute_query(query_name, params)``, that
dispatches to one of two backends depending on the ``USE_SAMPLE_DATA`` flag in
:mod:`backend.config`:

  * sample mode  → call the matching pandas handler in :mod:`backend.db.queries`
  * presto mode → not yet wired up; see ``_run_presto`` below

For this project ``USE_SAMPLE_DATA=true`` is the permanent mode until a Presto
service account is provisioned, so the pandas/CSV path is the only one that is
fully implemented here.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from backend import config
from backend.db import queries


def execute_query(query_name: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    """Run a named query and return the results as a DataFrame.

    Args:
        query_name: One of :data:`backend.db.queries.QUERY_NAMES`.
        params: Mapping of parameter name to value. May be ``None`` for
            queries that take no parameters (currently none).

    Returns:
        A :class:`pandas.DataFrame` matching the documented shape of the
        named query.

    Raises:
        ValueError: If ``query_name`` is unknown.
        NotImplementedError: If ``USE_SAMPLE_DATA`` is false — live Presto
            mode is not wired up yet.
    """
    if query_name not in queries.QUERY_NAMES:
        raise ValueError(
            f"Unknown query name: {query_name!r}. "
            f"Valid names: {queries.QUERY_NAMES}"
        )

    params = params or {}

    if config.USE_SAMPLE_DATA:
        handler = queries.SAMPLE_HANDLERS[query_name]
        return handler(params)

    return _run_presto(query_name, params)


# ---------------------------------------------------------------------------
# Presto / Trino path — STUB
# ---------------------------------------------------------------------------


def _run_presto(query_name: str, params: dict[str, Any]) -> pd.DataFrame:
    """Live Presto execution path.

    TO BE IMPLEMENTED WHEN SERVICE ACCOUNT IS PROVISIONED.

    When wired up this function will:
      * pull ``queries.SQL[query_name]`` (already authored against
        ``hive5.development.*``);
      * convert the DB-API ``%(name)s`` placeholders to Trino's positional
        ``?`` placeholders;
      * open a connection using credentials from :mod:`backend.config`
        (``PRESTO_HOST``, ``PRESTO_PORT``, ``PRESTO_USER``,
        ``PRESTO_PASSWORD``, ``PRESTO_CATALOG``, ``PRESTO_SCHEMA``);
      * execute the prepared statement and return the cursor rows as a
        :class:`pandas.DataFrame` with the same column shape as the matching
        pandas handler in :mod:`backend.db.queries`.

    Until then, calling this function (i.e. setting ``USE_SAMPLE_DATA=false``)
    will raise :class:`NotImplementedError`.
    """
    raise NotImplementedError(
        "Live Presto path is not implemented yet — to be implemented when "
        "the service account is provisioned. Set USE_SAMPLE_DATA=true to "
        "use the pandas/CSV path."
    )
