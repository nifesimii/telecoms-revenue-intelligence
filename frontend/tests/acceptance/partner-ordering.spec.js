// A partner's own ordering at the rendered application boundary, against the real
// simulation and login routes. Finance is a separate request context, so it never
// shares the partner's cookie. backend/tests/test_partner_orders.py proves the
// server enforces ownership and the order rules.
import { expect, test } from '@playwright/test';

const API_BASE = 'http://localhost:8199';
const PASSWORD = process.env.ACCEPTANCE_PASSWORD;

async function finance(playwright) {
  const context = await playwright.request.newContext();
  const response = await context.post(`${API_BASE}/auth/login`, { data: { username: 'finance', password: PASSWORD } });
  expect(response.ok()).toBe(true);
  return context;
}

// Starts each test from the seed, and records any request outside the simulation.
async function signInAsPartner(page, playwright, username = 'partner-296065') {
  const internal = await finance(playwright);
  expect((await internal.post(`${API_BASE}/partner-sales/reset`)).ok()).toBe(true);
  const outside = [];
  page.on('request', (request) => {
    const { pathname } = new URL(request.url());
    if (request.url().startsWith(API_BASE) && request.method() !== 'OPTIONS' && !pathname.startsWith('/auth/') && !pathname.startsWith('/partner-sales/my/')) outside.push(`${request.method()} ${pathname}`);
  });
  await page.goto('/');
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(workspace(page).getByRole('heading', { level: 1 })).toBeVisible();
  return { internal, outside };
}

const workspace = (page) => page.getByRole('main', { name: 'Partner Sales' });
const showTab = (page, name) => workspace(page).getByRole('navigation', { name: 'Partner Sales sections' }).getByRole('button', { name: new RegExp(`^${name}`) }).click();
const quantity = (page, code) => workspace(page).getByRole('textbox', { name: `Quantity for ${code}` });
const orderTotal = (page) => workspace(page).getByText('Order total').locator('..');
const orders = (page) => workspace(page).getByRole('table', { name: 'Your submitted orders' });
const startDraft = (page) => workspace(page).getByRole('button', { name: 'Start a draft order' }).click();
const addLine = async (page, code, units) => {
  await workspace(page).getByRole('button', { name: `Add ${code} to draft order` }).click();
  await expect(quantity(page, code)).toBeFocused();
  await quantity(page, code).fill(units);
};
const draftAcceptanceExample = async (page) => {
  await startDraft(page);
  await addLine(page, 'FBB-5G-ROUTER', '2');
  await addLine(page, 'RCC-0100', '100');
};
const preview = (page) => workspace(page).getByRole('region', { name: 'Order preview' });

test('a partner drafts, previews and submits an order in their own account', async ({ page, playwright }) => {
  const { internal, outside } = await signInAsPartner(page, playwright);
  await expect(workspace(page).getByRole('heading', { level: 1, name: 'River Isle Ventures' })).toBeVisible();
  await expect(workspace(page).getByText('Account 296065', { exact: true })).toBeVisible();
  await expect(workspace(page).getByRole('radio')).toHaveCount(0);
  await showTab(page, 'My orders');
  await expect(workspace(page).getByText('You have not submitted any orders yet.')).toBeVisible();
  await showTab(page, 'Order');

  await draftAcceptanceExample(page);
  const draftLines = workspace(page).getByRole('list', { name: 'Draft order lines' });
  await expect(draftLines.getByText('NGN 100,000.00')).toBeVisible();
  await expect(draftLines.getByText('NGN 10,000.00')).toBeVisible();
  await expect(orderTotal(page)).toContainText('NGN 110,000.00');

  await workspace(page).getByRole('button', { name: 'Preview order' }).click();
  await expect(preview(page).getByRole('heading', { name: 'Order preview' })).toBeFocused();
  await expect(preview(page).getByRole('row', { name: /Total NGN 110,000\.00/ })).toBeVisible();
  const before = await (await internal.get(`${API_BASE}/partner-sales/status`)).json();
  // The seeded order awaits Finance from the start.
  expect(before.orders).toBe(1);

  await preview(page).getByRole('button', { name: 'Submit order' }).dblclick();
  const notice = workspace(page).getByRole('status').filter({ hasText: 'Order SIM-ORD-0002 for NGN 110,000.00 was submitted' });
  await expect(notice).toBeFocused();
  await showTab(page, 'My orders');
  await expect(orders(page).getByRole('row', { name: /SIM-ORD-0002 Submitted NGN 110,000\.00/ })).toBeVisible();
  await expect(orders(page).getByRole('row')).toHaveCount(2);
  expect((await (await internal.get(`${API_BASE}/partner-sales/status`)).json()).orders).toBe(2);

  await page.reload();
  await showTab(page, 'My orders');
  await orders(page).getByRole('button', { name: 'Open order SIM-ORD-0002' }).click();
  const detail = workspace(page).getByRole('region', { name: 'Order SIM-ORD-0002' });
  await expect(detail.getByRole('heading', { name: 'Order SIM-ORD-0002' })).toBeFocused();
  await expect(detail.getByText('read-only')).toBeVisible();
  await expect(detail.getByRole('textbox')).toHaveCount(0);
  await expect(detail.getByRole('button')).toHaveText(['Back to your orders']);
  await detail.getByRole('button', { name: 'Back to your orders' }).click();
  await expect(orders(page).getByRole('button', { name: 'Open order SIM-ORD-0002' })).toBeFocused();
  expect(outside).toEqual([]);
});

test('empty drafts and invalid quantities explain themselves and are not sent', async ({ page, playwright }) => {
  const { internal } = await signInAsPartner(page, playwright);
  await startDraft(page);
  await workspace(page).getByRole('button', { name: 'Preview order' }).click();
  await expect(workspace(page).getByRole('alert')).toHaveText('Add at least one product before previewing.');
  await expect(workspace(page).getByRole('heading', { name: 'Your draft order' })).toBeFocused();

  await addLine(page, 'FBB-4G-ROUTER', '1.5');
  await expect(workspace(page).getByText('Enter a positive whole number.')).toBeVisible();
  await expect(orderTotal(page)).toContainText('Unavailable until quantities are corrected');
  await workspace(page).getByRole('button', { name: 'Preview order' }).click();
  await expect(workspace(page).getByRole('alert')).toHaveText('Correct the highlighted quantities before previewing.');
  await expect(quantity(page, 'FBB-4G-ROUTER')).toBeFocused();
  await quantity(page, 'FBB-4G-ROUTER').fill('3');
  await expect(orderTotal(page)).toContainText('NGN 105,000.00');
  await expect(preview(page)).toHaveCount(0);
  expect((await (await internal.get(`${API_BASE}/partner-sales/status`)).json()).orders).toBe(1);
});

test('a saved draft stays private and survives a refresh, and can be deleted', async ({ page, playwright }) => {
  const { internal } = await signInAsPartner(page, playwright);
  const financeView = async () => [await (await internal.get(`${API_BASE}/partner-sales/status`)).json(), await (await internal.get(`${API_BASE}/partner-sales/records?mon_period=202605`)).json()];
  const before = await financeView();
  await draftAcceptanceExample(page);
  await workspace(page).getByRole('button', { name: 'Save draft' }).click();
  await expect(workspace(page).getByRole('status').filter({ hasText: 'Draft saved. Nothing has been sent to MTN Finance.' })).toBeVisible();
  expect(await financeView()).toEqual(before);

  await page.reload();
  await expect(quantity(page, 'RCC-0100')).toHaveValue('100');
  await workspace(page).getByRole('button', { name: 'Delete draft' }).click();
  const confirm = workspace(page).getByRole('group', { name: 'Confirm draft deletion' });
  await expect(confirm.getByRole('button', { name: 'Keep draft' })).toBeFocused();
  await confirm.getByRole('button', { name: 'Delete draft order' }).click();
  await expect(workspace(page).getByText('Draft deleted. Nothing was sent to MTN Finance.')).toBeFocused();
  await page.reload();
  await expect(workspace(page).getByText('You have no draft order.')).toBeVisible();
});

test('a partner with the same name sees none of another account\'s orders', async ({ page, browser, playwright }) => {
  await signInAsPartner(page, playwright);
  await draftAcceptanceExample(page);
  await workspace(page).getByRole('button', { name: 'Preview order' }).click();
  await preview(page).getByRole('button', { name: 'Submit order' }).click();
  await expect(workspace(page).getByText('was submitted to MTN Finance')).toBeVisible();
  await showTab(page, 'My orders');
  await expect(orders(page).getByRole('row', { name: /SIM-ORD-0002/ })).toBeVisible();

  const other = await browser.newContext();
  const otherPage = await other.newPage();
  await otherPage.goto('/');
  await otherPage.getByLabel('Username').fill('partner-353072');
  await otherPage.getByLabel('Password').fill(PASSWORD);
  await otherPage.getByRole('button', { name: 'Sign in' }).click();
  await expect(workspace(otherPage).getByText('Account 353072', { exact: true })).toBeVisible();
  await expect(workspace(otherPage).getByText('You have no draft order.')).toBeVisible();
  await showTab(otherPage, 'My orders');
  await expect(workspace(otherPage).getByText('You have not submitted any orders yet.')).toBeVisible();
  await other.close();
});

test('a refused change offers the latest draft without losing the page', async ({ page, playwright }) => {
  const { internal } = await signInAsPartner(page, playwright);
  await draftAcceptanceExample(page);
  await workspace(page).getByRole('button', { name: 'Save draft' }).click();
  await expect(workspace(page).getByText('Draft saved.', { exact: false })).toBeVisible();
  // Finance resets the simulation, so this draft is gone.
  expect((await internal.post(`${API_BASE}/partner-sales/reset`)).ok()).toBe(true);
  await quantity(page, 'RCC-0100').fill('200');
  await workspace(page).getByRole('button', { name: 'Preview order' }).click();
  await expect(workspace(page).getByRole('alert')).toContainText('This changed elsewhere or the simulation was reset');
  await expect(quantity(page, 'RCC-0100')).toHaveValue('200');
  await workspace(page).getByRole('button', { name: 'Load latest' }).click();
  await expect(workspace(page).getByText('You have no draft order.')).toBeFocused();
});

test('a draft changed elsewhere is refused before it is previewed', async ({ page, playwright }) => {
  const { internal } = await signInAsPartner(page, playwright);
  await draftAcceptanceExample(page);
  await workspace(page).getByRole('button', { name: 'Save draft' }).click();
  await expect(workspace(page).getByText('Draft saved.', { exact: false })).toBeVisible();
  expect((await internal.post(`${API_BASE}/partner-sales/reset`)).ok()).toBe(true);
  await workspace(page).getByRole('button', { name: 'Preview order' }).click();
  await expect(workspace(page).getByRole('alert')).toContainText('This changed elsewhere or the simulation was reset');
  await expect(preview(page)).toHaveCount(0);
});

test('ordering fits a narrow screen', async ({ page, playwright }) => {
  await page.setViewportSize({ width: 360, height: 700 });
  await signInAsPartner(page, playwright);
  await expect(workspace(page).getByRole('region', { name: 'Your separate balances' })).toContainText('MTN would owe you');
  await expect(workspace(page).getByRole('region', { name: 'Your separate balances' })).toContainText('You would owe MTN');
  await draftAcceptanceExample(page);
  await workspace(page).getByRole('button', { name: 'View draft' }).click();
  await expect(workspace(page).getByRole('heading', { name: 'Your draft order' })).toBeFocused();
  await workspace(page).getByRole('button', { name: 'Preview order' }).click();
  await expect(preview(page)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
});
