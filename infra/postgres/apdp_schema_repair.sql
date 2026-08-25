-- Non-destructive APDP v1.3 schema repair for partially initialised databases.
-- This migration preserves normalized.transactions data and recreates only the
-- columns, indexes, and reconciliation view required by Payment Intelligence.

ALTER TABLE normalized.transactions
  ADD COLUMN IF NOT EXISTS event_type            VARCHAR(100),
  ADD COLUMN IF NOT EXISTS partner_id            VARCHAR(100),
  ADD COLUMN IF NOT EXISTS dealer_id             VARCHAR(100),
  ADD COLUMN IF NOT EXISTS product_type          VARCHAR(50),
  ADD COLUMN IF NOT EXISTS gross_revenue         NUMERIC(20, 2),
  ADD COLUMN IF NOT EXISTS commission_amount     NUMERIC(20, 2),
  ADD COLUMN IF NOT EXISTS commission_rate       NUMERIC(8, 6),
  ADD COLUMN IF NOT EXISTS settlement_period     VARCHAR(6),
  ADD COLUMN IF NOT EXISTS linked_statement_ref  VARCHAR(150);

CREATE INDEX IF NOT EXISTS idx_txn_event_type
  ON normalized.transactions(event_type);
CREATE INDEX IF NOT EXISTS idx_txn_dealer_period
  ON normalized.transactions(dealer_id, settlement_period);
CREATE INDEX IF NOT EXISTS idx_txn_partner_period
  ON normalized.transactions(partner_id, settlement_period);
CREATE INDEX IF NOT EXISTS idx_txn_linked_stmt
  ON normalized.transactions(linked_statement_ref)
  WHERE linked_statement_ref IS NOT NULL;

CREATE OR REPLACE VIEW normalized.partner_settlements AS
WITH sales_agg AS (
    SELECT dealer_id, settlement_period, COUNT(*) AS sale_count,
           SUM(amount_ngn) AS total_sales_ngn
    FROM normalized.transactions
    WHERE event_type = 'telecom.dealer_sale'
      AND dealer_id IS NOT NULL AND settlement_period IS NOT NULL
    GROUP BY dealer_id, settlement_period
), statements_agg AS (
    SELECT dealer_id, settlement_period, COUNT(*) AS statement_count,
           SUM(commission_amount) AS expected_commission_ngn,
           SUM(gross_revenue) AS statement_gross_revenue_ngn
    FROM normalized.transactions
    WHERE event_type = 'telecom.commission_statement'
      AND dealer_id IS NOT NULL AND settlement_period IS NOT NULL
    GROUP BY dealer_id, settlement_period
), settlements_agg AS (
    SELECT dealer_id, settlement_period, COUNT(*) AS settlement_count,
           SUM(amount_ngn) AS total_settled_ngn,
           COUNT(*) FILTER (WHERE status = 'SUCCESS') AS paid_count,
           COUNT(*) FILTER (WHERE status = 'PENDING') AS partial_count,
           COUNT(*) FILTER (WHERE status = 'FAILED') AS disputed_count
    FROM normalized.transactions
    WHERE event_type = 'telecom.settlement'
      AND dealer_id IS NOT NULL AND settlement_period IS NOT NULL
    GROUP BY dealer_id, settlement_period
)
SELECT dealer_id, settlement_period, sale_count, total_sales_ngn,
       statement_count, expected_commission_ngn,
       statement_gross_revenue_ngn, settlement_count, total_settled_ngn,
       paid_count, partial_count, disputed_count,
       COALESCE(total_settled_ngn, 0) - COALESCE(expected_commission_ngn, 0)
         AS payment_variance_ngn,
       CASE
         WHEN expected_commission_ngn IS NULL AND COALESCE(sale_count, 0) > 0
           THEN 'SALES_WITHOUT_STATEMENT'
         WHEN total_settled_ngn IS NULL AND expected_commission_ngn IS NOT NULL
           THEN 'STATEMENT_WITHOUT_PAYMENT'
         WHEN COALESCE(disputed_count, 0) > 0 THEN 'DISPUTED'
         WHEN COALESCE(partial_count, 0) > 0 THEN 'PARTIALLY_PAID'
         WHEN ABS(COALESCE(total_settled_ngn, 0)
                   - COALESCE(expected_commission_ngn, 0)) > 0.01
           THEN 'AMOUNT_MISMATCH'
         ELSE 'RECONCILED'
       END AS reconciliation_status
FROM sales_agg
FULL OUTER JOIN statements_agg USING (dealer_id, settlement_period)
FULL OUTER JOIN settlements_agg USING (dealer_id, settlement_period);

COMMENT ON VIEW normalized.partner_settlements IS
  'v1.3.0 — per-dealer per-period reconciliation surface consumed by FBB Revenue Intelligence.';
