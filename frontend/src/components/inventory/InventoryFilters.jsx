export const VIEWS = [
  ['exceptions', 'Needs investigation'],
  ['coverage', 'Invoice coverage gaps'],
  ['within', 'Within recorded purchases'],
];

export default function InventoryFilters({ filters, onChange }) {
  return <div className="space-y-4">
    <div role="group" aria-label="Inventory views" className="flex flex-wrap gap-2">{VIEWS.map(([id, label]) => <button key={id}
      className={`overview-button ${filters.view === id ? 'overview-primary' : ''}`} aria-pressed={filters.view === id}
      onClick={() => onChange('view', id)}>{label}</button>)}</div>
    <div className="flex flex-wrap items-end gap-3">
      <label className="text-sm text-gray-600 flex-1 min-w-0">Search dealer or product
        <input type="search" value={filters.search} onChange={(e) => onChange('search', e.target.value)}
          className="overview-select block mt-1 w-full" placeholder="Name or code" />
      </label>
      {filters.view === 'exceptions' && <label className="text-sm text-gray-600">Comparison
        <select className="overview-select block mt-1 max-w-full" value={filters.finding} onChange={(e) => onChange('finding', e.target.value)}>
          <option value="">All requiring investigation</option><option value="CONFIRMED_MISMATCH">Observed excess only</option>
        </select>
      </label>}
      <label className="text-sm text-gray-600">Sort by
        <select className="overview-select block mt-1" value={filters.sort_by} onChange={(e) => onChange('sort_by', e.target.value)}>
          <option value="inventory_gap">Excess units</option><option value="activation_count">Activations</option><option value="dealer_name">Dealer name</option><option value="product_code">Product code</option>
        </select>
      </label>
      <label className="text-sm text-gray-600">Order
        <select className="overview-select block mt-1" value={filters.sort_direction} onChange={(e) => onChange('sort_direction', e.target.value)}>
          <option value="desc">Descending</option><option value="asc">Ascending</option>
        </select>
      </label>
      <button className="overview-button" onClick={() => onChange('reset')}>Reset filters</button>
    </div>
  </div>;
}
