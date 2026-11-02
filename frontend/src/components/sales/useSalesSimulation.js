// Session-scoped Partner Sales state. One browser tab owns its simulation:
// sessionStorage survives refresh and nothing leaves the browser. The starting
// seed is versioned with the save format: an empty simulation over the fixed
// cohort, catalogue and statements, with references restarting at 0001.

import { useEffect, useRef, useState } from 'react';
import { CATALOGUE, PARTNERS, collectionSequenceOf, draftKey, dueDateError, isDate, issueDateError, sequenceOf } from './salesSimulation.js';

const STORAGE_KEY = 'fbb.partner-sales.simulation';
const STORAGE_VERSION = 3;
const newSimulation = () => ({ version: STORAGE_VERSION, nextSequence: 1, nextCollectionSequence: 1, partnerCode: '', drafts: {}, invoices: [], collections: [] });

const REFERENCE = /^SIM-INV-\d{4,}$/;
const COLLECTION_REFERENCE = /^SIM-PAY-\d{4,}$/;

function isDraft(key, draft) {
  if (!draft || !REFERENCE.test(draft.reference) || !/^\d{6}$/.test(draft.period)) return false;
  if (key !== draftKey(draft.partnerCode, draft.period) || !PARTNERS.some((partner) => partner.code === draft.partnerCode)) return false;
  if ((draft.issueDate !== '' && !isDate(draft.issueDate)) || (draft.dueDate !== '' && !isDate(draft.dueDate))) return false;
  if (!Array.isArray(draft.lines) || new Set(draft.lines.map((line) => line?.productCode)).size !== draft.lines.length) return false;
  return draft.lines.every((line) => typeof line.quantity === 'string' && CATALOGUE.some((product) => product.code === line.productCode));
}

const isAmount = (value) => Number.isSafeInteger(value) && value > 0;

function isInvoice(invoice) {
  if (!invoice || !REFERENCE.test(invoice.reference) || invoice.seller !== 'MTN' || invoice.currency !== 'NGN' || !/^\d{6}$/.test(invoice.period)) return false;
  if (!PARTNERS.some((partner) => partner.code === invoice.buyer?.code) || typeof invoice.buyer.name !== 'string') return false;
  if (!isDate(invoice.issueDate) || (invoice.dueDate !== '' && !isDate(invoice.dueDate)) || issueDateError(invoice, '') || dueDateError(invoice)) return false;
  if (!Array.isArray(invoice.lines) || !invoice.lines.length || !isAmount(invoice.totalMinor)) return false;
  const reconciles = invoice.lines.every((line) => isAmount(line?.quantity) && isAmount(line.unitPriceMinor) && line.lineTotalMinor === line.quantity * line.unitPriceMinor && typeof line.productCode === 'string' && typeof line.description === 'string' && typeof line.unit === 'string');
  return reconciles && invoice.lines.reduce((sum, line) => sum + line.lineTotalMinor, 0) === invoice.totalMinor;
}

// Each collection names one issued invoice, on or after its issue date, and
// together they never take that invoice below zero.
function areCollections(saved) {
  const { collections, invoices, nextCollectionSequence } = saved;
  if (!Array.isArray(collections) || !Number.isInteger(nextCollectionSequence) || nextCollectionSequence < 1) return false;
  const issued = new Map(invoices.map((invoice) => [invoice.reference, invoice]));
  const collected = new Map();
  for (const collection of collections) {
    const invoice = issued.get(collection?.invoiceReference);
    if (!invoice || typeof collection.actionId !== 'string' || !collection.actionId || !COLLECTION_REFERENCE.test(collection.reference)) return false;
    if (!isDate(collection.date) || collection.date < invoice.issueDate || !isAmount(collection.amountMinor) || collectionSequenceOf(collection.reference) >= nextCollectionSequence) return false;
    const total = (collected.get(invoice.reference) ?? 0) + collection.amountMinor;
    if (total > invoice.totalMinor) return false;
    collected.set(invoice.reference, total);
  }
  return new Set(collections.map((collection) => collection.actionId)).size === collections.length && new Set(collections.map((collection) => collection.reference)).size === collections.length;
}

function isSimulation(saved) {
  if (saved?.version !== STORAGE_VERSION || !Number.isInteger(saved.nextSequence) || saved.nextSequence < 1) return false;
  if (saved.partnerCode !== '' && !PARTNERS.some((partner) => partner.code === saved.partnerCode)) return false;
  if (!saved.drafts || typeof saved.drafts !== 'object') return false;
  if (!Array.isArray(saved.invoices) || !saved.invoices.every(isInvoice)) return false;
  if (!Object.entries(saved.drafts).every(([key, draft]) => isDraft(key, draft))) return false;
  if (!areCollections(saved)) return false;
  // A reference names one obligation: never two invoices, a draft already issued,
  // or a sequence the next draft would reuse.
  const references = [...saved.invoices, ...Object.values(saved.drafts)].map((record) => record.reference);
  return new Set(references).size === references.length && references.every((reference) => sequenceOf(reference) < saved.nextSequence);
}

function load() {
  let raw;
  try {
    raw = window.sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return { simulation: newSimulation(), saveFailed: true, incompatible: false };
  }
  if (raw === null) return { simulation: newSimulation(), saveFailed: false, incompatible: false };
  try {
    const saved = JSON.parse(raw);
    if (isSimulation(saved)) return { simulation: saved, saveFailed: false, incompatible: false };
  } catch { /* Unreadable content is reported like any other incompatible save. */ }
  return { simulation: newSimulation(), saveFailed: false, incompatible: true };
}

function save(simulation) {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(simulation));
    return true;
  } catch {
    return false;
  }
}

function clear() {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
    return true;
  } catch {
    return false;
  }
}

export default function useSalesSimulation() {
  const [initial] = useState(load);
  const [simulation, setSimulation] = useState(initial.simulation);
  const [saveFailed, setSaveFailed] = useState(initial.saveFailed);
  const [incompatible, setIncompatible] = useState(initial.incompatible);
  const [clearFailed, setClearFailed] = useState(false);
  const lastPersisted = useRef(initial.simulation);

  // Any successful save replaces whatever a failed reset left behind.
  const persist = (current) => {
    const saved = save(current);
    setSaveFailed(!saved);
    if (saved) setClearFailed(false);
    return saved;
  };

  useEffect(() => {
    if (simulation === lastPersisted.current) return;
    lastPersisted.current = simulation;
    persist(simulation);
  }, [simulation]);

  // Touches only this simulation's key. A save that survives would return on
  // refresh, so it is overwritten if it cannot be removed, and reported if neither works.
  const startOver = () => {
    const fresh = newSimulation();
    const cleared = clear() || save(fresh);
    lastPersisted.current = fresh;
    setSimulation(fresh);
    setIncompatible(false);
    setSaveFailed(!cleared);
    setClearFailed(!cleared);
    return fresh;
  };

  return { simulation, setSimulation, saveFailed, clearFailed, incompatible, startOver, retrySave: () => persist(simulation) };
}
