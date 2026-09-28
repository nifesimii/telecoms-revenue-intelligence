# KB Addendum — Reconciliation Reference Points

The comparison anchors Finance uses to validate the automated commission output. Fetch via ``get_kb_section("reconciliation_reference")`` when the user asks how Finance validates the report, where a variance might come from, or what the manual-vs-automated comparison points are.

| Validation step           | Finance source                        | IT source                                                  | Expected match                              |
| ------------------------- | ------------------------------------- | ---------------------------------------------------------- | ------------------------------------------- |
| Activation record count   | Finance's UDDM copy from prior months | `development.fbb_comm_dev_act` row count                   | Must match within transaction lag tolerance |
| Unit selling price        | Finance's manual Excel reports        | USP dimension joined to dev_act                            | Must match exactly for each product_code    |
| ORSC subscription amounts | Finance's settlement statements       | `development.fbb_comm_orsc.data_subscription_amount`       | Must match per IMEI per month               |
| Partner classification    | Finance's TAS master view             | `account_profile_class` from tas_augmented_customer_master | Mismatches indicate stale TAS join          |
