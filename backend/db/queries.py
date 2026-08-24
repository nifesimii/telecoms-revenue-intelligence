"""All parameterized SQL queries. SELECT only.

Single source of truth for every data access in the platform. Each of the four
queries is defined twice:

  * ``SQL[name]`` — a parameterized Presto/Trino SQL string using ``%(name)s``
    placeholders (DB-API named-paramstyle).
  * ``SAMPLE_HANDLERS[name]`` — a pandas-based implementation reading the
    sample CSVs under ``data/samples/`` so the agent loop can run end-to-end
    without a live Presto connection.

Both implementations must return DataFrames with identical column shapes.

Rules (from CLAUDE.md):
  * SELECT only — no INSERT, UPDATE, DELETE, DROP, CREATE.
  * Always filter by mon_period.
  * Read from the ``hive5.development`` schema only.
  * No string interpolation in SQL — parameters only.

The four tables in scope (fully qualified for Presto):
  * ``hive5.development.fbb_comm_dev_act``
  * ``hive5.development.fbb_comm_orsc``
  * ``hive5.development.fbb_comm_inv_sales`` (no query targets it yet)
  * ``hive5.development.usp_dimension`` (used for reference / future joins)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pandas as pd

from backend import config

# ---------------------------------------------------------------------------
# CSV loading helpers (sample mode only)
# ---------------------------------------------------------------------------


def _read_one(path: Path, label: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Sample CSV not found: {label} ({path})")
    return pd.read_csv(path)


# In-process CSV cache. Sample CSVs are bundled into the image and never
# change at runtime, so we can safely keep the parsed frames in memory
# once the first request has warmed them up. Before this cache, an audit
# run doing ~500 per-partner queries meant ~1500 re-reads of the same
# CSVs — a 120s+ HOTFIX-level slowdown on Render's shared-CPU tier.
# Callers get a defensive .copy() so they can filter/mutate without
# corrupting the cache.
_CSV_CACHE: dict[tuple[str, str | None], pd.DataFrame] = {}


def _clear_csv_cache() -> None:
    """Test/debug hook — drop the in-process CSV cache."""
    _CSV_CACHE.clear()


def _load_csv(name: str, period: str | None = None) -> pd.DataFrame:
    """Read sample CSV(s) by logical name, cached in-process.

    ``config.SAMPLE_DATA_PATHS[name]`` may be either:
      * a single ``Path`` — ``period`` is ignored; the file is returned as-is.
      * a ``dict[period, Path]`` — if ``period`` matches a key, only that
        file is loaded. Otherwise every available period CSV is concatenated.

    Concatenating across periods is what enables month-on-month queries to
    pull the whole window in one go.

    Cache keyed on ``(name, period)``. Callers receive a copy — safe to
    filter or mutate. Bundled CSVs don't change at runtime, so cache
    entries never expire; call :func:`_clear_csv_cache` in tests that
    need a clean read.
    """
    cache_key = (name, period)
    cached = _CSV_CACHE.get(cache_key)
    if cached is not None:
        return cached.copy()

    entry = config.SAMPLE_DATA_PATHS[name]

    if isinstance(entry, Path):
        df = _read_one(entry, name)
    elif isinstance(entry, dict):
        if period is not None and period in entry:
            df = _read_one(entry[period], f"{name}[{period}]")
        else:
            frames = []
            for p, path in entry.items():
                if path.exists():
                    frames.append(_read_one(path, f"{name}[{p}]"))
            if not frames:
                raise FileNotFoundError(
                    f"No CSVs found under SAMPLE_DATA_PATHS[{name!r}]: {entry}"
                )
            df = pd.concat(frames, ignore_index=True)
    else:
        raise TypeError(
            f"Unsupported SAMPLE_DATA_PATHS entry for {name!r}: {type(entry).__name__}"
        )

    _CSV_CACHE[cache_key] = df
    return df.copy()


def _norm_str(value: Any) -> str:
    """Normalise a value to its string form for cross-type comparison."""
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


# ---------------------------------------------------------------------------
# Presto SQL strings
# ---------------------------------------------------------------------------

_SQL_GET_DEALER_SUMMARY = """
WITH base AS (
    SELECT
        distributor_code,
        distributor_name,
        account_profile_class,
        product_denomination,
        COALESCE(commission_rate, 0) AS commission_rate
    FROM hive5.development.fbb_comm_dev_act
    WHERE mon_period = CAST(%(mon_period)s AS BIGINT)
      AND (%(distributor_code)s IS NULL
           OR distributor_code = CAST(%(distributor_code)s AS BIGINT))
),
per_denom AS (
    SELECT
        distributor_code,
        product_denomination,
        SUM(commission_rate) AS denom_total
    FROM base
    WHERE product_denomination IS NOT NULL AND product_denomination <> ''
    GROUP BY distributor_code, product_denomination
),
agg AS (
    SELECT
        distributor_code,
        MAX(distributor_name) AS distributor_name,
        MAX(account_profile_class) AS account_profile_class,
        COUNT(*) AS total_activations,
        SUM(commission_rate) AS total_commission_ngn,
        SUM(CASE WHEN commission_rate = 0 THEN 1 ELSE 0 END) AS zero_commission_count
    FROM base
    GROUP BY distributor_code
)
SELECT
    a.distributor_code,
    a.distributor_name,
    a.account_profile_class,
    a.total_activations,
    a.total_commission_ngn,
    a.zero_commission_count,
    COALESCE(
        map_agg(p.product_denomination, p.denom_total),
        MAP(ARRAY[], ARRAY[])
    ) AS commission_by_denomination
FROM agg a
LEFT JOIN per_denom p USING (distributor_code)
GROUP BY a.distributor_code, a.distributor_name, a.account_profile_class,
         a.total_activations, a.total_commission_ngn, a.zero_commission_count
ORDER BY a.total_commission_ngn DESC
"""

_SQL_GET_ZERO_COMMISSION_RECORDS = """
SELECT
    imei,
    product_name,
    product_code,
    invoice_date,
    first_activation_date,
    unit_selling_price,
    commission_rate
FROM hive5.development.fbb_comm_dev_act
WHERE mon_period = CAST(%(mon_period)s AS BIGINT)
  AND distributor_code = CAST(%(distributor_code)s AS BIGINT)
  AND (commission_rate IS NULL OR commission_rate = 0)
ORDER BY first_activation_date
"""

_SQL_GET_MONTH_ON_MONTH_VARIANCE = """
WITH base AS (
    SELECT
        mon_period,
        COALESCE(product_denomination, 'UNCLASSIFIED') AS product_denomination,
        COALESCE(commission_rate, 0) AS commission_rate,
        imei
    FROM hive5.development.fbb_comm_dev_act
    WHERE distributor_code = CAST(%(distributor_code)s AS BIGINT)
      AND mon_period IN (
          CAST(%(current_period)s AS BIGINT),
          CAST(%(prior_period)s AS BIGINT)
      )
),
agg AS (
    SELECT
        CAST(mon_period AS VARCHAR) AS period,
        product_denomination,
        COUNT(*) AS activation_count,
        SUM(commission_rate) AS total_commission_ngn
    FROM base
    GROUP BY mon_period, product_denomination
),
current_totals AS (
    SELECT product_denomination, total_commission_ngn AS cur_total
    FROM agg
    WHERE period = %(current_period)s
),
prior_totals AS (
    SELECT product_denomination, total_commission_ngn AS prior_total
    FROM agg
    WHERE period = %(prior_period)s
)
SELECT
    a.period,
    a.product_denomination,
    a.activation_count,
    a.total_commission_ngn,
    CASE
        WHEN a.period = %(current_period)s
        THEN COALESCE(c.cur_total, 0) - COALESCE(p.prior_total, 0)
        ELSE 0
    END AS delta_ngn,
    CASE
        WHEN a.period = %(current_period)s AND COALESCE(p.prior_total, 0) <> 0
        THEN (COALESCE(c.cur_total, 0) - COALESCE(p.prior_total, 0))
             / COALESCE(p.prior_total, 0) * 100.0
        WHEN a.period = %(current_period)s AND COALESCE(c.cur_total, 0) > 0
        THEN 100.0
        ELSE 0
    END AS delta_pct
FROM agg a
LEFT JOIN current_totals c USING (product_denomination)
LEFT JOIN prior_totals p USING (product_denomination)
ORDER BY a.product_denomination, a.period
"""

_SQL_GET_ORSC_SUMMARY = """
SELECT
    distributor_code,
    MAX(distributor_name) AS distributor_name,
    MAX(account_profile_class) AS account_profile_class,
    COUNT(*) AS device_count,
    SUM(COALESCE(data_subscription_amount, 0)) AS total_subscription_amount_ngn,
    SUM(CASE WHEN COALESCE(data_subscription_amount, 0) = 0 THEN 1 ELSE 0 END)
        AS zero_amount_count
FROM hive5.development.fbb_comm_orsc
WHERE mon_period = CAST(%(mon_period)s AS BIGINT)
  AND (%(distributor_code)s IS NULL
       OR distributor_code = CAST(%(distributor_code)s AS BIGINT))
GROUP BY distributor_code
ORDER BY total_subscription_amount_ngn DESC
"""


_SQL_GET_ACTIVATION_SUMMARY = """
SELECT
    CAST(distributor_code AS VARCHAR) AS dealer_id,
    MAX(distributor_name) AS dealer_name,
    COALESCE(MAX(account_profile_class), '') AS account_profile_class,
    CAST(mon_period AS VARCHAR) AS report_month,
    COUNT(*) AS activation_count,
    SUM(CASE WHEN COALESCE(commission_rate, 0) > 0 THEN 1 ELSE 0 END)
        AS qualified_activation_count,
    SUM(CASE WHEN COALESCE(commission_rate, 0) = 0 THEN 1 ELSE 0 END)
        AS non_qualified_activation_count,
    SUM(COALESCE(commission_rate, 0)) AS activation_commission_amount,
    ROUND(
        SUM(CASE WHEN COALESCE(commission_rate, 0) > 0 THEN 1.0 ELSE 0.0 END)
            * 100.0
            / NULLIF(COUNT(*), 0),
        2
    ) AS qualification_rate_pct
FROM hive5.development.fbb_comm_dev_act
WHERE mon_period = CAST(%(mon_period)s AS BIGINT)
GROUP BY distributor_code, mon_period
ORDER BY activation_count DESC
"""

_SQL_GET_ACTIVATION_VARIANCE = """
WITH per_period AS (
    SELECT
        distributor_code,
        MAX(distributor_name) AS distributor_name,
        CAST(mon_period AS VARCHAR) AS period,
        COUNT(*) AS activation_count,
        SUM(CASE WHEN COALESCE(commission_rate, 0) > 0 THEN 1 ELSE 0 END)
            AS qualified_count,
        SUM(COALESCE(commission_rate, 0)) AS commission_amount,
        ROUND(
            SUM(CASE WHEN COALESCE(commission_rate, 0) > 0 THEN 1.0 ELSE 0.0 END)
                * 100.0
                / NULLIF(COUNT(*), 0),
            2
        ) AS qualification_rate
    FROM hive5.development.fbb_comm_dev_act
    WHERE mon_period IN (
        CAST(%(period_a)s AS BIGINT),
        CAST(%(period_b)s AS BIGINT)
    )
    GROUP BY distributor_code, mon_period
)
SELECT
    CAST(a.distributor_code AS VARCHAR) AS dealer_id,
    COALESCE(b.distributor_name, a.distributor_name) AS dealer_name,
    %(period_a)s AS period_a,
    %(period_b)s AS period_b,
    a.activation_count AS activation_count_a,
    b.activation_count AS activation_count_b,
    b.activation_count - a.activation_count AS delta_activations,
    b.commission_amount - a.commission_amount AS delta_commission_ngn,
    ROUND(b.qualification_rate - a.qualification_rate, 2)
        AS delta_qualification_rate
FROM per_period a
INNER JOIN per_period b USING (distributor_code)
WHERE a.period = %(period_a)s AND b.period = %(period_b)s
ORDER BY ABS(b.activation_count - a.activation_count) DESC
"""

_SQL_GET_ACTIVATION_EXCEPTIONS = """
WITH summary AS (
    SELECT
        CAST(distributor_code AS VARCHAR) AS dealer_id,
        MAX(distributor_name) AS dealer_name,
        COALESCE(MAX(account_profile_class), '') AS account_profile_class,
        COUNT(*) AS activation_count,
        SUM(CASE WHEN COALESCE(commission_rate, 0) > 0 THEN 1 ELSE 0 END)
            AS qualified_activation_count,
        SUM(COALESCE(commission_rate, 0)) AS activation_commission_amount,
        ROUND(
            SUM(CASE WHEN COALESCE(commission_rate, 0) > 0 THEN 1.0 ELSE 0.0 END)
                * 100.0
                / NULLIF(COUNT(*), 0),
            2
        ) AS qualification_rate_pct
    FROM hive5.development.fbb_comm_dev_act
    WHERE mon_period = CAST(%(mon_period)s AS BIGINT)
    GROUP BY distributor_code
),
stats AS (
    SELECT
        AVG(CAST(activation_count AS DOUBLE)) AS mean_activations,
        STDDEV(CAST(activation_count AS DOUBLE)) AS std_activations
    FROM summary
)
SELECT s.dealer_id, s.dealer_name, s.account_profile_class,
       'ALL_UNQUALIFIED' AS exception_type,
       s.activation_count, s.qualified_activation_count,
       s.qualification_rate_pct, s.activation_commission_amount
FROM summary s
WHERE s.activation_count > 0 AND s.qualified_activation_count = 0
UNION ALL
SELECT s.dealer_id, s.dealer_name, s.account_profile_class,
       'HIGH_UNQUALIFIED_RATE' AS exception_type,
       s.activation_count, s.qualified_activation_count,
       s.qualification_rate_pct, s.activation_commission_amount
FROM summary s
WHERE s.qualification_rate_pct < 50
UNION ALL
SELECT s.dealer_id, s.dealer_name, s.account_profile_class,
       'UNUSUAL_VOLUME' AS exception_type,
       s.activation_count, s.qualified_activation_count,
       s.qualification_rate_pct, s.activation_commission_amount
FROM summary s
CROSS JOIN stats st
WHERE CAST(s.activation_count AS DOUBLE)
      >= st.mean_activations + 2.0 * st.std_activations
ORDER BY exception_type, activation_count DESC
"""


_SQL_GET_INVENTORY_COMPARISON = """
WITH dev_act AS (
    SELECT
        CAST(distributor_code AS VARCHAR) AS dealer_id,
        MAX(distributor_name) AS dealer_name,
        CAST(product_code AS VARCHAR) AS product_code,
        MAX(product_name) AS product_name,
        COUNT(*) AS activation_count,
        SUM(CASE WHEN COALESCE(commission_rate, 0) > 0 THEN 1 ELSE 0 END)
            AS qualified_count
    FROM hive5.development.fbb_comm_dev_act
    WHERE mon_period = CAST(%(mon_period)s AS BIGINT)
    GROUP BY distributor_code, product_code
),
fbb_products AS (
    SELECT DISTINCT product_code FROM dev_act
),
ifs_dedup AS (
    SELECT DISTINCT
        customer_no,
        part_no,
        implied_units,
        actual_completion_date
    FROM hive5.development.ifs_invoice_history
    WHERE CAST(part_no AS VARCHAR) IN (SELECT product_code FROM fbb_products)
),
ifs_aggr AS (
    SELECT
        CAST(customer_no AS VARCHAR) AS dealer_id,
        CAST(part_no AS VARCHAR) AS product_code,
        SUM(implied_units) AS total_units_purchased
    FROM ifs_dedup
    GROUP BY customer_no, part_no
)
SELECT
    COALESCE(d.dealer_id, i.dealer_id) AS dealer_id,
    d.dealer_name,
    COALESCE(d.product_code, i.product_code) AS product_code,
    d.product_name,
    COALESCE(d.activation_count, 0) AS activation_count,
    COALESCE(d.qualified_count, 0) AS qualified_count,
    i.total_units_purchased,
    CASE
        WHEN i.total_units_purchased IS NULL THEN NULL
        ELSE CAST(d.activation_count AS DOUBLE) - i.total_units_purchased
    END AS inventory_gap,
    CASE
        WHEN i.total_units_purchased IS NULL OR i.total_units_purchased = 0 THEN NULL
        ELSE ROUND(
            (CAST(d.activation_count AS DOUBLE) - i.total_units_purchased)
            / i.total_units_purchased * 100.0,
            1
        )
    END AS gap_pct,
    CASE
        WHEN i.total_units_purchased IS NULL THEN 'NO_INVOICE_RECORD'
        WHEN d.activation_count > i.total_units_purchased THEN 'CONFIRMED_MISMATCH'
        ELSE 'WITHIN_ALLOCATION'
    END AS finding_type
FROM dev_act d
FULL OUTER JOIN ifs_aggr i
    ON d.dealer_id = i.dealer_id AND d.product_code = i.product_code
WHERE COALESCE(d.activation_count, 0) > 0
ORDER BY
    CASE finding_type
        WHEN 'CONFIRMED_MISMATCH' THEN 0
        WHEN 'NO_INVOICE_RECORD' THEN 1
        ELSE 2
    END,
    activation_count DESC
"""


_SQL_GET_PAYMENT_SUMMARY = """
-- Phase 4: payment simulation source. The Presto path would read from a
-- materialised view; the sample path reads payment_simulation.csv directly.
SELECT
    distributor_code,
    distributor_name,
    account_profile_class,
    report_month,
    commission_owed,
    amount_paid,
    amount_unpaid,
    payment_status,
    payment_channel,
    payment_date,
    exception_flag,
    data_source
FROM hive5.development.payment_simulation
WHERE report_month = %(mon_period)s
ORDER BY amount_unpaid DESC
"""

_SQL_GET_PAYMENT_EXCEPTIONS = """
SELECT
    distributor_code,
    distributor_name,
    account_profile_class,
    report_month,
    commission_owed,
    amount_paid,
    amount_unpaid,
    payment_status,
    payment_channel,
    payment_date,
    exception_flag,
    data_source
FROM hive5.development.payment_simulation
WHERE report_month = %(mon_period)s
  AND payment_status <> 'FULLY_PAID'
ORDER BY
    CASE payment_status
        WHEN 'DISPUTED' THEN 0
        WHEN 'PARTIALLY_PAID' THEN 1
        WHEN 'PENDING' THEN 2
        ELSE 3
    END,
    amount_unpaid DESC
"""

_SQL_GET_PAYMENT_VARIANCE = """
WITH per_period AS (
    SELECT
        distributor_code,
        MAX(distributor_name) AS distributor_name,
        report_month,
        SUM(commission_owed) AS commission_owed,
        SUM(amount_paid) AS amount_paid,
        MAX(payment_status) AS payment_status
    FROM hive5.development.payment_simulation
    WHERE report_month IN (%(period_a)s, %(period_b)s)
    GROUP BY distributor_code, report_month
)
SELECT
    a.distributor_code,
    COALESCE(b.distributor_name, a.distributor_name) AS distributor_name,
    a.commission_owed AS commission_owed_a,
    a.amount_paid AS amount_paid_a,
    a.payment_status AS payment_status_a,
    b.commission_owed AS commission_owed_b,
    b.amount_paid AS amount_paid_b,
    b.payment_status AS payment_status_b,
    b.amount_paid - a.amount_paid AS delta_paid,
    CASE WHEN a.payment_status <> b.payment_status THEN TRUE ELSE FALSE END
        AS status_changed
FROM per_period a
INNER JOIN per_period b
    ON a.distributor_code = b.distributor_code
WHERE a.report_month = %(period_a)s AND b.report_month = %(period_b)s
ORDER BY ABS(b.amount_paid - a.amount_paid) DESC
"""


SQL: dict[str, str] = {
    "get_dealer_summary": _SQL_GET_DEALER_SUMMARY.strip(),
    "get_zero_commission_records": _SQL_GET_ZERO_COMMISSION_RECORDS.strip(),
    "get_month_on_month_variance": _SQL_GET_MONTH_ON_MONTH_VARIANCE.strip(),
    "get_orsc_summary": _SQL_GET_ORSC_SUMMARY.strip(),
    # --- Phase 2: Activation Intelligence ---
    "get_activation_summary": _SQL_GET_ACTIVATION_SUMMARY.strip(),
    "get_activation_variance": _SQL_GET_ACTIVATION_VARIANCE.strip(),
    "get_activation_exceptions": _SQL_GET_ACTIVATION_EXCEPTIONS.strip(),
    # --- Phase 3: Inventory Assurance ---
    "get_inventory_comparison": _SQL_GET_INVENTORY_COMPARISON.strip(),
    # --- Phase 4: Payment Intelligence ---
    "get_payment_summary": _SQL_GET_PAYMENT_SUMMARY.strip(),
    "get_payment_exceptions": _SQL_GET_PAYMENT_EXCEPTIONS.strip(),
    "get_payment_variance": _SQL_GET_PAYMENT_VARIANCE.strip(),
}


# ---------------------------------------------------------------------------
# pandas sample-mode handlers
# ---------------------------------------------------------------------------


def _filter_period_and_distributor(
    df: pd.DataFrame,
    mon_period: str,
    distributor_code: str | None,
) -> pd.DataFrame:
    out = df[df["mon_period"].apply(_norm_str) == _norm_str(mon_period)]
    if distributor_code is not None and distributor_code != "":
        out = out[out["distributor_code"].apply(_norm_str) == _norm_str(distributor_code)]
    return out.copy()


def _sample_get_dealer_summary(params: dict) -> pd.DataFrame:
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


def _sample_get_zero_commission_records(params: dict) -> pd.DataFrame:
    mon_period = params["mon_period"]
    distributor_code = params["distributor_code"]

    df = _load_csv("fbb_comm_dev_act", period=_norm_str(mon_period))
    df = _filter_period_and_distributor(df, mon_period, distributor_code)

    zero_mask = df["commission_rate"].isna() | (df["commission_rate"] == 0)
    df = df[zero_mask]

    cols = [
        "imei",
        "product_name",
        "product_code",
        "invoice_date",
        "first_activation_date",
        "unit_selling_price",
        "commission_rate",
    ]
    return df[cols].sort_values("first_activation_date").reset_index(drop=True)


def _sample_get_month_on_month_variance(params: dict) -> pd.DataFrame:
    distributor_code = params["distributor_code"]
    current_period = _norm_str(params["current_period"])
    prior_period = _norm_str(params["prior_period"])

    # Load ALL period CSVs and concatenate — the variance query needs both
    # current and prior months in one frame.
    df = _load_csv("fbb_comm_dev_act", period=None)
    df = df[df["distributor_code"].apply(_norm_str) == _norm_str(distributor_code)]
    df = df[df["mon_period"].apply(_norm_str).isin([current_period, prior_period])].copy()
    df["commission_rate"] = df["commission_rate"].fillna(0).astype(float)
    df["product_denomination"] = df["product_denomination"].fillna("UNCLASSIFIED")
    df["period"] = df["mon_period"].apply(_norm_str)

    if df.empty:
        return pd.DataFrame(
            columns=[
                "period",
                "product_denomination",
                "activation_count",
                "total_commission_ngn",
                "delta_ngn",
                "delta_pct",
            ]
        )

    agg = (
        df.groupby(["period", "product_denomination"], sort=False)
        .agg(
            activation_count=("imei", "count"),
            total_commission_ngn=("commission_rate", "sum"),
        )
        .reset_index()
    )

    # Per-denomination totals for delta calculation.
    cur_totals = (
        agg[agg["period"] == current_period]
        .set_index("product_denomination")["total_commission_ngn"]
        .to_dict()
    )
    prior_totals = (
        agg[agg["period"] == prior_period]
        .set_index("product_denomination")["total_commission_ngn"]
        .to_dict()
    )

    delta_ngn_col: list[float] = []
    delta_pct_col: list[float] = []
    for _, row in agg.iterrows():
        if row["period"] != current_period:
            delta_ngn_col.append(0.0)
            delta_pct_col.append(0.0)
            continue
        cur = float(cur_totals.get(row["product_denomination"], 0.0))
        prior = float(prior_totals.get(row["product_denomination"], 0.0))
        delta = cur - prior
        delta_ngn_col.append(delta)
        if prior != 0:
            delta_pct_col.append(delta / prior * 100.0)
        elif cur > 0:
            delta_pct_col.append(100.0)
        else:
            delta_pct_col.append(0.0)

    agg["delta_ngn"] = delta_ngn_col
    agg["delta_pct"] = delta_pct_col
    agg["activation_count"] = agg["activation_count"].astype(int)
    agg["total_commission_ngn"] = agg["total_commission_ngn"].astype(float)

    return agg.sort_values(["product_denomination", "period"]).reset_index(drop=True)[
        [
            "period",
            "product_denomination",
            "activation_count",
            "total_commission_ngn",
            "delta_ngn",
            "delta_pct",
        ]
    ]


def _sample_get_orsc_summary(params: dict) -> pd.DataFrame:
    mon_period = params["mon_period"]
    distributor_code = params.get("distributor_code")

    df = _load_csv("fbb_comm_orsc", period=_norm_str(mon_period))
    df = _filter_period_and_distributor(df, mon_period, distributor_code)

    df["data_subscription_amount"] = (
        df["data_subscription_amount"].fillna(0).astype(float)
    )

    rows: list[dict[str, Any]] = []
    for dist_code, group in df.groupby("distributor_code", sort=False):
        rows.append(
            {
                "dealer_id": _norm_str(dist_code),
                "dealer_name": str(group["distributor_name"].iloc[0]),
                "account_profile_class": str(group["account_profile_class"].iloc[0]),
                "device_count": int(len(group)),
                "total_subscription_amount_ngn": float(
                    group["data_subscription_amount"].sum()
                ),
                "zero_amount_count": int(
                    (group["data_subscription_amount"] == 0).sum()
                ),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "dealer_id",
                "dealer_name",
                "account_profile_class",
                "device_count",
                "total_subscription_amount_ngn",
                "zero_amount_count",
            ]
        )

    return (
        pd.DataFrame(rows)
        .sort_values("total_subscription_amount_ngn", ascending=False)
        .reset_index(drop=True)
    )


def _activation_summary_frame(mon_period: str) -> pd.DataFrame:
    """Internal helper — produces the dealer-month aggregate frame.

    Used both by ``_sample_get_activation_summary`` and (indirectly through
    re-aggregation) by the variance / exceptions handlers. Centralised so the
    qualified / non-qualified / rate calculation is defined in exactly one
    place.
    """
    mon_period = _norm_str(mon_period)
    df = _load_csv("fbb_comm_dev_act", period=mon_period)
    df = df[df["mon_period"].apply(_norm_str) == mon_period].copy()
    df["commission_rate"] = df["commission_rate"].fillna(0.0).astype(float)
    df["account_profile_class"] = df["account_profile_class"].fillna("")

    rows: list[dict[str, Any]] = []
    for dist_code, group in df.groupby("distributor_code", sort=False):
        total = int(len(group))
        qualified = int((group["commission_rate"] > 0).sum())
        non_qualified = int((group["commission_rate"] == 0).sum())
        commission = float(group["commission_rate"].sum())
        rate = round(qualified / total * 100.0, 2) if total > 0 else 0.0
        rows.append(
            {
                "dealer_id": _norm_str(dist_code),
                "dealer_name": str(group["distributor_name"].iloc[0]),
                "account_profile_class": str(
                    group["account_profile_class"].iloc[0]
                ),
                "report_month": mon_period,
                "activation_count": total,
                "qualified_activation_count": qualified,
                "non_qualified_activation_count": non_qualified,
                "activation_commission_amount": commission,
                "qualification_rate_pct": rate,
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "dealer_id",
                "dealer_name",
                "account_profile_class",
                "report_month",
                "activation_count",
                "qualified_activation_count",
                "non_qualified_activation_count",
                "activation_commission_amount",
                "qualification_rate_pct",
            ]
        )

    return (
        pd.DataFrame(rows)
        .sort_values("activation_count", ascending=False)
        .reset_index(drop=True)
    )


def _sample_get_activation_summary(params: dict) -> pd.DataFrame:
    """Phase 2 — per-dealer activation totals for one reporting month."""
    return _activation_summary_frame(params["mon_period"])


def _sample_get_activation_variance(params: dict) -> pd.DataFrame:
    """Phase 2 — per-dealer activation deltas across two reporting months.

    Inner-join on dealer_id: only dealers present in BOTH periods are
    returned. Sorted by ``abs(delta_activations)`` descending so the biggest
    movers come first.
    """
    pa = _norm_str(params["period_a"])
    pb = _norm_str(params["period_b"])

    df_a = _activation_summary_frame(pa)
    df_b = _activation_summary_frame(pb)
    if df_a.empty or df_b.empty:
        return pd.DataFrame(
            columns=[
                "dealer_id",
                "dealer_name",
                "period_a",
                "period_b",
                "activation_count_a",
                "activation_count_b",
                "delta_activations",
                "delta_commission_ngn",
                "delta_qualification_rate",
            ]
        )

    merged = df_a.merge(
        df_b, on="dealer_id", how="inner", suffixes=("_a", "_b")
    )

    rows: list[dict[str, Any]] = []
    for _, r in merged.iterrows():
        delta_act = int(r["activation_count_b"]) - int(r["activation_count_a"])
        delta_com = float(
            r["activation_commission_amount_b"]
        ) - float(r["activation_commission_amount_a"])
        delta_qr = float(r["qualification_rate_pct_b"]) - float(
            r["qualification_rate_pct_a"]
        )
        rows.append(
            {
                "dealer_id": _norm_str(r["dealer_id"]),
                # Prefer the current-period name if present.
                "dealer_name": str(r["dealer_name_b"] or r["dealer_name_a"]),
                "period_a": pa,
                "period_b": pb,
                "activation_count_a": int(r["activation_count_a"]),
                "activation_count_b": int(r["activation_count_b"]),
                "delta_activations": delta_act,
                "delta_commission_ngn": float(round(delta_com, 2)),
                "delta_qualification_rate": float(round(delta_qr, 2)),
            }
        )

    result = pd.DataFrame(rows)
    result = result.assign(_abs=result["delta_activations"].abs())
    result = result.sort_values("_abs", ascending=False).drop(columns="_abs")
    return result.reset_index(drop=True)


# Exception type labels are part of the public contract — keep them in one place.
EXCEPTION_ALL_UNQUALIFIED = "ALL_UNQUALIFIED"
EXCEPTION_HIGH_UNQUALIFIED_RATE = "HIGH_UNQUALIFIED_RATE"
EXCEPTION_UNUSUAL_VOLUME = "UNUSUAL_VOLUME"


def _sample_get_activation_exceptions(params: dict) -> pd.DataFrame:
    """Phase 2 — dealers matching one or more activation exception conditions.

    A dealer can appear multiple times (one row per matching condition).
    UNUSUAL_VOLUME threshold: ``mean + 2 * std_dev`` of activation_count
    across all dealers for the period.
    """
    mon_period = _norm_str(params["mon_period"])
    summary = _activation_summary_frame(mon_period)

    cols = [
        "dealer_id",
        "dealer_name",
        "account_profile_class",
        "exception_type",
        "activation_count",
        "qualified_activation_count",
        "qualification_rate_pct",
        "activation_commission_amount",
    ]

    if summary.empty:
        return pd.DataFrame(columns=cols)

    counts = summary["activation_count"].astype(float)
    mean_count = float(counts.mean())
    std_count = float(counts.std(ddof=1)) if len(counts) > 1 else 0.0
    threshold = mean_count + 2.0 * std_count

    rows: list[dict[str, Any]] = []
    for _, r in summary.iterrows():
        base = {
            "dealer_id": r["dealer_id"],
            "dealer_name": r["dealer_name"],
            "account_profile_class": r["account_profile_class"],
            "activation_count": int(r["activation_count"]),
            "qualified_activation_count": int(r["qualified_activation_count"]),
            "qualification_rate_pct": float(r["qualification_rate_pct"]),
            "activation_commission_amount": float(r["activation_commission_amount"]),
        }
        if r["activation_count"] > 0 and r["qualified_activation_count"] == 0:
            rows.append({**base, "exception_type": EXCEPTION_ALL_UNQUALIFIED})
        if r["qualification_rate_pct"] < 50:
            rows.append({**base, "exception_type": EXCEPTION_HIGH_UNQUALIFIED_RATE})
        if r["activation_count"] >= threshold:
            rows.append({**base, "exception_type": EXCEPTION_UNUSUAL_VOLUME})

    if not rows:
        return pd.DataFrame(columns=cols)

    return (
        pd.DataFrame(rows)
        .sort_values(["exception_type", "activation_count"], ascending=[True, False])
        .reset_index(drop=True)
    )[cols]


# ---------------------------------------------------------------------------
# Phase 3 — Inventory Assurance
# ---------------------------------------------------------------------------

# Finding-type labels — public contract used by query consumers, the
# InventoryAssuranceService, the API, and the UI.
FINDING_CONFIRMED_MISMATCH = "CONFIRMED_MISMATCH"
FINDING_NO_INVOICE_RECORD = "NO_INVOICE_RECORD"
FINDING_WITHIN_ALLOCATION = "WITHIN_ALLOCATION"

_INVENTORY_NOTES: dict[str, str] = {
    FINDING_CONFIRMED_MISMATCH: (
        "Invoice records found. Activations exceed purchased units."
    ),
    FINDING_NO_INVOICE_RECORD: (
        "No IFS invoice record found in available window. May reflect "
        "purchases outside the sample period."
    ),
    FINDING_WITHIN_ALLOCATION: "Activations within purchased allocation.",
}

_FINDING_ORDER: dict[str, int] = {
    FINDING_CONFIRMED_MISMATCH: 0,
    FINDING_NO_INVOICE_RECORD: 1,
    FINDING_WITHIN_ALLOCATION: 2,
}


def _sample_get_inventory_comparison(params: dict) -> pd.DataFrame:
    """Phase 3 — per-dealer-per-product activation-vs-purchase comparison.

    Steps (from the spec):
      1. Load dev_act for ``mon_period``.
      2. Load ifs_invoice_history.
      3. Filter IFS to FBB product codes present in dev_act for the period.
      4. Deduplicate IFS on (customer_no, part_no, implied_units,
         actual_completion_date) — same invoice line appears up to 60x in
         the raw data.
      5. Aggregate IFS to dealer-product level: ``total_units_purchased``.
      6. Aggregate dev_act to dealer-product level: ``activation_count``,
         ``qualified_count``.
      7. Outer-join the two aggregates.
      8. Classify each record as CONFIRMED_MISMATCH / NO_INVOICE_RECORD /
         WITHIN_ALLOCATION and compute gap / gap_pct where defined.
      9. Sort: CONFIRMED_MISMATCH first → NO_INVOICE_RECORD → WITHIN_ALLOCATION,
         each by activation_count desc.

    Only records with ``activation_count > 0`` are returned — pure-purchase
    rows (dealer bought stock but hasn't activated yet) are not actionable
    for this analysis.
    """
    mon_period = _norm_str(params["mon_period"])

    # ---- 1. Activations for the period -----------------------------------
    dev = _load_csv("fbb_comm_dev_act", period=mon_period)
    dev = dev[dev["mon_period"].apply(_norm_str) == mon_period].copy()
    dev["commission_rate"] = dev["commission_rate"].fillna(0.0).astype(float)
    dev["distributor_code"] = dev["distributor_code"].apply(_norm_str)
    dev["product_code"] = dev["product_code"].apply(_norm_str)

    dev_aggr = (
        dev.groupby(["distributor_code", "product_code"], sort=False)
        .agg(
            dealer_name=("distributor_name", "first"),
            product_name=("product_name", "first"),
            activation_count=("imei", "count"),
            qualified_count=("commission_rate", lambda s: int((s > 0).sum())),
        )
        .reset_index()
        .rename(columns={"distributor_code": "dealer_id"})
    )

    # ---- 2-5. IFS purchases, filtered to FBB products, deduped, aggregated
    ifs = _load_csv("ifs_invoice_history")
    ifs["customer_no"] = ifs["customer_no"].apply(_norm_str)
    ifs["part_no"] = ifs["part_no"].apply(_norm_str)

    fbb_products = set(dev_aggr["product_code"].astype(str))
    ifs = ifs[ifs["part_no"].isin(fbb_products)]

    # Dedup on the natural composite key per the spec.
    ifs_dedup = ifs.drop_duplicates(
        subset=["customer_no", "part_no", "implied_units", "actual_completion_date"]
    )

    ifs_aggr = (
        ifs_dedup.groupby(["customer_no", "part_no"], sort=False)["implied_units"]
        .sum()
        .reset_index()
        .rename(
            columns={
                "customer_no": "dealer_id",
                "part_no": "product_code",
                "implied_units": "total_units_purchased",
            }
        )
    )
    ifs_aggr["total_units_purchased"] = ifs_aggr["total_units_purchased"].astype(float)

    # ---- 7. Outer join ---------------------------------------------------
    merged = dev_aggr.merge(
        ifs_aggr,
        on=["dealer_id", "product_code"],
        how="outer",
        indicator=False,
    )

    # Keep only records where there are activations — pure-purchase rows
    # (no activations) are not actionable.
    merged = merged[merged["activation_count"].fillna(0) > 0].copy()
    merged["activation_count"] = merged["activation_count"].fillna(0).astype(int)
    merged["qualified_count"] = merged["qualified_count"].fillna(0).astype(int)

    # ---- 8. Classify + compute gap / gap_pct ------------------------------
    rows: list[dict[str, Any]] = []
    for _, r in merged.iterrows():
        purchased = r["total_units_purchased"]
        has_invoice = pd.notna(purchased)
        if not has_invoice:
            finding = FINDING_NO_INVOICE_RECORD
            gap: float | None = None
            gap_pct: float | None = None
            total_units_purchased: float | None = None
        else:
            purchased_f = float(purchased)
            total_units_purchased = purchased_f
            gap = float(r["activation_count"]) - purchased_f
            if purchased_f == 0:
                # Activations with a recorded purchase of zero units is itself
                # a mismatch — treat as CONFIRMED_MISMATCH but flag gap_pct as
                # None (division by zero).
                finding = FINDING_CONFIRMED_MISMATCH
                gap_pct = None
            elif r["activation_count"] > purchased_f:
                finding = FINDING_CONFIRMED_MISMATCH
                gap_pct = round(gap / purchased_f * 100.0, 1)
            else:
                finding = FINDING_WITHIN_ALLOCATION
                gap_pct = round(gap / purchased_f * 100.0, 1)

        rows.append(
            {
                "dealer_id": _norm_str(r["dealer_id"]),
                "dealer_name": ("" if pd.isna(r["dealer_name"]) else str(r["dealer_name"])),
                "product_code": _norm_str(r["product_code"]),
                "product_name": ("" if pd.isna(r["product_name"]) else str(r["product_name"])),
                "activation_count": int(r["activation_count"]),
                "qualified_count": int(r["qualified_count"]),
                "total_units_purchased": total_units_purchased,
                "inventory_gap": gap,
                "gap_pct": gap_pct,
                "finding_type": finding,
                "data_coverage_note": _INVENTORY_NOTES[finding],
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "dealer_id",
                "dealer_name",
                "product_code",
                "product_name",
                "activation_count",
                "qualified_count",
                "total_units_purchased",
                "inventory_gap",
                "gap_pct",
                "finding_type",
                "data_coverage_note",
            ]
        )

    result = pd.DataFrame(rows)
    result["_order"] = result["finding_type"].map(_FINDING_ORDER)
    result = result.sort_values(
        ["_order", "activation_count"], ascending=[True, False]
    ).drop(columns="_order")
    return result.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Phase 4 — Payment Intelligence (sample handlers)
# ---------------------------------------------------------------------------

_PAYMENT_STATUS_ORDER: dict[str, int] = {
    "DISPUTED": 0,
    "PARTIALLY_PAID": 1,
    "PENDING": 2,
    "FULLY_PAID": 3,
}


def _load_payment_simulation_for(period: str) -> pd.DataFrame:
    """Load the simulated payment CSV and filter to one ``report_month``.

    Cleans up NaN -> None for nullable string columns so downstream Pydantic
    serialisation behaves.
    """
    df = _load_csv("payment_simulation").copy()
    df["report_month"] = df["report_month"].apply(_norm_str)
    df = df[df["report_month"] == _norm_str(period)].copy()

    # Cast numerics defensively.
    for col in ("commission_owed", "amount_paid", "amount_unpaid", "payment_rate"):
        df[col] = df[col].astype(float)

    # Normalise nullable string columns: NaN -> None.
    for col in ("payment_date", "exception_flag"):
        df[col] = df[col].where(df[col].notna(), None)

    # Stable string casts on the rest.
    for col in (
        "distributor_code",
        "distributor_name",
        "account_profile_class",
        "payment_status",
        "payment_channel",
        "data_source",
    ):
        df[col] = df[col].fillna("").astype(str)

    return df.reset_index(drop=True)


def _sample_get_payment_summary(params: dict) -> pd.DataFrame:
    """Phase 4 — per-dealer payment record, sorted by amount_unpaid desc.

    Rename note: the simulated CSV carries raw ``distributor_code`` /
    ``distributor_name`` columns, but the platform-wide API convention is
    ``dealer_id`` / ``dealer_name`` (see ARCHITECTURE.md "Naming
    conventions"). The rename happens at this return boundary — internal
    handlers below (variance, exceptions) reuse the renamed frame.
    """
    df = _load_payment_simulation_for(params["mon_period"]).rename(
        columns={
            "distributor_code": "dealer_id",
            "distributor_name": "dealer_name",
        }
    )
    cols = [
        "dealer_id",
        "dealer_name",
        "account_profile_class",
        "report_month",
        "commission_owed",
        "amount_paid",
        "amount_unpaid",
        "payment_status",
        "payment_channel",
        "payment_date",
        "exception_flag",
        "data_source",
    ]
    return df.sort_values("amount_unpaid", ascending=False).reset_index(drop=True)[
        cols
    ]


def _sample_get_payment_exceptions(params: dict) -> pd.DataFrame:
    """Phase 4 — non-FULLY_PAID rows, sorted DISPUTED → PARTIAL → PENDING."""
    df = _sample_get_payment_summary(params)
    df = df[df["payment_status"] != "FULLY_PAID"].copy()
    df["_order"] = df["payment_status"].map(_PAYMENT_STATUS_ORDER).fillna(99)
    df = df.sort_values(["_order", "amount_unpaid"], ascending=[True, False])
    return df.drop(columns="_order").reset_index(drop=True)


def _sample_get_payment_variance(params: dict) -> pd.DataFrame:
    """Phase 4 — per-dealer payment delta between two periods.

    Inner join: only dealers present in both periods are returned. Sorted
    by ``abs(delta_paid)`` descending.
    """
    pa = _norm_str(params["period_a"])
    pb = _norm_str(params["period_b"])

    df_a = _sample_get_payment_summary({"mon_period": pa})
    df_b = _sample_get_payment_summary({"mon_period": pb})

    cols = [
        "dealer_id",
        "dealer_name",
        "period_a",
        "period_b",
        "commission_owed_a",
        "amount_paid_a",
        "payment_status_a",
        "commission_owed_b",
        "amount_paid_b",
        "payment_status_b",
        "delta_paid",
        "status_changed",
    ]

    if df_a.empty or df_b.empty:
        return pd.DataFrame(columns=cols)

    merged = df_a.merge(
        df_b,
        on="dealer_id",
        how="inner",
        suffixes=("_a", "_b"),
    )

    rows: list[dict[str, Any]] = []
    for _, r in merged.iterrows():
        delta = float(r["amount_paid_b"]) - float(r["amount_paid_a"])
        rows.append(
            {
                "dealer_id": str(r["dealer_id"]),
                "dealer_name": str(r["dealer_name_b"] or r["dealer_name_a"]),
                "period_a": pa,
                "period_b": pb,
                "commission_owed_a": float(r["commission_owed_a"]),
                "amount_paid_a": float(r["amount_paid_a"]),
                "payment_status_a": str(r["payment_status_a"]),
                "commission_owed_b": float(r["commission_owed_b"]),
                "amount_paid_b": float(r["amount_paid_b"]),
                "payment_status_b": str(r["payment_status_b"]),
                "delta_paid": float(round(delta, 2)),
                "status_changed": bool(
                    str(r["payment_status_a"]) != str(r["payment_status_b"])
                ),
            }
        )

    result = pd.DataFrame(rows)
    result = result.assign(_abs=result["delta_paid"].abs())
    result = result.sort_values("_abs", ascending=False).drop(columns="_abs")
    return result.reset_index(drop=True)


def _sample_get_health_scorecard(params: dict) -> pd.DataFrame:
    """Partner Financial Health Scorecard — composite ratios per dealer.

    Joins payment_simulation (settlement data) with fbb_comm_dev_act (activation
    data) for current_period and prior_period. Computes four ratios and a
    weighted health score (0-100). Sorted worst-first so the most at-risk
    partners surface immediately.

    Health score:
        settlement_rate (50 pts) + commission_consistency (30 pts) + clean_record (20 pts)
    Bands: HEALTHY ≥80 · WATCH ≥60 · AT RISK <60
    """
    current = _norm_str(params.get("current_period", ""))
    prior = _norm_str(params.get("prior_period", ""))

    # --- payment data for both periods ---
    # PAYMENT_SOURCE is independent from USE_SAMPLE_DATA: Render deliberately
    # combines sample activation data with live APDP settlement data. Keep the
    # scorecard aligned with the other payment endpoints in that deployment.
    from backend import config
    from backend.audit.payment_data import payment_lookup

    payment_source = config.PAYMENT_SOURCE
    pay_cur = payment_lookup(current, payment_source)
    pay_pri = payment_lookup(prior, payment_source) if prior else pd.DataFrame()

    if payment_source == "apdp":
        payment_renames = {
            "expected_commission_ngn": "commission_owed",
            "total_settled_ngn": "amount_paid",
            "reconciliation_status": "payment_status",
        }
        pay_cur = pay_cur.rename(columns=payment_renames)
        pay_pri = pay_pri.rename(columns=payment_renames)
    else:
        pay_cur = pay_cur.rename(columns={"distributor_code": "dealer_id"})
        pay_pri = pay_pri.rename(columns={"distributor_code": "dealer_id"})

    required_payment_columns = ("dealer_id", "commission_owed", "amount_paid", "payment_status")
    for df in (pay_cur, pay_pri):
        for col in required_payment_columns:
            if col not in df.columns:
                df[col] = pd.Series(dtype="object")

    # --- activation data for both periods ---
    act_cur = _load_csv("fbb_comm_dev_act", period=current).copy()
    act_pri = _load_csv("fbb_comm_dev_act", period=prior).copy() if prior else pd.DataFrame()

    # Cast numeric columns in activation frames; normalise distributor_code to str.
    for df in (act_cur, act_pri):
        if df.empty:
            continue
        for col in ("unit_selling_price", "commission_rate"):
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        df["distributor_code"] = df["distributor_code"].astype(str)

    # Normalise payment dealer IDs to strings for consistent merging.
    for df in (pay_cur, pay_pri):
        if df.empty:
            continue
        df["dealer_id"] = df["dealer_id"].astype(str)

    def _act_metrics(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=[
                "distributor_code", "dealer_name", "account_profile_class",
                "gross_revenue", "commission_earned", "zero_count", "total_count",
            ])
        grp = df.groupby("distributor_code").agg(
            dealer_name=("distributor_name", "first"),
            account_profile_class=("account_profile_class", "first"),
            gross_revenue=("unit_selling_price", "sum"),
            commission_earned=("commission_rate", "sum"),
            zero_count=("commission_rate", lambda x: (x == 0).sum()),
            total_count=("commission_rate", "count"),
        ).reset_index()
        return grp

    act_cur_m = _act_metrics(act_cur)
    act_pri_m = _act_metrics(act_pri)

    # --- merge current payment + activation ---
    cur = pay_cur.copy()
    cur = cur.merge(
        act_cur_m.rename(columns={"distributor_code": "dealer_id"}),
        on="dealer_id", how="left",
    )
    for col in ("gross_revenue", "commission_earned", "zero_count", "total_count"):
        cur[col] = cur[col].fillna(0.0)

    # --- prior period settlement rate per dealer for MoM delta ---
    if not pay_pri.empty:
        pri = pay_pri[["dealer_id", "commission_owed", "amount_paid"]].copy()
        pri["settlement_rate_prior"] = pri.apply(
            lambda r: (r["amount_paid"] / r["commission_owed"] * 100) if r["commission_owed"] > 0 else 0.0,
            axis=1,
        )
        pri = pri[["dealer_id", "settlement_rate_prior"]]
    else:
        pri = pd.DataFrame(columns=["dealer_id", "settlement_rate_prior"])

    cur = cur.merge(pri, on="dealer_id", how="left")
    cur["settlement_rate_prior"] = cur["settlement_rate_prior"].fillna(float("nan"))

    # --- compute ratios ---
    rows: list[dict] = []
    for _, r in cur.iterrows():
        owed = float(r["commission_owed"])
        paid = float(r["amount_paid"])
        gross = float(r["gross_revenue"])
        earned = float(r["commission_earned"])
        zero_count = int(r["zero_count"])
        total_count = int(r["total_count"])

        settlement_rate = (paid / owed * 100) if owed > 0 else 0.0
        commission_yield = (earned / gross * 100) if gross > 0 else 0.0
        zero_rate = (zero_count / total_count * 100) if total_count > 0 else 0.0
        outstanding = max(owed - paid, 0.0)
        dispute_flag = str(r["payment_status"]) in ("DISPUTED", "PARTIALLY_PAID")

        # MoM settlement rate delta
        prior_rate = r["settlement_rate_prior"]
        settlement_rate_delta = (
            round(settlement_rate - float(prior_rate), 1)
            if not (prior_rate != prior_rate)  # NaN check
            else None
        )

        # Weighted health score
        consistency_pts = (1 - zero_rate / 100) * 30
        clean_pts = 0.0 if dispute_flag else 20.0
        score = round((settlement_rate / 100 * 50) + consistency_pts + clean_pts, 1)
        band = "HEALTHY" if score >= 80 else "WATCH" if score >= 60 else "AT RISK"

        dealer_name = r.get("dealer_name")
        profile_class = r.get("account_profile_class")
        rows.append({
            "dealer_id": str(r["dealer_id"]),
            "dealer_name": (
                str(dealer_name)
                if dealer_name is not None and not pd.isna(dealer_name)
                else str(r["dealer_id"])
            ),
            "account_profile_class": (
                str(profile_class)
                if profile_class is not None and not pd.isna(profile_class)
                else ""
            ),
            "health_score": score,
            "health_band": band,
            "settlement_rate_pct": round(settlement_rate, 1),
            "settlement_rate_delta": settlement_rate_delta,
            "commission_yield_pct": round(commission_yield, 1),
            "zero_commission_rate_pct": round(zero_rate, 1),
            "outstanding_ngn": round(outstanding, 2),
            "dispute_flag": dispute_flag,
            "data_source": "APDP" if payment_source == "apdp" else "SIMULATED",
        })

    result = pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
        "dealer_id", "dealer_name", "account_profile_class",
        "health_score", "health_band", "settlement_rate_pct",
        "settlement_rate_delta", "commission_yield_pct",
        "zero_commission_rate_pct", "outstanding_ngn", "dispute_flag",
        "data_source",
    ])
    return result.sort_values("health_score", ascending=True).reset_index(drop=True)


SAMPLE_HANDLERS: dict[str, Callable[[dict], pd.DataFrame]] = {
    "get_dealer_summary": _sample_get_dealer_summary,
    "get_zero_commission_records": _sample_get_zero_commission_records,
    "get_month_on_month_variance": _sample_get_month_on_month_variance,
    "get_orsc_summary": _sample_get_orsc_summary,
    # --- Phase 2: Activation Intelligence ---
    "get_activation_summary": _sample_get_activation_summary,
    "get_activation_variance": _sample_get_activation_variance,
    "get_activation_exceptions": _sample_get_activation_exceptions,
    # --- Phase 3: Inventory Assurance ---
    "get_inventory_comparison": _sample_get_inventory_comparison,
    # --- Phase 4: Payment Intelligence ---
    "get_payment_summary": _sample_get_payment_summary,
    "get_payment_exceptions": _sample_get_payment_exceptions,
    "get_payment_variance": _sample_get_payment_variance,
    # --- Partner Health Scorecard ---
    "get_health_scorecard": _sample_get_health_scorecard,
}


QUERY_NAMES: list[str] = list(SAMPLE_HANDLERS.keys())


# ---------------------------------------------------------------------------
# Metadata helpers (not Claude-callable tools — used by the API layer)
# ---------------------------------------------------------------------------


def get_available_periods() -> list[str]:
    """Return distinct ``mon_period`` values present in ``fbb_comm_dev_act``.

    Used by ``GET /periods`` and as a fallback for ``GET /dealers`` when the
    caller does not pin a specific period. Sorted descending so the most
    recent month is first.

    In sample mode this reads the dev_act CSV. The Presto path will be wired
    up alongside ``_run_presto`` when the service account is provisioned.
    """
    if config.USE_SAMPLE_DATA:
        entry = config.SAMPLE_DATA_PATHS["fbb_comm_dev_act"]
        # Fast path: enumerate the dict keys directly — no CSV read needed.
        if isinstance(entry, dict):
            return sorted(entry.keys(), reverse=True)
        # Single-path fallback: read the CSV and dedupe its mon_period column.
        df = _load_csv("fbb_comm_dev_act")
        periods = {_norm_str(p) for p in df["mon_period"].dropna().tolist()}
        return sorted(periods, reverse=True)

    raise NotImplementedError(
        "get_available_periods is not implemented for live Presto mode yet "
        "— to be implemented when the service account is provisioned."
    )
