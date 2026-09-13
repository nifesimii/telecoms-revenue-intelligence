export const VIEWS = [['accounts', 'Dealer accounts'], ['comparison', 'Period comparison'], ['exceptions', 'Exceptions']];
export default function ActivationFilters({ filters, classes, onFilter }) {
  return <div className="space-y-3">
    <div className="flex flex-wrap gap-3">
      <label className="flex-1 min-w-0 basis-full sm:basis-56 text-xs text-gray-600">Search accounts<input type="search" className="overview-select mt-1 w-full" placeholder="Dealer name or account code" value={filters.search} onChange={(e) => onFilter('search', e.target.value)} /></label>
      <label className="text-xs text-gray-600 flex-1 min-w-0">Partner class<select className="overview-select mt-1 w-full" value={filters.partner_class} onChange={(e) => onFilter('partner_class', e.target.value)}><option value="">All classes</option>{classes.map((c) => <option key={c} value={c}>{c}</option>)}</select></label>
      <label className="text-xs text-gray-600 flex-1 min-w-0">Finding<select className="overview-select mt-1 w-full" value={filters.finding} onChange={(e) => onFilter('finding', e.target.value)}><option value="all">All accounts</option><option value="with_zero">With zero commission</option><option value="all_zero">Entirely zero commission</option><option value="ALL_UNQUALIFIED">All activations have zero commission</option><option value="HIGH_UNQUALIFIED_RATE">More than half have zero commission</option><option value="UNUSUAL_VOLUME">Unusual activation volume</option></select></label>
    </div>
    <div className="flex flex-wrap gap-3 items-center text-sm">
      <label className="flex flex-wrap gap-2 items-center text-gray-600">Sort by<select className="overview-select max-w-full" value={filters.sort_by} onChange={(e) => onFilter('sort_by', e.target.value)}><option value="activation_count">Activation records</option><option value="dealer_name">Dealer name</option><option value="non_qualified_activation_count">Zero-commission records</option><option value="qualification_rate_pct">Qualification rate</option><option value="activation_commission_amount">Recorded commission</option><option value="delta_activations">Activation change</option><option value="severity">Finding severity</option></select></label>
      <button className="overview-button" onClick={() => onFilter('direction', filters.direction === 'desc' ? 'asc' : 'desc')}>{filters.direction === 'desc' ? 'Descending ↓' : 'Ascending ↑'}</button>
      {(filters.search || filters.partner_class || filters.finding !== 'all') && <button className="underline" onClick={() => onFilter('reset')}>Clear filters</button>}
    </div>
  </div>;
}
