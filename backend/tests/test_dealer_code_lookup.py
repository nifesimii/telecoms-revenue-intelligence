"""Dealer-name association behavior at the query and Atlas executor boundaries."""
from __future__ import annotations

import csv
import json

import pytest

from backend import config
from backend.agent.tool_executor import execute_tool
from backend.agent.tools import TOOLS
from backend.db.connection import execute_query


@pytest.fixture
def source_files(tmp_path, monkeypatch):
    """Small source records with independently specified expected associations."""
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)
    paths = {"fbb_comm_dev_act": {}, "fbb_comm_orsc": {}}
    monkeypatch.setattr(config, "SAMPLE_DATA_PATHS", paths)

    def write(source, period, rows):
        path = tmp_path / f"{source}_{period}.csv"
        with path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["distributor_code", "distributor_name", "mon_period"])
            writer.writerows(rows)
        paths[source][period] = path
        return path

    write("fbb_comm_dev_act", "202601", [
        ("0012", "Acme Trading", "202601"),
        ("0012", "Acme Trading", "202601"),  # Duplicate transaction.
        ("20", " Acme Trading ", "202601"),
        ("99", "Acme Trading Limited", "202601"),
        ("98", "Acme-Trading", "202601"),
        ("97", "Acme  Trading", "202601"),
        ("", "Acme Trading", "202601"),
        ("96", "", "202601"),
    ])
    write("fbb_comm_dev_act", "202603", [
        ("0012", "ACME TRADING", "202603"),
        ("30", "Acme Trading", "202603"),
    ])
    write("fbb_comm_orsc", "202602", [
        ("0012", "Acme Trading", "202602"),
        ("40", "Acme Trading", "202602"),  # ORSC-only code/month.
        ("88", "Unrelated Dealer", "202602"),
    ])
    return paths, write


def lookup(**params):
    return execute_query("get_dealer_codes", {"dealer_name": "Acme Trading", **params})


def tool_lookup(**params):
    return execute_tool({
        "id": "dealer-codes-call", "name": "get_dealer_codes",
        "input": {"dealer_name": "Acme Trading", **params},
    })


def test_distinct_codes_preserve_names_leading_zeroes_and_source_history(source_files):
    result = lookup(dealer_name="  aCmE tRaDiNg  ")
    assert result.to_dict("records") == [
        {"dealer_id": "0012", "recorded_names": ["ACME TRADING", "Acme Trading"],
         "first_observed_period": "202601", "last_observed_period": "202603",
         "sources": ["fbb_comm_dev_act", "fbb_comm_orsc"]},
        {"dealer_id": "20", "recorded_names": [" Acme Trading "],
         "first_observed_period": "202601", "last_observed_period": "202601",
         "sources": ["fbb_comm_dev_act"]},
        {"dealer_id": "30", "recorded_names": ["Acme Trading"],
         "first_observed_period": "202603", "last_observed_period": "202603",
         "sources": ["fbb_comm_dev_act"]},
        {"dealer_id": "40", "recorded_names": ["Acme Trading"],
         "first_observed_period": "202602", "last_observed_period": "202602",
         "sources": ["fbb_comm_orsc"]},
    ]


@pytest.mark.parametrize("bounds, codes, first, last", [
    ({"start_period": "202602", "end_period": "202602"}, ["0012", "40"], "202602", "202602"),
    ({"start_period": "202602"}, ["0012", "30", "40"], "202602", "202603"),
    ({"end_period": "202602"}, ["0012", "20", "40"], "202601", "202602"),
])
def test_inclusive_and_open_bounds_limit_observations(source_files, bounds, codes, first, last):
    result = lookup(**bounds)
    assert result["dealer_id"].tolist() == codes
    assert result.iloc[0]["first_observed_period"] == first
    assert result.iloc[0]["last_observed_period"] == last


def test_tool_exposes_complete_coverage_even_for_no_match(source_files):
    assert "get_dealer_codes" in {tool["name"] for tool in TOOLS}
    response = tool_lookup(dealer_name="Acme")  # Partial names must not match.
    assert response["type"] == "tool_result"
    assert response["tool_use_id"] == "dealer-codes-call"
    assert not response.get("is_error")
    payload = json.loads(response["content"])
    assert payload["rows"] == []
    assert payload["row_count"] == payload["total_codes"] == 0
    assert payload["has_more"] is False
    assert payload["coverage_by_source"] == {
        "fbb_comm_dev_act": ["202601", "202603"],
        "fbb_comm_orsc": ["202602"],
    }
    assert payload["data_source"] == "SAMPLE"
    assert "not verified branches or legal entities" in payload["association_note"]
    assert "do not prove continuity" in payload["association_note"]


def test_tool_returns_codes_and_coverage_for_requested_month(source_files):
    payload = json.loads(tool_lookup(start_period="202602", end_period="202602")["content"])
    assert [row["dealer_id"] for row in payload["rows"]] == ["0012", "40"]
    assert payload["row_count"] == payload["total_codes"] == 2
    assert payload["coverage_by_source"] == {
        "fbb_comm_dev_act": [], "fbb_comm_orsc": ["202602"],
    }


def test_range_outside_available_data_has_no_coverage(source_files):
    payload = json.loads(tool_lookup(start_period="202701", end_period="202712")["content"])
    assert payload["rows"] == []
    assert payload["total_codes"] == 0
    assert payload["coverage_by_source"] == {"fbb_comm_dev_act": [], "fbb_comm_orsc": []}


def test_pagination_is_bounded_complete_and_deterministic(source_files):
    _, write = source_files
    write("fbb_comm_dev_act", "202604", [
        (f"{code:03}", "Large Dealer", "202604") for code in range(104, -1, -1)
    ])
    first = json.loads(tool_lookup(dealer_name="Large Dealer")["content"])
    second = json.loads(tool_lookup(dealer_name="Large Dealer", page=2)["content"])
    beyond = json.loads(tool_lookup(dealer_name="Large Dealer", page=3)["content"])
    assert first["row_count"] == first["page_size"] == 100
    assert first["page"] == 1 and first["has_more"] is True
    assert first["rows"][0]["dealer_id"] == "000"
    assert first["rows"][-1]["dealer_id"] == "099"
    assert [row["dealer_id"] for row in second["rows"]] == ["100", "101", "102", "103", "104"]
    assert second["page"] == 2 and second["has_more"] is False
    assert beyond["rows"] == [] and beyond["has_more"] is False
    assert first["total_codes"] == second["total_codes"] == beyond["total_codes"] == 105
    assert len({row["dealer_id"] for row in first["rows"] + second["rows"]}) == 105
    small_page = lookup(page_size=2, page=2)
    assert small_page["dealer_id"].tolist() == ["30", "40"]


@pytest.mark.parametrize("params, error", [
    ({"dealer_name": " "}, "dealer_name"),
    ({"dealer_name": None}, "dealer_name"),
    ({"dealer_name": 12}, "dealer_name"),
    ({"dealer_name": "x" * 301}, "dealer_name"),
    ({"start_period": "202600"}, "start_period"),
    ({"end_period": "202613"}, "end_period"),
    ({"start_period": "2026-01"}, "start_period"),
    ({"start_period": 202601}, "start_period"),
    ({"start_period": "202603", "end_period": "202601"}, "start_period"),
    ({"page": 0}, "page"),
    ({"page": True}, "page"),
    ({"page": "2"}, "page"),
    ({"page_size": 101}, "page_size"),
    ({"page_size": 0}, "page_size"),
    ({"page_size": 1.5}, "page_size"),
    ({"page_size": False}, "page_size"),
])
def test_invalid_inputs_fail_query_and_return_readable_tool_errors(source_files, params, error):
    with pytest.raises(ValueError, match=error):
        lookup(**params)
    response = tool_lookup(**params)
    assert response["is_error"] is True
    assert response["tool_use_id"] == "dealer-codes-call"
    assert error in response["content"]


def test_missing_source_file_is_not_silently_omitted(source_files):
    paths, _ = source_files
    paths["fbb_comm_orsc"]["202602"].unlink()
    with pytest.raises(FileNotFoundError):
        lookup()
    response = tool_lookup()
    assert response["is_error"] is True
    assert "FileNotFoundError" in response["content"]
    # Evidence outside an explicitly requested window is not required.
    assert lookup(start_period="202603")["dealer_id"].tolist() == ["0012", "30"]


def test_single_csv_source_configuration_filters_actual_record_months(source_files):
    paths, write = source_files
    path = write("fbb_comm_dev_act", "combined", [
        ("007", "Acme Trading", "202601"),
        ("008", "Acme Trading", "202603"),
    ])
    paths["fbb_comm_dev_act"] = path
    result = lookup(start_period="202603", end_period="202603")
    assert result["dealer_id"].tolist() == ["008"]
    assert result.attrs["lookup_metadata"]["coverage_by_source"] == {
        "fbb_comm_dev_act": ["202603"], "fbb_comm_orsc": [],
    }
