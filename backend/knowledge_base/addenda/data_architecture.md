# KB Addendum — Data Architecture

This is the full source-system inventory and development-schema layout. It lives outside the always-resident system prompt so it does not eat tokens on every request. Fetch via ``get_kb_section("data_architecture")`` when you need the canonical table names, schemas, or source-system mapping.

### Source systems


| Table                            | Schema         | Description                                                                  |
| -------------------------------- | -------------- | ---------------------------------------------------------------------------- |
| `device_activation_m`            | `dataops_prod` | Raw device activation records — one row per IMEI activation event            |
| `device_orsc_summary`            | `dataops_prod` | Monthly ORSC summary — subscription revenue per active IMEI                  |
| `ifs_vw_invoiced_sales_tran_new` | `flare_8`      | Oracle IFS invoiced sales — unit selling prices and order amounts            |
| `tas_augmented_customer_master`  | `flare_8`      | Trade partner master — maps `distributor_code` to `partner_type`             |
| `usp_dimension`                  | `mtnn_it`      | Unit Selling Price dimension — product pricing and commission rates by month |
| `cs6_ccn_cdr`                    | `flare_8`      | CDR data — FBB/FIBRENET subscription revenue (FTTH subscriptions)            |


### Development (staging) tables


| Table                  | Schema        | Contents                                                       |
| ---------------------- | ------------- | -------------------------------------------------------------- |
| `fbb_comm_dev_act`     | `development` | Processed device activation commission records                 |
| `fbb_comm_inv_sales`   | `development` | Processed invoiced sales records                               |
| `fbb_comm_orsc`        | `development` | Processed ORSC commission records                              |
| `fbb_comm_dev_act_rpt` | `development` | Final report output — product_code, product_name, tbl_dt       |
| `usp_dimension`        | `development` | Monthly copy of mtnn_it.usp_dimension for the reporting period |


### Script location

`/opt/airflow/progs/fbb_commission/fbb_commission.py`
