// Session-scoped Partner Sales state. One browser tab owns its simulation:
// sessionStorage survives refresh and nothing leaves the browser.

import { useEffect, useRef, useState } from 'react';
import { CATALOGUE, PARTNERS, draftKey, dueDateError, issueDateError, sequenceOf } from './salesSimulation.js';

const STORAGE_KEY = 'fbb.partner-sales.simulation';
const STORAGE_VERSION = 2;
const newSimulation = () => ({ version: STORAGE_VERSION, nextSequence: 1, partnerCode: '', drafts: {}, invoices: [] });

const REFERENCE = /^SIM-INV-\d{4,}$/;
const isDate = (value) => /^\d{4}-\d{2}-\d{2}$/.test(value) && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;

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

function isSimulation(saved) {
  if (saved?.version !== STORAGE_VERSION || !Number.isInteger(saved.nextSequence) || saved.nextSequence < 1) return false;
  if (saved.partnerCode !== '' && !PARTNERS.some((partner) => partner.code === saved.partnerCode)) return false;
  if (!saved.drafts || typeof saved.drafts !== 'object') return false;
  if (!Array.isArray(saved.invoices) || !saved.invoices.every(isInvoice)) return false;
  if (!Object.entries(saved.drafts).every(([key, draft]) => isDraft(key, draft))) return false;
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

export default function useSalesSimulation() {
  const [initial] = useState(load);
  const [simulation, setSimulation] = useState(initial.simulation);
  const [saveFailed, setSaveFailed] = useState(initial.saveFailed);
  const [incompatible, setIncompatible] = useState(initial.incompatible);
  const lastPersisted = useRef(initial.simulation);

  useEffect(() => {
    if (simulation === lastPersisted.current) return;
    lastPersisted.current = simulation;
    setSaveFailed(!save(simulation));
  }, [simulation]);

  const startOver = () => {
    try { window.sessionStorage.removeItem(STORAGE_KEY); } catch { /* The next save reports any failure. */ }
    const fresh = newSimulation();
    lastPersisted.current = fresh;
    setSimulation(fresh);
    setIncompatible(false);
  };

  return { simulation, setSimulation, saveFailed, incompatible, startOver, retrySave: () => setSaveFailed(!save(simulation)) };
}
