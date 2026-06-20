# KB Addendum — Commission Calculation Logic

Pseudo-SQL describing how the upstream ``fbb_commission.py`` ETL produces the dev_act and ORSC commission tables. Fetch via ``get_kb_section("calculation_logic")`` when a user asks how a commission figure was derived, why the eligibility window matters, or how dedup works.

This is reference for *your* reasoning — do **not** paste raw SQL back to the user. Use the rules to explain results in plain English.

### Device Activation commission calculation

```sql
-- Step 1: Pull activations for the reporting month
-- Eligibility window: first_activation_date must be within 6 months of mon_period
WHERE mon_period = '{YYYYMM}'
AND substring(first_activation_date, 1, 6) BETWEEN
    substring(date_format(date_add('month', -5, date_parse(...)), '%Y%m'), 1, 6)
    AND replace(cast(mon_period AS varchar), ',', '')
AND first_activation_date != ''

-- Step 2: Join to USP dimension on product_name = itemdescription
-- Filter USP to the reporting month: tbl_dt BETWEEN '{YYYYMM}01' AND '{YYYYMM}30'
-- CRITICAL: strip comma formatting from unit_selling_price before casting to DOUBLE

-- Step 3: Deduplicate by IMEI (one activation record per device)
-- ROW_NUMBER() OVER (PARTITION BY imei ORDER BY product_code DESC) = 1

-- Step 4: commission_rate = unit_selling_price * 0.10
```

### ORSC commission calculation

```sql
-- Step 1: Pull ORSC summary for the reporting month
-- Same 6-month eligibility window on last_detection_date
WHERE month_period = {YYYYMM}
AND rnk = 1  -- most recent last_detection_date per IMEI

-- Step 2: Join to IFS invoiced sales to get actual_completion_date
-- Join key: substring(imei, 1, 14) = substring(serial_no, 1, 14)  -- 14-char IMEI match
-- IFS filter: tbl_dt BETWEEN {YYYYMM}01 AND {YYYYMM}30, bill_to_customer_account_type_name = 'External', unit_selling_price > 0

-- Step 3: ORSC payable = data_subscription_amount (already a monetary value from source)
-- No rate multiplication needed — data_subscription_amount IS the commission basis
```

### Partner type enrichment (both tables)

```sql
-- Both dev_act and ORSC join to TAS master for account_profile_class
LEFT JOIN (
    SELECT partner_type, partner_code, partner_name, max(tbl_dt)
    FROM flare_8.tas_augmented_customer_master
    GROUP BY partner_type, partner_code, partner_name
) d ON distributor_code = d.partner_code
```

### Invoiced sales (fbb_comm_inv_sales)

```sql
-- Source: flare_8.ifs_vw_invoiced_sales_tran_new
-- Filter: actual_completion_date in reporting month, External customers only, unit_selling_price > 0
-- Deduplication: dense_rank() over (partition by product_code order by unit_selling_price asc)
-- Aggregation: sum(ordered_amount) grouped by distributor + product + invoice_date + price
```
