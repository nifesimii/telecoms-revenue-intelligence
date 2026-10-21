"""Exact compatibility checks for the optimized sample dealer aggregation.

The frozen pre-optimization handler is an independent differential oracle.
"""
import os
os.environ["USE_SAMPLE_DATA"] = "true"

from typing import Any
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import config
from backend.db import queries
from backend.db.connection import execute_query
from backend.api.commission_routes import router

_load_csv = queries._load_csv
_filter_period_and_distributor = queries._filter_period_and_distributor
_norm_str = queries._norm_str


@pytest.fixture(autouse=True)
def sample_mode(monkeypatch):
    # config loads dotenv with override=True, so setting os.environ alone is
    # insufficient when the developer has a live configuration.
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)
    assert config.USE_SAMPLE_DATA is True


def legacy_dealer_summary(params: dict) -> pd.DataFrame:
    mon_period = params["mon_period"]
    distributor_code = params.get("distributor_code")

    df = _load_csv("fbb_comm_dev_act", period=_norm_str(mon_period))
    df = _filter_period_and_distributor(df, mon_period, distributor_code)

    df["commission_rate"] = df["commission_rate"].fillna(0).astype(float)
    df["product_denomination"] = df["product_denomination"].fillna("")

    rows: list[dict[str, Any]] = []
    for dist_code, group in df.groupby("distributor_code", sort=False):
        denom_group = group[group["product_denomination"] != ""]
        commission_by_denom = (
            denom_group.groupby("product_denomination")["commission_rate"].sum().to_dict()
            if not denom_group.empty
            else {}
        )
        commission_by_denom = {k: float(v) for k, v in commission_by_denom.items()}

        rows.append(
            {
                # API convention: dealer_id / dealer_name in the response.
                # Raw column in fbb_comm_dev_act is distributor_code — we
                # keep that name inside the DataFrame and rename at the
                # return boundary. See ARCHITECTURE.md "Naming conventions".
                "dealer_id": _norm_str(dist_code),
                "dealer_name": str(group["distributor_name"].iloc[0]),
                "account_profile_class": str(group["account_profile_class"].iloc[0]),
                "total_activations": int(len(group)),
                "total_commission_ngn": float(group["commission_rate"].sum()),
                "zero_commission_count": int((group["commission_rate"] == 0).sum()),
                "commission_by_denomination": commission_by_denom,
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "dealer_id",
                "dealer_name",
                "account_profile_class",
                "total_activations",
                "total_commission_ngn",
                "zero_commission_count",
                "commission_by_denomination",
            ]
        )

    return (
        pd.DataFrame(rows)
        .sort_values("total_commission_ngn", ascending=False)
        .reset_index(drop=True)
    )


PERIODS = tuple(config.SAMPLE_DATA_PATHS["fbb_comm_dev_act"])


@pytest.mark.parametrize("period", PERIODS)
def test_fixture_period_matches_legacy_exactly(period):
    params = {"mon_period": period}
    expected = legacy_dealer_summary(params)
    actual = execute_query("get_dealer_summary", params)
    pd.testing.assert_frame_equal(actual, expected, check_exact=True)
    # Dict equality ignores insertion order; denomination presentation must not.
    assert [list(d.items()) for d in actual.commission_by_denomination] == [
        list(d.items()) for d in expected.commission_by_denomination]
    dealers = [expected.iloc[0].dealer_id, expected.iloc[-1].dealer_id,
               expected.loc[expected.zero_commission_count > 0].iloc[0].dealer_id,
               "missing", "", None]
    for dealer in dealers:
        params["distributor_code"] = dealer
        pd.testing.assert_frame_equal(
            execute_query("get_dealer_summary", params),
            legacy_dealer_summary(params), check_exact=True)


@pytest.fixture
def edge_csv(tmp_path, monkeypatch):
    frame = pd.DataFrame([
        # First-row null metadata must not become later non-null metadata.
        (202603, 2, None, None, "Z", 0.1),
        (202603, 1, "First", "A", "", 7),
        (202603, 2, "Later", "B", "A", 0.2),
        (202603, 2, "Later", "B", "A", None),
        (202603, 2, "Later", "B", None, -0.3),
        (202603, 1, "Changed", "B", None, None),
        (202603, 3, "Tie", "A", "Z", 7),
        (202603, 4, "Zero", "A", "Z", None),
        (202603, None, "No dealer", "A", "Z", 100),
        (202602, 1, "Other month", "B", "Z", 999),
    ], columns=["mon_period", "distributor_code", "distributor_name",
                "account_profile_class", "product_denomination", "commission_rate"])
    path = tmp_path / "edge.csv"
    frame.to_csv(path, index=False)
    monkeypatch.setitem(config.SAMPLE_DATA_PATHS, "fbb_comm_dev_act", path)
    queries._clear_csv_cache()
    yield
    queries._clear_csv_cache()


@pytest.mark.parametrize("period,dealer", [
    ("202603", None), (202603.0, "2"), ("202603", 2.0),
    ("202603", ""), ("202603", "missing"), ("190001", None),
    ("202602", "1"),
])
def test_edge_cases_preserve_first_row_nulls_sums_order_and_filtering(edge_csv, period, dealer):
    params = {"mon_period": period, "distributor_code": dealer}
    actual = execute_query("get_dealer_summary", params)
    pd.testing.assert_frame_equal(actual, legacy_dealer_summary(params), check_exact=True)
    if period == "202603" and dealer is None:
        by_id = actual.set_index("dealer_id")
        assert by_id.loc["2", "dealer_name"] == "nan"
        assert by_id.loc["2", "account_profile_class"] == "nan"
        assert by_id.loc["2", "total_activations"] == 4
        assert by_id.loc["2", "zero_commission_count"] == 1
        assert by_id.loc["1", "commission_by_denomination"] == {}
        assert list(by_id.loc["2", "commission_by_denomination"]) == ["A", "Z"]
        assert "" not in by_id.index


@pytest.mark.parametrize("suffix", [
    "", "&status=with_zero&limit=10&offset=10",
    "&status=all_zero&sort_by=dealer_name&direction=asc",
    "&search=1&sort_by=delta_ngn&direction=asc",
])
def test_commission_api_matches_legacy(monkeypatch, suffix):
    # Mount the production router without app lifespan/provider integrations.
    app = FastAPI()
    app.include_router(router)
    url = "/commissions?mon_period=202603&prior_period=202602" + suffix
    with TestClient(app) as client:
        actual = client.get(url)
        assert actual.status_code == 200
        with monkeypatch.context() as patch:
            patch.setitem(queries.SAMPLE_HANDLERS, "get_dealer_summary", legacy_dealer_summary)
            expected = client.get(url)
        assert expected.status_code == 200
    actual_body, expected_body = actual.json(), expected.json()
    actual_body.pop("generated_at")
    expected_body.pop("generated_at")
    assert actual_body == expected_body
