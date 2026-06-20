"""Routes Claude tool calls to the right backend. No Claude API calls here.

Two routing paths:

  * ``QUERY tools`` — names listed in
    :data:`backend.db.queries.QUERY_NAMES`. The executor calls
    :func:`backend.db.connection.execute_query` and wraps the resulting
    DataFrame in a JSON envelope.

  * ``DIRECT tools`` — names listed in :data:`_DIRECT_HANDLERS`. The executor
    invokes the registered Python handler directly and returns its
    ``tool_result`` block as-is. Used for L2 lookups (e.g.
    ``get_kb_section``) that don't go through the SQL/pandas layer.

Errors (unknown tool, missing parameter, query failure) are returned as
``tool_result`` blocks with ``is_error=True`` and a human-readable message —
the agent loop forwards them to Claude so it can recover or apologise.
"""
from __future__ import annotations

import json
from typing import Any, Callable

import pandas as pd

from backend.agent import prompts
from backend.db import queries
from backend.db.composite import assemble_dealer_full_context
from backend.db.connection import execute_query
from backend.db.triage import TRIAGE_HANDLERS

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

    # Direct handlers (L2 KB lookup, etc.) bypass the SQL/pandas layer.
    if tool_name in _DIRECT_HANDLERS:
        try:
            return _DIRECT_HANDLERS[tool_name](tool_use_id, tool_input)
        except Exception as exc:  # noqa: BLE001 — surface any failure to Claude
            return _error_result(
                tool_use_id,
                f"Tool {tool_name!r} failed: {type(exc).__name__}: {exc}",
            )

    if tool_name not in queries.QUERY_NAMES:
        valid_query = list(queries.QUERY_NAMES)
        valid_direct = list(_DIRECT_HANDLERS.keys())
        return _error_result(
            tool_use_id,
            (
                f"Unknown tool: {tool_name!r}. "
                f"Valid tools: {valid_query + valid_direct}."
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
# Direct handlers — non-query tools that bypass the SQL layer entirely
# ---------------------------------------------------------------------------


def _handle_get_kb_section(
    tool_use_id: str, tool_input: dict[str, Any]
) -> dict[str, Any]:
    """L2 KB lookup. Returns the requested addendum's markdown verbatim."""
    section = tool_input.get("section")
    if not section or not isinstance(section, str):
        valid = sorted(prompts.ADDENDA_REGISTRY.keys())
        return _error_result(
            tool_use_id,
            (
                "get_kb_section requires a 'section' string parameter. "
                f"Valid sections: {valid}."
            ),
        )

    try:
        content = prompts.get_kb_section(section)
    except KeyError:
        valid = sorted(prompts.ADDENDA_REGISTRY.keys())
        return _error_result(
            tool_use_id,
            (
                f"Unknown KB section: {section!r}. "
                f"Valid sections: {valid}."
            ),
        )
    except FileNotFoundError as exc:
        return _error_result(
            tool_use_id,
            f"KB addendum file missing on disk: {exc}",
        )

    envelope = {
        "tool": "get_kb_section",
        "section": section,
        "description": str(
            prompts.ADDENDA_REGISTRY[section].get("description", "")
        ),
        "content_chars": len(content),
        "content": content,
    }
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(envelope, ensure_ascii=False),
    }


def _handle_get_dealer_full_context(
    tool_use_id: str, tool_input: dict[str, Any]
) -> dict[str, Any]:
    """L1 composite — one call returns the full dealer dossier across Phases 1-4."""
    distributor_code = tool_input.get("distributor_code")
    mon_period = tool_input.get("mon_period")

    if not distributor_code or not isinstance(distributor_code, (str, int)):
        return _error_result(
            tool_use_id,
            "get_dealer_full_context requires a 'distributor_code' parameter.",
        )
    if not mon_period or not isinstance(mon_period, str):
        return _error_result(
            tool_use_id,
            "get_dealer_full_context requires a 'mon_period' string parameter "
            "in YYYYMM format.",
        )

    try:
        dossier = assemble_dealer_full_context(
            str(distributor_code), str(mon_period)
        )
    except Exception as exc:  # noqa: BLE001 — surface to Claude
        return _error_result(
            tool_use_id,
            f"get_dealer_full_context failed: {type(exc).__name__}: {exc}",
        )

    envelope: dict[str, Any] = {
        "tool": "get_dealer_full_context",
        "parameters": {
            "distributor_code": str(distributor_code),
            "mon_period": str(mon_period),
        },
        **dossier,
        "drill_down_hint": (
            "This is the dealer's full Phase 1-4 dossier in one envelope. "
            "Lead the response with the dealer name + period, then the "
            "headline (commission, qualification rate, payment status). "
            "If there are inventory.confirmed_mismatches > 0 or "
            "activation_exceptions, present those next — they explain why "
            "payment is DISPUTED / PARTIALLY_PAID. Always disclose SIMULATED "
            "data when referencing payment fields. For prior-month "
            "comparison call get_month_on_month_variance separately."
        ),
    }

    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(envelope, ensure_ascii=False),
    }


# Registry: tool name -> (tool_use_id, tool_input) -> tool_result dict
_DIRECT_HANDLERS: dict[
    str, Callable[[str, dict[str, Any]], dict[str, Any]]
] = {
    "get_kb_section": _handle_get_kb_section,
    "get_dealer_full_context": _handle_get_dealer_full_context,
}


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

    Two envelope shapes:

      1. **Triaged** — if the tool has a registered triage handler in
         :data:`backend.db.triage.TRIAGE_HANDLERS`, the envelope contains
         ``headline`` + ``must_review`` (≤10 rows) + ``worth_review`` (≤10 rows)
         plus the full ``row_count`` and an optional ``drill_down_hint``. The
         full row dump is replaced — the agent gets the answer first, not the
         haystack.

      2. **Raw rows** — fallback for tools without a triage handler. Same shape
         as before: ``row_count`` + ``rows`` (capped at ``_TOOL_ROW_CAP`` with
         ``truncated`` / ``total_rows`` indicators if the cap kicks in).
    """
    total_rows = int(len(df))

    triage_fn = TRIAGE_HANDLERS.get(tool_name)
    if triage_fn is not None:
        triage = triage_fn(df, tool_input)
        envelope: dict[str, Any] = {
            "tool": tool_name,
            "parameters": tool_input,
            "row_count": total_rows,
            "envelope_shape": "triaged",
            "headline": triage.get("headline", {}),
            "must_review": triage.get("must_review", []),
            "worth_review": triage.get("worth_review", []),
        }
        if "drill_down_hint" in triage:
            envelope["drill_down_hint"] = triage["drill_down_hint"]
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": json.dumps(envelope, ensure_ascii=False),
        }

    # Untriaged fallback — same shape as before.
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
