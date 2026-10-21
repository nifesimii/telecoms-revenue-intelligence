// Shared semantic colour maps — single source of truth for audit conclusion states.

// Full badge tone: use with a bordered span (bg + text + border).
export const CONCLUSION_BADGE = {
  NOT_PAID:           'bg-red-100 text-red-800 border-red-200',
  PAID:               'bg-emerald-100 text-emerald-800 border-emerald-200',
  EXCESS_ACTIVATION:  'bg-red-100 text-red-800 border-red-200',
  RECONCILED:         'bg-emerald-100 text-emerald-800 border-emerald-200',
  PAID_IN_FULL:       'bg-emerald-100 text-emerald-800 border-emerald-200',
  UNDERPAID:          'bg-red-100 text-red-800 border-red-200',
  OVERPAID:           'bg-amber-100 text-amber-800 border-amber-200',
  DISPUTED_ROUNDING:  'bg-amber-100 text-amber-800 border-amber-200',
  POLICY_MET:         'bg-emerald-100 text-emerald-800 border-emerald-200',
  POLICY_VIOLATED:    'bg-red-100 text-red-800 border-red-200',
  MIXED_ATTRIBUTION:  'bg-amber-100 text-amber-800 border-amber-200',
  INSUFFICIENT_DATA:  'bg-gray-100 text-gray-700 border-gray-200',
};

// Text-only tone: use inline where no background or border is needed.
export const CONCLUSION_TEXT = {
  PAID:               'text-emerald-700',
  PAID_IN_FULL:       'text-emerald-700',
  RECONCILED:         'text-emerald-700',
  POLICY_MET:         'text-emerald-700',
  NOT_PAID:           'text-red-700',
  UNDERPAID:          'text-red-700',
  EXCESS_ACTIVATION:  'text-red-700',
  POLICY_VIOLATED:    'text-red-700',
  OVERPAID:           'text-amber-700',
  DISPUTED_ROUNDING:  'text-amber-700',
  MIXED_ATTRIBUTION:  'text-amber-700',
  INSUFFICIENT_DATA:  'text-gray-600',
};
