"""Measure questions that name a dealer instead of giving its code.

The model copies the name; the application resolves it with the recorded
name/code lookup before any evidence is read, and never picks between
several matching dealers.
"""
import asyncio

import pytest

from backend import config
from backend.agent import agent
from backend.agent.dealer_resolution import resolve_dealer_name
from backend.agent.measure_scope import SCOPE_TOOL, MeasureScope
from backend.db import audit_store
from backend.db.connection import execute_query


@pytest.fixture(autouse=True)
def sample_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)
    monkeypatch.setattr(config, "PAYMENT_SOURCE", "simulated")
    monkeypatch.setattr(audit_store, "healthcheck", lambda: True)
    monkeypatch.setattr(audit_store, "get_partner_trail", lambda *args: None)


def statement(**overrides):
    plan = {"kind": "measure", "measures": ["dealer_statement"], "periods": ["202606"],
            "operation": "total"}
    plan.update(overrides)
    return plan


# ── Scope validation ────────────────────────────────────────────────────────

def test_measure_scope_accepts_a_dealer_name_instead_of_a_code():
    scope = MeasureScope.model_validate(statement(dealer_name="River Isle"))
    assert scope.dealer_name == "River Isle" and scope.dealer_id is None
    MeasureScope.model_validate({"kind": "measure", "measures": ["activation_count"],
                                 "periods": ["202606"], "dealer_name": "River Isle"})
    MeasureScope.model_validate({"kind": "measure", "measures": ["commission_variance"],
                                 "periods": ["202605", "202606"], "operation": "explain",
                                 "dealer_name": "River Isle"})


@pytest.mark.parametrize("plan", [
    statement(dealer_name="River Isle", dealer_id="296065"),
    statement(dealer_name="   "),
    statement(),
])
def test_measure_scope_rejects_name_with_code_blank_name_or_no_dealer(plan):
    with pytest.raises(ValueError):
        MeasureScope.model_validate(plan)


def test_identity_and_other_kinds_are_unchanged():
    MeasureScope.model_validate({"kind": "identity", "dealer_name": "River Isle Ventures"})
    with pytest.raises(ValueError):
        MeasureScope.model_validate({"kind": "clarification", "clarification": "dealer",
                                     "dealer_name": "River Isle"})


def test_scope_tool_tells_the_model_to_copy_names_and_never_guess_codes():
    description = SCOPE_TOOL["description"]
    assert "dealer_name" in description and "never guess" in description.lower()


# ── Recorded-name matching in the lookup query ──────────────────────────────

def test_lookup_contains_mode_finds_partial_names_and_exact_mode_is_unchanged():
    params = {"dealer_name": "  amber ARC ", "start_period": "202606", "end_period": "202606"}
    assert execute_query("get_dealer_codes", params).empty
    found = execute_query("get_dealer_codes", {**params, "match": "contains"})
    assert found["dealer_id"].tolist() == ["130062"]
    assert found["recorded_names"].tolist() == [["Amber Arc Communications"]]
    with pytest.raises(ValueError):
        execute_query("get_dealer_codes", {**params, "match": "fuzzy"})


# ── Resolver with a fake lookup ─────────────────────────────────────────────

def fake_lookup(exact=(), contains=(), calls=None):
    def lookup(request):
        if calls is not None:
            calls.append(request)
        rows = exact if request["match"] == "exact" else contains
        return {"tool": "get_dealer_codes", "total_codes": len(rows), "rows": [
            {"dealer_id": code, "recorded_names": [name], "first_observed_period": "202606",
             "last_observed_period": "202606", "sources": ["fbb_comm_dev_act"]}
            for name, code in rows][:100]}
    return lookup


def test_one_match_proceeds_with_its_code_and_a_match_line():
    calls = []
    result = resolve_dealer_name(statement(dealer_name="  river   isle "), fake_lookup(
        contains=[("River Isle Ventures", "296065")], calls=calls))
    assert result.status == "matched" and result.dealer_id == "296065"
    # The match line quotes the name as the user wrote it; the lookup gets it normalised.
    assert result.text == "Matched “river   isle” to River Isle Ventures \\(296065\\)."
    assert [call["match"] for call in calls] == ["exact", "contains"]
    assert calls[0]["dealer_name"] == "river isle" and calls[0]["periods"] == ["202606"]


def test_exact_name_wins_over_longer_partial_matches():
    result = resolve_dealer_name(statement(dealer_name="Acme"), fake_lookup(
        exact=[("Acme", "7")], contains=[("Acme", "7"), ("Acme Trading", "8")]))
    assert result.status == "matched" and result.dealer_id == "7"


def test_no_match_asks_for_the_code_and_reads_no_evidence():
    result = resolve_dealer_name(statement(dealer_name="Nowhere Ltd"), fake_lookup())
    assert result.status == "none" and result.dealer_id is None
    assert result.text == ("No dealer named “Nowhere Ltd” is recorded for 202606; "
                           "give the dealer code or the full recorded name.")


def test_many_matches_list_five_candidates_with_the_total_and_never_pick():
    rows = [(f"Acme {n}", str(n)) for n in range(1, 8)]
    result = resolve_dealer_name(statement(dealer_name="Acme"), fake_lookup(contains=rows))
    assert result.status == "ambiguous" and result.dealer_id is None
    lines = result.text.split("\n")
    assert lines[0] == "Several recorded dealers match “Acme” for 202606 (7 in total; showing 5)."
    assert lines[2:7] == [f"- Acme {n} \\({n}\\)" for n in range(1, 6)]
    assert lines[-1] == "Which dealer do you mean? Give the dealer code."


def test_few_matches_list_every_candidate_without_a_total():
    result = resolve_dealer_name(statement(dealer_name="Acme"),
                                 fake_lookup(exact=[("Acme", "1"), ("Acme", "2")]))
    assert result.status == "ambiguous"
    assert result.text.split("\n")[0] == "Several recorded dealers match “Acme” for 202606."
    assert "- Acme \\(1\\)" in result.text and "- Acme \\(2\\)" in result.text


def test_lookup_failure_is_unresolved_not_not_found():
    def broken(request):
        raise FileNotFoundError("dealer records")
    result = resolve_dealer_name(statement(dealer_name="River Isle"), broken)
    assert result.status == "unavailable" and result.dealer_id is None
    assert "could not be resolved" in result.text
    assert "No dealer named" not in result.text and "not found" not in result.text.lower()


def test_names_are_escaped_in_answer_text():
    result = resolve_dealer_name(statement(dealer_name="*Acme*"), fake_lookup(
        contains=[("*Acme* [Ltd]", "9")]))
    assert result.text == "Matched “\\*Acme\\*” to \\*Acme\\* \\[Ltd\\] \\(9\\)."


def test_two_month_scope_searches_the_span_between_them():
    calls = []
    resolve_dealer_name({"kind": "measure", "measures": ["commission_variance"],
                         "periods": ["202606", "202603"], "operation": "explain",
                         "dealer_name": "Acme"}, fake_lookup(calls=calls))
    assert calls[0]["periods"] == ["202603", "202604", "202605", "202606"]


# ── Real-data oracles through the agent ─────────────────────────────────────

def install(monkeypatch, plan):
    from backend.tests.test_measure_scope import install_plan
    return install_plan(monkeypatch, plan)


def test_unique_partial_name_answers_the_statement_for_the_resolved_account(monkeypatch):
    install(monkeypatch, statement(dealer_name="Amber Arc"))
    result = asyncio.run(agent.run_agent("What do we owe Amber Arc in June?"))
    assert "Amber Arc Communications" in result["response"]
    assert "130062" in result["response"] and "202606" in result["response"]
    assert result["tools_called"] == ["get_dealer_codes", "dealer_statement"]
    assert result["raw_data"]["measure_evidence"]["dealer_id"] == "130062"


def test_statement_by_name_matches_the_statement_by_code(monkeypatch):
    install(monkeypatch, statement(dealer_name="river isle trading"))
    by_name = asyncio.run(agent.run_agent("Statement for river isle trading"))
    install(monkeypatch, statement(dealer_id="19969"))
    by_code = asyncio.run(agent.run_agent("Statement for 19969"))
    assert "19969" in by_name["response"] and "19969" in by_code["response"]
    assert by_name["raw_data"]["measure_evidence"] == by_code["raw_data"]["measure_evidence"]


def test_river_isle_is_ambiguous_in_june_and_reads_no_evidence(monkeypatch):
    install(monkeypatch, statement(dealer_name="River Isle"))
    calls = []
    monkeypatch.setattr(agent.tool_executor, "execute_measure_request", calls.append)
    result = asyncio.run(agent.run_agent("What do we owe River Isle in June?"))
    assert calls == []
    assert result["response"].split("\n\n### Verification evidence", 1)[0] == "\n".join([
        "Several recorded dealers match “River Isle” for 202606 (6 in total; showing 5).",
        "",
        "- River Isle Ventures \\(121038\\)",
        "- River Isle Trading \\(19969\\)",
        "- River Isle Ventures \\(294129\\)",
        "- River Isle Ventures \\(296065\\)",
        "- River Isle Networks \\(347058\\)",
        "",
        "Which dealer do you mean? Give the dealer code.",
    ])
    assert result["tools_called"] == ["get_dealer_codes"]
    assert "NGN" not in result["response"]


def test_unknown_name_answers_with_a_clarification(monkeypatch):
    install(monkeypatch, statement(dealer_name="Nowhere Ltd"))
    result = asyncio.run(agent.run_agent("What do we owe Nowhere Ltd?"))
    assert result["response"].split("\n\n### Verification evidence", 1)[0] == ("No dealer named “Nowhere Ltd” is recorded for 202606; "
                                  "give the dealer code or the full recorded name.")


def test_unreadable_dealer_records_do_not_become_not_found(monkeypatch):
    install(monkeypatch, statement(dealer_name="Amber Arc"))
    def broken(request):
        raise OSError("source unreadable")
    monkeypatch.setattr(agent.tool_executor, "execute_dealer_lookup", broken)
    result = asyncio.run(agent.run_agent("What do we owe Amber Arc?"))
    assert "could not be resolved" in result["response"]
    assert "No dealer named" not in result["response"]
    assert result["tools_called"] == []


def test_months_without_any_dealer_records_are_unresolved_not_not_found():
    def uncovered(request):
        return {"tool": "get_dealer_codes", "total_codes": 0, "rows": [],
                "coverage_by_source": {"fbb_comm_dev_act": [], "fbb_comm_orsc": []}}
    result = resolve_dealer_name(statement(dealer_name="Amber Arc", periods=["209901"]), uncovered)
    assert result.status == "unavailable" and result.dealer_id is None
    assert result.text == ("The dealer name “Amber Arc” could not be resolved because no dealer records "
                           "are available for 209901; give the dealer code to continue.")


def test_months_too_far_apart_ask_for_the_code_without_a_lookup():
    calls = []
    result = resolve_dealer_name(statement(dealer_name="Amber Arc", periods=["202001", "202606"],
                                           measures=["commission_variance"], operation="compare"),
                                 fake_lookup(calls=calls))
    assert result.status == "invalid" and calls == []
    assert result.text == ("Dealer names can be searched across at most 24 months; 202001 and 202606 "
                           "are further apart. Give the dealer code to continue.")
