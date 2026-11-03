// Fictional Partner Sales seed data and rules. Browser-only presentation simulation (see
// docs/adr/0001-partner-sales-presentation-boundary.md): nothing here is read
// from, or written to, a financial source.

import { formatCount, formatDate, formatMinorNGN } from '../../lib/format.js';

// Sample dealer identities. Same-name accounts stay separate; the account code
// is the identity.
export const PARTNERS = [
  { code: '296065', name: 'River Isle Ventures' },
  { code: '353072', name: 'River Isle Ventures' },
  { code: '74050', name: 'Stone Light Networks' },
  { code: '98052', name: 'Ember Hill Networks' },
  { code: '205044', name: 'Sunset Crest Communications' },
  { code: '295083', name: 'Sunset Crest Communications' },
];

// Bounded catalogue. Prices are fixed demo values in kobo, never MTN price lists.
export const CATALOGUE = [
  { code: 'FBB-5G-ROUTER', description: 'Fictional 5G FBB router', unit: 'device', priceMinor: 5000000 },
  { code: 'FBB-4G-ROUTER', description: 'Fictional 4G FBB router', unit: 'device', priceMinor: 3500000 },
  { code: 'FBB-MIFI', description: 'Fictional portable FBB MiFi', unit: 'device', priceMinor: 3333333 },
  { code: 'RCC-0100', description: 'Fictional NGN 100 physical recharge card', unit: 'card', priceMinor: 10000 },
  { code: 'RCC-0200', description: 'Fictional NGN 200 physical recharge card', unit: 'card', priceMinor: 20000 },
  { code: 'RCC-0500', description: 'Fictional NGN 500 physical recharge card', unit: 'card', priceMinor: 50000 },
];
export const productByCode = (code) => CATALOGUE.find((product) => product.code === code);

export const partnerByCode = (code) => PARTNERS.find((partner) => partner.code === code);

export const partnerLabel = (partner) => `${partner.name} · Account ${partner.code}`;
export const quantityLabel = (quantity, unit) => `${formatCount(quantity)} ${unit}${quantity === 1 ? '' : 's'}`;
export const partnerMatches = (partner, term) => partner.code.includes(term) || partner.name.toLowerCase().includes(term);

// Keeps every line and draft total well inside Number.MAX_SAFE_INTEGER kobo.
const MAX_QUANTITY = 1000000;

export const draftKey = (partnerCode, period) => `${partnerCode}|${period}`;

// Last day of a YYYYMM reporting month, as a date-only string.
export function defaultIssueDate(period) {
  const year = Number(period.slice(0, 4));
  const month = Number(period.slice(4, 6));
  const day = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return `${period.slice(0, 4)}-${period.slice(4, 6)}-${String(day).padStart(2, '0')}`;
}

// Quantities stay as typed so an invalid edit remains visible and correctable.
export function quantityError(quantity) {
  if (!/^\d+$/.test(quantity) || Number(quantity) < 1) return 'Enter a positive whole number.';
  if (Number(quantity) > MAX_QUANTITY) return `Enter ${formatCount(MAX_QUANTITY)} or fewer.`;
  return null;
}

export function lineTotalMinor(line) {
  return quantityError(line.quantity) ? null : Number(line.quantity) * productByCode(line.productCode).priceMinor;
}

// Null while any line is invalid: a partial total would misstate the draft.
export function draftTotalMinor(draft) {
  let total = 0;
  for (const line of draft.lines) {
    const lineTotal = lineTotalMinor(line);
    if (lineTotal === null) return null;
    total += lineTotal;
  }
  return total;
}

export const referenceFor = (sequence) => `SIM-INV-${String(sequence).padStart(4, '0')}`;

// A date input yields five-digit years unless capped, and those neither compare
// correctly as strings nor restore from a save.
export const isDate = (value) => /^\d{4}-\d{2}-\d{2}$/.test(value) && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;

// Date-only values compare correctly as strings and never shift across time zones.
const inMonth = (date, period) => date.slice(0, 7) === `${period.slice(0, 4)}-${period.slice(4, 6)}`;

export function issueDateError(draft, periodLabel) {
  if (!draft.issueDate) return 'Enter an intended issue date.';
  return inMonth(draft.issueDate, draft.period) ? null : `Choose a date in ${periodLabel}.`;
}

export function dueDateError(draft) {
  return draft.dueDate && draft.issueDate && draft.dueDate < draft.issueDate ? 'Due date cannot be before the issue date.' : null;
}

const isIssuable = (draft) => draft.lines.length > 0 && draftTotalMinor(draft) !== null && !issueDateError(draft, '') && !dueDateError(draft);

// Copies catalogue facts onto the invoice so nothing later can reprice it.
function freezeInvoice(draft) {
  const partner = partnerByCode(draft.partnerCode);
  return {
    reference: draft.reference,
    seller: 'MTN',
    buyer: { code: partner.code, name: partner.name },
    period: draft.period,
    issueDate: draft.issueDate,
    dueDate: draft.dueDate,
    currency: 'NGN',
    lines: draft.lines.map((line) => {
      const product = productByCode(line.productCode);
      return { productCode: product.code, description: product.description, unit: product.unit, quantity: Number(line.quantity), unitPriceMinor: product.priceMinor, lineTotalMinor: lineTotalMinor(line) };
    }),
    totalMinor: draftTotalMinor(draft),
  };
}

// Issuing consumes the draft, so a repeated action for its reference finds
// nothing to issue and returns the simulation unchanged.
export function issueDraft(simulation, reference) {
  const [key, draft] = Object.entries(simulation.drafts).find(([, candidate]) => candidate.reference === reference) ?? [];
  if (!draft || !isIssuable(draft)) return simulation;
  const drafts = { ...simulation.drafts };
  delete drafts[key];
  return { ...simulation, drafts, invoices: [...simulation.invoices, freezeInvoice(draft)] };
}

// The list row that opens an invoice, where focus returns after its detail closes.
export const invoiceOpenerId = (reference) => `sales-open-${reference}`;

export const invoiceByReference = (simulation, reference) => simulation.invoices.find((invoice) => invoice.reference === reference);

export const sequenceOf = (reference) => Number(reference.slice('SIM-INV-'.length));

export const collectionReferenceFor = (sequence) => `SIM-PAY-${String(sequence).padStart(4, '0')}`;
export const collectionSequenceOf = (reference) => Number(reference.slice('SIM-PAY-'.length));
// The sequence only advances when a collection is recorded, so a form keeps one
// action until it succeeds and the next collection is a different action.
export const collectionActionId = (invoiceReference, sequence) => `collect-${invoiceReference}-${sequence}`;

// Status derives from collections, never stored. Collections run oldest first, so
// each one states the balance it left and backdating cannot misorder the history.
export function invoiceBalance(simulation, invoice) {
  let outstandingMinor = invoice.totalMinor;
  const history = simulation.collections
    .filter((collection) => collection.invoiceReference === invoice.reference)
    .sort((a, b) => a.date.localeCompare(b.date) || collectionSequenceOf(a.reference) - collectionSequenceOf(b.reference))
    .map((collection) => {
      outstandingMinor -= collection.amountMinor;
      return { ...collection, outstandingAfterMinor: outstandingMinor };
    });
  const status = !history.length ? 'Unpaid' : outstandingMinor ? 'Partially paid' : 'Paid';
  return { history, status, outstandingMinor, collectedMinor: invoice.totalMinor - outstandingMinor, asOf: history.length ? history[history.length - 1].date : invoice.issueDate };
}

// Exact kobo from typed text, never through a fractional number. Null when the
// text is not a money amount, which includes any sign.
export function parseAmountMinor(text) {
  const match = /^(\d+|\d{1,3}(?:,\d{3})+)(?:\.(\d{1,2}))?$/.exec(text.trim());
  return match ? Number(match[1].replaceAll(',', '')) * 100 + Number((match[2] ?? '').padEnd(2, '0')) : null;
}

export function collectionErrors(invoice, outstandingMinor, { date, amount }) {
  const amountMinor = parseAmountMinor(amount);
  return {
    date: !date ? 'Enter a collection date.' : !isDate(date) ? 'Enter a valid collection date.' : date < invoice.issueDate ? `A collection cannot be dated before the issue date, ${formatDate(invoice.issueDate)}.` : null,
    amount: !amountMinor ? 'Enter a positive NGN amount with at most two decimal places.' : amountMinor > outstandingMinor ? `Enter ${formatMinorNGN(outstandingMinor)} or less, the outstanding balance.` : null,
  };
}

// Repeating an action finds it already recorded and returns the simulation
// unchanged, as does anything invalid or naming something other than an issued invoice.
export function recordCollection(simulation, { actionId, invoiceReference, date, amount }) {
  if (simulation.collections.some((collection) => collection.actionId === actionId)) return simulation;
  const invoice = invoiceByReference(simulation, invoiceReference);
  if (!invoice) return simulation;
  const errors = collectionErrors(invoice, invoiceBalance(simulation, invoice).outstandingMinor, { date, amount });
  if (errors.date || errors.amount) return simulation;
  const collection = { actionId, reference: collectionReferenceFor(simulation.nextCollectionSequence), invoiceReference, date, amountMinor: parseAmountMinor(amount) };
  return { ...simulation, nextCollectionSequence: simulation.nextCollectionSequence + 1, collections: [...simulation.collections, collection] };
}

// The starting point: one example of each status, dated before the presentation's
// own invoice and clear of its account, 296065. Issued and collected through the
// same rules as a presenter's invoices, so an example can never disagree with the catalogue.
const EXAMPLE_INVOICES = [
  { partnerCode: '205044', issueDate: '2026-05-05', dueDate: '2026-06-04', lines: [{ productCode: 'FBB-4G-ROUTER', quantity: '1' }, { productCode: 'RCC-0500', quantity: '50' }], collection: { date: '2026-05-18', amount: '60000' } },
  { partnerCode: '98052', issueDate: '2026-05-08', dueDate: '2026-06-07', lines: [{ productCode: 'FBB-5G-ROUTER', quantity: '2' }, { productCode: 'RCC-0200', quantity: '100' }], collection: { date: '2026-05-20', amount: '45000' } },
  { partnerCode: '74050', issueDate: '2026-05-12', dueDate: '2026-06-11', lines: [{ productCode: 'FBB-4G-ROUTER', quantity: '3' }] },
];

export function startingSimulation() {
  return EXAMPLE_INVOICES.reduce((simulation, { collection, ...example }) => {
    const reference = referenceFor(simulation.nextSequence);
    const period = example.issueDate.slice(0, 7).replace('-', '');
    const issued = issueDraft({ ...simulation, nextSequence: simulation.nextSequence + 1, drafts: { [draftKey(example.partnerCode, period)]: { ...example, reference, period } } }, reference);
    return collection ? recordCollection(issued, { ...collection, actionId: collectionActionId(reference, issued.nextCollectionSequence), invoiceReference: reference }) : issued;
  }, { nextSequence: 1, nextCollectionSequence: 1, partnerCode: '', drafts: {}, invoices: [], collections: [] });
}

// References are unique, so this is a total order: latest date first, then latest reference.
const newestFirst = (a, b) => b.date.localeCompare(a.date) || sequenceOf(b.reference) - sequenceOf(a.reference);

function invoiceRecord(simulation, invoice) {
  const { status, outstandingMinor, asOf } = invoiceBalance(simulation, invoice);
  return { reference: invoice.reference, status, partner: invoice.buyer, date: invoice.issueDate, amountMinor: invoice.totalMinor, outstandingMinor, asOf, period: invoice.period };
}
const draftRecord = (draft) => ({ reference: draft.reference, status: 'Draft', partner: partnerByCode(draft.partnerCode), date: draft.issueDate, amountMinor: draftTotalMinor(draft), period: draft.period });

export const STATUSES = ['Draft', 'Unpaid', 'Partially paid', 'Paid'];

// Invoices belong to their issue month and drafts to their intended issue month.
export function matchingRecords(simulation, { period, search, status }) {
  const term = search.trim().toLowerCase();
  return [...simulation.invoices.map((invoice) => invoiceRecord(simulation, invoice)), ...Object.values(simulation.drafts).map(draftRecord)]
    .filter((record) => record.period === period && (!status || record.status === status) && partnerMatches(record.partner, term))
    .sort(newestFirst);
}

const issuedOf = (records) => records.filter((record) => record.status !== 'Draft');
const outstandingOf = (records) => issuedOf(records).reduce((sum, record) => sum + record.outstandingMinor, 0);
const latestActivityOf = (records) => issuedOf(records).reduce((latest, record) => (record.asOf > latest ? record.asOf : latest), '');

export function summarizeRecords(records) {
  const issued = issuedOf(records).length;
  return { count: records.length, issued, drafts: records.length - issued, outstandingMinor: outstandingOf(records), asOf: latestActivityOf(records) };
}

// One exact account across every month. The balance runs to the account's
// latest simulated activity, not to the end of any reporting month.
export function partnerObligations(simulation, partnerCode) {
  const invoices = simulation.invoices.filter((invoice) => invoice.buyer.code === partnerCode).map((invoice) => invoiceRecord(simulation, invoice)).sort(newestFirst);
  const drafts = Object.values(simulation.drafts).filter((draft) => draft.partnerCode === partnerCode).map(draftRecord).sort(newestFirst);
  return { invoices, drafts, outstandingMinor: outstandingOf(invoices), asOf: latestActivityOf(invoices) };
}
