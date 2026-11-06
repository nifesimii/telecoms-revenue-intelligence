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
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { ...cors, 'access-control-allow-headers': 'content-type,accept', 'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE' } });
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
  expect((await (await finance.request.get(`${API_BASE}/partner-sales/status`)).json()).invoices).toBe(4);

  await partner.reload();
  await expect(partnerOrders(partner).getByRole('row', { name: /SIM-ORD-0002 Issued NGN 110,000\.00/ })).toBeVisible();
  await partnerOrders(partner).getByRole('button', { name: 'Open order SIM-ORD-0002' }).click();
  await expect(workspace(partner).getByText('MTN Finance issued this order as invoice SIM-INV-0004 on 30 May 2026, due 29 Jun 2026.')).toBeVisible();
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
  const status = await (await elsewhere.request.get(`${API_BASE}/partner-sales/status`)).json();

  await order.getByLabel('Due date').fill('2026-06-30');
  await order.getByRole('button', { name: 'Issue invoice' }).click();
  await expect(order.getByRole('alert')).toContainText('This order was already decided, possibly in another session, or the simulation was reset. Nothing here was applied.');
  await expect(order.getByRole('button', { name: 'Issue invoice' })).toBeDisabled();
  await expect(order.getByRole('button', { name: 'Reject order' })).toBeDisabled();
  expect(await (await elsewhere.request.get(`${API_BASE}/partner-sales/status`)).json()).toEqual(status);

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
  expect(await finance.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
});
