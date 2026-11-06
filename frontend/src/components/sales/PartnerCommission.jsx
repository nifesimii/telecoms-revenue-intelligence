// A partner's own fictional Partner Commission Account, one month at a time. The
// server sends only this account's statements, and nothing here links to the internal
// explanation workspaces.

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { formatPeriod } from '../../lib/format.js';
import { CommissionStatement } from './CommissionAccount.jsx';
import { ReadState } from './InvoiceViews.jsx';
import { ownStatementQuery } from './useSalesQueries.js';

export default function PartnerCommission({ partner, periods }) {
  const [period, setPeriod] = useState(periods[0]);
  return <section className="sales-paper" aria-labelledby="sales-own-commission-heading">
    <h2 id="sales-own-commission-heading" className="text-lg font-semibold">Your Partner Commission Account</h2>
    <p className="text-xs text-gray-600 mt-1">Fictional commission MTN would owe you. Your invoices are what you would owe MTN, a separate balance that is never netted against this one.</p>
    {!periods.length ? <p role="status" className="text-sm text-gray-600 mt-4">No fictional commission statement exists for your account. Its amounts are unavailable, not zero.</p> : <>
      <div className="sales-filters">
        <label className="sales-field">Statement month<select value={period} onChange={(event) => setPeriod(event.target.value)}>
          {periods.map((option) => <option key={option} value={option}>{formatPeriod(option)}</option>)}
        </select></label>
      </div>
      <OwnStatement partner={partner} period={period} />
    </>}
  </section>;
}

function OwnStatement({ partner, period }) {
  const read = useQuery(ownStatementQuery(period));
  return <>
    <ReadState query={read} what="commission statement" />
    {read.data && <CommissionStatement statement={read.data.statement} partner={partner} period={period} />}
  </>;
}
