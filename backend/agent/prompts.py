"""System prompt builder.

Reads ``backend/knowledge_base/fbb_commission_kb.md`` once at module import
and injects the entire contents verbatim into the system prompt.

Phase-2-of-the-platform housekeeping (the "vertical agents" rework): the KB
is now an L1 *core* file kept as small as we can manage. Reference material
that the agent rarely needs inline — table schemas, calculation SQL,
reconciliation anchors, documents inventory — has been moved to *addenda*
under ``backend/knowledge_base/addenda/``. The agent fetches them on demand
via the ``get_kb_section`` tool, which delegates to :func:`get_kb_section`
defined below.

This keeps every system prompt smaller, which directly relieves the
per-minute token-rate budget the agent burns through on cold runs.

Exports:
    * ``KB_PATH``             — path to the core (L1) KB file.
    * ``KB_CONTENT``          — raw markdown of the core KB.
    * ``ADDENDA_DIR``         — directory holding addendum files.
    * ``ADDENDA_REGISTRY``    — ``name -> {path, description}`` for each addendum.
    * ``get_kb_section(name)``— fetch an addendum's text; KeyError on unknown.
    * ``build_system_prompt()`` — assemble the full system prompt.
    * ``SYSTEM_PROMPT``       — pre-built prompt (computed at import time).
    * ``get_system_prompt()`` — alias returning ``SYSTEM_PROMPT``.
"""
from __future__ import annotations

from pathlib import Path

# backend/agent/prompts.py -> backend/knowledge_base/fbb_commission_kb.md
KB_PATH: Path = (
    Path(__file__).resolve().parent.parent
    / "knowledge_base"
    / "fbb_commission_kb.md"
)

# backend/agent/prompts.py -> backend/knowledge_base/addenda/
ADDENDA_DIR: Path = (
    Path(__file__).resolve().parent.parent / "knowledge_base" / "addenda"
)


def _load_kb() -> str:
    """Read the core KB file as UTF-8 text. Raises FileNotFoundError if missing."""
    if not KB_PATH.exists():
        raise FileNotFoundError(
            f"FBB commission KB not found at {KB_PATH}. "
            "Ensure backend/knowledge_base/fbb_commission_kb.md exists."
        )
    return KB_PATH.read_text(encoding="utf-8")


KB_CONTENT: str = _load_kb()


# ---------------------------------------------------------------------------
# Addenda registry (L2)
# ---------------------------------------------------------------------------
#
# Each entry maps a stable, public ``name`` (passed by the agent as the
# ``section`` parameter on ``get_kb_section``) to the path of the addendum
# file plus a one-line description used in tool error messages and the
# system-prompt signpost.

ADDENDA_REGISTRY: dict[str, dict[str, str | Path]] = {
    "data_architecture": {
        "path": ADDENDA_DIR / "data_architecture.md",
        "description": "Source-system inventory + development schema layout",
    },
    "table_schemas": {
        "path": ADDENDA_DIR / "table_schemas.md",
        "description": "Column-level field definitions for dev_act / ORSC / USP",
    },
    "calculation_logic": {
        "path": ADDENDA_DIR / "calculation_logic.md",
        "description": "Pseudo-SQL for the commission calculation pipeline",
    },
    "ftth_subscriptions_query": {
        "path": ADDENDA_DIR / "ftth_subscriptions_query.md",
        "description": "FBB / FIBRENET subscription revenue CDR query",
    },
    "reconciliation_reference": {
        "path": ADDENDA_DIR / "reconciliation_reference.md",
        "description": "Comparison anchors Finance uses to validate the report",
    },
    "documents_inventory": {
        "path": ADDENDA_DIR / "documents_inventory.md",
        "description": "Underpinning policy / spec / sample documents",
    },
    "gaps_and_missing": {
        "path": ADDENDA_DIR / "gaps_and_missing.md",
        "description": "Known gaps in the KB worth flagging to users",
    },
}


def get_kb_section(name: str) -> str:
    """Return the markdown body of an addendum by registry name.

    Args:
        name: a key in :data:`ADDENDA_REGISTRY`.

    Returns:
        UTF-8 text of the addendum file.

    Raises:
        KeyError: if ``name`` is not in the registry.
        FileNotFoundError: if the registered file is missing on disk.
    """
    if name not in ADDENDA_REGISTRY:
        valid = sorted(ADDENDA_REGISTRY.keys())
        raise KeyError(
            f"Unknown KB section {name!r}. Valid sections: {valid}"
        )
    path = ADDENDA_REGISTRY[name]["path"]
    assert isinstance(path, Path)  # narrow for the type checker
    if not path.exists():
        raise FileNotFoundError(
            f"Addendum file missing on disk: {path} (registered as {name!r})"
        )
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Static prompt sections
# ---------------------------------------------------------------------------

_ROLE = """\
# Role

You are the FBB Trade Partner Intelligence assistant for MTN Nigeria. \
You help Finance and Revenue Assurance answer Fixed Broadband trade partner \
commission questions using a fixed set of query tools and the knowledge \
base below. You explain, validate, and investigate commissions so disputes \
can be resolved with evidence.\
"""

_USERS = """\
# Who you're talking to

You will be speaking to two kinds of internal users. Recognise which one is \
asking and shape the response accordingly.

- **Finance** — asks dealer aggregate questions and monthly summaries. They \
  want to know what MTN owes each dealer. Typical questions: "Summarise \
  dealer commissions for [month]", "What is the ORSC summary for [month]?", \
  "Who are the top dealers by commission this month?".

- **Revenue Assurance** — investigates anomalies and variances. They want \
  root-cause explanations grounded in the KB. Typical questions: "Why did \
  Dealer X's commission change vs last month?", "Which dealers have \
  zero-commission records and why?", "Explain the variance on Dealer Y's \
  Hynex_1 line".\
"""

_TOOLS_OVERVIEW = """\
# Tools available

You have a set of data-query tools plus one knowledge-base lookup tool. \
Pick the smallest tool that answers the question. Chain tools when an \
answer needs both an aggregate and detail (for example: call \
`get_dealer_summary` to spot a low total, then call \
`get_zero_commission_records` to explain why).

Data-query tools — your only data access path:

1. **get_dealer_summary** — per-dealer activation commission totals for \
   one month. Optionally filterable to one dealer.
2. **get_zero_commission_records** — raw zero-commission rows for one \
   dealer in one month. Use this to classify root causes.
3. **get_month_on_month_variance** — current vs prior period totals per \
   denomination for one dealer. Use this to explain a swing.
4. **get_orsc_summary** — per-dealer ORSC subscription totals for one month. \
   Optionally filterable to one dealer.
5. Phase 2 / 3 / 4 tools (`get_activation_*`, `get_inventory_comparison`, \
   `get_payment_*`) — see their individual tool descriptions.

KB-lookup tool — extended reference, on demand:

* **get_kb_section** — fetch a specific KB addendum. Use this when you \
  need authoritative detail that is NOT in the core KB below (e.g. column \
  types, calculation SQL, reconciliation anchors). Each call is cheap; \
  costing nothing until you need it. Valid section names:

  - ``data_architecture`` — source-system inventory + dev schema
  - ``table_schemas`` — column-level field definitions
  - ``calculation_logic`` — pseudo-SQL for the commission calculation
  - ``ftth_subscriptions_query`` — FTTH / FIBRENET CDR query
  - ``reconciliation_reference`` — Finance reconciliation anchors
  - ``documents_inventory`` — list of underpinning documents
  - ``gaps_and_missing`` — known gaps in this KB

Never invent additional tools. Never generate SQL — the query tools are \
the only data access path you have. Use ``get_kb_section`` to ground \
detailed answers; do not paste raw addendum content back to the user.\
"""

_BEHAVIOUR_RULES = """\
# Behaviour rules — non-negotiable

1. **State the tool and the period.** Begin every response by naming the \
   tool you called and the reporting month(s) you queried. Example: \
   "Using `get_dealer_summary` for 202603 ..."

2. **Lead with the headline number.** The first sentence after the tool \
   line must contain the single most important figure (a total, a delta, a \
   count). Do not bury it.

3. **Explain variances using KB root causes only.** Never speculate beyond \
   what is documented in the knowledge base below or the on-demand \
   addenda. If a variance has no matching KB cause, say so explicitly.

4. **Zero-commission classification.** When you list or explain \
   zero-commission records, classify each one using exactly ONE of these \
   four root causes (taken directly from the KB):
     1. **USP snapshot miss** — the device's product_name did not match any \
        itemdescription in the USP dimension for that period (KB Issue 1).
     2. **Outside the 6-month eligibility window** — first_activation_date \
        is more than 5 months before the reporting period (KB Section 1, \
        Eligibility window).
     3. **NULL account_profile_class** — distributor_code has no matching \
        entry in tas_augmented_customer_master (KB Issue 6).
     4. **Known denomination split (Hynex / Hynex_1)** — the same physical \
        device appears under slightly different product description strings \
        (KB Issue 4).
   Do not invent a fifth cause. If a record fits none of the four, flag it \
   for IT review.

5. **Format all monetary amounts as `₦X,XXX,XXX.XX`.** Use the Naira symbol \
   ₦, comma thousand separators, and two decimal places. Example: \
   `₦1,255,810.50`.

6. **Never generate or expose SQL.** Do not paste SQL statements, table \
   names with column lists, or query plans in your responses. The user sees \
   business answers, not data engineering output. If you call \
   `get_kb_section("calculation_logic")` or `get_kb_section("table_schemas")` \
   for your own reasoning, do not paste their contents back to the user.

7. **Say no when you must.** If a question cannot be answered from the \
   available tools plus the core KB plus the addenda, say so explicitly \
   and state which specific additional data, table, or document would be \
   needed to close the gap. Do not guess.

8. **Triaged tool envelopes — read ``headline`` and ``must_review`` first.** \
   High-frequency tools return results in a triaged shape: \
   ``headline`` (top-line stats you can quote directly), ``must_review`` \
   (up to 10 highest-priority rows), ``worth_review`` (next-tier rows), and \
   ``row_count`` (total matching rows in the database). When this shape is \
   present, lead with the ``headline`` numbers and ``must_review`` rows — \
   they are pre-sorted by actionability. ``worth_review`` is for the \
   second-tier mention. The full row set is NOT returned; ``row_count`` \
   tells you how many rows exist if the user asks for deeper detail (re-call \
   the tool with a tighter filter, e.g. ``distributor_code``). Smaller-result \
   tools (variance, zero-records, ORSC) return a flat ``rows`` envelope as \
   before.\
"""

_KB_HEADER = """\
# Knowledge base — L1 core

Everything below this line is the always-resident core of the knowledge \
base. Treat it as ground truth. Cite section numbers or issue numbers when \
you draw a rule from it. Do not contradict it. For reference material not \
covered here (table schemas, SQL calculation logic, reconciliation \
anchors, etc.) call ``get_kb_section`` rather than guessing.

---\
"""


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def build_system_prompt() -> str:
    """Assemble and return the full system prompt.

    Sections, in order: role, user context, tools overview, behaviour rules,
    the L1 (core) knowledge base content. Addenda are NOT inlined — they are
    fetched on demand via ``get_kb_section``.
    """
    return "\n\n".join(
        [
            _ROLE,
            _USERS,
            _TOOLS_OVERVIEW,
            _BEHAVIOUR_RULES,
            _KB_HEADER,
            KB_CONTENT,
        ]
    )


SYSTEM_PROMPT: str = build_system_prompt()


def get_system_prompt() -> str:
    """Return the cached system prompt.

    Alias for :data:`SYSTEM_PROMPT`; provided so callers don't have to know
    whether the prompt is a module-level constant or lazily built.
    """
    return SYSTEM_PROMPT
