# KB Addendum — FTTH Subscriptions Revenue Query

A separate revenue stream from device commissions: subscription-level CDR data for FBB / FIBRENET. Fetch via ``get_kb_section("ftth_subscriptions_query")`` only when the user asks about subscription / FTTH revenue rather than activation commissions.

For FBB subscription revenue from CDR (separate from device commissions), the source is `flare_8.cs6_ccn_cdr`:

```sql
SELECT
    COALESCE(b.msisdn_key, a.msisdn_key) AS msisdn,
    'PREPAID' AS svc_category,
    -- channel name logic handles DOM channel via JSON extract
    'FIBRENET' AS product_category,
    a.vas_productid AS vas_code,
    a.vas_productname AS product_type,
    (CAST(a.vas_chargeamount AS DOUBLE) / 100) AS revenue,
    a.tbl_dt
FROM flare_8.cs6_ccn_cdr a
LEFT JOIN flare_8.cs6_sdp_cdr b ON a.vas_transactionid = b.origtransactionid
-- DOM channel resolution via flare_8.dom_order_transactions + flare_8.dclm_partyinteraction_details
WHERE a.servicetype = 'VAS'
AND regexp_like(LOWER(a.vas_productname), 'fibre|fiber')
AND a.tbl_dt = {run_dt}
```

Note: `vas_chargeamount` is stored in kobo — divide by 100 to get Naira.
