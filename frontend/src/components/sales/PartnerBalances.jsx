// A partner's two separate balances, shown side by side and never netted. Both come
// from the server's own reads for this account, independent of any filter or tab.

import { useQuery } from '@tanstack/react-query';
import { formatMinorNGN, formatPeriod } from '../../lib/format.js';
import { summarizeStatement } from './commissionAccount.js';
import { displayAmount } from './SalesReads.jsx';
import { ownInvoicesQuery, ownStatementQuery } from './useSalesQueries.js';

export const OWN_INVOICE_COUNT = { status: '', limit: 1, offset: 0 };

export default function PartnerBalances({ periods }) {
  const latest = periods[0];
  const read = useQuery({ ...ownStatementQuery(latest), enabled: Boolean(latest) });
  const invoices = useQuery(ownInvoicesQuery(OWN_INVOICE_COUNT));
  // No statement leaves the balance unavailable, never zero.
  const owedToPartner = read.isLoading ? 'Loading…' : displayAmount(summarizeStatement(read.data?.statement ?? null).closingMinor);
  const owedToMtn = invoices.data ? formatMinorNGN(invoices.data.summary.outstanding_minor) : invoices.isError ? 'Unavailable' : 'Loading…';
  return <section className="overview-surface sales-balances" aria-label="Your separate balances">
    <div className="sales-tint">
      <p className="sales-muted">MTN would owe you</p>
      <p className="sales-big">{owedToPartner}</p>
      <p className="sales-note">Closing commission outstanding{latest ? ` · ${formatPeriod(latest)}` : ''}</p>
    </div>
    <div>
      <p className="sales-muted">You would owe MTN</p>
      <p className="sales-big">{owedToMtn}</p>
      <p className="sales-note">Purchase obligation. A separate balance, never netted against commission.</p>
    </div>
  </section>;
}
