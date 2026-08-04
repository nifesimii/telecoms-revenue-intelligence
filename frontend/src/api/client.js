// Axios client. Wraps backend FastAPI endpoints.
//
// Base URL is taken from VITE_API_URL (defaults to http://localhost:8000).
// All three exported helpers return the response body directly so callers
// don't have to dig past `.data`.

import axios from 'axios';

const baseURL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

const api = axios.create({
  baseURL,
  timeout: 60_000, // /chat can take ~30s when Claude runs tools
  headers: { 'Content-Type': 'application/json' },
});

/**
 * POST /chat
 * @param {string} message The user's question.
 * @param {Array<{role: string, content: string}>} conversation_history Prior turns.
 * @param {string|null} mon_period Optional reporting period to pin (YYYYMM).
 * @returns {Promise<{response: string, tools_called: string[], raw_data: object, error: string|null}>}
 */
export async function sendMessage(message, conversation_history = [], mon_period = null) {
  const payload = { message, conversation_history };
  if (mon_period) payload.mon_period = mon_period;
  const { data } = await api.post('/chat', payload);
  return data;
}

/**
 * GET /periods
 * @returns {Promise<{periods: string[]}>}
 */
export async function getPeriods() {
  const { data } = await api.get('/periods');
  return data;
}

/**
 * GET /health
 * @returns {Promise<{status: string, sample_data_mode: boolean}>}
 */
export async function getHealth() {
  const { data } = await api.get('/health');
  return data;
}

/**
 * GET /dealers?mon_period=YYYYMM
 * @param {string|null} mon_period Optional reporting period; backend uses most recent if omitted.
 * @returns {Promise<Array<{distributor_code: string, distributor_name: string, account_profile_class: string, total_activations: number, total_commission_ngn: number, zero_commission_count: number}>>}
 */
export async function getDealers(mon_period = null) {
  const params = mon_period ? { mon_period } : {};
  const { data } = await api.get('/dealers', { params });
  return data;
}

// ---------------------------------------------------------------------------
// Phase 2 — Activation Intelligence endpoints
// ---------------------------------------------------------------------------

/**
 * GET /activations/summary?mon_period=YYYYMM
 * @param {string|null} mon_period
 */
export async function getActivationSummary(mon_period = null) {
  const params = mon_period ? { mon_period } : {};
  const { data } = await api.get('/activations/summary', { params });
  return data;
}

/**
 * GET /activations/variance?period_a=YYYYMM&period_b=YYYYMM
 * @param {string} period_a
 * @param {string} period_b
 */
export async function getActivationVariance(period_a, period_b) {
  const { data } = await api.get('/activations/variance', {
    params: { period_a, period_b },
  });
  return data;
}

/**
 * GET /activations/exceptions?mon_period=YYYYMM
 * @param {string|null} mon_period
 */
export async function getActivationExceptions(mon_period = null) {
  const params = mon_period ? { mon_period } : {};
  const { data } = await api.get('/activations/exceptions', { params });
  return data;
}

// ---------------------------------------------------------------------------
// Assurance Layer scaffolding endpoint
// ---------------------------------------------------------------------------

/**
 * GET /assurance/status?mon_period=YYYYMM
 * @param {string|null} mon_period
 * @returns {Promise<{period: string, modules: Array<object>}>}
 */
export async function getAssuranceStatus(mon_period = null) {
  const params = mon_period ? { mon_period } : {};
  const { data } = await api.get('/assurance/status', { params });
  return data;
}

// ---------------------------------------------------------------------------
// Phase 3 — Inventory Assurance endpoint
// ---------------------------------------------------------------------------

/**
 * GET /inventory/comparison?mon_period=YYYYMM
 * @param {string|null} mon_period
 * @param {boolean} include_within_allocation
 */
export async function getInventoryComparison(
  mon_period = null,
  include_within_allocation = false,
) {
  const params = {};
  if (mon_period) params.mon_period = mon_period;
  if (include_within_allocation) params.include_within_allocation = true;
  const { data } = await api.get('/inventory/comparison', { params });
  return data;
}

/**
 * GET /inventory/data-coverage-issues?mon_period=YYYYMM&source=ifs|usp|both
 * Returns the ServiceNow-ready ticket draft for data coverage gaps.
 *
 * @param {string|null} mon_period
 * @param {'ifs'|'usp'|'both'} source
 * @returns {Promise<{
 *   mon_period: string,
 *   source: string,
 *   severity: 'LOW'|'MEDIUM'|'HIGH',
 *   severity_action: string,
 *   affected_dealers: number,
 *   ifs_missing: Array<object>,
 *   usp_missing: Array<object>,
 *   ticket_body: string,
 * }>}
 */
export async function getDataCoverageIssues(mon_period = null, source = 'both') {
  const params = { source };
  if (mon_period) params.mon_period = mon_period;
  const { data } = await api.get('/inventory/data-coverage-issues', { params });
  return data;
}

/**
 * POST /payments/disputes/draft
 * Compose a finance-ready dispute response letter for one (dealer, period).
 *
 * @param {object} body
 * @param {string} body.distributor_code
 * @param {string} body.mon_period
 * @param {string|null} [body.dispute_text]
 * @param {number|null} [body.amount_paid]
 * @returns {Promise<{markdown: string, summary: object}>}
 */
export async function draftDisputeResponse(body) {
  const { data } = await api.post('/payments/disputes/draft', body);
  return data;
}

// ---------------------------------------------------------------------------
// Audit trails (generic, module-aware)
// ---------------------------------------------------------------------------

/** GET /assurance/audit/modules — registered audit modules for the dropdown. */
export async function getAuditModules() {
  const { data } = await api.get('/assurance/audit/modules');
  return data;
}

/** POST /assurance/audit/run?module=&mon_period= — generate + persist trails. */
export async function runAuditModule(module, mon_period) {
  const { data } = await api.post('/assurance/audit/run', null, {
    params: { module, mon_period },
  });
  return data;
}

/**
 * GET /assurance/audit/trails?module=&mon_period=[&caveat_step=]
 * @returns {Promise<Array<object>>} persisted trails
 */
export async function getAuditTrails(module, mon_period, caveat_step = null) {
  const params = { module, mon_period };
  if (caveat_step) params.caveat_step = caveat_step;
  const { data } = await api.get('/assurance/audit/trails', { params });
  return data;
}

/** GET /assurance/audit/breakdown?module=&mon_period= — conclusion/confidence counts. */
export async function getAuditBreakdown(module, mon_period) {
  const { data } = await api.get('/assurance/audit/breakdown', {
    params: { module, mon_period },
  });
  return data;
}

// ---------------------------------------------------------------------------
// Phase 4 — Payment Intelligence
// ---------------------------------------------------------------------------

/**
 * GET /payments/summary?mon_period=YYYYMM
 * @param {string|null} mon_period
 */
export async function getPaymentSummary(mon_period = null) {
  const params = mon_period ? { mon_period } : {};
  const { data } = await api.get('/payments/summary', { params });
  return data;
}

/**
 * GET /payments/exceptions?mon_period=YYYYMM
 * @param {string|null} mon_period
 */
export async function getPaymentExceptions(mon_period = null) {
  const params = mon_period ? { mon_period } : {};
  const { data } = await api.get('/payments/exceptions', { params });
  return data;
}

/**
 * GET /payments/variance?period_a=YYYYMM&period_b=YYYYMM
 * @param {string} period_a
 * @param {string} period_b
 */
export async function getPaymentVariance(period_a, period_b) {
  const { data } = await api.get('/payments/variance', {
    params: { period_a, period_b },
  });
  return data;
}

export default api;
