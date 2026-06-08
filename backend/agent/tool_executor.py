"""Routes Claude tool calls to queries.py. No Claude API calls here.

The agent loop (``backend/agent/agent.py``) hands each ``tool_use`` block
from Claude to :func:`execute_tool`. This module:

  1. Extracts the tool name and input from the ``tool_use`` block.
  2. Validates the tool name against :data:`backend.db.queries.QUERY_NAMES`.
  3. Calls :func:`backend.db.connection.execute_query` to run the query.
  4. Wraps the resulting DataFrame in a JSON envelope and returns it as a
     ``tool_result`` block ready to send back to Claude.

Errors (unknown tool, missing parameter, query failure) are returned as
``tool_result`` blocks with ``is_error=True`` and a human-readable message —
the agent loop forwards them to Claude so it can recover or apologise.
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

from backend.db import queries
from backend.db.connection import execute_query

# Defensive cap on the number of tool-result rows we hand back to Claude.
# Anthropic's input context window is 200k tokens; very large tool results
# (e.g. get_inventory_comparison returning 4,000+ NO_INVOICE_RECORD rows)
# can blow past that on the next round-trip. The cap kicks in only when a
# tool returns more rows than this — no existing tool returns more than ~1k
# rows in production so existing behaviour is unaffected. Sort order on the
# original query is preserved, so the most-actionable rows are kept.
_TOOL_ROW_CAP = 500


def execute_tool(tool_use: dict[str, Any]) -> dict[str, Any]:
    """Execute one ``tool_use`` block and return a ``tool_result`` block.

    Args:
        tool_use: The dict-shaped ``tool_use`` content block from Claude.
            Expected keys: ``id`` (str), ``name`` (str), ``input`` (dict).
            Extra keys are tolerated.

    Returns:
        A ``tool_result`` content block dict with:
            * ``type``: always ``"tool_result"``
            * ``tool_use_id``: echoes ``tool_use["id"]``
            * ``content``: JSON-stringified envelope on success,
              human-readable error message on failure
            * ``is_error``: present and ``True`` only on failure
    """
    tool_use_id = str(tool_use.get("id", ""))
    tool_name = str(tool_use.get("name", ""))
    tool_input = tool_use.get("input") or {}

    if not isinstance(tool_input, dict):
        return _error_result(
            tool_use_id,
            f"Tool input must be a JSON object, got {type(tool_input).__name__}.",
        )

    if tool_name not in queries.QUERY_NAMES:
        return _error_result(
            tool_use_id,
            (
                f"Unknown tool: {tool_name!r}. "
                f"Valid tools: {queries.QUERY_NAMES}."
            ),
        )

    try:
        df = execute_query(tool_name, tool_input)
    except KeyError as exc:
        return _error_result(
            tool_use_id,
            f"Missing required parameter for {tool_name}: {exc}",
        )
    except Exception as exc:  # noqa: BLE001 — surface any failure to Claude
        return _error_result(
            tool_use_id,
            f"Tool {tool_name!r} failed: {type(exc).__name__}: {exc}",
        )

    return _success_result(tool_use_id, tool_name, tool_input, df)


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------


def _success_result(
    tool_use_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
    df: pd.DataFrame,
) -> dict[str, Any]:
    """Wrap a successful DataFrame result in a tool_result block.

    If the DataFrame has more rows than :data:`_TOOL_ROW_CAP`, only the first
    ``_TOOL_ROW_CAP`` rows (in the query's sort order) are serialised, and
    the envelope includes ``truncated=True`` plus the full ``total_rows``
    count so the agent can reason about coverage.
    """
    total_rows = int(len(df))
    if total_rows > _TOOL_ROW_CAP:
        df_for_wire = df.head(_TOOL_ROW_CAP)
        envelope = {
            "tool": tool_name,
            "parameters": tool_input,
            "row_count": _TOOL_ROW_CAP,
            "total_rows": total_rows,
            "truncated": True,
            "truncation_note": (
                f"Result truncated to the first {_TOOL_ROW_CAP} rows of "
                f"{total_rows} total. Rows are returned in the query's "
                "natural sort order; the most-actionable rows come first."
            ),
            "rows": _df_to_records(df_for_wire),
        }
    else:
        envelope = {
            "tool": tool_name,
            "parameters": tool_input,
            "row_count": total_rows,
            "rows": _df_to_records(df),
        }
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(envelope, ensure_ascii=False),
    }


def _error_result(tool_use_id: str, message: str) -> dict[str, Any]:
    """Wrap an error message in a tool_result block flagged as an error."""
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": message,
        "is_error": True,
    }


def _df_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame to a list of JSON-friendly dicts.

    Round-trips through ``df.to_json`` so numpy ints/floats, NaN, and date
    columns are normalised exactly the way pandas would normalise them for
    network transport. Returns ``[]`` for an empty DataFrame.
    """
    if df.empty:
        return []
    rows_json = df.to_json(
        orient="records",
        date_format="iso",
        default_handler=str,
    )
    return json.loads(rows_json)
