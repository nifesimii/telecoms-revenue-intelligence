// The handoff between the two logins: a partner submits an order and Finance issues or
// rejects it, each in their own browser context against the real simulation and login
// routes. Finance's other reads are fixtures. backend/tests/test_order_review.py proves
// the server's decision rules.
import { expect, test } from '@playwright/test';

const API_BASE = 'http://localhost:8199';
const PASSWORD = process.env.ACCEPTANCE_PASSWORD;
const cors = { 'access-control-allow-origin': 'http://localhost:5199', 'access-control-allow-credentials': 'true' };

const workspace = (page) => page.getByRole('main', { name: 'Partner Sales' });
const queue = (page) => workspace(page).getByRole('table', { name: 'Orders awaiting review' });
const review = (page, reference) => workspace(page).getByRole('region', { name: `Review order ${reference}` });
const partnerOrders = (page) => workspace(page).getByRole('table', { name: 'Your submitted orders' });
const partnerInvoices = (page) => workspace(page).getByRole('table', { name: 'Your invoices' });
const partnerCommission = (page) => workspace(page).getByRole('region', { name: 'Your Partner Commission Account' });
// The fictional statements for 296065, whose balances no order, invoice or collection changes.
async function expectCommissionUnchanged(page) {
  const account = partnerCommission(page);
  await expect(account.getByLabel('Statement month')).toHaveValue('202606');
  await expect(account.getByLabel('Statement reconciliation')).toContainText('Closing outstandingNGN 1,418,759.61');
  await account.getByLabel('Statement month').selectOption('202605');
  await expect(account.getByLabel('Statement reconciliation')).toContainText('Opening outstandingNGN 250,000.00');
  await expect(account.getByLabel('Statement reconciliation')).toContainText('Closing outstandingNGN 822,582.53');
  await expect(account.getByText('Revenue is not commission entitlement, and it is in no total on this statement.')).toBeVisible();
  await expect(account.getByRole('table', { name: 'Commission by stream' }).getByRole('rowheader', { name: 'Activation commission' })).toBeVisible();
  await expect(account.getByRole('table', { name: 'Commission by stream' }).getByRole('rowheader', { name: 'Subscription commission' })).toBeVisible();
  await expect(account.getByRole('button', { name: /^Explain/ })).toHaveCount(0);
  await expect(account.getByRole('region', { name: 'Existing explanations' })).toHaveCount(0);
}

const simulationStatus = async (page) => (await page.request.get(`${API_BASE}/partner-sales/status`)).json();
const fitsWidth = async (page) => expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);

// A fresh context per side, so the two logins never share a cookie.
async function signedIn(browser, username) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const response = await page.request.post(`${API_BASE}/auth/login`, { data: { username, password: PASSWORD } });
  expect(response.ok()).toBe(true);
  return page;
}

async function openFinance(browser) {
  const page = await signedIn(browser, 'finance');
  expect((await page.request.post(`${API_BASE}/partner-sales/reset`)).ok()).toBe(true);
  await page.route(`${API_BASE}/**`, (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname.startsWith('/partner-sales') || pathname.startsWith('/auth/')) return route.fallback();
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { ...cors, 'access-control-allow-headers': 'content-type,accept,x-fbb-expected-user', 'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE' } });
    if (pathname === '/periods') return route.fulfill({ headers: cors, json: { periods: ['202606', '202605'] } });
    if (pathname === '/health') return route.fulfill({ headers: cors, json: { sample_data_mode: true } });
    return route.fulfill({ status: 503, headers: cors, json: { detail: 'Unavailable in acceptance fixture' } });
  });
  return page;
}

async function openPartnerSales(page) {
  await page.goto('/?view=partner-sales&period=202605');
  await expect(workspace(page).getByRole('heading', { name: 'Orders awaiting review' })).toBeVisible();
}

// Finance opens the presentation's invoice from the May 2026 list and records a collection.
async function financeCollects(page, amount) {
  await openPartnerSales(page);
  await workspace(page).getByRole('button', { name: 'Open invoice SIM-INV-0004' }).click();
  const invoice = workspace(page).getByRole('region', { name: 'Simulated invoice SIM-INV-0004' });
  await invoice.getByLabel('Amount in NGN').fill(amount);
  await invoice.getByRole('button', { name: 'Record collection' }).click();
  await expect(invoice.getByRole('status').filter({ hasText: /^Recorded SIM-PAY-/ })).toBeVisible();
}

// The acceptance example from #7: NGN 110,000.00, as SIM-ORD-0002 after the seeded order.
async function partnerSubmits(browser) {
  const page = await signedIn(browser, 'partner-296065');
  await page.goto('/');
  await workspace(page).getByRole('button', { name: 'Start a draft order' }).click();
  for (const [code, units] of [['FBB-5G-ROUTER', '2'], ['RCC-0100', '100']]) {
    await workspace(page).getByRole('button', { name: `Add ${code} to draft order` }).click();
    await workspace(page).getByRole('textbox', { name: `Quantity for ${code}` }).fill(units);
  }
  await workspace(page).getByRole('button', { name: 'Preview order' }).click();
  await workspace(page).getByRole('button', { name: 'Submit order' }).click();
  await expect(partnerOrders(page).getByRole('row', { name: /SIM-ORD-0002 Submitted/ })).toBeVisible();
  return page;
}

test('Finance issues a partner order and the partner sees the invoice', async ({ browser }) => {
  const finance = await openFinance(browser);
  const partner = await partnerSubmits(browser);
  await expectCommissionUnchanged(partner);
  await openPartnerSales(finance);
  await expect(queue(finance).getByRole('row', { name: /SIM-ORD-0001 Sunset Crest Communications · Account 295083 NGN 109,999\.99/ })).toBeVisible();
  await expect(queue(finance).getByRole('row', { name: /SIM-ORD-0002 River Isle Ventures · Account 296065 NGN 110,000\.00/ })).toBeVisible();

  await queue(finance).getByRole('button', { name: 'Review order SIM-ORD-0002' }).click();
  const order = review(finance, 'SIM-ORD-0002');
  await expect(order.getByRole('heading', { name: 'Review order SIM-ORD-0002' })).toBeFocused();
  await expect(order.getByText('River Isle Ventures · Account 296065')).toBeVisible();
  await expect(order.getByRole('row', { name: /Total NGN 110,000\.00/ })).toBeVisible();

  // The invoice belongs to its issue month, so it stays in the month being reviewed.
  await expect(order.getByLabel('Issue date')).toHaveValue('2026-05-31');
  await order.getByLabel('Issue date').fill('2026-06-02');
  await order.getByLabel('Due date').fill('2026-06-30');
  await order.getByRole('button', { name: 'Issue invoice' }).click();
  await expect(order.getByText('Choose a date in May 2026.')).toBeVisible();
  await expect(order.getByLabel('Issue date')).toBeFocused();
  await order.getByLabel('Issue date').fill('2026-05-30');
  await order.getByLabel('Due date').fill('2026-05-29');
  await order.getByRole('button', { name: 'Issue invoice' }).click();
  await expect(order.getByText('Enter a due date on or after the issue date.')).toBeVisible();
  await expect(order.getByLabel('Due date')).toBeFocused();
  await order.getByLabel('Due date').fill('2026-06-29');
  await order.getByRole('button', { name: 'Issue invoice' }).dblclick();

  const invoice = workspace(finance).getByRole('region', { name: 'Simulated invoice SIM-INV-0004' });
  await expect(invoice.getByRole('heading', { name: 'Simulated invoice SIM-INV-0004' })).toBeFocused();
  await expect(invoice.getByText('From partner order SIM-ORD-0002')).toBeVisible();
  await expect(invoice.getByText('Unpaid', { exact: true })).toBeVisible();
  await invoice.getByRole('button', { name: 'Back to invoices' }).click();
  await expect(workspace(finance).getByRole('status').filter({ hasText: 'Order SIM-ORD-0002 was issued as invoice SIM-INV-0004.' })).toBeFocused();
  await expect(queue(finance).getByRole('row')).toHaveCount(2);
  expect((await simulationStatus(finance)).invoices).toBe(4);

  await partner.reload();
  await expect(partnerOrders(partner).getByRole('row', { name: /SIM-ORD-0002 Issued NGN 110,000\.00/ })).toBeVisible();
  await partnerOrders(partner).getByRole('button', { name: 'Open order SIM-ORD-0002' }).click();
  await expect(workspace(partner).getByText('MTN Finance issued this order as invoice SIM-INV-0004 on 30 May 2026, due 29 Jun 2026.')).toBeVisible();
  await workspace(partner).getByRole('button', { name: 'Back to your orders' }).click();
  await expect(partnerInvoices(partner).getByRole('row', { name: /SIM-INV-0004 30 May 2026 Unpaid NGN 110,000\.00 Outstanding NGN 110,000\.00/ })).toBeVisible();

  // Finance records the collections; the partner sees each on their next refresh.
  await financeCollects(finance, '40,000');
  await partner.reload();
  await expect(partnerInvoices(partner).getByRole('row', { name: /SIM-INV-0004 .* Partially paid NGN 110,000\.00 Outstanding NGN 70,000\.00/ })).toBeVisible();
  await expect(workspace(partner).getByLabel('Totals for all matching invoices')).toContainText('Outstanding purchase obligationNGN 70,000.00');
  await financeCollects(finance, '70,000');
  await partner.reload();
  await partnerInvoices(partner).getByRole('button', { name: 'Open invoice SIM-INV-0004' }).click();
  const seen = workspace(partner).getByRole('region', { name: 'Simulated invoice SIM-INV-0004' });
  await expect(seen.getByRole('heading', { name: 'Simulated invoice SIM-INV-0004' })).toBeFocused();
  await expect(seen.getByText('Paid', { exact: true })).toBeVisible();
  await expect(seen.getByRole('table', { name: 'Collections recorded against SIM-INV-0004' }).getByRole('row')).toHaveCount(3);
  await expect(seen.getByText('From partner order SIM-ORD-0002')).toBeVisible();
  await expect(seen.getByRole('button', { name: 'Record collection' })).toHaveCount(0);
  await expect(seen.getByRole('button', { name: /View purchase obligations/ })).toHaveCount(0);
  await seen.getByRole('button', { name: 'Back to your invoices' }).click();
  await expect(partnerInvoices(partner).getByRole('button', { name: 'Open invoice SIM-INV-0004' })).toBeFocused();
  await expectCommissionUnchanged(partner);

  // The same-named account sees none of it, and only its own statement.
  const namesake = await signedIn(browser, 'partner-353072');
  await namesake.goto('/');
  await expect(workspace(namesake).getByText('MTN Finance has not issued you any invoices yet.')).toBeVisible();
  await expect(workspace(namesake).getByText('You have not submitted any orders yet.')).toBeVisible();
  await expect(partnerCommission(namesake).getByLabel('Statement month')).toHaveValue('202605');
  await expect(partnerCommission(namesake).getByLabel('Statement reconciliation')).toContainText('Opening outstandingUnavailable');
  await expect(partnerCommission(namesake).getByLabel('Statement month').locator('option')).toHaveText(['May 2026']);
});

test('a partner sees their invoice without a payment control until Finance collects', async ({ browser }) => {
  const finance = await openFinance(browser);
  const partner = await partnerSubmits(browser);
  await openPartnerSales(finance);
  await queue(finance).getByRole('button', { name: 'Review order SIM-ORD-0002' }).click();
  await review(finance, 'SIM-ORD-0002').getByLabel('Due date').fill('2026-06-30');
  await review(finance, 'SIM-ORD-0002').getByRole('button', { name: 'Issue invoice' }).click();
  await expect(workspace(finance).getByRole('heading', { name: 'Simulated invoice SIM-INV-0004' })).toBeVisible();

  await partner.setViewportSize({ width: 360, height: 700 });
  await partner.reload();
  await partnerInvoices(partner).getByRole('button', { name: 'Open invoice SIM-INV-0004' }).focus();
  await partner.keyboard.press('Enter');
  const seen = workspace(partner).getByRole('region', { name: 'Simulated invoice SIM-INV-0004' });
  await expect(seen.getByRole('heading', { name: 'Simulated invoice SIM-INV-0004' })).toBeFocused();
  await expect(seen.getByText('NGN 110,000.00 outstanding. MTN Finance records collections against this invoice. Refresh to see new ones.')).toBeVisible();
  await expect(seen.getByRole('textbox', { name: 'Amount in NGN' })).toHaveCount(0);
  await fitsWidth(partner);
  const [invoice] = (await (await partner.request.get(`${API_BASE}/partner-sales/my/invoices`)).json()).items;
  expect((await partner.request.post(`${API_BASE}/partner-sales/invoices/${invoice.reference}/collections`, { data: { token: 'any', action_id: 'partner-try', date: '2026-06-01', amount_minor: 100 } })).status()).toBe(403);

  await seen.getByRole('button', { name: 'Back to your invoices' }).focus();
  await partner.keyboard.press('Enter');
  await expect(partnerInvoices(partner).getByRole('button', { name: 'Open invoice SIM-INV-0004' })).toBeFocused();
  await workspace(partner).getByLabel('Status').selectOption('Paid');
  await expect(workspace(partner).getByText('None of your invoices are paid.')).toBeVisible();
  await workspace(partner).getByRole('button', { name: 'Show all statuses' }).click();
  await expect(workspace(partner).getByLabel('Status')).toBeFocused();
  await expect(partnerInvoices(partner).getByRole('row', { name: /SIM-INV-0004/ })).toBeVisible();
});

test('Finance rejects a partner order with a reason the partner then sees', async ({ browser }) => {
  const finance = await openFinance(browser);
  const partner = await partnerSubmits(browser);
  await openPartnerSales(finance);
  await queue(finance).getByRole('button', { name: 'Review order SIM-ORD-0002' }).click();
  const order = review(finance, 'SIM-ORD-0002');
  await order.getByRole('button', { name: 'Reject order' }).click();
  await expect(order.getByText('Enter a reason for the partner.')).toBeVisible();
  await expect(order.getByLabel('Reason for rejecting')).toBeFocused();
  await order.getByLabel('Reason for rejecting').fill('Recharge cards are out of stock this month.');
  await order.getByRole('button', { name: 'Reject order' }).click();

  const notice = workspace(finance).getByRole('status').filter({ hasText: 'Order SIM-ORD-0002 was rejected. The partner sees your reason when they next refresh.' });
  await expect(notice).toBeFocused();
  await expect(queue(finance).getByRole('row')).toHaveCount(2);
  await expect(queue(finance).getByRole('button', { name: 'Review order SIM-ORD-0002' })).toHaveCount(0);

  await partner.reload();
  await expect(partnerOrders(partner).getByRole('row', { name: /SIM-ORD-0002 Rejected/ })).toBeVisible();
  await partnerOrders(partner).getByRole('button', { name: 'Open order SIM-ORD-0002' }).click();
  await expect(workspace(partner).getByText('MTN Finance rejected this order: Recharge cards are out of stock this month.')).toBeVisible();
  await expect(workspace(partner).getByText('A rejected order is final. Start a new draft to order again.')).toBeVisible();
});

test('an order decided elsewhere is refused with an explanation, and nothing changes', async ({ browser }) => {
  const finance = await openFinance(browser);
  await openPartnerSales(finance);
  await queue(finance).getByRole('button', { name: 'Review order SIM-ORD-0001' }).click();
  const order = review(finance, 'SIM-ORD-0001');
  await expect(order.getByText('Sunset Crest Communications · Account 295083')).toBeVisible();

  // Another Finance session decides it first.
  const elsewhere = await signedIn(browser, 'finance');
  const [waiting] = (await (await elsewhere.request.get(`${API_BASE}/partner-sales/orders`)).json()).items;
  expect((await elsewhere.request.post(`${API_BASE}/partner-sales/orders/SIM-ORD-0001/reject`, { data: { token: waiting.token, reason: 'Duplicate of an earlier order.' } })).ok()).toBe(true);
  const status = await simulationStatus(elsewhere);

  await order.getByLabel('Due date').fill('2026-06-30');
  await order.getByRole('button', { name: 'Issue invoice' }).click();
  await expect(order.getByRole('alert')).toContainText('This order was already decided, possibly in another session, or the simulation was reset. Nothing here was applied.');
  await expect(order.getByRole('button', { name: 'Issue invoice' })).toBeDisabled();
  await expect(order.getByRole('button', { name: 'Reject order' })).toBeDisabled();
  expect(await simulationStatus(elsewhere)).toEqual(status);

  await order.getByRole('button', { name: 'Load latest orders' }).click();
  await expect(workspace(finance).getByRole('heading', { name: 'Orders awaiting review' })).toBeFocused();
  await expect(workspace(finance).getByText('No partner orders await review.')).toBeVisible();
});

test('order review fits a narrow screen', async ({ browser }) => {
  const finance = await openFinance(browser);
  await finance.setViewportSize({ width: 360, height: 700 });
  await openPartnerSales(finance);
  await queue(finance).getByRole('button', { name: 'Review order SIM-ORD-0001' }).click();
  await expect(review(finance, 'SIM-ORD-0001')).toBeVisible();
  await fitsWidth(finance);
});

test('Finance resets for everyone after confirming, and a signed-in partner sees the seed on their next refresh', async ({ browser }) => {
  const finance = await openFinance(browser);
  const partner = await partnerSubmits(browser);
  await workspace(partner).getByRole('button', { name: 'Start a draft order' }).click();
  await workspace(partner).getByRole('button', { name: 'Add RCC-0100 to draft order' }).click();
  await workspace(partner).getByRole('button', { name: 'Save draft' }).click();
  await expect(workspace(partner).getByText('Draft saved. Nothing has been sent to MTN Finance.')).toBeVisible();

  // A partner has no reset, on the page or through the API.
  await expect(partner.getByRole('button', { name: 'Reset simulation' })).toHaveCount(0);
  expect((await partner.request.post(`${API_BASE}/partner-sales/reset`)).status()).toBe(403);
  expect((await simulationStatus(finance)).orders).toBe(2);

  await openPartnerSales(finance);
  await workspace(finance).getByRole('button', { name: 'Reset simulation' }).click();
  const confirm = workspace(finance).getByRole('group', { name: 'Confirm simulation reset' });
  await expect(confirm).toContainText('2 partner orders');
  await expect(confirm.getByRole('button', { name: 'Keep simulation' })).toBeFocused();
  await finance.keyboard.press('Enter');
  await expect(workspace(finance).getByRole('button', { name: 'Reset simulation' })).toBeFocused();
  expect((await simulationStatus(finance)).orders).toBe(2);

  await finance.keyboard.press('Enter');
  await confirm.getByRole('button', { name: 'Reset to starting point' }).click();
  await expect(workspace(finance).getByText('Simulation reset to its starting point: 3 example invoices in May 2026, and the next invoice will be SIM-INV-0004.')).toBeFocused();
  await expect(queue(finance).getByRole('button', { name: 'Review order SIM-ORD-0001' })).toBeVisible();
  await expect(queue(finance).getByRole('button', { name: 'Review order SIM-ORD-0002' })).toHaveCount(0);

  await partner.reload();
  await expect(workspace(partner).getByText('You have no draft order.')).toBeVisible();
  await expect(workspace(partner).getByText('You have not submitted any orders yet.')).toBeVisible();
  await expect(workspace(partner).getByText('MTN Finance has not issued you any invoices yet.')).toBeVisible();
  await expectCommissionUnchanged(partner);
});

test('a session that ends mid-action returns to sign-in with an explanation, and nothing was applied', async ({ browser }) => {
  const finance = await openFinance(browser);
  const partner = await signedIn(browser, 'partner-296065');
  await partner.goto('/');
  await workspace(partner).getByRole('button', { name: 'Start a draft order' }).click();
  await workspace(partner).getByRole('button', { name: 'Add RCC-0100 to draft order' }).click();
  await partner.context().clearCookies();
  await workspace(partner).getByRole('button', { name: 'Save draft' }).click();
  const signIn = partner.getByRole('main', { name: 'Sign in' });
  await expect(signIn.getByText('Your session has ended. Sign in again to continue.')).toBeVisible();
  await expect(signIn.getByText('Demonstration only. Partner Sales records are fictional and are not actual obligations.')).toBeVisible();

  await signIn.getByLabel('Username').fill('partner-296065');
  await signIn.getByLabel('Password').fill(PASSWORD);
  await signIn.getByLabel('Password').press('Enter');
  await expect(workspace(partner).getByRole('heading', { name: 'Your draft order' })).toBeVisible();
  await expect(workspace(partner).getByText('No lines yet. Add a product from the catalogue.')).toBeVisible();

  await openPartnerSales(finance);
  await queue(finance).getByRole('button', { name: 'Review order SIM-ORD-0001' }).click();
  await review(finance, 'SIM-ORD-0001').getByLabel('Due date').fill('2026-06-30');
  await finance.context().clearCookies();
  await review(finance, 'SIM-ORD-0001').getByRole('button', { name: 'Issue invoice' }).click();
  await expect(finance.getByRole('main', { name: 'Sign in' }).getByText('Your session has ended. Sign in again to continue.')).toBeVisible();
  const elsewhere = await signedIn(browser, 'finance');
  expect(await simulationStatus(elsewhere)).toMatchObject({ invoices: 3, orders: 1 });
  expect((await (await elsewhere.request.get(`${API_BASE}/partner-sales/orders`)).json()).items.map((order) => order.reference)).toEqual(['SIM-ORD-0001']);
});

test('ordering, rejection, issuing and collection work by keyboard on a narrow screen', async ({ browser }) => {
  const finance = await openFinance(browser);
  const partner = await signedIn(browser, 'partner-296065');
  const press = async (page, locator) => {
    await locator.focus();
    await page.keyboard.press('Enter');
  };

  await partner.setViewportSize({ width: 360, height: 700 });
  await partner.goto('/');
  await expect(partner.getByText('Synthetic demonstration')).toBeVisible();
  await press(partner, workspace(partner).getByRole('button', { name: 'Start a draft order' }));
  await expect(workspace(partner).getByRole('heading', { name: 'Fictional product catalogue' })).toBeFocused();
  await press(partner, workspace(partner).getByRole('button', { name: 'Add RCC-0100 to draft order' }));
  await expect(workspace(partner).getByRole('textbox', { name: 'Quantity for RCC-0100' })).toBeFocused();
  await partner.keyboard.press('Backspace');
  await partner.keyboard.type('100');
  await press(partner, workspace(partner).getByRole('button', { name: 'Preview order' }));
  await expect(workspace(partner).getByRole('heading', { name: 'Order preview' })).toBeFocused();
  await fitsWidth(partner);
  await press(partner, workspace(partner).getByRole('button', { name: 'Submit order' }));
  await expect(workspace(partner).getByText('Order SIM-ORD-0002 for NGN 10,000.00 was submitted to MTN Finance for review. It can no longer be changed or withdrawn.')).toBeFocused();
  await fitsWidth(partner);

  await finance.setViewportSize({ width: 360, height: 700 });
  await openPartnerSales(finance);
  await expect(finance.getByText('Synthetic demonstration').first()).toBeVisible();
  await press(finance, queue(finance).getByRole('button', { name: 'Review order SIM-ORD-0002' }));
  const rejecting = review(finance, 'SIM-ORD-0002');
  await expect(rejecting.getByRole('heading', { name: 'Review order SIM-ORD-0002' })).toBeFocused();
  await press(finance, rejecting.getByRole('button', { name: 'Reject order' }));
  await expect(rejecting.getByLabel('Reason for rejecting')).toBeFocused();
  await finance.keyboard.type('Order recharge cards in packs of 500.');
  await press(finance, rejecting.getByRole('button', { name: 'Reject order' }));
  await expect(workspace(finance).getByRole('status').filter({ hasText: 'Order SIM-ORD-0002 was rejected.' })).toBeFocused();

  await press(finance, queue(finance).getByRole('button', { name: 'Review order SIM-ORD-0001' }));
  const issuing = review(finance, 'SIM-ORD-0001');
  await expect(issuing.getByRole('heading', { name: 'Review order SIM-ORD-0001' })).toBeFocused();
  await issuing.getByLabel('Due date').fill('2026-06-30');
  await fitsWidth(finance);
  await press(finance, issuing.getByRole('button', { name: 'Issue invoice' }));
  const invoice = workspace(finance).getByRole('region', { name: 'Simulated invoice SIM-INV-0004' });
  await expect(invoice.getByRole('heading', { name: 'Simulated invoice SIM-INV-0004' })).toBeFocused();
  await invoice.getByLabel('Amount in NGN').focus();
  await finance.keyboard.type('40000');
  await press(finance, invoice.getByRole('button', { name: 'Record collection' }));
  await expect(invoice.getByRole('status').filter({ hasText: /^Recorded SIM-PAY-/ })).toBeVisible();
  await expect(invoice.getByText('Partially paid', { exact: true })).toBeVisible();
  await fitsWidth(finance);

  await partner.reload();
  await expect(partnerOrders(partner).getByRole('row', { name: /SIM-ORD-0002 Rejected/ })).toBeVisible();
  await press(partner, partnerOrders(partner).getByRole('button', { name: 'Open order SIM-ORD-0002' }));
  await expect(workspace(partner).getByText('MTN Finance rejected this order: Order recharge cards in packs of 500.')).toBeVisible();
  await fitsWidth(partner);
});

test('signing in as Finance in the same browser stops the partner page before it saves anything', async ({ browser }) => {
  await openFinance(browser);
  const partner = await signedIn(browser, 'partner-296065');
  await partner.goto('/');
  await workspace(partner).getByRole('button', { name: 'Start a draft order' }).click();
  await workspace(partner).getByRole('button', { name: 'Add RCC-0100 to draft order' }).click();

  // Another tab in the same browser profile signs in as Finance, replacing the cookie.
  expect((await partner.request.post(`${API_BASE}/auth/login`, { data: { username: 'finance', password: PASSWORD } })).ok()).toBe(true);
  await workspace(partner).getByRole('button', { name: 'Save draft' }).click();
  const signIn = partner.getByRole('main', { name: 'Sign in' });
  await expect(signIn.getByRole('status')).toContainText('This browser is now signed in as a different user');

  const again = await signedIn(browser, 'partner-296065');
  expect((await (await again.request.get(`${API_BASE}/partner-sales/my/draft`)).json()).draft.lines).toEqual([]);
});

test('signing in as another partner in the same browser applies nothing to either account', async ({ browser }) => {
  await openFinance(browser);
  const partner = await signedIn(browser, 'partner-296065');
  await partner.goto('/');
  await workspace(partner).getByRole('button', { name: 'Start a draft order' }).click();
  await workspace(partner).getByRole('button', { name: 'Add RCC-0100 to draft order' }).click();

  // The same role, so only the page's own login tells the server it was replaced.
  expect((await partner.request.post(`${API_BASE}/auth/login`, { data: { username: 'partner-353072', password: PASSWORD } })).ok()).toBe(true);
  await workspace(partner).getByRole('button', { name: 'Save draft' }).click();
  await expect(partner.getByRole('main', { name: 'Sign in' }).getByRole('status')).toContainText('This browser is now signed in as a different user');

  expect((await (await partner.request.get(`${API_BASE}/partner-sales/my/draft`)).json()).draft).toBeNull();
  const first = await signedIn(browser, 'partner-296065');
  expect((await (await first.request.get(`${API_BASE}/partner-sales/my/draft`)).json()).draft.lines).toEqual([]);
});
