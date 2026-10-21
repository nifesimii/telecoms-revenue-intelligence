import { useRef } from 'react';
import { parseSort, sortOptionsFor, sortValue } from './inventoryPresentation.js';

export const VIEWS = [
  ['exceptions', 'Needs investigation'],
  ['coverage', 'Invoice coverage gaps'],
  ['within', 'Within recorded purchases'],
];

export function InventoryViewTabs({ view, onChange }) {
  const tabRefs = useRef({});
  function activate(index) {
    const [id] = VIEWS[(index + VIEWS.length) % VIEWS.length];
    tabRefs.current[id]?.focus();
    onChange('view', id);
  }
  function onKeyDown(e, index) {
    const target = { ArrowLeft: index - 1, ArrowRight: index + 1, Home: 0, End: VIEWS.length - 1 }[e.key];
    if (target === undefined) return;
    e.preventDefault();
    activate(target);
  }
  return <div role="tablist" aria-label="Inventory views" className="flex flex-wrap gap-4 border-b border-gray-200">{VIEWS.map(([id, label], i) => {
    const selected = view === id;
    return <button key={id} ref={(node) => { tabRefs.current[id] = node; }} type="button" role="tab" id={`inventory-tab-${id}`}
      aria-controls="inventory-view-panel" aria-selected={selected} tabIndex={selected ? 0 : -1}
      className={`-mb-px border-b-2 px-1 py-2 text-sm ${selected ? 'border-gray-900 font-semibold text-gray-900' : 'border-transparent text-gray-600 hover:text-gray-900'}`}
      onClick={() => onChange('view', id)} onKeyDown={(e) => onKeyDown(e, i)}>{label}</button>;
  })}</div>;
}

export default function InventoryFilters({ filters, onChange }) {
  const options = sortOptionsFor(filters.view);
  function changeSort(value) {
    const { sort_by, sort_direction } = parseSort(value);
    onChange('sort_by', sort_by);
    onChange('sort_direction', sort_direction);
  }
  return <div className="flex flex-wrap items-end gap-3">
    <label className="text-sm text-gray-600 w-full sm:w-auto sm:flex-1 min-w-0">Search dealer or product
      <input type="search" value={filters.search} onChange={(e) => onChange('search', e.target.value)}
        className="overview-select block mt-1 w-full" placeholder="Name or code" />
    </label>
    {filters.view === 'exceptions' && <label className="text-sm text-gray-600">Comparison
      <select className="overview-select block mt-1 max-w-full" value={filters.finding} onChange={(e) => onChange('finding', e.target.value)}>
        <option value="">All requiring investigation</option><option value="CONFIRMED_MISMATCH">Observed excess only</option>
      </select>
    </label>}
    <label className="text-sm text-gray-600">Sort by
      <select className="overview-select block mt-1" value={sortValue(filters.sort_by, filters.sort_direction, options)} onChange={(e) => changeSort(e.target.value)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
    <button className="overview-button" onClick={() => onChange('reset')}>Reset filters</button>
  </div>;
}
