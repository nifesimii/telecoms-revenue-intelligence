"""End-to-end tests for the four parameterised queries against sample CSVs.

These tests exercise the public ``execute_query`` entry point in
:mod:`backend.db.connection`, which in sample mode routes to the pandas
handlers in :mod:`backend.db.queries`. Expected values are computed directly
from the CSV at test time so the assertions stay correct if the sample data
is regenerated.

Run from the project root:

    python -m pytest backend/tests/test_queries.py -v
"""
from __future__ import annotations

import os

# Force sample-data mode regardless of the developer's local .env.
os.environ["USE_SAMPLE_DATA"] = "true"

import pandas as pd  # noqa: E402  — must be imported after env var is set
import pytest  # noqa: E402

from backend import config  # noqa: E402
from backend.db.connection import execute_query  # noqa: E402

# Periods present in the sample data.
DEV_ACT_PERIOD = "202603"
ORSC_PERIOD = "202602"


def _csv_path(name: str, period: str | None = None):
    """Resolve a sample-data path that may be a Path or a {period: Path} dict."""
    entry = config.SAMPLE_DATA_PATHS[name]
    if not isinstance(entry, dict):
        return entry
    if period is not None and period in entry:
        return entry[period]
    # Fall back to the first available period.
    return next(iter(entry.values()))


@pytest.fixture(scope="module")
def dev_act_df() -> pd.DataFrame:
    # Existing tests anchor on DEV_ACT_PERIOD (202603); load that file directly.
    return pd.read_csv(_csv_path("fbb_comm_dev_act", DEV_ACT_PERIOD))


@pytest.fixture(scope="module")
def orsc_df() -> pd.DataFrame:
    return pd.read_csv(_csv_path("fbb_comm_orsc", ORSC_PERIOD))


# ---------------------------------------------------------------------------
# Query 1: get_dealer_summary
# ---------------------------------------------------------------------------


class TestDealerSummary:
    def test_returns_expected_columns(self) -> None:
        result = execute_query("get_dealer_summary", {"mon_period": DEV_ACT_PERIOD})
        expected = {
            "dealer_id",
            "dealer_name",
            "account_profile_class",
            "total_activations",
            "total_commission_ngn",
            "zero_commission_count",
            "commission_by_denomination",
        }
        assert expected.issubset(set(result.columns))

    def test_total_activations_equals_row_count(
        self, dev_act_df: pd.DataFrame
    ) -> None:
        period_rows = dev_act_df[dev_act_df["mon_period"].astype(str) == DEV_ACT_PERIOD]
        result = execute_query("get_dealer_summary", {"mon_period": DEV_ACT_PERIOD})
        assert int(result["total_activations"].sum()) == len(period_rows)

    def test_total_commission_matches_csv_sum(
        self, dev_act_df: pd.DataFrame
    ) -> None:
        period_rows = dev_act_df[
            dev_act_df["mon_period"].astype(str) == DEV_ACT_PERIOD
        ].copy()
        period_rows["commission_rate"] = period_rows["commission_rate"].fillna(0)
        expected_total = float(period_rows["commission_rate"].sum())

        result = execute_query("get_dealer_summary", {"mon_period": DEV_ACT_PERIOD})
        assert result["total_commission_ngn"].sum() == pytest.approx(
            expected_total, abs=1e-6
        )

    def test_zero_commission_count_matches_csv(
        self, dev_act_df: pd.DataFrame
    ) -> None:
        period_rows = dev_act_df[
            dev_act_df["mon_period"].astype(str) == DEV_ACT_PERIOD
        ].copy()
        period_rows["commission_rate"] = period_rows["commission_rate"].fillna(0)
        expected_zero = int((period_rows["commission_rate"] == 0).sum())

        result = execute_query("get_dealer_summary", {"mon_period": DEV_ACT_PERIOD})
        assert int(result["zero_commission_count"].sum()) == expected_zero

    def test_filter_by_distributor_code_narrows_result(
        self, dev_act_df: pd.DataFrame
    ) -> None:
        period_rows = dev_act_df[dev_act_df["mon_period"].astype(str) == DEV_ACT_PERIOD]
        # Pick a distributor known to be present in the sample.
        sample_dist = str(period_rows["distributor_code"].iloc[0])

        result = execute_query(
            "get_dealer_summary",
            {"mon_period": DEV_ACT_PERIOD, "distributor_code": sample_dist},
        )
        assert len(result) == 1
        assert str(result["dealer_id"].iloc[0]) == sample_dist

    def test_commission_by_denomination_is_dict(self) -> None:
        result = execute_query("get_dealer_summary", {"mon_period": DEV_ACT_PERIOD})
        assert len(result) > 0
        first = result["commission_by_denomination"].iloc[0]
        assert isinstance(first, dict)

    def test_sorted_descending_by_total_commission(self) -> None:
        result = execute_query("get_dealer_summary", {"mon_period": DEV_ACT_PERIOD})
        totals = result["total_commission_ngn"].tolist()
        assert totals == sorted(totals, reverse=True)

    def test_unknown_period_returns_empty(self) -> None:
        result = execute_query("get_dealer_summary", {"mon_period": "190001"})
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Query 2: get_zero_commission_records
# ---------------------------------------------------------------------------


class TestZeroCommissionRecords:
    def _pick_dealer_with_zeros(self, df: pd.DataFrame) -> str:
        period_rows = df[df["mon_period"].astype(str) == DEV_ACT_PERIOD].copy()
        period_rows["commission_rate"] = period_rows["commission_rate"].fillna(0)
        zero_rows = period_rows[period_rows["commission_rate"] == 0]
        assert len(zero_rows) > 0, "Sample data has no zero-commission rows"
        return str(zero_rows["distributor_code"].iloc[0])

    def test_returns_expected_columns(self, dev_act_df: pd.DataFrame) -> None:
        dealer = self._pick_dealer_with_zeros(dev_act_df)
        result = execute_query(
            "get_zero_commission_records",
            {"mon_period": DEV_ACT_PERIOD, "distributor_code": dealer},
        )
        expected = {
            "imei",
            "product_name",
            "product_code",
            "invoice_date",
            "first_activation_date",
            "unit_selling_price",
            "commission_rate",
        }
        assert expected == set(result.columns)

    def test_all_returned_rows_have_zero_commission(
        self, dev_act_df: pd.DataFrame
    ) -> None:
        dealer = self._pick_dealer_with_zeros(dev_act_df)
        result = execute_query(
            "get_zero_commission_records",
            {"mon_period": DEV_ACT_PERIOD, "distributor_code": dealer},
        )
        commissions = result["commission_rate"].fillna(0)
        assert (commissions == 0).all()

    def test_row_count_matches_csv(self, dev_act_df: pd.DataFrame) -> None:
        dealer = self._pick_dealer_with_zeros(dev_act_df)

        period_dealer = dev_act_df[
            (dev_act_df["mon_period"].astype(str) == DEV_ACT_PERIOD)
            & (dev_act_df["distributor_code"].astype(str) == dealer)
        ].copy()
        period_dealer["commission_rate"] = period_dealer["commission_rate"].fillna(0)
        expected_zero_count = int((period_dealer["commission_rate"] == 0).sum())

        result = execute_query(
            "get_zero_commission_records",
            {"mon_period": DEV_ACT_PERIOD, "distributor_code": dealer},
        )
        assert len(result) == expected_zero_count

    def test_dealer_with_no_zeros_returns_empty(
        self, dev_act_df: pd.DataFrame
    ) -> None:
        period_rows = dev_act_df[
            dev_act_df["mon_period"].astype(str) == DEV_ACT_PERIOD
        ].copy()
        period_rows["commission_rate"] = period_rows["commission_rate"].fillna(0)

        # Find a dealer that has only non-zero commissions in the period.
        non_zero = period_rows[period_rows["commission_rate"] > 0]
        zero = period_rows[period_rows["commission_rate"] == 0]
        clean_dealers = set(non_zero["distributor_code"].astype(str)) - set(
            zero["distributor_code"].astype(str)
        )
        if not clean_dealers:
            pytest.skip("Every dealer in sample has at least one zero record.")
        clean = next(iter(clean_dealers))

        result = execute_query(
            "get_zero_commission_records",
            {"mon_period": DEV_ACT_PERIOD, "distributor_code": clean},
        )
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Query 3: get_month_on_month_variance
# ---------------------------------------------------------------------------


class TestMonthOnMonthVariance:
    def test_returns_expected_columns_when_data_present(
        self, dev_act_df: pd.DataFrame
    ) -> None:
        dealer = str(dev_act_df["distributor_code"].iloc[0])
        result = execute_query(
            "get_month_on_month_variance",
            {
                "distributor_code": dealer,
                "current_period": DEV_ACT_PERIOD,
                "prior_period": "202602",
            },
        )
        expected = {
            "period",
            "product_denomination",
            "activation_count",
            "total_commission_ngn",
            "delta_ngn",
            "delta_pct",
        }
        assert expected == set(result.columns)

    def test_same_period_for_current_and_prior_gives_zero_delta(
        self, dev_act_df: pd.DataFrame
    ) -> None:
        # Pick a dealer with at least one activation in the period.
        dealer = str(
            dev_act_df[dev_act_df["mon_period"].astype(str) == DEV_ACT_PERIOD][
                "distributor_code"
            ].iloc[0]
        )
        result = execute_query(
            "get_month_on_month_variance",
            {
                "distributor_code": dealer,
                "current_period": DEV_ACT_PERIOD,
                "prior_period": DEV_ACT_PERIOD,
            },
        )
        # All deltas should be zero — current and prior are the same period.
        assert (result["delta_ngn"] == 0).all()
        assert (result["delta_pct"] == 0).all()

    def test_prior_period_missing_gives_full_delta_on_current(
        self, dev_act_df: pd.DataFrame
    ) -> None:
        # Pick a dealer with activations in the period.
        period_rows = dev_act_df[
            dev_act_df["mon_period"].astype(str) == DEV_ACT_PERIOD
        ].copy()
        period_rows["commission_rate"] = period_rows["commission_rate"].fillna(0)
        dealer_with_revenue = (
            period_rows[period_rows["commission_rate"] > 0]
            ["distributor_code"]
            .astype(str)
            .iloc[0]
        )

        result = execute_query(
            "get_month_on_month_variance",
            {
                "distributor_code": dealer_with_revenue,
                "current_period": DEV_ACT_PERIOD,
                "prior_period": "190001",  # synthetic period with no rows
            },
        )

        # All result rows should be in current period; delta equals total.
        current_rows = result[result["period"] == DEV_ACT_PERIOD]
        assert len(current_rows) > 0
        for _, row in current_rows.iterrows():
            assert row["delta_ngn"] == pytest.approx(
                row["total_commission_ngn"], abs=1e-6
            )

    def test_dealer_with_no_data_returns_empty(self) -> None:
        result = execute_query(
            "get_month_on_month_variance",
            {
                "distributor_code": "999999999",
                "current_period": DEV_ACT_PERIOD,
                "prior_period": "202602",
            },
        )
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Query 4: get_orsc_summary
# ---------------------------------------------------------------------------


class TestOrscSummary:
    def test_returns_expected_columns(self) -> None:
        result = execute_query("get_orsc_summary", {"mon_period": ORSC_PERIOD})
        expected = {
            "dealer_id",
            "dealer_name",
            "account_profile_class",
            "device_count",
            "total_subscription_amount_ngn",
            "zero_amount_count",
        }
        assert expected == set(result.columns)

    def test_device_count_matches_csv(self, orsc_df: pd.DataFrame) -> None:
        period_rows = orsc_df[orsc_df["mon_period"].astype(str) == ORSC_PERIOD]
        result = execute_query("get_orsc_summary", {"mon_period": ORSC_PERIOD})
        assert int(result["device_count"].sum()) == len(period_rows)

    def test_total_subscription_matches_csv(self, orsc_df: pd.DataFrame) -> None:
        period_rows = orsc_df[
            orsc_df["mon_period"].astype(str) == ORSC_PERIOD
        ].copy()
        period_rows["data_subscription_amount"] = period_rows[
            "data_subscription_amount"
        ].fillna(0)
        expected_total = float(period_rows["data_subscription_amount"].sum())

        result = execute_query("get_orsc_summary", {"mon_period": ORSC_PERIOD})
        assert result["total_subscription_amount_ngn"].sum() == pytest.approx(
            expected_total, abs=1e-6
        )

    def test_zero_amount_count_matches_csv(self, orsc_df: pd.DataFrame) -> None:
        period_rows = orsc_df[
            orsc_df["mon_period"].astype(str) == ORSC_PERIOD
        ].copy()
        period_rows["data_subscription_amount"] = period_rows[
            "data_subscription_amount"
        ].fillna(0)
        expected_zero = int((period_rows["data_subscription_amount"] == 0).sum())

        result = execute_query("get_orsc_summary", {"mon_period": ORSC_PERIOD})
        assert int(result["zero_amount_count"].sum()) == expected_zero

    def test_filter_by_distributor_code(self, orsc_df: pd.DataFrame) -> None:
        period_rows = orsc_df[orsc_df["mon_period"].astype(str) == ORSC_PERIOD]
        sample_dist = str(period_rows["distributor_code"].iloc[0])

        result = execute_query(
            "get_orsc_summary",
            {"mon_period": ORSC_PERIOD, "distributor_code": sample_dist},
        )
        assert len(result) == 1
        assert str(result["dealer_id"].iloc[0]) == sample_dist

    def test_sorted_descending_by_subscription_total(self) -> None:
        result = execute_query("get_orsc_summary", {"mon_period": ORSC_PERIOD})
        totals = result["total_subscription_amount_ngn"].tolist()
        assert totals == sorted(totals, reverse=True)


# ---------------------------------------------------------------------------
# Dispatcher behaviour
# ---------------------------------------------------------------------------


def test_execute_query_unknown_name_raises() -> None:
    with pytest.raises(ValueError):
        execute_query("does_not_exist", {})


# ---------------------------------------------------------------------------
# Production-export sanity checks — pin the headline figures Finance signed
# off on. If anyone re-pulls the sample data and these change, the tests fail
# loudly so we re-confirm with Finance rather than drifting silently.
# ---------------------------------------------------------------------------

# Expected aggregates straight from the production export the user pinned.
_MAR_EXPECTED = {
    "total_commission_ngn": 47_642_607.64,
    "total_activations": 30_892,
    "zero_commission_count": 6_005,
    "unique_dealers": 922,
}
_FEB_EXPECTED = {
    "total_commission_ngn": 41_649_665.49,
    "total_activations": 25_537,
    "zero_commission_count": 4_176,
    "unique_dealers": 939,
}


def test_dealer_summary_202603_totals() -> None:
    df = execute_query("get_dealer_summary", {"mon_period": "202603"})
    assert float(df["total_commission_ngn"].sum()) == pytest.approx(
        _MAR_EXPECTED["total_commission_ngn"], abs=0.01
    )
    assert int(df["total_activations"].sum()) == _MAR_EXPECTED["total_activations"]
    assert int(df["zero_commission_count"].sum()) == _MAR_EXPECTED["zero_commission_count"]
    assert len(df) == _MAR_EXPECTED["unique_dealers"]


def test_dealer_summary_202602_totals() -> None:
    df = execute_query("get_dealer_summary", {"mon_period": "202602"})
    assert float(df["total_commission_ngn"].sum()) == pytest.approx(
        _FEB_EXPECTED["total_commission_ngn"], abs=0.01
    )
    assert int(df["total_activations"].sum()) == _FEB_EXPECTED["total_activations"]
    assert int(df["zero_commission_count"].sum()) == _FEB_EXPECTED["zero_commission_count"]
    assert len(df) == _FEB_EXPECTED["unique_dealers"]


def test_month_on_month_variance_has_two_periods() -> None:
    """Variance must return rows for both 202602 and 202603 for the top March dealer."""
    march = execute_query("get_dealer_summary", {"mon_period": "202603"})
    top = march.sort_values("total_commission_ngn", ascending=False).iloc[0]
    top_code = str(top["dealer_id"])

    var = execute_query(
        "get_month_on_month_variance",
        {
            "distributor_code": top_code,
            "current_period": "202603",
            "prior_period": "202602",
        },
    )

    periods_present = set(var["period"].astype(str).tolist())
    assert "202603" in periods_present, (
        f"Variance result missing 202603 rows for top dealer {top_code}"
    )
    assert "202602" in periods_present, (
        f"Variance result missing 202602 rows for top dealer {top_code}"
    )

    # The current-period rows must carry non-zero deltas where prior data exists
    # (otherwise the variance computation is silently broken).
    current_rows = var[var["period"].astype(str) == "202603"]
    assert len(current_rows) > 0
    # At least one denomination should have a non-zero delta — the top dealer
    # didn't transact identically across the two months.
    assert (current_rows["delta_ngn"] != 0).any(), (
        "Expected at least one non-zero delta on the top dealer's current rows"
    )


def test_commission_growth_feb_to_mar() -> None:
    """Aggregate Feb -> Mar growth ~ +NGN 5,992,942.15 (+14.4%)."""
    mar_total = float(
        execute_query("get_dealer_summary", {"mon_period": "202603"})[
            "total_commission_ngn"
        ].sum()
    )
    feb_total = float(
        execute_query("get_dealer_summary", {"mon_period": "202602"})[
            "total_commission_ngn"
        ].sum()
    )
    delta = mar_total - feb_total
    pct = delta / feb_total * 100.0

    assert delta == pytest.approx(5_992_942.15, abs=0.01)
    assert pct == pytest.approx(14.4, abs=0.1)
