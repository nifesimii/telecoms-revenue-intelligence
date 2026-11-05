// The partner selected here is only this tab's view of the shared records.

import { useState } from 'react';

const SELECTED_PARTNER_KEY = 'fbb.partner-sales.partner';

function readSelectedPartner() {
  try {
    return window.sessionStorage.getItem(SELECTED_PARTNER_KEY) ?? '';
  } catch {
    return '';
  }
}

export function useSelectedPartner() {
  const [accountCode, setAccountCode] = useState(readSelectedPartner);
  const select = (next) => {
    setAccountCode(next);
    try {
      if (next) window.sessionStorage.setItem(SELECTED_PARTNER_KEY, next);
      else window.sessionStorage.removeItem(SELECTED_PARTNER_KEY);
    } catch { /* The selection then lasts until this page refreshes. */ }
  };
  return [accountCode, select];
}
