// Session-scoped Partner Sales state. One browser tab owns its simulation:
// sessionStorage survives refresh and nothing leaves the browser.

import { useEffect, useRef, useState } from 'react';
import { CATALOGUE, PARTNERS, draftKey } from './salesSimulation.js';

const STORAGE_KEY = 'fbb.partner-sales.simulation';
const STORAGE_VERSION = 1;
const newSimulation = () => ({ version: STORAGE_VERSION, nextSequence: 1, partnerCode: '', drafts: {} });

const isDate = (value) => /^\d{4}-\d{2}-\d{2}$/.test(value) && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;

function isDraft(key, draft) {
  if (!draft || !/^SIM-INV-\d{4,}$/.test(draft.reference) || !/^\d{6}$/.test(draft.period)) return false;
  if (key !== draftKey(draft.partnerCode, draft.period) || !PARTNERS.some((partner) => partner.code === draft.partnerCode)) return false;
  if ((draft.issueDate !== '' && !isDate(draft.issueDate)) || (draft.dueDate !== '' && !isDate(draft.dueDate))) return false;
  if (!Array.isArray(draft.lines) || new Set(draft.lines.map((line) => line?.productCode)).size !== draft.lines.length) return false;
  return draft.lines.every((line) => typeof line.quantity === 'string' && CATALOGUE.some((product) => product.code === line.productCode));
}

function isSimulation(saved) {
  if (saved?.version !== STORAGE_VERSION || !Number.isInteger(saved.nextSequence) || saved.nextSequence < 1) return false;
  if (saved.partnerCode !== '' && !PARTNERS.some((partner) => partner.code === saved.partnerCode)) return false;
  if (!saved.drafts || typeof saved.drafts !== 'object') return false;
  return Object.entries(saved.drafts).every(([key, draft]) => isDraft(key, draft));
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
