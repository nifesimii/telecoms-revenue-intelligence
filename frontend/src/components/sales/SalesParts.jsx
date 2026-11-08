// The pieces every Partner Sales screen shares, for both logins.

const BADGE_TONE = { Unpaid: 'unpaid', 'Partially paid': 'partial', Paid: 'paid', Issued: 'issued', Rejected: 'rejected' };

// The word carries the status, and the colour only repeats it.
export function StatusBadge({ status }) {
  return <span className={`sales-badge ${BADGE_TONE[status] ? `sales-badge-${BADGE_TONE[status]}` : ''}`}>{status}</span>;
}

export function PartnerCell({ partner }) {
  return <>{partner.name}<span className="sales-sub">Account {partner.code}</span></>;
}

// One visible line that names the screen as fictional, expanding to the full text.
export function Disclaimer({ summary, className = '', children }) {
  return <details className={`sales-disclaimer ${className}`}>
    <summary>{summary}</summary>
    <p>{children}</p>
  </details>;
}

export function Figures({ items }) {
  return <dl className="sales-figures">{items.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}

// The heading's name keeps the record's reference, which the visible title moves to the
// line below, so a screen reader landing on it still hears which record opened.
export function DetailHeader({ eyebrow, title, headingId, headingLabel, meta, backLabel, onBack, backDisabled }) {
  return <>
    <div><button type="button" className="overview-button sales-back" disabled={backDisabled} onClick={onBack}>{backLabel}</button></div>
    <div>
      <p className="sales-eyebrow">{eyebrow}</p>
      <h1 id={headingId} tabIndex={-1} aria-label={headingLabel} className="sales-title">{title}</h1>
      {meta && <p className="sales-muted mt-1">{meta}</p>}
    </div>
  </>;
}
