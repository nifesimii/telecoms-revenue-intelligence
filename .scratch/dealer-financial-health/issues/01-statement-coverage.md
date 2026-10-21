# Define the dealer financial statements and business boundary

Type: grilling
Labels: wayfinder:grilling
Status: superseded
Assignee: unassigned
Parent: ../map.md
Blocked by: none

## Question

Which statements, reporting periods and business boundary must the demo cover
for Finance to understand a dealer's whole business? Decide whether to include
profit and loss, balance sheet and cash-flow views; the minimum line items and
comparisons; and how multiple outlets, accounts and non-MTN activity are scoped.
Establish the meaning of each figure rather than equating payment movements
with revenue, expense or profit. Identify which figures require periodic records.

## Comments

### Scope confirmed by the user — 2026-09-16

Include the balance sheet, income statement, and cash flow statement. The user
initially deferred KPIs, then explicitly requested a bare-minimum set covering
profitability and lending considerations. This supersedes the KPI deferral.
Existing exclusions of funding recommendations and dealer rankings still apply.

### Proposed minimum KPI set — 2026-09-16

Selected as a demo baseline under the user's request; these are not confirmed
MTN lending requirements or approval criteria.

| KPI | Demo definition | Purpose |
| --- | --- | --- |
| Gross profit margin | (Revenue minus cost of sales) / revenue × 100 | Profitability before operating expenses |
| Net profit margin | Profit after tax / revenue × 100 | Profitability after all expenses |
| Operating cash flow | Net cash from operating activities in the cash flow statement | Cash generated or consumed by operations |
| Current ratio | Current assets / current liabilities | Short-term liquidity |
| Debt-to-equity ratio | Total liabilities / total equity | Balance-sheet leverage; explicitly disclose the total-liabilities convention |
| Debt-service coverage ratio (DSCR) | EBITDA / scheduled principal and interest due for the same period | Indicative debt-servicing capacity using a labelled EBITDA-based demo measure |

Show operating cash flow in NGN, margins as percentages, and ratios as multiples.
DSCR requires a debt repayment schedule as well as statement inputs. Do not infer
scheduled obligations from observed payments or treat EBITDA as operating cash
flow. This simplified DSCR definition requires Finance review before pilot use;
lenders may use adjusted definitions.

Use aligned reporting periods and balance-sheet dates. Missing inputs produce
"Unavailable" with the missing evidence named. Zero denominators do not produce
infinite ratios; verified absence of debt service is "Not applicable". With
non-positive equity, explain the equity deficit rather than showing an ordinary
debt-to-equity multiple. Missing debt records do not establish no debt.

For the demo, present values and traceable explanations without invented
good/bad thresholds, credit scores, or approval recommendations.

Definition references consulted:
- [BDC: financial ratios](https://www.bdc.ca/en/articles-tools/money-finance/manage-finances/financial-ratios-what-are-how-use)
- [BDC: four types of financial ratios](https://www.bdc.ca/en/articles-tools/money-finance/manage-finances/financial-ratios-4-ways-assess-business)
- [BDC: debt-service coverage ratio](https://www.bdc.ca/en/articles-tools/entrepreneur-toolkit/templates-business-guides/glossary/debt-service-coverage-ratio)

### Still open

Reporting periods/comparisons, the minimum statement line items, and the treatment
of multiple outlets/accounts within a dealer business remain to be settled.
The ticket stays claimed; no resolution is implied by recording partial scope.


## Execution handoff — 2026-09-16

The user requested implementation with synthetic data throughout. This planning
interview is superseded by [the implemented demo specification](../../../docs/DEALER_FINANCIAL_HEALTH.md).
Remaining demo choices use the documented implementation defaults, not an
assertion of further user interview answers. Real-data questions remain pilot work.
