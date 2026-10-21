import { formatNGN } from '../../lib/format.js';

export const statusLabel = (value) => ({ FULLY_PAID: 'Fully paid', PARTIALLY_PAID: 'Partially paid', DISPUTED: 'Disputed', PENDING: 'Pending' }[value] || 'Unavailable');
export const findingLabel = (value) => ({ ALL_UNQUALIFIED: 'All activation records have zero commission', HIGH_UNQUALIFIED_RATE: 'High share of zero-commission records', CONFIRMED_MISMATCH: 'Source reports a mismatch' }[value] || (value ? value.replaceAll('_', ' ').toLowerCase() : 'No source finding'));
export const money = (value) => value == null ? 'Unavailable' : formatNGN(value);
export const percent = (value) => value == null ? 'Unavailable' : `${Number(value).toFixed(1)}%`;
