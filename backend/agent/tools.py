"""Tool definitions in Anthropic API tool-use format.

Each tool dict has three keys — ``name``, ``description``, ``input_schema`` —
and matches one query in :mod:`backend.db.queries`. The descriptions are
deliberately detailed so Claude can pick the right tool without prompting.

Exports:
    * Four module-level tool dicts (one per tool).
    * ``TOOLS``      — list passed straight to ``client.messages.create(...)``.
    * ``TOOL_NAMES`` — list of tool names, useful for validation.
"""
from __future__ import annotations

from typing import Any

# JSON-Schema fragments reused across the four tools.
_MON_PERIOD_SCHEMA: dict[str, Any] = {
    "type": "string",
    "description": (
        "Reporting month in YYYYMM format, e.g. '202603' for March 2026. "
        "Must be a 6-character numeric string."
    ),
    "pattern": r"^\d{6}$",
}

_DISTRIBUTOR_CODE_SCHEMA: dict[str, Any] = {
    "type": "string",
    "description": (
        "Trade partner / distributor code as a numeric string, e.g. '215043'. "
        "This is the same value as the distributor_code column in "
        "development.fbb_comm_dev_act and development.fbb_comm_orsc."
    ),
}


# ---------------------------------------------------------------------------
# Tool 1
# ---------------------------------------------------------------------------

GET_DEALER_SUMMARY: dict[str, Any] = {
    "name": "get_dealer_summary",
    "description": (
        "Returns per-dealer activation commission totals for a single "
        "reporting month from development.fbb_comm_dev_act.\n\n"
        "Use this for:\n"
        "  * 'Summarise dealer commissions for [month]'\n"
        "  * 'What does MTN owe Dealer X this month?'\n"
        "  * 'Who are the top trade partners by activation commission?'\n\n"
        "Behaviour:\n"
        "  * Without distributor_code: one row per dealer, sorted by "
        "total_commission_ngn descending.\n"
        "  * With distributor_code: a single row for that dealer.\n\n"
        "Each row contains: distributor_code, distributor_name, "
        "account_profile_class, total_activations, total_commission_ngn, "
        "zero_commission_count, commission_by_denomination (object mapping "
        "product_denomination → commission total in Naira)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mon_period": _MON_PERIOD_SCHEMA,
            "distributor_code": {
                **_DISTRIBUTOR_CODE_SCHEMA,
                "description": (
                    _DISTRIBUTOR_CODE_SCHEMA["description"]
                    + " Optional — omit to get every dealer for the period."
                ),
            },
        },
        "required": ["mon_period"],
    },
}


# ---------------------------------------------------------------------------
# Tool 2
# ---------------------------------------------------------------------------

GET_ZERO_COMMISSION_RECORDS: dict[str, Any] = {
    "name": "get_zero_commission_records",
    "description": (
        "Returns the raw activation rows where commission_rate is 0 or NULL "
        "for ONE dealer in ONE reporting month from development.fbb_comm_dev_act.\n\n"
        "Use this when the user asks:\n"
        "  * 'Why is Dealer X's commission lower than expected?'\n"
        "  * 'Which records on Dealer Y are unpaid?'\n"
        "  * 'List the leakage candidates for Dealer Z in [month]'\n\n"
        "Each row contains: imei, product_name, product_code, invoice_date, "
        "first_activation_date, unit_selling_price, commission_rate.\n\n"
        "After calling this tool you MUST classify each returned record using "
        "exactly one of the four KB root causes:\n"
        "  1. USP snapshot miss\n"
        "  2. Outside 6-month eligibility window\n"
        "  3. NULL account_profile_class\n"
        "  4. Known denomination split (Hynex / Hynex_1)\n"
        "Do not invent any other root cause. Both inputs are required."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mon_period": _MON_PERIOD_SCHEMA,
            "distributor_code": _DISTRIBUTOR_CODE_SCHEMA,
        },
        "required": ["mon_period", "distributor_code"],
    },
}


# ---------------------------------------------------------------------------
# Tool 3
# ---------------------------------------------------------------------------

GET_MONTH_ON_MONTH_VARIANCE: dict[str, Any] = {
    "name": "get_month_on_month_variance",
    "description": (
        "Returns one dealer's activation totals broken down by "
        "product_denomination for TWO periods (current vs prior) with the "
        "month-on-month delta computed.\n\n"
        "Use this when the user asks:\n"
        "  * 'Why did Dealer X's commission change vs last month?'\n"
        "  * 'Compare Dealer Y's June vs May totals'\n"
        "  * 'What drove the swing for Dealer Z between [month] and [month]?'\n\n"
        "Output: one row per (period, product_denomination). Rows where "
        "period = current_period carry delta_ngn (current minus prior) and "
        "delta_pct; rows where period = prior_period have delta_ngn = 0.\n\n"
        "After calling this tool, you MUST explain the variance using KB "
        "root causes only (e.g. USP snapshot miss, transaction lag from "
        "Issue 3, denomination split from Issue 4). Do not speculate beyond "
        "the KB. All three inputs are required."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "distributor_code": _DISTRIBUTOR_CODE_SCHEMA,
            "current_period": {
                **_MON_PERIOD_SCHEMA,
                "description": (
                    "Current reporting month in YYYYMM format (the period "
                    "the user is investigating)."
                ),
            },
            "prior_period": {
                **_MON_PERIOD_SCHEMA,
                "description": (
                    "Prior reporting month in YYYYMM format (the baseline "
                    "to compare against, typically the immediately preceding "
                    "month)."
                ),
            },
        },
        "required": ["distributor_code", "current_period", "prior_period"],
    },
}


# ---------------------------------------------------------------------------
# Tool 4
# ---------------------------------------------------------------------------

GET_ORSC_SUMMARY: dict[str, Any] = {
    "name": "get_orsc_summary",
    "description": (
        "Returns per-dealer Ongoing Revenue Service Commission (ORSC) "
        "subscription totals for a single reporting month from "
        "development.fbb_comm_orsc.\n\n"
        "Use this for:\n"
        "  * 'What is the ORSC summary for [month]?'\n"
        "  * 'Which dealers are earning ORSC and how much?'\n"
        "  * 'How many devices on Dealer X are still generating ORSC?'\n\n"
        "Behaviour:\n"
        "  * Without distributor_code: one row per dealer, sorted by "
        "total_subscription_amount_ngn descending.\n"
        "  * With distributor_code: a single row for that dealer.\n\n"
        "Each row contains: distributor_code, distributor_name, "
        "account_profile_class, device_count, total_subscription_amount_ngn, "
        "zero_amount_count.\n\n"
        "Important: data_subscription_amount IS the commission basis. There "
        "is no 10%% rate multiplication for ORSC — the amount returned is "
        "what MTN owes the dealer for that month."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mon_period": _MON_PERIOD_SCHEMA,
            "distributor_code": {
                **_DISTRIBUTOR_CODE_SCHEMA,
                "description": (
                    _DISTRIBUTOR_CODE_SCHEMA["description"]
                    + " Optional — omit to get every dealer for the period."
                ),
            },
        },
        "required": ["mon_period"],
    },
}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Phase 2 — Activation Intelligence tools
# ---------------------------------------------------------------------------


GET_ACTIVATION_SUMMARY: dict[str, Any] = {
    "name": "get_activation_summary",
    "description": (
        "Returns activation totals by dealer for a given reporting month "
        "from development.fbb_comm_dev_act.\n\n"
        "Use this for:\n"
        "  * 'Show activation summary for [month]'\n"
        "  * 'Which dealers generated the most activations?'\n"
        "  * 'What is the qualification rate by dealer?'\n\n"
        "Each row contains: dealer_id, dealer_name, account_profile_class, "
        "report_month, activation_count, qualified_activation_count "
        "(commission_rate > 0), non_qualified_activation_count "
        "(commission_rate = 0), activation_commission_amount (sum in Naira), "
        "qualification_rate_pct (qualified / total × 100, rounded 2dp).\n\n"
        "Rows are sorted by activation_count descending. KB rules of thumb: "
        "qualification_rate_pct above 80%% is healthy; below 50%% warrants "
        "investigation via get_zero_commission_records."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mon_period": _MON_PERIOD_SCHEMA,
        },
        "required": ["mon_period"],
    },
}


GET_ACTIVATION_VARIANCE: dict[str, Any] = {
    "name": "get_activation_variance",
    "description": (
        "Compares dealer-level activation counts, commission, and "
        "qualification rates between two reporting months. Returns one "
        "row per dealer present in BOTH periods.\n\n"
        "Use this for:\n"
        "  * 'Why did activation counts change vs last month?'\n"
        "  * 'Which dealers grew or declined in activation volume?'\n"
        "  * 'Compare February and March activation performance for Dealer X'\n\n"
        "Each row contains: dealer_id, dealer_name, period_a, period_b, "
        "activation_count_a, activation_count_b, delta_activations "
        "(b minus a), delta_commission_ngn, delta_qualification_rate.\n\n"
        "Rows are sorted by abs(delta_activations) descending — the biggest "
        "movers in either direction come first. ``period_a`` is the earlier "
        "period, ``period_b`` is the later one. Use KB explanation rules to "
        "interpret the variance — never speculate beyond the four documented "
        "patterns."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "period_a": {
                **_MON_PERIOD_SCHEMA,
                "description": "Earlier reporting month in YYYYMM format.",
            },
            "period_b": {
                **_MON_PERIOD_SCHEMA,
                "description": "Later reporting month in YYYYMM format.",
            },
        },
        "required": ["period_a", "period_b"],
    },
}


GET_ACTIVATION_EXCEPTIONS: dict[str, Any] = {
    "name": "get_activation_exceptions",
    "description": (
        "Returns dealers with unusual or concerning activation patterns "
        "for the given reporting month. Three exception types — a dealer "
        "may appear multiple times if they hit more than one condition.\n\n"
        "Exception types:\n"
        "  * ALL_UNQUALIFIED — activation_count > 0 but "
        "qualified_activation_count = 0; the dealer has activations but "
        "earned no commission.\n"
        "  * HIGH_UNQUALIFIED_RATE — qualification_rate_pct < 50; more "
        "than half of the dealer's activations did not earn commission.\n"
        "  * UNUSUAL_VOLUME — activation_count is at or above "
        "(mean + 2 × std_dev) across all dealers for the period; "
        "statistically high vs peers.\n\n"
        "Use this when the user asks about anomalies, exceptions, dealers "
        "to investigate, or 'who should we look at'.\n\n"
        "Important: UNUSUAL_VOLUME flags require investigation — they are "
        "NOT evidence of wrongdoing or fraud. Present these as 'volume "
        "above peer norms; requires investigation'. Never use the word "
        "'fraud' in the explanation."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mon_period": _MON_PERIOD_SCHEMA,
        },
        "required": ["mon_period"],
    },
}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Phase 3 — Inventory Assurance tool
# ---------------------------------------------------------------------------


GET_INVENTORY_COMPARISON: dict[str, Any] = {
    "name": "get_inventory_comparison",
    "description": (
        "Compares dealer device activations against IFS invoice purchase "
        "records to identify inventory mismatches. Returns three finding "
        "types:\n"
        "  * CONFIRMED_MISMATCH — IFS invoice records exist AND activations "
        "exceed purchased units. Requires investigation.\n"
        "  * NO_INVOICE_RECORD — activations exist but no IFS invoice was "
        "found in the available data window. May reflect purchases outside "
        "the sample period; NOT a confirmed mismatch.\n"
        "  * WITHIN_ALLOCATION — activations are within the dealer's "
        "purchased unit count.\n\n"
        "Use this for:\n"
        "  * 'Show inventory comparison for [month]'\n"
        "  * 'Which dealers activated more devices than they purchased?'\n"
        "  * 'Find inventory mismatches for [month]'\n"
        "  * 'Did Dealer X activate devices they purchased?'\n\n"
        "Each row contains: dealer_id, dealer_name, product_code, "
        "product_name, activation_count, qualified_count, "
        "total_units_purchased, inventory_gap (activations minus purchases), "
        "gap_pct (excess as percentage of purchased), finding_type, "
        "data_coverage_note.\n\n"
        "Severity bands from the KB (use these when classifying findings): "
        "gap_pct >= 200 is HIGH (3x or more units activated), 100-199 is "
        "MEDIUM (~2x), below 100 is LOW. NO_INVOICE_RECORD findings are "
        "NEVER confirmed mismatches — always note the data window caveat. "
        "Never use the words fraud, theft, grey market, or criminal in your "
        "response — use 'mismatch', 'excess activations', or 'requires "
        "investigation' instead."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mon_period": _MON_PERIOD_SCHEMA,
        },
        "required": ["mon_period"],
    },
}


# ---------------------------------------------------------------------------
# Phase 4 — Payment Intelligence tools
# ---------------------------------------------------------------------------


GET_PAYMENT_SUMMARY: dict[str, Any] = {
    "name": "get_payment_summary",
    "description": (
        "Returns commission payment status for all dealers in a given "
        "month. Shows what MTN owes each dealer, what has been paid, "
        "what remains outstanding, and the payment channel.\n\n"
        "Use this for:\n"
        "  * 'Show payment status for [month]'\n"
        "  * 'What has MTN paid each dealer this month?'\n"
        "  * 'Which dealers have outstanding commissions?'\n\n"
        "Each row contains: distributor_code, distributor_name, "
        "account_profile_class, report_month, commission_owed, "
        "amount_paid, amount_unpaid, payment_status (FULLY_PAID / "
        "PARTIALLY_PAID / DISPUTED / PENDING), payment_channel, "
        "payment_date, exception_flag, data_source.\n\n"
        "IMPORTANT: Payment data is simulated. Derived from real "
        "commission and exception records — live Oracle AP integration "
        "will replace this in production. Always disclose this when "
        "presenting payment findings."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"mon_period": _MON_PERIOD_SCHEMA},
        "required": ["mon_period"],
    },
}


GET_PAYMENT_EXCEPTIONS: dict[str, Any] = {
    "name": "get_payment_exceptions",
    "description": (
        "Returns dealers with outstanding or disputed commission "
        "payments for a given month. Excludes FULLY_PAID dealers.\n\n"
        "Three statuses returned (in priority order):\n"
        "  * DISPUTED — linked to a Phase 2 ALL_UNQUALIFIED or Phase 3 "
        "CONFIRMED_MISMATCH exception. Commission held pending dispute "
        "resolution.\n"
        "  * PARTIALLY_PAID — linked to a Phase 2 HIGH_UNQUALIFIED_RATE "
        "exception. Partial settlement processed for the qualified "
        "portion only.\n"
        "  * PENDING — no exception flag. Commission within the normal "
        "settlement window.\n\n"
        "Use this for:\n"
        "  * 'Which dealers have disputed commissions?'\n"
        "  * 'Show me unpaid commissions for [month]'\n"
        "  * 'Which dealers have settlement exceptions?'\n\n"
        "Each row includes ``exception_flag`` linking back to the "
        "underlying Phase 2 / Phase 3 finding — use this for cross-"
        "phase reasoning. IMPORTANT: payment data is simulated; always "
        "disclose this."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"mon_period": _MON_PERIOD_SCHEMA},
        "required": ["mon_period"],
    },
}


GET_PAYMENT_VARIANCE: dict[str, Any] = {
    "name": "get_payment_variance",
    "description": (
        "Compares commission payment amounts and status between two "
        "periods for each dealer present in both. Shows whether "
        "settlement coverage improved or declined, and which dealers "
        "moved between payment statuses.\n\n"
        "Use this for:\n"
        "  * 'How did payment coverage change vs last month?'\n"
        "  * 'Which dealers moved from DISPUTED to PAID?'\n"
        "  * 'Compare settlement rates between [month] and [month]'\n\n"
        "Each row contains: dealer_id, dealer_name, period_a, period_b, "
        "commission_owed_a / amount_paid_a / payment_status_a, "
        "commission_owed_b / amount_paid_b / payment_status_b, "
        "delta_paid (period_b minus period_a), status_changed (bool).\n\n"
        "Rows are sorted by abs(delta_paid) descending. IMPORTANT: "
        "payment data is simulated; always disclose this."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "period_a": {
                **_MON_PERIOD_SCHEMA,
                "description": "Earlier reporting month in YYYYMM format.",
            },
            "period_b": {
                **_MON_PERIOD_SCHEMA,
                "description": "Later reporting month in YYYYMM format.",
            },
        },
        "required": ["period_a", "period_b"],
    },
}


# ---------------------------------------------------------------------------
# L2 — on-demand KB section lookup
# ---------------------------------------------------------------------------
#
# Reference material that is rarely needed inline (table schemas, calculation
# SQL, reconciliation anchors, etc.) has been moved out of the always-resident
# system prompt and into addendum files. The agent fetches them when needed
# via this single lookup tool. Section names are stable: see
# :data:`backend.agent.prompts.ADDENDA_REGISTRY` for the canonical list.

GET_KB_SECTION: dict[str, Any] = {
    "name": "get_kb_section",
    "description": (
        "Fetches a named addendum from the FBB commission knowledge base. "
        "Reference material — table schemas, calculation SQL, reconciliation "
        "anchors, documents inventory — lives outside the always-resident "
        "system prompt to keep it small; use this tool when you need that "
        "level of detail to ground a specific answer.\n\n"
        "Valid section names:\n"
        "  * data_architecture       — source-system inventory + dev schema\n"
        "  * table_schemas           — column-level field definitions for "
        "dev_act / ORSC / USP\n"
        "  * calculation_logic       — pseudo-SQL for the commission "
        "calculation pipeline\n"
        "  * ftth_subscriptions_query — FBB / FIBRENET subscription "
        "revenue CDR query\n"
        "  * reconciliation_reference — comparison anchors Finance uses to "
        "validate the report\n"
        "  * documents_inventory     — underpinning policy / spec / sample "
        "documents\n"
        "  * gaps_and_missing        — known gaps in the KB worth flagging "
        "to users\n\n"
        "IMPORTANT: use the addendum content for your own reasoning only. "
        "Do not paste raw SQL, table dumps, or addendum text back to the "
        "user — translate any relevant detail into a plain-English answer."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "section": {
                "type": "string",
                "description": (
                    "The addendum to fetch. One of: data_architecture, "
                    "table_schemas, calculation_logic, "
                    "ftth_subscriptions_query, reconciliation_reference, "
                    "documents_inventory, gaps_and_missing."
                ),
                "enum": [
                    "data_architecture",
                    "table_schemas",
                    "calculation_logic",
                    "ftth_subscriptions_query",
                    "reconciliation_reference",
                    "documents_inventory",
                    "gaps_and_missing",
                ],
            }
        },
        "required": ["section"],
    },
}


# ---------------------------------------------------------------------------
# L1 composite — one call returns the full dealer dossier across all phases
# ---------------------------------------------------------------------------

GET_DEALER_FULL_CONTEXT: dict[str, Any] = {
    "name": "get_dealer_full_context",
    "description": (
        "Returns a complete dealer dossier in ONE call: identity + Phase 1 "
        "commission summary + Phase 2 activation breakdown + Phase 2 "
        "activation exceptions + Phase 3 inventory findings (sorted "
        "CONFIRMED_MISMATCH first) + Phase 4 payment status (with "
        "exception_flag linking back to the underlying root cause) + a "
        "5-row sample of zero-commission records if any exist.\n\n"
        "Use this tool whenever the user asks about a SPECIFIC dealer — "
        "'tell me about Dealer X', 'why is Dealer Y disputed', 'what is the "
        "situation with distributor_code Z'. It replaces what would otherwise "
        "be 4-5 separate tool calls (get_dealer_summary, "
        "get_activation_summary, get_inventory_comparison, get_payment_summary, "
        "get_zero_commission_records) and presents the data already joined.\n\n"
        "Both inputs are required:\n"
        "  * distributor_code — the dealer's numeric distributor_code as a "
        "string, e.g. '296065'\n"
        "  * mon_period — reporting month in YYYYMM format\n\n"
        "Response shape:\n"
        "  found (bool), dealer{...}, commission{...}, activation{...}, "
        "activation_exceptions[...], inventory{confirmed_mismatches, "
        "no_invoice_records, within_allocation, findings[...]}, "
        "payment{...}, zero_records_sample[...].\n\n"
        "Payment data is SIMULATED — disclose this when quoting payment "
        "figures. For month-on-month comparison run "
        "get_month_on_month_variance separately."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "distributor_code": {
                **_DISTRIBUTOR_CODE_SCHEMA,
                "description": (
                    _DISTRIBUTOR_CODE_SCHEMA["description"]
                    + " Required — the dealer to assemble the dossier for."
                ),
            },
            "mon_period": _MON_PERIOD_SCHEMA,
        },
        "required": ["distributor_code", "mon_period"],
    },
}


# ---------------------------------------------------------------------------
# Data coverage ticket compiler
# ---------------------------------------------------------------------------

COMPILE_DATA_COVERAGE_TICKET: dict[str, Any] = {
    "name": "compile_data_coverage_ticket",
    "description": (
        "Compile a ServiceNow-ready ticket draft for FBB data coverage "
        "gaps that affect commission accuracy. Returns the list of "
        "affected dealers plus a markdown ticket body the finance officer "
        "can paste into ServiceNow.\n\n"
        "Two gap classes are covered:\n"
        "  * IFS missing — dealers with NO_INVOICE_RECORD inventory rows.\n"
        "  * USP missing — dealers with NULL account_profile_class (one of "
        "the four KB-documented root causes for zero-commission records).\n\n"
        "Use this when:\n"
        "  * The user asks to 'compile / draft / generate a ticket for data "
        "coverage issues / data team / task team'.\n"
        "  * After investigating a dealer dispute that bottoms out in "
        "missing IFS or USP data — escalate by drafting a ticket.\n\n"
        "Severity scales with the affected-dealer count: 1-3 = LOW, "
        "4-10 = MEDIUM, 10+ = HIGH. Stage 1 only — this does NOT submit to "
        "ServiceNow; the finance officer pastes the body manually."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mon_period": _MON_PERIOD_SCHEMA,
            "source": {
                "type": "string",
                "enum": ["ifs", "usp", "both"],
                "description": (
                    "Which gap class to include. Default 'both'. Use 'ifs' "
                    "only for inventory data-window questions, 'usp' only "
                    "for commission-classification questions."
                ),
                "default": "both",
            },
        },
        "required": ["mon_period"],
    },
}


TOOLS: list[dict[str, Any]] = [
    GET_DEALER_SUMMARY,
    GET_ZERO_COMMISSION_RECORDS,
    GET_MONTH_ON_MONTH_VARIANCE,
    GET_ORSC_SUMMARY,
    # --- Phase 2: Activation Intelligence ---
    GET_ACTIVATION_SUMMARY,
    GET_ACTIVATION_VARIANCE,
    GET_ACTIVATION_EXCEPTIONS,
    # --- Phase 3: Inventory Assurance ---
    GET_INVENTORY_COMPARISON,
    # --- Phase 4: Payment Intelligence ---
    GET_PAYMENT_SUMMARY,
    GET_PAYMENT_EXCEPTIONS,
    GET_PAYMENT_VARIANCE,
    # --- L2: on-demand KB lookup ---
    GET_KB_SECTION,
    # --- L1 composite — replaces 4+ tool calls for "tell me about Dealer X" ---
    GET_DEALER_FULL_CONTEXT,
    # --- Operational: ServiceNow ticket draft (Stage 1 — compile only) ---
    COMPILE_DATA_COVERAGE_TICKET,
]

TOOL_NAMES: list[str] = [tool["name"] for tool in TOOLS]
