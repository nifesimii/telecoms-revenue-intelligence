// CSV export helper. Single shared implementation so every "Export CSV"
// button across the app produces the same shape (CRLF line endings,
// double-quoted strings with commas / quotes / newlines escaped per RFC 4180).

function _esc(v) {
  const s = v === null || v === undefined ? '' : String(v);
  return s.includes(',') || s.includes('"') || s.includes('\n') || s.includes('\r')
    ? `"${s.replace(/"/g, '""')}"`
    : s;
}

/**
 * Build a CSV string from a list of column descriptors + rows.
 *
 * @param {Array<{key: string, header: string, get?: (row) => any}>} columns
 * @param {Array<object>} rows
 */
export function buildCsv(columns, rows) {
  const header = columns.map((c) => _esc(c.header)).join(',');
  const lines = [header];
  for (const row of rows) {
    lines.push(
      columns
        .map((c) => _esc(c.get ? c.get(row) : row[c.key]))
        .join(','),
    );
  }
  return lines.join('\n');
}

/** Trigger a browser download of `text` as a UTF-8 CSV named `filename`. */
export function downloadCsv(text, filename) {
  const blob = new Blob([text], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/** Convenience: build + download in one call. */
export function exportCsv(columns, rows, filename) {
  downloadCsv(buildCsv(columns, rows), filename);
}
