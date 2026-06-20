# KB Addendum — Table Schemas

Column-level field definitions for the three development tables in scope. Fetch via ``get_kb_section("table_schemas")`` when you need to reason about a specific field — type, source, or semantic meaning.

### `development.fbb_comm_dev_act` — Device Activation


| Field                 | Type    | Source                                 | Description                                          |
| --------------------- | ------- | -------------------------------------- | ---------------------------------------------------- |
| imei                  | BIGINT  | device_activation_m                    | Device IMEI — unique device identifier               |
| distributor_code      | BIGINT  | device_activation_m                    | Partner ID — joins to TAS master                     |
| distributor_name      | VARCHAR | device_activation_m                    | Partner name                                         |
| account_profile_class | VARCHAR | tas_augmented_customer_master          | Partner type (FIXED BROADBAND, DATA PARTNERS, etc.)  |
| product_code          | BIGINT  | device_activation_m                    | Product SKU code                                     |
| product_name          | VARCHAR | device_activation_m                    | Full product description string                      |
| invoice_date          | VARCHAR | device_activation_m                    | Date device was invoiced to partner                  |
| source                | VARCHAR | hardcoded                              | Always 'DEVICE_ACTIVATION'                           |
| first_activation_date | VARCHAR | device_activation_m                    | Timestamp of first subscriber activation             |
| mon_period            | BIGINT  | derived                                | Reporting month in YYYYMM format                     |
| unit_selling_price    | DOUBLE  | usp_dimension (joined on product_name) | Price from USP dimension for that month              |
| product_denomination  | VARCHAR | usp_dimension                          | Device tier (MIFI, HYNETFLEX, etc.)                  |
| commission_rate       | DOUBLE  | usp_dimension                          | 10% of unit_selling_price; NULL or 0 if no USP match |
| tbl_dt                | BIGINT  | ifs_vw_invoiced_sales_tran_new         | Invoice date from Oracle IFS                         |


### `development.fbb_comm_orsc` — ORSC


| Field                    | Type    | Source                         | Description                                                     |
| ------------------------ | ------- | ------------------------------ | --------------------------------------------------------------- |
| imei                     | BIGINT  | device_orsc_summary            | Device IMEI                                                     |
| distributor_code         | BIGINT  | device_orsc_summary            | Partner ID                                                      |
| distributor_name         | VARCHAR | device_orsc_summary            | Partner name                                                    |
| account_profile_class    | VARCHAR | tas_augmented_customer_master  | Partner type                                                    |
| product_name             | VARCHAR | device_orsc_summary            | Product description                                             |
| product_code             | BIGINT  | device_orsc_summary            | Product SKU                                                     |
| data_subscription_amount | DOUBLE  | device_orsc_summary            | Monthly subscription revenue for this IMEI                      |
| invoice_date             | VARCHAR | device_orsc_summary            | Invoice date                                                    |
| source                   | VARCHAR | hardcoded                      | Always 'ORSC'                                                   |
| first_activation_date    | VARCHAR | device_orsc_summary            | Maps to `last_detection_date` in source                         |
| mon_period               | BIGINT  | derived                        | YYYYMM                                                          |
| actual_completion_date   | DOUBLE  | ifs_vw_invoiced_sales_tran_new | Completion date from IFS (joined on IMEI truncated to 14 chars) |
| tbl_dt                   | DOUBLE  | ifs_vw_invoiced_sales_tran_new | IFS tbl_dt                                                      |


### `mtnn_it.usp_dimension` — USP Dimension


| Field                | Type           | Description                                                                                         |
| -------------------- | -------------- | --------------------------------------------------------------------------------------------------- |
| item_no              | BIGINT         | Product item number — joins to product_code in commission tables                                    |
| itemdescription      | VARCHAR        | Full product description — joins to product_name in dev_act                                         |
| unit_selling_price   | VARCHAR/DOUBLE | Selling price (note: source has comma-formatted strings; must REGEXP_REPLACE commas before casting) |
| product_denomination | VARCHAR        | Device tier bucket (MIFI, MIFI_1, HYNETFLEX, HYNETFLEX_1, 5G ROUTER)                                |
| commission_rate      | VARCHAR/DOUBLE | 10% commission (same formatting issue as unit_selling_price)                                        |
| tbl_dt               | BIGINT         | Snapshot date YYYYMMDD — filter to the reporting month window                                       |
