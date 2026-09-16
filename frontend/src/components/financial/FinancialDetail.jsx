import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getFinancialReport } from '../../api/client.js';
import { formatNGN, formatPeriod } from '../../lib/format.js';
import { downloadCsv } from '../../lib/csv.js';
import { financialReportCsv, metricValue } from './financialPresentation.js';
import FinancialStatements from './FinancialStatements.jsx';

export default function FinancialDetail({ dealer, period, onBack }) {
  const heading = useRef(null);
  const [exportError, setExportError] = useState('');
  const query = useQuery({ queryKey: ['financial-report', dealer.dealer_id, period],
    queryFn: ({ signal }) => getFinancialReport(dealer.dealer_id, period, signal) });
  useEffect(() => { heading.current?.focus(); }, []);
  const report = query.data;
  function exportReport() {
    try { downloadCsv(financialReportCsv(report), `synthetic_financial_statements_${report.dealer_id}_${period}.csv`); setExportError(''); }
    catch { setExportError('The report could not be downloaded. Please retry.'); }
  }
  return <>
    <p className="hidden print:block text-xs">Synthetic demonstration — fictional financial records; no live accounts connected.</p>
    <button className="fh-button self-start" onClick={onBack}>← All dealers</button>
    <div className="flex flex-wrap justify-between gap-4 items-start">
      <div><p className="text-xs text-gray-500 mb-1">{dealer.dealer_id}</p>
        <h2 className="text-2xl font-semibold" ref={heading} tabIndex={-1}>{dealer.dealer_name}</h2>
        <p className="text-sm text-gray-600 mt-2">{dealer.scenario}</p></div>
      {report && !query.isError && <button className="fh-button" disabled={query.isFetching} onClick={exportReport}>Export financial report</button>}
    </div>
    {exportError && <p role="alert" className="text-red-800">{exportError}</p>}
    {query.isPending ? <div className="fh-paper p-6" role="status">Loading statements and supporting evidence…</div>
      : query.isError ? <div className="fh-paper p-6" role="alert"><p>Financial statements could not be loaded for this dealer and month.</p><button className="fh-button mt-3" onClick={() => query.refetch()}>Retry statements</button></div>
      : report && <>
        <div className="text-sm text-gray-600 flex flex-wrap justify-between gap-2"><p>{report.scope}</p><p>{formatPeriod(period)}{report.prior_period ? ` compared with ${formatPeriod(report.prior_period)}` : ' · No earlier comparison'}</p></div>
        <section className="fh-paper" aria-label="Financial health indicators">
          <div className="px-5 pt-5"><h2 className="text-base font-semibold">Financial health at a glance</h2><p className="text-xs text-gray-600 mt-1">Six indicators for review. Open a calculation to see its inputs.</p></div>
          <div className="fh-metrics">{report.kpis.map((metric) => <div key={metric.id} className="fh-metric">
            <h3 className="text-xs font-medium text-gray-600">{metric.label}</h3>
            <p className={`fh-metric-value ${metric.value < 0 ? 'text-red-800' : ''}`}>{metric.value == null ? metric.status === 'not_applicable' ? 'Not applicable' : metric.status === 'not_meaningful' ? 'Not meaningful' : 'Unavailable' : metricValue(metric.value, metric.unit)}</p>
            <p className="text-xs text-gray-500">Prior month: {metric.prior_value == null ? '—' : metricValue(metric.prior_value, metric.unit)}</p>
            {metric.reason && <p className="text-xs text-amber-900 mt-2">{metric.reason}</p>}
            <details className="fh-calculation"><summary>Calculation</summary><p className="mt-2">{metric.formula}</p><dl className="mt-2 space-y-1">{Object.entries(metric.inputs).map(([key, value]) => <div key={key}><dt className="capitalize">{key.replaceAll('_', ' ')}</dt><dd className="font-medium">{value == null ? 'Unavailable' : formatNGN(value)}</dd></div>)}</dl></details>
          </div>)}</div>
        </section>
        <FinancialStatements report={report} />
        <section className="fh-paper p-5 sm:p-6" aria-label="Statement observations">
          <h2 className="text-lg font-semibold">What the statements show</h2>
          <div className="divide-y divide-gray-200 mt-3">{report.observations.map((observation) => <article key={observation.title} className="py-4">
            <h3 className="text-sm font-semibold">{observation.title}</h3><p className="text-sm text-gray-600 mt-1">{observation.detail}</p>
            <dl className="flex flex-wrap gap-x-6 gap-y-2 mt-3 text-xs">{observation.evidence.map((key) => <div key={key}><dt className="capitalize text-gray-500">{key.replaceAll('_', ' ')}</dt><dd className="font-medium mt-1">{report.values[key] == null ? 'Unavailable' : formatNGN(report.values[key])}</dd></div>)}</dl>
          </article>)}</div>
        </section>
        <details className="fh-paper p-5 sm:p-6">
          <summary className="text-sm font-semibold cursor-pointer">Statement details</summary>
          <div className="divide-y divide-gray-200 mt-3">{report.evidence.map((source) => <div key={source.id} className="py-4">
            <div className="flex flex-wrap justify-between gap-2"><h3 className="text-sm font-semibold">{source.label}</h3><span className="text-xs font-medium text-amber-900">{[source.status === 'Synthetic' ? null : source.status, source.as_of ? `Through ${source.as_of}` : null].filter(Boolean).join(' · ')}</span></div>
            <p className="text-sm text-gray-600 mt-1">{source.detail}</p>
          </div>)}</div>
          <details className="border-t border-gray-200 pt-4 text-sm"><summary className="font-medium cursor-pointer">Statement assumptions</summary><ul className="list-disc pl-5 mt-3 space-y-2 text-gray-600">{report.assumptions.map((note) => <li key={note}>{note}</li>)}</ul></details>
        </details>
      </>}
  </>;
}
