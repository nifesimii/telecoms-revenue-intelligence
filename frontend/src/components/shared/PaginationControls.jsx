export default function PaginationControls({ pagination, onOffsetChange, pageSize, onPageSizeChange }) {
  if (!pagination) return null;
  const start = pagination.total ? pagination.offset + 1 : 0;
  const end = pagination.offset + pagination.returned;
  return (
    <div className="flex items-center gap-3 text-[11px] text-gray-500">
      <span>{start.toLocaleString()}–{end.toLocaleString()} of {pagination.total.toLocaleString()}</span>
      <select
        value={pageSize}
        onChange={(e) => onPageSizeChange(Number(e.target.value))}
        className="border border-gray-200 rounded px-1 py-0.5 bg-white"
        aria-label="Rows per page"
      >
        {[25, 50, 100].map((n) => <option key={n} value={n}>{n} rows</option>)}
      </select>
      <button
        onClick={() => onOffsetChange(Math.max(0, pagination.offset - pagination.limit))}
        disabled={pagination.offset === 0}
        className="border border-gray-200 rounded px-2 py-0.5 disabled:opacity-40"
      >Previous</button>
      <button
        onClick={() => onOffsetChange(pagination.offset + pagination.limit)}
        disabled={!pagination.has_more}
        className="border border-gray-200 rounded px-2 py-0.5 disabled:opacity-40"
      >Next</button>
    </div>
  );
}
