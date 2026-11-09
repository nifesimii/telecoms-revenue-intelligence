// A partner's own fictional Partner Commission Account, one month at a time. The
// server sends only this account's statements, and nothing here links to the internal
// explanation workspaces.

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { formatPeriod } from '../../lib/format.js';
import { CommissionStatement } from './CommissionAccount.jsx';
import { ReadState } from './SalesReads.jsx';
import { ownStatementQuery } from './useSalesQueries.js';

const HEADING = 'sales-own-commission-heading';

export default function PartnerCommission({ partner, periods }) {
  const [period, setPeriod] = useState(periods[0]);
  const read = useQuery({ ...ownStatementQuery(period), enabled: Boolean(period) });
  const heading = <div className="sales-sec">
    <div><h2 id={HEADING} aria-label="Your Partner Commission Account" className="sales-h">Commission statement</h2>
      <p className="sales-muted">Closing outstanding is opening outstanding plus earnings less settlements.</p></div>
    {periods.length > 0 && <label><span className="sr-only">Statement month</span><select className="overview-select" value={period} onChange={(event) => setPeriod(event.target.value)}>
      {periods.map((option) => <option key={option} value={option}>{formatPeriod(option)}</option>)}
    </select></label>}
  </div>;
  if (!periods.length || !read.data || read.isError) {
    return <section className="overview-surface" aria-labelledby={HEADING}>{heading}
      <div className="sales-body">{periods.length ? <ReadState query={read} what="commission statement" /> : <p role="status" className="sales-muted">No fictional commission statement exists for your account. Its amounts are unavailable, not zero.</p>}</div>
    </section>;
  }
  return <section className="sales-stack" aria-labelledby={HEADING}>
    <CommissionStatement statement={read.data.statement} partner={partner} period={period} heading={heading} />
  </section>;
}
