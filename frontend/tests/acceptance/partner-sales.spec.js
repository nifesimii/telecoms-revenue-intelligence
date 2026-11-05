// Partner Sales simulation at the rendered workspace boundary, against the real
// simulation and login routes. Every other read is a fixture, and any other non-GET
// request is recorded, so the suite proves sales actions reach only the simulation.
import { expect, test } from '@playwright/test';

const API_BASE = 'http://localhost:8199';
const API = `${API_BASE}/**`;
const cors = { 'access-control-allow-origin': 'http://localhost:5199', 'access-control-allow-credentials': 'true' };
const servedForReal = (pathname) => pathname.startsWith('/partner-sales') || pathname.startsWith('/auth/');

// Mechanics tests run from an empty simulation so their references and totals stay
// their own. `examples: true` keeps the real starting point with its example invoices.
const EMPTY_SIMULATION = { next_sequence: 1, next_collection_sequence: 1, drafts: [], invoices: [], collections: [] };

const seed = async (page, state) => {
  const response = await page.request.put(`${API_BASE}/__acceptance__/simulation`, { data: state });
  expect(response.ok()).toBe(true);
};
const signIn = async (page) => {
  const response = await page.request.post(`${API_BASE}/auth/login`, { data: { username: 'finance', password: process.env.ACCEPTANCE_PASSWORD } });
  expect(response.ok()).toBe(true);
};
async function routeReads(page, { health = { sample_data_mode: true }, periods = ['202606', '202605'], reads = () => undefined } = {}) {
  const mutations = [];
  const requests = [];
  await page.route(API, async (route) => {
    const request = route.request();
    const { pathname, searchParams } = new URL(request.url());
    if (servedForReal(pathname)) return route.fallback();
    requests.push(pathname);
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { ...cors, 'access-control-allow-headers': 'content-type,accept', 'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE' } });
    if (request.method() !== 'GET') {
      mutations.push(`${request.method()} ${pathname}`);
      return route.fulfill({ status: 503, headers: cors, json: { detail: 'Blocked by acceptance test' } });
    }
    if (pathname === '/periods') return periods ? route.fulfill({ headers: cors, json: { periods } }) : route.fulfill({ status: 503, headers: cors, json: { detail: 'Unavailable' } });
    if (pathname === '/health') return route.fulfill({ headers: cors, json: health });
    const read = reads(pathname, searchParams);
    if (read) return route.fulfill({ headers: cors, ...read });
    return route.fulfill({ status: 503, headers: cors, json: { detail: 'Unavailable in acceptance fixture' } });
  });
  return { mutations, requests };
}
async function mockApi(page, { examples = false, ...options } = {}) {
  await signIn(page);
  if (examples) await page.request.post(`${API_BASE}/partner-sales/reset`);
  else await seed(page, EMPTY_SIMULATION);
  return routeReads(page, options);
}

const workspace = (page) => page.getByRole('main', { name: 'Partner Sales' });
const nav = (page, name) => page.getByRole('navigation', { name: 'Workspace' }).getByRole('button', { name, exact: true }).click();
const openSales = async (page, path = '/?period=202605') => {
  await page.goto(path);
  await nav(page, 'Partner Sales');
  await expect(workspace(page)).toBeVisible();
};
const choosePartner = (page, name) => workspace(page).getByRole('radio', { name }).check();

test('opens from navigation, keeps the reporting month and separates same-name accounts', async ({ page }) => {
  await mockApi(page);
  await openSales(page);

  await expect(page.getByRole('combobox', { name: /Reporting period/ })).toHaveValue('202605');
  await expect(page).toHaveURL(/view=partner-sales/);
  await expect(page).toHaveURL(/period=202605/);
  await expect(workspace(page).getByText('May 2026', { exact: false }).first()).toBeVisible();

  const first = workspace(page).getByRole('radio', { name: 'River Isle Ventures · Account 296065' });
  const second = workspace(page).getByRole('radio', { name: 'River Isle Ventures · Account 353072' });
  await expect(first).toBeVisible();
  await expect(second).toBeVisible();
  await first.check();
  await expect(first).toBeChecked();
  await expect(second).not.toBeChecked();

  await workspace(page).getByRole('searchbox', { name: 'Find a partner' }).fill('353072');
  await expect(first).toHaveCount(0);
  await expect(second).toBeVisible();
  await workspace(page).getByRole('searchbox', { name: 'Find a partner' }).fill('no such partner');
  await expect(workspace(page).getByText('No partners match')).toBeVisible();
});

const catalogue = (page) => workspace(page).getByRole('table', { name: 'Fictional product catalogue' });
const lines = (page) => workspace(page).getByRole('list', { name: 'Draft lines' });
const quantity = (page, code) => workspace(page).getByRole('textbox', { name: `Quantity for ${code}` });
const add = (page, code) => workspace(page).getByRole('button', { name: `Add ${code} to draft` });
const draftTotal = (page) => workspace(page).getByText('Draft total').locator('..');
const startDraft = async (page, partner = 'River Isle Ventures · Account 296065') => {
  await choosePartner(page, partner);
  await workspace(page).getByRole('button', { name: 'Create draft' }).click();
};
const addLine = async (page, code, units) => {
  await add(page, code).click();
  // Adding moves focus on the next frame; let it land so it cannot steal later focus.
  await expect(quantity(page, code)).toBeFocused();
  await quantity(page, code).fill(units);
  await draftSaved(page);
};
const draftSaved = (page) => expect(workspace(page).getByRole('status').filter({ hasText: 'Draft saved.' })).toBeVisible();

test('builds a mixed draft whose total is exact in minor units', async ({ page }) => {
  await mockApi(page);
  await openSales(page);

  await expect(workspace(page).getByText('Select a trade partner to create a draft.')).toBeVisible();
  await choosePartner(page, 'River Isle Ventures · Account 296065');
  await expect(workspace(page).getByText('No draft for River Isle Ventures · Account 296065 in May 2026.')).toBeVisible();
  await workspace(page).getByRole('button', { name: 'Create draft' }).click();

  await expect(catalogue(page).getByRole('row', { name: /FBB-5G-ROUTER Fictional 5G FBB router device NGN 50,000\.00/ })).toBeVisible();
  await expect(catalogue(page).getByRole('row', { name: /RCC-0100 Fictional NGN 100 physical recharge card card NGN 100\.00/ })).toBeVisible();

  await addLine(page, 'FBB-5G-ROUTER', '2');
  await addLine(page, 'RCC-0100', '100');
  await expect(lines(page).getByText('NGN 100,000.00')).toBeVisible();
  await expect(lines(page).getByText('NGN 10,000.00')).toBeVisible();
  await expect(draftTotal(page)).toContainText('NGN 110,000.00');
});

test('keeps kobo exact where binary floating point would drift', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await startDraft(page);

  // Worked by hand: 3 x 33,333.33 = 99,999.99; 1,000,000 x 100.00 = 100,000,000.00.
  await addLine(page, 'FBB-MIFI', '3');
  await addLine(page, 'RCC-0100', '1000000');
  await expect(draftTotal(page)).toContainText('NGN 100,099,999.99');
});

const previewButton = (page) => workspace(page).getByRole('button', { name: 'Preview invoice' });
const preview = (page) => workspace(page).getByRole('region', { name: 'Simulated invoice preview' });

test('rejects empty and invalid drafts, and corrections restore a valid total', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await startDraft(page);

  await previewButton(page).click();
  await expect(workspace(page).getByRole('alert')).toContainText('Add at least one product line');
  await expect(preview(page)).toHaveCount(0);

  await addLine(page, 'FBB-5G-ROUTER', '3');
  await addLine(page, 'RCC-0200', '5');
  for (const bad of ['0', '-1', '1.5', 'abc', '', '1000001']) {
    await quantity(page, 'FBB-5G-ROUTER').fill(bad);
    await expect(quantity(page, 'FBB-5G-ROUTER')).toHaveAttribute('aria-invalid', 'true');
    await expect(draftTotal(page)).toContainText('Unavailable');
    await previewButton(page).click();
    await expect(workspace(page).getByRole('alert')).toContainText('Correct the highlighted fields');
    await expect(preview(page)).toHaveCount(0);
    await expect(quantity(page, 'FBB-5G-ROUTER')).toBeFocused();
  }

  await quantity(page, 'FBB-5G-ROUTER').fill('2');
  await expect(quantity(page, 'FBB-5G-ROUTER')).toHaveAttribute('aria-invalid', 'false');
  await expect(workspace(page).getByRole('alert')).toHaveCount(0);
  await workspace(page).getByRole('button', { name: 'Remove RCC-0200 from draft' }).click();
  await expect(lines(page).getByText('RCC-0200')).toHaveCount(0);
  await expect(add(page, 'RCC-0200')).toBeEnabled();
  await expect(draftTotal(page)).toContainText('NGN 100,000.00');

  const issue = workspace(page).getByLabel('Intended issue date');
  const due = workspace(page).getByLabel('Due date (optional)');
  await expect(issue).toHaveValue('2026-05-31');
  await due.fill('2026-05-30');
  await previewButton(page).click();
  await expect(workspace(page).getByRole('alert')).toContainText('Correct the highlighted fields');
  await expect(workspace(page).getByText('Due date cannot be before the issue date.')).toBeVisible();
  await due.fill('');
  await issue.fill('2026-06-01');
  await expect(workspace(page).getByText('Choose a date in May 2026.')).toBeVisible();
  await issue.fill('');
  await expect(workspace(page).getByText('Enter an intended issue date.')).toBeVisible();
  await issue.fill('2026-05-15');
  await previewButton(page).click();
  await expect(preview(page)).toBeVisible();
});

test('previews seller, buyer, reference, dates, lines and total with its limits stated', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await startDraft(page);
  await addLine(page, 'FBB-5G-ROUTER', '2');
  await addLine(page, 'RCC-0100', '100');
  await workspace(page).getByLabel('Due date (optional)').fill('2026-06-30');
  await previewButton(page).click();

  const invoice = preview(page);
  await expect(invoice.getByRole('heading', { name: 'Simulated invoice preview' })).toBeFocused();
  const field = (term) => invoice.getByRole('term').filter({ hasText: new RegExp(`^${term}$`) }).locator('+ dd');
  await expect(field('Seller')).toHaveText('MTN');
  await expect(field('Buyer')).toHaveText('River Isle Ventures · Account 296065');
  await expect(field('Simulation reference')).toHaveText('SIM-INV-0001');
  await expect(field('Intended issue date')).toHaveText('31 May 2026');
  await expect(field('Due date')).toHaveText('30 Jun 2026');
  await expect(field('Currency')).toHaveText('NGN');

  await expect(invoice.getByRole('row', { name: /FBB-5G-ROUTER.*NGN 100,000\.00/ })).toBeVisible();
  await expect(invoice.getByRole('row', { name: /RCC-0100.*NGN 10,000\.00/ })).toBeVisible();
  await expect(invoice.getByRole('row', { name: /Total.*NGN 110,000\.00/ })).toBeVisible();
  await expect(invoice).toContainText('Taxes and discounts are not modeled');
  await expect(invoice).toContainText('not an operational tax invoice');
  await expect(invoice).toContainText('does not create an invoice obligation or commission');
  await expect(invoice).toContainText('Fictional');

  await invoice.getByRole('button', { name: 'Back to draft' }).click();
  await expect(previewButton(page)).toBeFocused();
  await expect(quantity(page, 'RCC-0100')).toHaveValue('100');
  await previewButton(page).click();
  await expect(field('Simulation reference')).toHaveText('SIM-INV-0001');

  await workspace(page).getByRole('radio', { name: 'Stone Light Networks · Account 74050' }).check();
  await expect(preview(page)).toHaveCount(0);
  await workspace(page).getByRole('button', { name: 'Create draft' }).click();
  await addLine(page, 'RCC-0500', '1');
  await previewButton(page).click();
  await expect(field('Buyer')).toHaveText('Stone Light Networks · Account 74050');
  await expect(field('Simulation reference')).toHaveText('SIM-INV-0002');
  await expect(invoice.getByRole('row', { name: /FBB-5G-ROUTER/ })).toHaveCount(0);
});

const buildMixedDraft = async (page) => {
  await startDraft(page);
  await addLine(page, 'FBB-5G-ROUTER', '2');
  await addLine(page, 'RCC-0100', '100');
};
const expectRestoredDraft = async (page) => {
  await expect(workspace(page).getByRole('radio', { name: 'River Isle Ventures · Account 296065' })).toBeChecked();
  await expect(quantity(page, 'FBB-5G-ROUTER')).toHaveValue('2');
  await expect(quantity(page, 'RCC-0100')).toHaveValue('100');
  await expect(workspace(page).getByText('SIM-INV-0001 · May 2026')).toBeVisible();
  await expect(draftTotal(page)).toContainText('NGN 110,000.00');
};

test('drafts survive workspace navigation and refresh, per month, and another session sees them', async ({ page, browser }) => {
  await mockApi(page);
  await openSales(page);
  await buildMixedDraft(page);

  await nav(page, 'Payments');
  await nav(page, 'Partner Sales');
  await expectRestoredDraft(page);

  await page.reload();
  await expectRestoredDraft(page);

  // A draft belongs to its intended issue month; changing month neither moves nor reprices it.
  await page.getByRole('combobox', { name: /Reporting period/ }).selectOption('202606');
  await expect(workspace(page).getByText('No draft for River Isle Ventures · Account 296065 in Jun 2026.')).toBeVisible();
  await page.getByRole('combobox', { name: /Reporting period/ }).selectOption('202605');
  await expectRestoredDraft(page);

  // The records are shared; the selected partner belongs to each tab.
  const session = await browser.newContext({ baseURL: 'http://localhost:5199' });
  const other = await session.newPage();
  await signIn(other);
  await routeReads(other);
  await openSales(other);
  await expect(workspace(other).getByText('Select a trade partner to create a draft.')).toBeVisible();
  await expect(invoiceRow(other, 'SIM-INV-0001')).toContainText('Draft');
  await choosePartner(other, 'River Isle Ventures · Account 296065');
  await expect(quantity(other, 'RCC-0100')).toHaveValue('100');
  await session.close();
});

test('says when a draft cannot be saved, keeps the typing and recovers on retry', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await startDraft(page);
  await addLine(page, 'FBB-5G-ROUTER', '1');

  const saves = `${API_BASE}/partner-sales/drafts/*`;
  await page.route(saves, (route) => (route.request().method() === 'PUT' ? route.abort() : route.fallback()));
  await quantity(page, 'FBB-5G-ROUTER').fill('2');
  const alert = workspace(page).getByRole('alert');
  await expect(alert).toContainText('could not be saved');
  await expect(draftTotal(page)).toContainText('NGN 100,000.00');

  await page.unroute(saves);
  await workspace(page).getByRole('button', { name: 'Try saving again' }).click();
  await draftSaved(page);
  await expect(alert).toHaveCount(0);
  await page.reload();
  await expect(quantity(page, 'FBB-5G-ROUTER')).toHaveValue('2');
});

test('the newest typing wins however slowly earlier saves finish', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await startDraft(page);
  await addLine(page, 'RCC-0100', '1');
  await page.route(`${API_BASE}/partner-sales/drafts/*`, async (route) => {
    await new Promise((resolve) => { setTimeout(resolve, 100); });
    return route.fallback();
  });
  for (const units of ['12', '123', '1234']) await quantity(page, 'RCC-0100').fill(units);
  await draftSaved(page);
  await page.reload();
  await expect(quantity(page, 'RCC-0100')).toHaveValue('1234');
});

test('shows when the simulation cannot be read, and recovers on retry', async ({ page }) => {
  await mockApi(page);
  const reference = `${API_BASE}/partner-sales/reference`;
  await page.route(reference, (route) => route.abort());
  await page.goto('/?view=partner-sales&period=202605');
  await expect(page.getByRole('alert').filter({ hasText: 'Partner Sales could not be loaded' })).toBeVisible();
  await page.unroute(reference);
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(workspace(page).getByRole('radio').first()).toBeVisible();
});

test('completes draft, correction and preview in live-read mode through simulation routes alone', async ({ page }) => {
  const { mutations, requests } = await mockApi(page, { health: { sample_data_mode: false } });
  await page.goto('/?view=partner-sales&period=202605');
  await expect(workspace(page).getByText('Fictional simulation', { exact: false }).first()).toBeVisible();
  await expect(page.getByRole('status').filter({ hasText: 'Synthetic demonstration' })).toBeVisible();
  await expect(page.getByText('Live Presto')).toHaveCount(0);
  await expect(workspace(page)).toContainText('separate from recorded commission, payment and inventory evidence');
  await page.waitForLoadState('networkidle');
  requests.length = 0;

  await buildMixedDraft(page);
  await quantity(page, 'FBB-5G-ROUTER').fill('x');
  await quantity(page, 'FBB-5G-ROUTER').fill('2');
  await previewButton(page).click();
  await expect(preview(page).getByRole('row', { name: /Total.*NGN 110,000\.00/ })).toBeVisible();
  await preview(page).getByRole('button', { name: 'Back to draft' }).click();
  await page.waitForTimeout(200);

  expect(requests).toEqual([]);
  expect(mutations).toEqual([]);
});

test('can be completed with the keyboard alone', async ({ page }) => {
  await mockApi(page);
  await openSales(page);

  await workspace(page).getByRole('searchbox', { name: 'Find a partner' }).focus();
  await page.keyboard.press('Tab');
  await page.keyboard.press('Space');
  await expect(workspace(page).getByRole('radio', { name: 'River Isle Ventures · Account 296065' })).toBeChecked();
  await page.keyboard.press('ArrowDown');
  await expect(workspace(page).getByRole('radio', { name: 'River Isle Ventures · Account 353072' })).toBeChecked();

  await workspace(page).getByRole('button', { name: 'Create draft' }).focus();
  await page.keyboard.press('Enter');
  await expect(workspace(page).getByRole('heading', { name: 'Fictional product catalogue' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(add(page, 'FBB-5G-ROUTER')).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(quantity(page, 'FBB-5G-ROUTER')).toBeFocused();
  await page.keyboard.press('ControlOrMeta+a');
  await page.keyboard.type('2');
  await page.keyboard.press('Tab');
  await expect(workspace(page).getByRole('button', { name: 'Remove FBB-5G-ROUTER from draft' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(previewButton(page)).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(preview(page).getByRole('heading')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(issueButton(page)).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(preview(page).getByRole('button', { name: 'Back to draft' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(previewButton(page)).toBeFocused();

  await workspace(page).getByRole('button', { name: 'Remove FBB-5G-ROUTER from draft' }).focus();
  await page.keyboard.press('Enter');
  await expect(workspace(page).getByRole('heading', { name: /^Draft for/ })).toBeFocused();
});

for (const width of [320, 768, 1024, 1440]) {
  test(`fits the draft and preview at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await mockApi(page);
    await page.goto('/?view=partner-sales&period=202605');
    await expect(workspace(page)).toBeVisible();
    await startDraft(page);
    await addLine(page, 'FBB-5G-ROUTER', '1000000');
    await addLine(page, 'FBB-MIFI', '1000000');
    await addLine(page, 'RCC-0500', '1000000');
    const contained = () => page.evaluate(() => [document.documentElement, document.querySelector('main[aria-label="Partner Sales"]'), document.querySelector('header')]
      .every((element) => element.scrollWidth <= element.clientWidth));
    expect(await contained()).toBe(true);
    await previewButton(page).click();
    await expect(preview(page).getByRole('row', { name: /Total.*NGN 83,833,330,000\.00/ })).toBeVisible();
    await expect(preview(page).getByRole('row', { name: /RCC-0500/ })).toContainText('1,000,000');
    expect(await contained()).toBe(true);
  });
}

test('keeps amounts unbroken and reads naturally on a narrow screen', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await mockApi(page);
  await page.goto('/?period=202605');
  await page.getByRole('combobox', { name: 'Workspace' }).selectOption({ label: 'Partner Sales' });
  await expect(workspace(page)).toBeVisible();
  await startDraft(page);
  await addLine(page, 'FBB-5G-ROUTER', '2');
  await addLine(page, 'RCC-0100', '1');
  await previewButton(page).click();

  await expect(preview(page).getByRole('row', { name: /FBB-5G-ROUTER/ })).toContainText('2 devices');
  await expect(preview(page).getByRole('row', { name: /RCC-0100/ })).toContainText('1 card ×');
  const amounts = preview(page).locator('tbody td:last-child, tfoot td:last-child');
  await expect(amounts).toHaveCount(3);
  for (const amount of await amounts.all()) {
    const lineBoxes = await amount.evaluate((cell) => {
      const range = document.createRange();
      range.selectNodeContents(cell);
      return range.getClientRects().length;
    });
    expect(lineBoxes).toBe(1);
  }
});

const fact = (scope, term) => scope.getByRole('term').filter({ hasText: new RegExp(`^${term}$`) }).locator('+ dd');
const issueButton = (page) => preview(page).getByRole('button', { name: 'Issue simulated invoice' });
const issuedInvoice = (page, reference) => workspace(page).getByRole('region', { name: `Simulated invoice ${reference}` });
const invoiceList = (page) => workspace(page).getByRole('region', { name: /^Invoices for/ });
const invoiceRow = (page, reference) => invoiceList(page).getByRole('row', { name: new RegExp(reference) });
const back = (page) => workspace(page).getByRole('button', { name: /^Back to/ }).last();

test('issuing freezes a valid draft as an unpaid invoice and clears the draft', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await buildMixedDraft(page);
  await workspace(page).getByLabel('Due date (optional)').fill('2026-06-30');
  await previewButton(page).click();
  await issueButton(page).click();

  const invoice = issuedInvoice(page, 'SIM-INV-0001');
  await expect(invoice.getByRole('heading', { name: 'Simulated invoice SIM-INV-0001' })).toBeFocused();
  await expect(fact(invoice, 'Status')).toHaveText('Unpaid');
  await expect(fact(invoice, 'Seller')).toHaveText('MTN');
  await expect(fact(invoice, 'Buyer')).toHaveText('River Isle Ventures · Account 296065');
  await expect(fact(invoice, 'Issue date')).toHaveText('31 May 2026');
  await expect(fact(invoice, 'Due date')).toHaveText('30 Jun 2026');
  await expect(fact(invoice, 'Outstanding as of 31 May 2026')).toHaveText('NGN 110,000.00');
  await expect(invoice.getByRole('row', { name: /FBB-5G-ROUTER.*2 devices.*NGN 50,000\.00.*NGN 100,000\.00/ })).toBeVisible();
  await expect(invoice.getByRole('row', { name: /RCC-0100.*100 cards.*NGN 100\.00.*NGN 10,000\.00/ })).toBeVisible();
  await expect(invoice.getByRole('row', { name: /Total.*NGN 110,000\.00/ })).toBeVisible();
  await expect(invoice).toContainText('Fictional simulation');
  await expect(invoice).toContainText('not an actual purchase obligation');
  // Only the collection date and amount are editable; the commercial details are not.
  await expect(invoice.getByRole('textbox')).toHaveCount(2);
  await expect(collectionDate(page)).toBeVisible();
  await expect(collectionAmount(page)).toBeVisible();

  await leaveDetail(page);
  await expect(invoiceRow(page, 'SIM-INV-0001')).toContainText('Unpaid');
  await expect(workspace(page).getByText('No draft for River Isle Ventures · Account 296065 in May 2026.')).toBeVisible();
});

const issueMixedInvoice = async (page, reference = 'SIM-INV-0001') => {
  await buildMixedDraft(page);
  await previewButton(page).click();
  await issueButton(page).click();
  await expect(issuedInvoice(page, reference).getByRole('heading', { name: `Simulated invoice ${reference}` })).toBeFocused();
};
const summary = (page, term) => fact(invoiceList(page), term);
const period = (page) => page.getByRole('combobox', { name: /Reporting period/ });

test('issuing twice in one tick creates one obligation, and a later draft cannot change it', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await buildMixedDraft(page);
  await previewButton(page).click();
  await issueButton(page).evaluate((button) => { button.click(); button.click(); });
  await expect(issuedInvoice(page, 'SIM-INV-0001')).toBeVisible();
  await leaveDetail(page);

  await expect(summary(page, 'Issued invoices')).toHaveText('1');
  await expect(summary(page, 'Outstanding purchase obligation')).toHaveText('NGN 110,000.00');

  await workspace(page).getByRole('button', { name: 'Create draft' }).click();
  await addLine(page, 'RCC-0500', '1');
  await expect(workspace(page).getByText('SIM-INV-0002', { exact: false }).first()).toBeVisible();
  await expect(summary(page, 'Outstanding purchase obligation')).toHaveText('NGN 110,000.00');
  await expect(summary(page, 'Drafts \\(excluded from outstanding\\)')).toHaveText('1');
  await expect(invoiceRow(page, 'SIM-INV-0002')).toContainText('Draft');

  await page.reload();
  await expect(summary(page, 'Issued invoices')).toHaveText('1');
  await expect(invoiceRow(page, 'SIM-INV-0001')).toContainText('NGN 110,000.00');
  await invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0001' }).click();
  await expect(fact(issuedInvoice(page, 'SIM-INV-0001'), 'Buyer')).toHaveText('River Isle Ventures · Account 296065');
  await expect(issuedInvoice(page, 'SIM-INV-0001').getByRole('row', { name: /RCC-0500/ })).toHaveCount(0);
});

test('invoices keep their issue month, dates and amounts when the reporting month changes', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await buildMixedDraft(page);
  await workspace(page).getByLabel('Intended issue date').fill('2026-05-15');
  await previewButton(page).click();
  await issueButton(page).click();

  await period(page).selectOption('202606');
  const invoice = issuedInvoice(page, 'SIM-INV-0001');
  await expect(fact(invoice, 'Issue date')).toHaveText('15 May 2026');
  await expect(fact(invoice, 'Outstanding as of 15 May 2026')).toHaveText('NGN 110,000.00');

  await leaveDetail(page);
  await expect(invoiceList(page).getByRole('heading', { name: 'Invoices for Jun 2026' })).toBeVisible();
  await expect(invoiceList(page).getByText('No invoices or drafts for Jun 2026.')).toBeVisible();
  await expect(summary(page, 'Outstanding purchase obligation')).toHaveText('NGN 0.00');

  await workspace(page).getByRole('button', { name: 'Create draft' }).click();
  await addLine(page, 'RCC-0100', '1');
  await expect(invoiceRow(page, 'SIM-INV-0002')).toContainText('Draft');
  await period(page).selectOption('202605');
  await expect(invoiceRow(page, 'SIM-INV-0002')).toHaveCount(0);
  await expect(invoiceRow(page, 'SIM-INV-0001')).toContainText('15 May 2026');
  await expect(invoiceRow(page, 'SIM-INV-0001')).toContainText('NGN 110,000.00');
});

// Each invoice is one NGN 100.00 card. Odd references are account 296065 and even
// ones 74050, so May totals are known by hand: 205 x 100.00 = 20,500.00 overall,
// 103 x 100.00 = 10,300.00 and 102 x 100.00 = 10,200.00 per account.
const seededInvoice = (sequence, issueDate = '2026-05-10') => {
  const buyer = sequence % 2 ? { code: '296065', name: 'River Isle Ventures' } : { code: '74050', name: 'Stone Light Networks' };
  return {
    reference: `SIM-INV-${String(sequence).padStart(4, '0')}`,
    token: `seeded-invoice-${sequence}`,
    seller: 'MTN',
    buyer,
    period: issueDate.slice(0, 7).replace('-', ''),
    issue_date: issueDate,
    due_date: '',
    currency: 'NGN',
    lines: [{ product_code: 'RCC-0100', description: 'Fictional NGN 100 physical recharge card', unit: 'card', quantity: 1, unit_price_minor: 10000, line_total_minor: 10000 }],
    total_minor: 10000,
  };
};
const seededSimulation = () => ({
  next_sequence: 208,
  next_collection_sequence: 1,
  collections: [],
  drafts: [{ reference: 'SIM-INV-0207', token: 'seeded-draft', account_code: '296065', period: '202605', issue_date: '2026-05-31', due_date: '', lines: [{ product_code: 'FBB-5G-ROUTER', quantity: '1' }] }],
  invoices: [...Array.from({ length: 205 }, (_, index) => seededInvoice(index + 1)), seededInvoice(206, '2026-06-02')],
});
const firstReferences = (page, count) => invoiceList(page).locator('tbody tr th > span:first-child').evaluateAll((cells, n) => cells.slice(0, n).map((cell) => cell.textContent), count);
const rows = (page) => invoiceList(page).locator('tbody tr');

test('pages at most 100 records in a fixed order while totals describe the whole matching set', async ({ page }) => {
  await mockApi(page);
  await seed(page, seededSimulation());
  await openSales(page);

  const expectWholeSet = async () => {
    await expect(summary(page, 'Matching records')).toHaveText('206');
    await expect(summary(page, 'Issued invoices')).toHaveText('205');
    await expect(summary(page, 'Drafts \\(excluded from outstanding\\)')).toHaveText('1');
    await expect(summary(page, 'Outstanding purchase obligation')).toHaveText('NGN 20,500.00');
  };
  await expectWholeSet();
  await expect(rows(page)).toHaveCount(25);
  // The draft has the latest date; invoices sharing a date run newest reference first.
  await expect.poll(() => firstReferences(page, 3)).toEqual(['SIM-INV-0207', 'SIM-INV-0205', 'SIM-INV-0204']);

  await invoiceList(page).getByRole('button', { name: 'Next' }).click();
  await expectWholeSet();
  // Row 26 of 207, 205, 204, ... is 206 - 25.
  await expect.poll(() => firstReferences(page, 1)).toEqual(['SIM-INV-0181']);
  await expect(invoiceList(page).getByRole('heading', { name: 'Invoices for May 2026' })).toBeFocused();

  await invoiceList(page).getByRole('combobox', { name: 'Rows per page' }).selectOption('100');
  await expect(rows(page)).toHaveCount(100);
  await expectWholeSet();
  await expect(invoiceList(page).getByRole('combobox', { name: 'Rows per page' }).getByRole('option')).toHaveText(['25 rows', '50 rows', '100 rows']);
  for (let next = 0; next < 2; next++) await invoiceList(page).getByRole('button', { name: 'Next' }).click();
  await expect(rows(page)).toHaveCount(6);
  await expect(invoiceList(page).getByRole('button', { name: 'Next' })).toBeDisabled();
  await expect(invoiceList(page).getByRole('heading', { name: 'Invoices for May 2026' })).toBeFocused();
  await expectWholeSet();

  // Filtering returns to a first page, and totals follow the new matching set.
  await invoiceList(page).getByRole('searchbox').fill('74050');
  await expect(summary(page, 'Matching records')).toHaveText('102');
  await expect(summary(page, 'Outstanding purchase obligation')).toHaveText('NGN 10,200.00');
  await expect.poll(() => firstReferences(page, 1)).toEqual(['SIM-INV-0204']);
  await invoiceList(page).getByRole('searchbox').fill('river isle');
  await expect(summary(page, 'Matching records')).toHaveText('104');
  await expect(summary(page, 'Outstanding purchase obligation')).toHaveText('NGN 10,300.00');

  await invoiceList(page).getByLabel('Status').selectOption('Draft');
  await expect(rows(page)).toHaveCount(1);
  await expect(summary(page, 'Outstanding purchase obligation')).toHaveText('NGN 0.00');
  await invoiceList(page).getByLabel('Status').selectOption('Unpaid');
  await expect(summary(page, 'Matching records')).toHaveText('103');
  await expect(summary(page, 'Drafts \\(excluded from outstanding\\)')).toHaveText('0');

  await invoiceList(page).getByRole('searchbox').fill('no such partner');
  await expect(invoiceList(page).getByRole('status')).toContainText('match your search and status');
  await invoiceList(page).getByRole('button', { name: 'Clear filters' }).click();
  await expect(invoiceList(page).getByRole('searchbox')).toBeFocused();
  await expect(invoiceList(page).getByRole('searchbox')).toHaveValue('');
  await expectWholeSet();

  await period(page).selectOption('202606');
  await expect(summary(page, 'Matching records')).toHaveText('1');
  await expect(summary(page, 'Outstanding purchase obligation')).toHaveText('NGN 100.00');
});

test('a changed filter or month starts at the first page, even when changed back', async ({ page }) => {
  await mockApi(page);
  await seed(page, seededSimulation());
  await openSales(page);
  const next = invoiceList(page).getByRole('button', { name: 'Next' });

  await next.click();
  await expect.poll(() => firstReferences(page, 1)).toEqual(['SIM-INV-0181']);
  await invoiceList(page).getByRole('searchbox').fill('no such partner');
  await invoiceList(page).getByRole('button', { name: 'Clear filters' }).click();
  await expect(rows(page)).toHaveCount(25);
  await expect.poll(() => firstReferences(page, 1)).toEqual(['SIM-INV-0207']);

  await next.click();
  await period(page).selectOption('202606');
  await expect(summary(page, 'Matching records')).toHaveText('1');
  await period(page).selectOption('202605');
  await expect(summary(page, 'Matching records')).toHaveText('206');
  await expect.poll(() => firstReferences(page, 1)).toEqual(['SIM-INV-0207']);
});

test('a filter that shrinks the set shows its rows rather than an empty page, and labels draft dates as intended', async ({ page }) => {
  await mockApi(page);
  const simulation = seededSimulation();
  // One draft plus 25 May invoices fills page 1 and spills one row onto page 2.
  simulation.invoices = simulation.invoices.slice(0, 25);
  await seed(page, simulation);
  await openSales(page);
  await expect(summary(page, 'Matching records')).toHaveText('26');
  await invoiceList(page).getByRole('button', { name: 'Next' }).click();
  await expect(rows(page)).toHaveCount(1);

  // The draft alone cannot fill a second page.
  await invoiceList(page).getByLabel('Status').selectOption('Draft');
  await expect(rows(page)).toHaveCount(1);
  await expect.poll(() => firstReferences(page, 1)).toEqual(['SIM-INV-0207']);
  await expect(invoiceRow(page, 'SIM-INV-0207')).toContainText('Intended 31 May 2026');
});

test('reopening an invoice from its partner keeps the way back and the partner page', async ({ page }) => {
  await mockApi(page);
  await seed(page, seededSimulation());
  await openSales(page);
  await invoiceList(page).getByRole('searchbox').fill('river isle');
  await invoiceList(page).getByRole('button', { name: 'Next' }).click();
  await invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0155' }).click();
  await workspace(page).getByRole('button', { name: 'View purchase obligations for River Isle Ventures · Account 296065', exact: true }).click();
  const detail = workspace(page).getByRole('region', { name: 'Purchase obligations for River Isle Ventures · Account 296065' });
  await detail.getByRole('button', { name: 'Next' }).click();

  const reopen = detail.getByRole('button', { name: 'Open invoice SIM-INV-0155' });
  await reopen.click();
  await expect(issuedInvoice(page, 'SIM-INV-0155').getByRole('heading', { name: 'Simulated invoice SIM-INV-0155' })).toBeFocused();
  await workspace(page).getByRole('button', { name: 'Back to purchase obligations' }).click();
  await expect(reopen).toBeFocused();
  await workspace(page).getByRole('button', { name: 'Back to invoices' }).click();
  await expect(invoiceList(page).getByRole('searchbox')).toHaveValue('river isle');
});

test('returning from detail restores filters, page and focus', async ({ page }) => {
  await mockApi(page);
  await seed(page, seededSimulation());
  await openSales(page);

  await invoiceList(page).getByRole('searchbox').fill('river isle');
  await invoiceList(page).getByLabel('Status').selectOption('Unpaid');
  await invoiceList(page).getByRole('button', { name: 'Next' }).click();
  // Page 2 of the 103 odd references: 205 descending, so row 26 is 205 - 2 x 25 = 155.
  await expect.poll(() => firstReferences(page, 1)).toEqual(['SIM-INV-0155']);

  const opener = invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0153' });
  await opener.click();
  await expect(issuedInvoice(page, 'SIM-INV-0153').getByRole('heading', { name: 'Simulated invoice SIM-INV-0153' })).toBeFocused();
  await expect(invoiceList(page)).toBeHidden();
  await workspace(page).getByRole('button', { name: 'Back to invoices' }).click();

  await expect(opener).toBeFocused();
  await expect(invoiceList(page).getByRole('searchbox')).toHaveValue('river isle');
  await expect(invoiceList(page).getByLabel('Status')).toHaveValue('Unpaid');
  await expect.poll(() => firstReferences(page, 1)).toEqual(['SIM-INV-0155']);

  // Through partner detail and one invoice, each return lands on its opener.
  const obligations = invoiceList(page).getByRole('button', { name: 'View purchase obligations for River Isle Ventures · Account 296065 from SIM-INV-0153' });
  await obligations.click();
  const detail = workspace(page).getByRole('region', { name: 'Purchase obligations for River Isle Ventures · Account 296065' });
  await expect(detail.getByRole('heading', { name: /^Purchase obligations/ })).toBeFocused();
  await detail.getByRole('button', { name: 'Next' }).click();
  const fromDetail = detail.getByRole('button', { name: 'Open invoice SIM-INV-0155' });
  await fromDetail.click();
  await workspace(page).getByRole('button', { name: 'Back to purchase obligations' }).click();
  await expect(fromDetail).toBeFocused();
  await workspace(page).getByRole('button', { name: 'Back to invoices' }).click();
  await expect(obligations).toBeFocused();
  await expect.poll(() => firstReferences(page, 1)).toEqual(['SIM-INV-0155']);
});

test('partner detail isolates the exact account and keeps obligations apart from commission and drafts', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await issueMixedInvoice(page);
  await leaveDetail(page);

  // Same-name account: nothing issued, so no balance to show.
  await choosePartner(page, 'River Isle Ventures · Account 353072');
  await workspace(page).getByRole('button', { name: 'Create draft' }).click();
  await addLine(page, 'RCC-0100', '1');
  await workspace(page).getByRole('button', { name: 'View purchase obligations for River Isle Ventures · Account 353072', exact: true }).click();
  const other = workspace(page).getByRole('region', { name: 'Purchase obligations for River Isle Ventures · Account 353072' });
  await expect(other).toContainText('No issued invoices for this account');
  await expect(other).not.toContainText('SIM-INV-0001');
  await expect(other.getByRole('list', { name: 'Drafts excluded from outstanding' })).toContainText('SIM-INV-0002 · intended May 2026 · NGN 100.00');
  await leaveDetail(page);

  // A June invoice on the first account: its balance spans issue months.
  await choosePartner(page, 'River Isle Ventures · Account 296065');
  await period(page).selectOption('202606');
  await workspace(page).getByRole('button', { name: 'Create draft' }).click();
  await addLine(page, 'FBB-MIFI', '3');
  await previewButton(page).click();
  await issueButton(page).click();
  await expect(issuedInvoice(page, 'SIM-INV-0003')).toBeVisible();
  await workspace(page).getByRole('button', { name: 'View purchase obligations for River Isle Ventures · Account 296065', exact: true }).click();

  const detail = workspace(page).getByRole('region', { name: 'Purchase obligations for River Isle Ventures · Account 296065' });
  await expect(fact(detail, 'Issued invoices')).toHaveText('2');
  // 110,000.00 + 3 x 33,333.33 = 209,999.99, up to the June issue date.
  await expect(fact(detail, 'Outstanding as of 30 Jun 2026')).toHaveText('NGN 209,999.99');
  await expect(detail).toContainText('not a month-end balance');
  await expect(detail).toContainText('It is not commission');
  await expect(detail).toContainText('Partner Commission Account');
  await expect(detail).toContainText('Fictional simulation');
  await expect(detail.getByRole('row', { name: /SIM-INV-0001.*31 May 2026.*Unpaid.*NGN 110,000\.00/ })).toBeVisible();
  await expect(detail.getByRole('row', { name: /SIM-INV-0003.*30 Jun 2026.*Unpaid.*NGN 99,999\.99/ })).toBeVisible();
  await expect(detail.getByRole('row', { name: /SIM-INV-0002/ })).toHaveCount(0);

  // The trail never stacks a second copy of a view already open.
  await detail.getByRole('button', { name: 'Open invoice SIM-INV-0001' }).click();
  await workspace(page).getByRole('button', { name: 'View purchase obligations for River Isle Ventures · Account 296065', exact: true }).click();
  await expect(detail.getByRole('heading', { name: /^Purchase obligations/ })).toBeFocused();
});

test('opening a draft from the list selects its exact partner for editing', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await startDraft(page, 'River Isle Ventures · Account 353072');
  await addLine(page, 'RCC-0100', '1');
  await choosePartner(page, 'River Isle Ventures · Account 296065');
  await invoiceList(page).getByRole('button', { name: 'Open draft SIM-INV-0001' }).click();
  await expect(workspace(page).getByRole('radio', { name: 'River Isle Ventures · Account 353072' })).toBeChecked();
  await expect(workspace(page).getByRole('heading', { name: /^Draft for River Isle Ventures · Account 353072/ })).toBeFocused();
});

test('issues and browses in live-read mode through simulation routes alone', async ({ page }) => {
  const { mutations, requests } = await mockApi(page, { health: { sample_data_mode: false } });
  await page.goto('/?view=partner-sales&period=202605');
  await expect(page.getByRole('status').filter({ hasText: 'Synthetic demonstration' })).toBeVisible();
  await page.waitForLoadState('networkidle');
  requests.length = 0;

  await issueMixedInvoice(page);
  await expect(issuedInvoice(page, 'SIM-INV-0001')).toContainText('Fictional simulation');
  await leaveDetail(page);
  await invoiceList(page).getByRole('searchbox').fill('296065');
  await invoiceList(page).getByRole('button', { name: /^View purchase obligations/ }).click();
  await expect(workspace(page).getByRole('region', { name: /^Purchase obligations/ })).toContainText('Fictional simulation');
  await page.waitForTimeout(200);

  expect(requests).toEqual([]);
  expect(mutations).toEqual([]);
});

test('an invoice that cannot be issued says so and stays a draft until a retry succeeds', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await buildMixedDraft(page);
  await previewButton(page).click();
  const issuing = `${API_BASE}/partner-sales/drafts/*/issue`;
  await page.route(issuing, (route) => route.abort());
  await issueButton(page).click();
  await expect(preview(page).getByRole('alert')).toContainText('could not be issued');
  await expect(invoiceRow(page, 'SIM-INV-0001')).toContainText('Draft');
  await page.unroute(issuing);
  await issueButton(page).click();
  await expect(fact(issuedInvoice(page, 'SIM-INV-0001'), 'Status')).toHaveText('Unpaid');
});

test('a collection whose response was lost records once when retried', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await issueMixedInvoice(page);
  const recording = `${API_BASE}/partner-sales/invoices/*/collections`;
  await page.route(recording, async (route) => {
    await route.fetch();
    return route.abort();
  });
  await recordCollection(page, '2026-06-10', '40000');
  await expect(collections(page).getByRole('alert')).toContainText('could not be recorded');
  await page.unroute(recording);
  await recordButton(page).click();
  await expect(collections(page).getByRole('status')).toContainText('Recorded SIM-PAY-0001');
  await expect(fact(issuedInvoice(page, 'SIM-INV-0001'), 'Collected')).toHaveText('NGN 40,000.00');
  await expect(history(page).locator('tbody tr')).toHaveCount(1);
});

test('a collection the server refuses leaves the balance unchanged and gives its reason', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await issueMixedInvoice(page);
  // Another session collects first, so this page's balance is out of date.
  const { invoice } = await (await page.request.get(`${API_BASE}/partner-sales/invoices/SIM-INV-0001`)).json();
  await page.request.post(`${API_BASE}/partner-sales/invoices/SIM-INV-0001/collections`, { data: { token: invoice.token, action_id: 'other-session', date: '2026-06-01', amount_minor: 10999999 } });
  await recordCollection(page, '2026-06-10', '40000');
  await expect(collections(page).getByRole('alert')).toContainText('no more than the outstanding balance');
  await expect(history(page).locator('tbody tr')).toHaveCount(0);
});

test('issues, finds and returns from an invoice with the keyboard alone', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await buildMixedDraft(page);
  await previewButton(page).focus();
  await page.keyboard.press('Enter');
  await expect(preview(page).getByRole('heading')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(issueButton(page)).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(issuedInvoice(page, 'SIM-INV-0001').getByRole('heading', { name: 'Simulated invoice SIM-INV-0001' })).toBeFocused();
  // The heading takes focus before the detail loads, so wait for what Tab should reach.
  await collectionDate(page).waitFor();
  await page.keyboard.press('Tab');
  await expect(collectionDate(page)).toBeFocused();
  await back(page).focus();
  await page.keyboard.press('Enter');

  const opener = invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0001' });
  await expect(opener).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(invoiceList(page).getByRole('button', { name: /^View purchase obligations/ })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(workspace(page).getByRole('heading', { name: /^Purchase obligations/ })).toBeFocused();
  await workspace(page).getByRole('button', { name: 'Open invoice SIM-INV-0001' }).waitFor();
  await page.keyboard.press('Tab');
  await expect(workspace(page).getByRole('button', { name: 'Open invoice SIM-INV-0001' })).toBeFocused();

  await back(page).focus();
  await page.keyboard.press('Enter');
  await expect(invoiceList(page).getByRole('button', { name: /^View purchase obligations/ })).toBeFocused();
  await invoiceList(page).getByRole('searchbox').focus();
  await page.keyboard.press('Tab');
  await expect(invoiceList(page).getByLabel('Status')).toBeFocused();
});

for (const width of [320, 768, 1024, 1440]) {
  test(`fits the invoice list and details with the largest amounts at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await mockApi(page);
    await page.goto('/?view=partner-sales&period=202605');
    await startDraft(page);
    await addLine(page, 'FBB-5G-ROUTER', '1000000');
    await addLine(page, 'FBB-MIFI', '1000000');
    await addLine(page, 'RCC-0500', '1000000');
    await previewButton(page).click();
    const contained = () => page.evaluate(() => [document.documentElement, document.querySelector('main[aria-label="Partner Sales"]')]
      .every((element) => element.scrollWidth <= element.clientWidth));
    await issueButton(page).click();
    await expect(fact(issuedInvoice(page, 'SIM-INV-0001'), 'Outstanding as of 31 May 2026')).toHaveText('NGN 83,833,330,000.00');
    expect(await contained()).toBe(true);
    await leaveDetail(page);
    await expect(invoiceRow(page, 'SIM-INV-0001')).toContainText('NGN 83,833,330,000.00');
    expect(await contained()).toBe(true);
    await invoiceList(page).getByRole('button', { name: /^View purchase obligations/ }).click();
    const obligation = workspace(page).getByRole('region', { name: /^Purchase obligations/ }).getByRole('row', { name: /SIM-INV-0001/ });
    await expect(obligation).toContainText('NGN 83,833,330,000.00');
    await expect(obligation).toContainText('Outstanding');
    expect(await contained()).toBe(true);
  });
}

const collections = (page, reference = 'SIM-INV-0001') => issuedInvoice(page, reference).getByRole('region', { name: 'Invoice collections' });
const history = (page, reference) => collections(page, reference).getByRole('table', { name: /^Collections recorded/ });
const collectionDate = (page, reference) => collections(page, reference).getByLabel('Collection date');
const collectionAmount = (page, reference) => collections(page, reference).getByRole('textbox', { name: 'Amount in NGN' });
const recordButton = (page, reference) => collections(page, reference).getByRole('button', { name: 'Record collection' });
const recordCollection = async (page, date, amount, reference) => {
  await collectionDate(page, reference).fill(date);
  await collectionAmount(page, reference).fill(amount);
  await recordButton(page, reference).click();
};

test('records a partial then a full collection, moving the invoice from unpaid to paid', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await issueMixedInvoice(page);
  const invoice = issuedInvoice(page, 'SIM-INV-0001');

  await expect(fact(invoice, 'Status')).toHaveText('Unpaid');
  await expect(collections(page)).toContainText('No collections recorded');

  await recordCollection(page, '2026-06-10', '40000');
  await expect(fact(invoice, 'Status')).toHaveText('Partially paid');
  await expect(fact(invoice, 'Collected')).toHaveText('NGN 40,000.00');
  await expect(fact(invoice, 'Outstanding as of 10 Jun 2026')).toHaveText('NGN 70,000.00');
  await expect(history(page).getByRole('row', { name: /10 Jun 2026.*SIM-PAY-0001.*NGN 40,000\.00.*NGN 70,000\.00/ })).toBeVisible();
  await expect(collections(page).getByRole('status')).toContainText('Recorded SIM-PAY-0001');

  await recordCollection(page, '2026-07-02', '70,000.00');
  await expect(fact(invoice, 'Status')).toHaveText('Paid');
  await expect(fact(invoice, 'Outstanding as of 2 Jul 2026')).toHaveText('NGN 0.00');
  await expect(history(page).getByRole('row', { name: /2 Jul 2026.*SIM-PAY-0002.*NGN 70,000\.00.*NGN 0\.00/ })).toBeVisible();
  await expect(history(page).getByRole('row', { name: /SIM-PAY-0001/ })).toBeVisible();
  // A paid invoice offers no further collection.
  await expect(collectionAmount(page)).toHaveCount(0);
  await expect(collections(page)).toContainText('Paid in full');
});

test('rejects invalid amounts and dates, leaving the valid balance unchanged', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await issueMixedInvoice(page);
  await recordCollection(page, '2026-06-10', '40000');
  await expect(collections(page).getByRole('heading', { name: 'Invoice collections' })).toBeFocused();
  const invoice = issuedInvoice(page, 'SIM-INV-0001');
  const expectUnchanged = async () => {
    await expect(fact(invoice, 'Status')).toHaveText('Partially paid');
    await expect(fact(invoice, 'Outstanding as of 10 Jun 2026')).toHaveText('NGN 70,000.00');
    await expect(history(page).locator('tbody tr')).toHaveCount(1);
  };

  for (const bad of ['0', '0.00', '-1', '-40000', 'abc', '1.234', '1,00', '1e3', '']) {
    await collectionAmount(page).fill(bad);
    await recordButton(page).click();
    await expect(collections(page).getByText('Enter a positive NGN amount')).toBeVisible();
    await expect(collectionAmount(page)).toHaveAttribute('aria-invalid', 'true');
    await expect(collectionAmount(page)).toBeFocused();
    await expectUnchanged();
  }

  // One kobo over the remaining balance.
  await collectionAmount(page).fill('70000.01');
  await recordButton(page).click();
  await expect(collections(page).getByText('Enter NGN 70,000.00 or less')).toBeVisible();
  await expectUnchanged();

  await collectionAmount(page).fill('10');
  await collectionDate(page).fill('2026-05-30');
  await recordButton(page).click();
  await expect(collections(page).getByText('cannot be dated before the issue date, 31 May 2026')).toBeVisible();
  await expect(collectionDate(page)).toBeFocused();
  await expectUnchanged();

  await collectionDate(page).fill('');
  await recordButton(page).click();
  await expect(collections(page).getByText('Enter a collection date.')).toBeVisible();
  await expectUnchanged();

  // Exact kobo: 70,000.00 - 0.10 - 33,333.33 = 36,666.57. Issue day itself is allowed.
  await recordCollection(page, '2026-05-31', '0.10');
  await recordCollection(page, '2026-05-31', '33,333.33');
  await expect(fact(invoice, 'Outstanding as of 10 Jun 2026')).toHaveText('NGN 36,666.57');
  // Backdated collections run in date order, each with the balance it left.
  await expect(history(page).locator('tbody tr').first()).toContainText('SIM-PAY-0002');
  await expect(history(page).getByRole('row', { name: /31 May 2026.*SIM-PAY-0002.*NGN 0\.10.*NGN 109,999\.90/ })).toBeVisible();
  await expect(history(page).getByRole('row', { name: /10 Jun 2026.*SIM-PAY-0001.*NGN 40,000\.00.*NGN 36,666\.57/ })).toBeVisible();
});

test('rejects a five-digit collection year', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await issueMixedInvoice(page);
  // Chrome accepts this value unless the field caps the year, so set it as a stray keystroke would.
  await collectionDate(page).evaluate((input) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, '20261-10-06');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await collectionAmount(page).fill('40000');
  await recordButton(page).click();
  await expect(collections(page).getByText('Enter a valid collection date.')).toBeVisible();
  await expect(fact(issuedInvoice(page, 'SIM-INV-0001'), 'Status')).toHaveText('Unpaid');

  await page.reload();
  await expect(workspace(page).getByRole('alert')).toHaveCount(0);
  await expect(invoiceRow(page, 'SIM-INV-0001')).toContainText('Unpaid');
});

test('an empty amount straight after a success is still explained', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await issueMixedInvoice(page);
  await recordCollection(page, '2026-06-10', '40000');
  await expect(collections(page).getByRole('heading', { name: 'Invoice collections' })).toBeFocused();
  await recordButton(page).click();
  await expect(collections(page).getByText('Enter a positive NGN amount')).toBeVisible();
  await expect(collectionAmount(page)).toBeFocused();
  await expect(history(page).locator('tbody tr')).toHaveCount(1);
});

test('a collection never reaches the same-name account', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await issueMixedInvoice(page);
  await leaveDetail(page);
  await startDraft(page, 'River Isle Ventures · Account 353072');
  await addLine(page, 'RCC-0100', '1');
  await previewButton(page).click();
  await issueButton(page).click();
  await expect(issuedInvoice(page, 'SIM-INV-0002')).toBeVisible();
  await leaveDetail(page);

  await invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0001' }).click();
  await recordCollection(page, '2026-06-10', '40000');
  await leaveDetail(page);

  // 110,000.00 less 40,000.00 on 296065, plus 100.00 untouched on 353072.
  await expect(summary(page, 'Outstanding purchase obligation')).toHaveText('NGN 70,100.00');
  await invoiceList(page).getByRole('searchbox').fill('353072');
  await expect(summary(page, 'Outstanding purchase obligation')).toHaveText('NGN 100.00');
  await expect(invoiceRow(page, 'SIM-INV-0002')).toContainText('Unpaid');
  await invoiceList(page).getByRole('button', { name: /^View purchase obligations/ }).click();
  const other = workspace(page).getByRole('region', { name: 'Purchase obligations for River Isle Ventures · Account 353072' });
  await expect(fact(other, 'Outstanding as of 31 May 2026')).toHaveText('NGN 100.00');
  await expect(other.getByRole('row', { name: /SIM-INV-0001/ })).toHaveCount(0);
  await other.getByRole('button', { name: 'Open invoice SIM-INV-0002' }).click();
  await expect(fact(issuedInvoice(page, 'SIM-INV-0002'), 'Status')).toHaveText('Unpaid');
  await expect(collections(page, 'SIM-INV-0002')).toContainText('No collections recorded');
});

test('a draft has no collection path, and repeating an action has one effect', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await buildMixedDraft(page);
  await expect(workspace(page).getByRole('region', { name: 'Invoice collections' })).toHaveCount(0);
  await previewButton(page).click();
  await expect(workspace(page).getByRole('region', { name: 'Invoice collections' })).toHaveCount(0);
  await issueButton(page).click();
  const invoice = issuedInvoice(page, 'SIM-INV-0001');

  // Two submissions in one tick carry the same action.
  await collectionDate(page).fill('2026-06-10');
  await collectionAmount(page).fill('40000');
  await recordButton(page).evaluate((button) => { button.click(); button.click(); });
  await expect(fact(invoice, 'Outstanding as of 10 Jun 2026')).toHaveText('NGN 70,000.00');
  await expect(history(page).locator('tbody tr')).toHaveCount(1);

  // An ordinary double click records once and shows no validation error.
  await collectionAmount(page).fill('1000');
  await recordButton(page).dblclick();
  await expect(fact(invoice, 'Collected')).toHaveText('NGN 41,000.00');
  await expect(history(page).locator('tbody tr')).toHaveCount(2);
  await expect(collections(page).getByRole('status')).toContainText('Recorded SIM-PAY-0002');
  await expect(collections(page).getByText('Enter a positive NGN amount')).toHaveCount(0);

  // Double clicking the final payment records it once and stays on the invoice.
  await collectionAmount(page).fill('69000');
  await recordButton(page).dblclick();
  await expect(fact(invoice, 'Status')).toHaveText('Paid');
  await expect(history(page).locator('tbody tr')).toHaveCount(3);
  await expect(invoice).toBeVisible();
});

test('history, detail and matching-set summaries agree after refresh and navigation', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await issueMixedInvoice(page);
  await recordCollection(page, '2026-06-10', '40000');

  const expectAgreement = async () => {
    await expect(summary(page, 'Outstanding purchase obligation')).toHaveText('NGN 70,000.00');
    await expect(invoiceRow(page, 'SIM-INV-0001')).toContainText('Partially paid');
    await expect(invoiceRow(page, 'SIM-INV-0001')).toContainText('NGN 110,000.00');
    await expect(invoiceRow(page, 'SIM-INV-0001')).toContainText('Outstanding NGN 70,000.00');
    await invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0001' }).click();
    await expect(fact(issuedInvoice(page, 'SIM-INV-0001'), 'Status')).toHaveText('Partially paid');
    await expect(fact(issuedInvoice(page, 'SIM-INV-0001'), 'Outstanding as of 10 Jun 2026')).toHaveText('NGN 70,000.00');
    await expect(history(page).getByRole('row', { name: /SIM-PAY-0001.*NGN 40,000\.00.*NGN 70,000\.00/ })).toBeVisible();
    await leaveDetail(page);
  };

  await leaveDetail(page);
  await expectAgreement();
  await page.reload();
  await expectAgreement();
  await nav(page, 'Payments');
  await nav(page, 'Partner Sales');
  await expectAgreement();

  const status = invoiceList(page).getByLabel('Status');
  await status.selectOption('Unpaid');
  await expect(invoiceList(page).getByRole('status')).toContainText('match your search and status');
  await status.selectOption('Partially paid');
  await expect(summary(page, 'Matching records')).toHaveText('1');
  await expect(summary(page, 'Outstanding purchase obligation')).toHaveText('NGN 70,000.00');
  await status.selectOption('');

  // A reference is never reused after a reload.
  await invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0001' }).click();
  await recordCollection(page, '2026-06-11', '70000');
  await expect(history(page).getByRole('row', { name: /11 Jun 2026.*SIM-PAY-0002/ })).toBeVisible();
  await leaveDetail(page);
  await status.selectOption('Paid');
  await expect(summary(page, 'Matching records')).toHaveText('1');
  await expect(summary(page, 'Outstanding purchase obligation')).toHaveText('NGN 0.00');
});

test('a later collection is dated, and is not presented as a month-end balance', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await issueMixedInvoice(page);
  await recordCollection(page, '2026-07-02', '40000');
  await expect(issuedInvoice(page, 'SIM-INV-0001')).toContainText('not a month-end balance');
  await leaveDetail(page);

  // The invoice stays in its May issue month, and May's total says what it includes.
  await expect(invoiceList(page).getByRole('heading', { name: 'Invoices for May 2026' })).toBeVisible();
  await expect(invoiceList(page)).toContainText('every collection recorded up to 2 Jul 2026, including any dated after May 2026');
  await expect(invoiceList(page)).toContainText('not a month-end balance for May 2026');
});

test('collections stay on their invoice and exact account, and show all recorded across pages', async ({ page }) => {
  await mockApi(page);
  const simulation = seededSimulation();
  // Hand-worked: invoice 1 (account 296065) is NGN 100.00, paid in 30 collections of
  // 1.00, leaving 70.00. Invoice 2 (account 74050) and its same-priced peers are untouched.
  simulation.next_collection_sequence = 31;
  simulation.collections = Array.from({ length: 30 }, (_, index) => ({ action_id: `seeded-${index}`, reference: `SIM-PAY-${String(index + 1).padStart(4, '0')}`, invoice_reference: 'SIM-INV-0001', date: '2026-06-01', amount_minor: 100 }));
  await seed(page, simulation);
  await openSales(page);

  // 20,500.00 across May less 30.00 collected.
  await expect(summary(page, 'Outstanding purchase obligation')).toHaveText('NGN 20,470.00');
  await invoiceList(page).getByRole('searchbox').fill('74050');
  await expect(summary(page, 'Outstanding purchase obligation')).toHaveText('NGN 10,200.00');
  await invoiceList(page).getByRole('searchbox').fill('296065');
  await expect(summary(page, 'Outstanding purchase obligation')).toHaveText('NGN 10,270.00');

  await invoiceList(page).getByRole('button', { name: 'View purchase obligations for River Isle Ventures · Account 296065 from SIM-INV-0205' }).click();
  const detail = workspace(page).getByRole('region', { name: 'Purchase obligations for River Isle Ventures · Account 296065' });
  // 10,300.00 less 30.00.
  await expect(fact(detail, 'Outstanding as of 1 Jun 2026')).toHaveText('NGN 10,270.00');
  await leaveDetail(page);

  await invoiceList(page).getByRole('searchbox').fill('');
  await invoiceList(page).getByRole('combobox', { name: 'Rows per page' }).selectOption('100');
  for (let next = 0; next < 2; next++) await invoiceList(page).getByRole('button', { name: 'Next' }).click();
  await invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0001' }).click();
  const invoice = issuedInvoice(page, 'SIM-INV-0001');
  await expect(fact(invoice, 'Status')).toHaveText('Partially paid');
  await expect(history(page).locator('tbody tr')).toHaveCount(25);
  await collections(page).getByRole('button', { name: 'Next' }).click();
  await expect(history(page).locator('tbody tr')).toHaveCount(5);
  await expect(history(page).getByRole('row', { name: /SIM-PAY-0030.*NGN 1\.00.*NGN 70\.00/ })).toBeVisible();
  await expect(collections(page).getByRole('heading', { name: 'Invoice collections' })).toBeFocused();
  await leaveDetail(page);
  await invoiceList(page).getByRole('searchbox').fill('74050');
  await invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0204' }).click();
  await expect(fact(issuedInvoice(page, 'SIM-INV-0204'), 'Status')).toHaveText('Unpaid');
  await expect(collections(page, 'SIM-INV-0204')).toContainText('No collections recorded');
});

test('collects in live-read mode through simulation routes alone, and says commission is unaffected', async ({ page }) => {
  const { mutations, requests } = await mockApi(page, { health: { sample_data_mode: false } });
  await page.goto('/?view=partner-sales&period=202605');
  await expect(page.getByRole('status').filter({ hasText: 'Synthetic demonstration' })).toBeVisible();
  await page.waitForLoadState('networkidle');
  requests.length = 0;

  await issueMixedInvoice(page);
  await recordCollection(page, '2026-06-10', '40000');
  await recordCollection(page, '2026-06-11', '70000');
  await expect(fact(issuedInvoice(page, 'SIM-INV-0001'), 'Status')).toHaveText('Paid');
  await expect(issuedInvoice(page, 'SIM-INV-0001')).toContainText('Fictional simulation');
  await expect(collections(page)).toContainText('never generate commission or offset commission outstanding');
  await page.waitForTimeout(200);

  expect(requests).toEqual([]);
  expect(mutations).toEqual([]);
});

test('records a collection with the keyboard alone', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await issueMixedInvoice(page);
  // Typed segment by segment, then on to the amount. Day and month match, because
  // Chrome orders those segments by locale.
  await collectionDate(page).focus();
  await page.keyboard.type('06062026');
  await expect(collectionDate(page)).toHaveValue('2026-06-06');
  await page.keyboard.press('Tab');
  await page.keyboard.press('Tab');
  await expect(collectionAmount(page)).toBeFocused();

  // Enter submits from the field, and an error returns focus there.
  await page.keyboard.type('nope');
  await page.keyboard.press('Enter');
  await expect(collectionAmount(page)).toBeFocused();
  await expect(collections(page).getByText('Enter a positive NGN amount')).toBeVisible();

  await page.keyboard.press('ControlOrMeta+a');
  await page.keyboard.type('40000');
  await page.keyboard.press('Tab');
  await expect(recordButton(page)).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(collections(page).getByRole('heading', { name: 'Invoice collections' })).toBeFocused();
  await expect(fact(issuedInvoice(page, 'SIM-INV-0001'), 'Collected')).toHaveText('NGN 40,000.00');

  // Paying in full removes the form, and focus does not fall to the page.
  await collectionAmount(page).fill('70000');
  await page.keyboard.press('Tab');
  await collectionAmount(page).press('Enter');
  await expect(collections(page).getByRole('heading', { name: 'Invoice collections' })).toBeFocused();
  await expect(collectionAmount(page)).toHaveCount(0);
});

for (const width of [320, 768, 1024, 1440]) {
  test(`fits collections with the largest amounts at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await mockApi(page);
    await page.goto('/?view=partner-sales&period=202605');
    await startDraft(page);
    await addLine(page, 'FBB-5G-ROUTER', '1000000');
    await addLine(page, 'FBB-MIFI', '1000000');
    await addLine(page, 'RCC-0500', '1000000');
    await previewButton(page).click();
    await issueButton(page).click();
    const contained = () => page.evaluate(() => [document.documentElement, document.querySelector('main[aria-label="Partner Sales"]')]
      .every((element) => element.scrollWidth <= element.clientWidth));

    // 83,833,330,000.00 less 3,333,330,000.00 leaves 80,500,000,000.00.
    await recordCollection(page, '2026-06-10', '3,333,330,000.00');
    await expect(fact(issuedInvoice(page, 'SIM-INV-0001'), 'Outstanding as of 10 Jun 2026')).toHaveText('NGN 80,500,000,000.00');
    await expect(history(page).getByRole('row', { name: /SIM-PAY-0001/ })).toContainText('NGN 80,500,000,000.00');
    expect(await contained()).toBe(true);
    await leaveDetail(page);
    await expect(invoiceRow(page, 'SIM-INV-0001')).toContainText('NGN 80,500,000,000.00');
    expect(await contained()).toBe(true);
  });
}

test('does not offer drafting without a confirmed reporting month', async ({ page }) => {
  await mockApi(page, { periods: null });
  await page.goto('/?view=partner-sales&period=202613');
  await expect(page.getByText('Reporting periods unavailable. Reload to retry.')).toBeVisible();
  await expect(page.getByRole('radio')).toHaveCount(0);
});

test('explains when no reporting months exist', async ({ page }) => {
  await mockApi(page, { periods: [] });
  await page.goto('/?view=partner-sales');
  await expect(page.getByText('No reporting periods available.')).toBeVisible();
  await expect(page.getByRole('radio')).toHaveCount(0);
});

// Partner Commission Account. Expected amounts are worked by hand from the fixture
// statements, never recomputed here.
const openCommissionAccount = async (page, partner) => {
  await choosePartner(page, partner);
  await workspace(page).getByRole('button', { name: `View commission account for ${partner}` }).click();
  // Opening moves focus on the next frame; let it land so its scroll cannot swallow a click.
  await expect(commissionAccount(page).getByRole('heading', { level: 2 })).toBeFocused();
};
const commissionAccount = (page) => workspace(page).getByRole('region', { name: /^Partner Commission Account for/ });
const statementFact = (page, name) => commissionAccount(page).getByRole('definition').filter({ has: page.locator(`xpath=preceding-sibling::dt[normalize-space()="${name}"]`) }).first();

test('reconciles opening, earnings and settlements to the closing commission outstanding', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await openCommissionAccount(page, 'Stone Light Networks · Account 74050');

  await expect(commissionAccount(page).getByRole('heading', { name: 'Partner Commission Account for Stone Light Networks · Account 74050' })).toBeFocused();
  await expect(commissionAccount(page).getByText('Statement for May 2026')).toBeVisible();
  await expect(commissionAccount(page).getByText('Fictional simulation', { exact: true })).toBeVisible();
  await expect(commissionAccount(page).getByText('Source reference SIM-OPEN-74050-202605')).toBeVisible();
  await expect(statementFact(page, 'Opening outstanding')).toHaveText('NGN 20,000.00');
  await expect(statementFact(page, 'Period earnings')).toHaveText('NGN 15,000.00');
  await expect(statementFact(page, 'Period settlements')).toHaveText('NGN 10,000.00');
  await expect(statementFact(page, 'Closing outstanding')).toHaveText('NGN 25,000.00');
});

test('keeps missing evidence unavailable and a recorded zero distinct from it', async ({ page }) => {
  await mockApi(page);
  await openSales(page);

  // Settlements recorded at zero: 5,000.00 + 12,000.00 - 0.00.
  await openCommissionAccount(page, 'Ember Hill Networks · Account 98052');
  await expect(statementFact(page, 'Period settlements')).toHaveText('NGN 0.00');
  await expect(statementFact(page, 'Closing outstanding')).toHaveText('NGN 17,000.00');
  await expect(commissionAccount(page).getByRole('row', { name: /SIM-SET-98052-0501.*Recorded zero/ })).toContainText('NGN 0.00');
  await commissionAccount(page).getByRole('button', { name: 'Back to invoices' }).click();

  // Missing settlements: earnings alone must not become a closing balance.
  await openCommissionAccount(page, 'Sunset Crest Communications · Account 205044');
  await expect(statementFact(page, 'Opening outstanding')).toHaveText('NGN 10,000.00');
  await expect(statementFact(page, 'Period earnings')).toHaveText('NGN 30,000.00');
  await expect(statementFact(page, 'Period settlements')).toHaveText('Unavailable');
  await expect(statementFact(page, 'Closing outstanding')).toHaveText('Unavailable');
  await expect(commissionAccount(page).getByText('Closing outstanding is unavailable because settlements lack evidence.')).toBeVisible();
  await expect(commissionAccount(page).getByText('All 1 entry across every page: earnings NGN 30,000.00, settlements unavailable.')).toBeVisible();
  await expect(commissionAccount(page).getByRole('table', { name: 'Commission by stream' }).getByText('NGN 0.00')).toHaveCount(0);
  await commissionAccount(page).getByRole('button', { name: 'Back to invoices' }).click();

  // Missing opening: the period figures stand, the closing balance does not.
  await openCommissionAccount(page, 'River Isle Ventures · Account 353072');
  await expect(statementFact(page, 'Opening outstanding')).toHaveText('Unavailable');
  await expect(statementFact(page, 'Period earnings')).toHaveText('NGN 53,999.83');
  await expect(statementFact(page, 'Period settlements')).toHaveText('NGN 48,599.85');
  await expect(statementFact(page, 'Closing outstanding')).toHaveText('Unavailable');
  await expect(commissionAccount(page).getByText('Closing outstanding is unavailable because the opening balance lacks evidence.')).toBeVisible();
  await commissionAccount(page).getByRole('button', { name: 'Back to invoices' }).click();

  // Missing subscription earnings: activation alone would be a misleading partial total.
  await page.getByRole('combobox', { name: /Reporting period/ }).selectOption('202606');
  await openCommissionAccount(page, 'Ember Hill Networks · Account 98052');
  await expect(statementFact(page, 'Period earnings')).toHaveText('Unavailable');
  await expect(statementFact(page, 'Closing outstanding')).toHaveText('Unavailable');
  await expect(commissionAccount(page).getByRole('row', { name: /^Subscription commission/ })).toContainText('Unavailable');
  await expect(commissionAccount(page).getByRole('row', { name: /^Activation commission/ })).toContainText('NGN 8,000.00');
  // No subscription settlement entry is missing evidence, not a settlement of zero.
  await expect(commissionAccount(page).getByRole('row', { name: /^Subscription commission/ })).not.toContainText('NGN 0.00');
  await expect(statementFact(page, 'Period settlements')).toHaveText('Unavailable');
  await expect(commissionAccount(page).getByText(/earnings unavailable, settlements unavailable/)).toBeVisible();
  await commissionAccount(page).getByRole('button', { name: 'Back to invoices' }).click();

  // No statement for this account and month: nothing is shown as zero.
  await openCommissionAccount(page, 'River Isle Ventures · Account 353072');
  await expect(commissionAccount(page).getByText('No fictional statement exists for River Isle Ventures · Account 353072 in Jun 2026.')).toBeVisible();
  for (const fact of ['Opening outstanding', 'Period earnings', 'Period settlements', 'Closing outstanding']) await expect(statementFact(page, fact)).toHaveText('Unavailable');
  await expect(commissionAccount(page).getByText('NGN 0.00')).toHaveCount(0);
});

test('keeps activation and subscription commission apart from subscription revenue and recharge cards', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await openCommissionAccount(page, 'Stone Light Networks · Account 74050');

  const streams = commissionAccount(page).getByRole('table', { name: 'Commission by stream' });
  await expect(streams.getByRole('row', { name: /^Activation commission/ })).toContainText('NGN 9,000.00');
  await expect(streams.getByRole('row', { name: /^Activation commission/ })).toContainText('NGN 7,500.00');
  await expect(streams.getByRole('row', { name: /^Subscription commission/ })).toContainText('NGN 6,000.00');
  await expect(streams.getByRole('row', { name: /^Subscription commission/ })).toContainText('NGN 2,500.00');
  await expect(streams.getByRole('row', { name: /^Total/ })).toContainText('NGN 15,000.00');
  await expect(streams.getByRole('row', { name: /^Total/ })).toContainText('NGN 10,000.00');

  // Revenue is shown but enters no total: 240,000.00 is absent from every figure above.
  const revenue = commissionAccount(page).getByText('Subscription revenue', { exact: true }).locator('..');
  await expect(revenue).toContainText('NGN 240,000.00');
  await expect(revenue).toContainText('not commission entitlement');
  await expect(streams.getByText('NGN 240,000.00')).toHaveCount(0);
  await expect(commissionAccount(page).getByText(/Recharge-card commissions are excluded/)).toBeVisible();
  await expect(commissionAccount(page).getByText(/Purchase obligations.*separate/)).toBeVisible();

  // No subscription records is not a recorded zero, and it does not block the total.
  await commissionAccount(page).getByRole('button', { name: 'Back to invoices' }).click();
  await openCommissionAccount(page, 'Ember Hill Networks · Account 98052');
  await expect(commissionAccount(page).getByRole('row', { name: /^Subscription commission/ })).toContainText('No source records');
  await expect(commissionAccount(page).getByRole('row', { name: /^Subscription commission/ })).not.toContainText('NGN');
});

test('pages dated activity in deterministic order and reconciles it to the whole statement', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await openCommissionAccount(page, 'Sunset Crest Communications · Account 295083');

  // Worked by hand: 110 x 1,000.00 earned, 10 x 500.00 settled, 1,000.00 opening.
  await expect(statementFact(page, 'Period earnings')).toHaveText('NGN 110,000.00');
  await expect(statementFact(page, 'Period settlements')).toHaveText('NGN 5,000.00');
  await expect(statementFact(page, 'Closing outstanding')).toHaveText('NGN 106,000.00');

  const activity = commissionAccount(page).getByRole('table', { name: /Dated commission activity/ });
  const rows = activity.locator('tbody tr');
  const reconciliation = commissionAccount(page).getByText('All 120 entries across every page: earnings NGN 110,000.00, settlements NGN 5,000.00.');
  await expect(rows).toHaveCount(25);
  await expect(reconciliation).toBeVisible();
  await expect(rows.first()).toContainText('1 May 2026');
  // Entries 1 and 32 share 1 May; the reference settles their order.
  await expect(rows.nth(0)).toContainText('SIM-COM-295083-0001');
  await expect(rows.nth(1)).toContainText('SIM-COM-295083-0032');

  await commissionAccount(page).getByRole('combobox', { name: 'Rows per page' }).selectOption('100');
  await expect(rows).toHaveCount(100);
  await expect(commissionAccount(page).getByText('1–100 of 120')).toBeVisible();
  await expect(reconciliation).toBeVisible();
  await commissionAccount(page).getByRole('button', { name: 'Next' }).click();
  await expect(rows).toHaveCount(20);
  await expect(commissionAccount(page).getByText('101–120 of 120')).toBeVisible();
  await expect(reconciliation).toBeVisible();
  await expect(statementFact(page, 'Closing outstanding')).toHaveText('NGN 106,000.00');
});

// Same fields and values as the sample-mode API: backend/tests/test_partner_commission_fixtures.py
// holds the fixtures to it, and the statement response carries no subscription commission.
const recordedStatements = {
  '296065|202605': { dealer_id: '296065', mon_period: '202605', commission: { expected_ngn: 951213.38 }, payment: { data_source: 'simulated', payment_found: true, amount_paid_ngn: 380485.35 }, orsc: { total_subscription_amount_ngn: 114986.29 } },
  '353072|202605': { dealer_id: '353072', mon_period: '202605', commission: { expected_ngn: 53999.83 }, payment: { data_source: 'simulated', payment_found: true, amount_paid_ngn: 48599.85 }, orsc: null },
};
const recordedSubscriptions = {
  '296065|202605': { dealer_id: '296065', dealer_name: 'River Isle Ventures', amount_ngn: 114986.29, record_count: 2, zero_count: 0, delta_ngn: null, prior_amount_ngn: null, subscription_commission_ngn: 3709, subscription_settled_ngn: 1854.5, subscription_outstanding_ngn: 1854.5, subscription_commission_record_count: 2, subscription_commission_complete: true },
};
const statementRead = (overrides = {}) => (pathname, params) => {
  const statement = /^\/dealers\/(\d+)\/statement$/.exec(pathname);
  const subscription = /^\/commissions\/(\d+)\/detail$/.exec(pathname);
  if (subscription && params.get('stream') !== 'orsc') return undefined;
  const match = statement ?? subscription;
  if (!match) return undefined;
  const key = `${statement ? '' : 'subscription:'}${match[1]}|${params.get('mon_period')}`;
  if (key in overrides) return overrides[key];
  const account = recordedSubscriptions[`${match[1]}|${params.get('mon_period')}`];
  if (subscription) return account ? { json: { account, denominations: [], source: 'Sample fixture', generated_at: '2026-06-01T00:00:00Z' } } : { status: 404, json: { detail: 'No account records for this stream and period' } };
  return recordedStatements[key] ? { json: recordedStatements[key] } : { status: 404, json: { detail: 'No activation record' } };
};
const explanationLink = (page, name) => commissionAccount(page).getByRole('button', { name, exact: true });
const evidenceLinks = (page) => commissionAccount(page).getByRole('region', { name: 'Existing explanations' });
const returnToSales = (page) => page.getByRole('button', { name: 'Return to Partner Sales' });

// The explanations themselves answer from these, recording exactly what they asked for.
function explanationReads(calls) {
  const statement = statementRead();
  return (pathname, params) => {
    if (/^\/commissions\/\d+\/detail$/.test(pathname) || /^\/payments\/accounts\/\d+$/.test(pathname)) {
      calls.push(`${pathname}?mon_period=${params.get('mon_period')}&stream=${params.get('stream')}`);
      if (params.get('stream') === 'orsc') return statement(pathname, params);
      const account = { dealer_id: '296065', dealer_name: 'River Isle Ventures', amount_ngn: 951213.38, record_count: 3, zero_count: 0, delta_ngn: null, prior_amount_ngn: null, commission_owed: 951213.38, amount_paid: 380485.35, amount_unpaid: 570728.03 };
      return { json: { account, denominations: [], source: 'Sample fixture', generated_at: '2026-06-01T00:00:00Z' } };
    }
    return statement(pathname, params);
  };
}

test('explains the period basis of a linked statement and discloses the opening carry-forward', async ({ page }) => {
  await mockApi(page, { reads: statementRead() });
  await openSales(page);
  await openCommissionAccount(page, 'River Isle Ventures · Account 296065');

  // 951,213.38 + 3,709.00 earned; 380,485.35 + 1,854.50 settled; 250,000.00 carried in.
  await expect(statementFact(page, 'Opening outstanding')).toHaveText('NGN 250,000.00');
  await expect(statementFact(page, 'Period earnings')).toHaveText('NGN 954,922.38');
  await expect(statementFact(page, 'Period settlements')).toHaveText('NGN 382,339.85');
  await expect(statementFact(page, 'Closing outstanding')).toHaveText('NGN 822,582.53');
  await expect(statementFact(page, 'Period-only outstanding')).toHaveText('NGN 572,582.53');
  await expect(explanationLink(page, 'Explain activation commission')).toBeVisible();
  await expect(evidenceLinks(page)).toContainText('match recorded evidence for Account 296065, May 2026, stream by stream');
  await expect(evidenceLinks(page)).toContainText('do not include the fictional opening carry-forward of NGN 250,000.00');
});

test('follows each explanation link to the exact account and month and returns to sales context', async ({ page }) => {
  const calls = [];
  const { mutations, requests } = await mockApi(page, { reads: explanationReads(calls) });
  await openSales(page);
  await openCommissionAccount(page, 'River Isle Ventures · Account 296065');

  const commission = page.getByRole('main', { name: 'Commission intelligence' });
  for (const [name, expected, explained] of [
    ['Explain activation commission', '/commissions/296065/detail?mon_period=202605&stream=activation', () => commission.getByRole('button', { name: 'Activation commission', exact: true })],
    // The evidence check already read this account, so the explanation shares that read.
    ['Explain subscription commission', '/commissions/296065/detail?mon_period=202605&stream=orsc', () => commission.getByRole('button', { name: 'Subscriptions', exact: true })],
    ['Explain settlement', '/payments/accounts/296065?mon_period=202605&stream=null', null],
  ]) {
    await explanationLink(page, name).click();
    await expect(returnToSales(page)).toBeVisible();
    await expect(page.getByText('Opened from the Partner Sales simulation for exact account 296065, May 2026.')).toBeVisible();
    await expect(workspace(page)).toBeHidden();
    await expect.poll(() => calls).toContain(expected);
    if (explained) await expect(explained()).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('heading', { name: 'River Isle Ventures' })).toBeVisible();
    expect(calls.every((call) => call.includes('296065') && call.includes('mon_period=202605'))).toBe(true);
    await expect(page.getByRole('combobox', { name: /Reporting period/ })).toHaveValue('202605');

    await returnToSales(page).click();
    await expect(commissionAccount(page)).toBeVisible();
    await expect(explanationLink(page, name)).toBeFocused();
    await expect(returnToSales(page)).toHaveCount(0);
    await expect(statementFact(page, 'Closing outstanding')).toHaveText('NGN 822,582.53');
  }
  expect(mutations).toEqual([]);
  expect(requests.filter((path) => path.includes('chat'))).toEqual([]);
});

test('restores sales context after a browser back and after refreshing an explanation', async ({ page }) => {
  await mockApi(page, { reads: explanationReads([]) });
  await openSales(page);
  await openCommissionAccount(page, 'River Isle Ventures · Account 296065');

  await explanationLink(page, 'Explain settlement').click();
  await expect(returnToSales(page)).toBeVisible();
  await page.goBack();
  await expect(commissionAccount(page)).toBeVisible();

  await explanationLink(page, 'Explain settlement').click();
  await expect(returnToSales(page)).toBeVisible();
  await page.reload();
  await returnToSales(page).click();
  // Focus returns to the link if it has rendered by the next frame, otherwise to the heading.
  await expect(commissionAccount(page).getByRole('heading', { name: /River Isle Ventures · Account 296065/ })).toBeVisible();
  await expect(commissionAccount(page).locator(':focus')).toHaveCount(1);
  await expect(statementFact(page, 'Closing outstanding')).toHaveText('NGN 822,582.53');
});

test('a month changed during an explanation reaches the statement without substituting evidence', async ({ page }) => {
  await mockApi(page, { reads: explanationReads([]) });
  await openSales(page);
  await openCommissionAccount(page, 'River Isle Ventures · Account 296065');
  await explanationLink(page, 'Explain settlement').click();
  await page.getByRole('combobox', { name: /Reporting period/ }).selectOption('202606');
  // The handoff stays true to what it opened and says the month has since moved on.
  await expect(page.getByText('Opened from the Partner Sales simulation for exact account 296065, May 2026. The reporting month is now Jun 2026.')).toBeVisible();
  await returnToSales(page).click();

  // June opens on May's closing: 822,582.53 + 994,136.80 - 397,959.72. June has no
  // recorded statement in this fixture, so its links stay unavailable.
  await expect(commissionAccount(page).getByText('Statement for Jun 2026')).toBeVisible();
  await expect(statementFact(page, 'Opening outstanding')).toHaveText('NGN 822,582.53');
  await expect(statementFact(page, 'Closing outstanding')).toHaveText('NGN 1,418,759.61');
  await expect(evidenceLinks(page)).toContainText('No recorded statement exists for Account 296065 in Jun 2026');
  await expect(evidenceLinks(page).getByRole('button')).toHaveCount(0);
});

test('a link followed from another month carries that month', async ({ page }) => {
  const calls = [];
  const reads = explanationReads(calls);
  const june = { json: { dealer_id: '296065', mon_period: '202606', commission: { expected_ngn: 991086.8 }, payment: { data_source: 'simulated', payment_found: true, amount_paid_ngn: 396434.72 }, orsc: { total_subscription_amount_ngn: 120266.83 } } };
  const juneSubscription = { json: { account: { ...recordedSubscriptions['296065|202605'], subscription_commission_ngn: 3050, subscription_settled_ngn: 1525 } } };
  await mockApi(page, { reads: (pathname, params) => {
    if (params.get('mon_period') === '202606' && pathname === '/dealers/296065/statement') return june;
    if (params.get('mon_period') === '202606' && pathname === '/commissions/296065/detail' && params.get('stream') === 'orsc') return juneSubscription;
    return reads(pathname, params);
  } });
  await openSales(page, '/?period=202606');
  await openCommissionAccount(page, 'River Isle Ventures · Account 296065');
  await explanationLink(page, 'Explain settlement').click();
  await expect(page.getByText('Opened from the Partner Sales simulation for exact account 296065, Jun 2026.')).toBeVisible();
  await expect.poll(() => calls).toContain('/payments/accounts/296065?mon_period=202606&stream=null');
  expect(calls.filter((call) => call.includes('202605'))).toEqual([]);
});

test('shows an unavailable handoff, never a substitute, when evidence is missing or incompatible', async ({ page }) => {
  const { requests } = await mockApi(page, { reads: statementRead({ '296065|202605': { json: { ...recordedStatements['296065|202605'], commission: { expected_ngn: 951213.39 } } } }) });
  await openSales(page);

  // One kobo away from the fixture is incompatible evidence.
  await openCommissionAccount(page, 'River Isle Ventures · Account 296065');
  await expect(evidenceLinks(page)).toContainText('does not reconcile with recorded evidence');
  await expect(evidenceLinks(page).getByRole('button')).toHaveCount(0);
  await commissionAccount(page).getByRole('button', { name: 'Back to invoices' }).click();

  // The acceptance example never asserts values for a sample dealer, so it never asks.
  requests.length = 0;
  await openCommissionAccount(page, 'Stone Light Networks · Account 74050');
  await expect(evidenceLinks(page)).toContainText('not connected to a recorded statement');
  await expect(evidenceLinks(page).getByRole('button')).toHaveCount(0);
  expect(requests.filter((path) => path.startsWith('/dealers') || path.startsWith('/commissions'))).toEqual([]);
  await commissionAccount(page).getByRole('button', { name: 'Back to invoices' }).click();

  // No subscription records means no subscription link, on an otherwise linked statement.
  await openCommissionAccount(page, 'River Isle Ventures · Account 353072');
  await expect(explanationLink(page, 'Explain activation commission')).toBeVisible();
  await expect(explanationLink(page, 'Explain subscription commission')).toHaveCount(0);
  await expect(evidenceLinks(page)).toContainText('The opening balance is unavailable');
});

test('a subscription amount one kobo from the recorded account offers no explanation', async ({ page }) => {
  const account = { ...recordedSubscriptions['296065|202605'], subscription_settled_ngn: 1854.51 };
  await mockApi(page, { reads: statementRead({ 'subscription:296065|202605': { json: { account } } }) });
  await openSales(page);
  await openCommissionAccount(page, 'River Isle Ventures · Account 296065');
  await expect(evidenceLinks(page)).toContainText('does not reconcile with recorded evidence');
  await expect(evidenceLinks(page).getByRole('button')).toHaveCount(0);
});

test('incomplete subscription evidence offers no explanation', async ({ page }) => {
  const account = { ...recordedSubscriptions['296065|202605'], subscription_commission_complete: false };
  await mockApi(page, { reads: statementRead({ 'subscription:296065|202605': { json: { account } } }) });
  await openSales(page);
  await openCommissionAccount(page, 'River Isle Ventures · Account 296065');
  await expect(evidenceLinks(page)).toContainText('does not reconcile with recorded evidence');
});

test('offers a retry when recorded evidence cannot be read, and no link until it can', async ({ page }) => {
  let failing = true;
  const statement = statementRead();
  await mockApi(page, { reads: (pathname, params) => (failing && (pathname.startsWith('/dealers') || pathname.startsWith('/commissions')) ? { status: 503, json: { detail: 'Unavailable' } } : statement(pathname, params)) });
  await openSales(page);
  await openCommissionAccount(page, 'River Isle Ventures · Account 296065');

  await expect(evidenceLinks(page)).toContainText('could not be checked');
  await expect(explanationLink(page, 'Explain settlement')).toHaveCount(0);
  await expect(statementFact(page, 'Closing outstanding')).toHaveText('NGN 822,582.53');
  failing = false;
  await evidenceLinks(page).getByRole('button', { name: 'Retry evidence check' }).click();
  await expect(explanationLink(page, 'Explain settlement')).toBeVisible();
});

test('stays fictional and unlinked in live-read mode, and asks live sources nothing', async ({ page }) => {
  const { mutations, requests } = await mockApi(page, { health: { sample_data_mode: false }, reads: statementRead() });
  await openSales(page);
  await openCommissionAccount(page, 'River Isle Ventures · Account 296065');

  await expect(evidenceLinks(page)).toContainText('reading live data');
  await expect(evidenceLinks(page).getByRole('button')).toHaveCount(0);
  await expect(commissionAccount(page).getByText('Fictional simulation', { exact: true })).toBeVisible();
  await expect(commissionAccount(page).getByText(/not recorded evidence or amounts owed/)).toBeVisible();
  await expect(page.getByText('Synthetic demonstration')).toBeVisible();
  await expect(page.getByText('Live Presto')).toHaveCount(0);
  expect(requests.filter((path) => path.startsWith('/dealers') || path.startsWith('/commissions') || path.includes('chat'))).toEqual([]);
  expect(mutations).toEqual([]);
});

test('sales activity leaves the commission account unchanged and links both separate balances', async ({ page }) => {
  const { mutations } = await mockApi(page);
  await openSales(page);
  await startDraft(page, 'Stone Light Networks · Account 74050');
  await addLine(page, 'FBB-5G-ROUTER', '2');
  await previewButton(page).click();
  await workspace(page).getByRole('button', { name: 'Issue simulated invoice' }).click();
  await workspace(page).getByLabel('Amount in NGN').fill('40000');
  await workspace(page).getByRole('button', { name: 'Record collection' }).click();
  await workspace(page).getByRole('button', { name: /View purchase obligations/ }).click();

  await workspace(page).getByRole('button', { name: 'View commission account for Stone Light Networks · Account 74050' }).click();
  await expect(statementFact(page, 'Opening outstanding')).toHaveText('NGN 20,000.00');
  await expect(statementFact(page, 'Period earnings')).toHaveText('NGN 15,000.00');
  await expect(statementFact(page, 'Period settlements')).toHaveText('NGN 10,000.00');
  await expect(statementFact(page, 'Closing outstanding')).toHaveText('NGN 25,000.00');
  await expect(commissionAccount(page).getByText('SIM-INV')).toHaveCount(0);
  await expect(commissionAccount(page).getByText('SIM-PAY')).toHaveCount(0);

  await commissionAccount(page).getByRole('button', { name: 'Back to purchase obligations' }).click();
  await expect(workspace(page).getByRole('heading', { name: /^Purchase obligations for Stone Light Networks/ })).toBeVisible();
  expect(mutations).toEqual([]);
});

test('operates by keyboard and fits a narrow screen', async ({ page }) => {
  await mockApi(page, { reads: explanationReads([]) });
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto('/?period=202605&view=partner-sales');
  await choosePartner(page, 'River Isle Ventures · Account 296065');

  const opener = workspace(page).getByRole('button', { name: 'View commission account for River Isle Ventures · Account 296065' });
  await opener.focus();
  await page.keyboard.press('Enter');
  await expect(commissionAccount(page).getByRole('heading', { level: 2 })).toBeFocused();
  await expect(explanationLink(page, 'Explain settlement')).toBeVisible();

  const overflow = () => page.evaluate(() => {
    const scroller = document.querySelector('.sales-workspace');
    return [scroller.scrollWidth - scroller.clientWidth, document.documentElement.scrollWidth - document.documentElement.clientWidth];
  });
  expect(await overflow()).toEqual([0, 0]);
  await expect(commissionAccount(page).getByRole('row', { name: /^Activation commission/ })).toContainText('NGN 951,213.38');
  await expect(commissionAccount(page).getByRole('row', { name: /SIM-COM-296065-0501/ })).toContainText('NGN 500,000.00');

  await explanationLink(page, 'Explain settlement').focus();
  await page.keyboard.press('Enter');
  await returnToSales(page).focus();
  await page.keyboard.press('Enter');
  await expect(explanationLink(page, 'Explain settlement')).toBeFocused();

  await commissionAccount(page).getByRole('button', { name: 'Back to invoices' }).focus();
  await page.keyboard.press('Enter');
  await expect(opener).toBeFocused();
  for (const width of [768, 1024]) {
    await page.setViewportSize({ width, height: 800 });
    await opener.click();
    expect(await overflow()).toEqual([0, 0]);
    await commissionAccount(page).getByRole('button', { name: 'Back to invoices' }).click();
  }
});

// Reset and replay. The presentation values are the specification's worked example:
// 2 x 50,000.00 + 100 x 100.00 = 110,000.00; 110,000.00 - 40,000.00 = 70,000.00.
const resetButton = (page) => workspace(page).getByRole('button', { name: 'Reset simulation', exact: true });
const resetPanel = (page) => workspace(page).getByRole('group', { name: 'Confirm simulation reset' });
const confirmReset = (page) => resetPanel(page).getByRole('button', { name: 'Reset to starting point' });
const resetNotice = (page) => workspace(page).getByRole('status').filter({ hasText: 'Simulation reset' });
const matchingRecordCount = (page) => fact(invoiceList(page), 'Matching records');

// Worked by hand from the catalogue. Paid: 35,000.00 + 50 x 500.00 = 60,000.00.
// Partially paid: 2 x 50,000.00 + 100 x 200.00 = 120,000.00, less 45,000.00 = 75,000.00.
// Unpaid: 3 x 35,000.00 = 105,000.00. Outstanding 75,000.00 + 105,000.00 = 180,000.00.
const expectExampleInvoices = async (page) => {
  await expect(matchingRecordCount(page)).toHaveText('3');
  await expect(fact(invoiceList(page), 'Outstanding purchase obligation')).toHaveText('NGN 180,000.00');
  await expect(invoiceRow(page, 'SIM-INV-0001')).toContainText('Sunset Crest Communications · Account 205044');
  await expect(invoiceRow(page, 'SIM-INV-0001')).toContainText('Paid');
  await expect(invoiceRow(page, 'SIM-INV-0001')).toContainText('NGN 60,000.00');
  await expect(invoiceRow(page, 'SIM-INV-0002')).toContainText('Ember Hill Networks · Account 98052');
  await expect(invoiceRow(page, 'SIM-INV-0002')).toContainText('Partially paid');
  await expect(invoiceRow(page, 'SIM-INV-0002')).toContainText('Outstanding NGN 75,000.00');
  await expect(invoiceRow(page, 'SIM-INV-0003')).toContainText('Stone Light Networks · Account 74050');
  await expect(invoiceRow(page, 'SIM-INV-0003')).toContainText('Unpaid');
  await expect(invoiceRow(page, 'SIM-INV-0003')).toContainText('NGN 105,000.00');
};

test('the simulation starts with one example invoice of each status, clear of the presentation account', async ({ page }) => {
  await mockApi(page, { examples: true });
  await openSales(page);
  await expectExampleInvoices(page);
  await expect(workspace(page).getByRole('radio', { checked: true })).toHaveCount(0);

  await invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0002' }).click();
  const example = issuedInvoice(page, 'SIM-INV-0002');
  await expect(example).toContainText('Fictional simulation');
  await expect(example.getByRole('row', { name: /Total.*NGN 120,000\.00/ })).toBeVisible();
  await expect(history(page, 'SIM-INV-0002').getByRole('row', { name: /20 May 2026.*SIM-PAY-0002.*NGN 45,000\.00.*NGN 75,000\.00/ })).toBeVisible();
  await leaveDetail(page);

  await choosePartner(page, 'River Isle Ventures · Account 296065');
  await workspace(page).getByRole('button', { name: /^View purchase obligations for River Isle Ventures/ }).click();
  const obligations = workspace(page).getByRole('region', { name: /^Purchase obligations/ });
  await expect(obligations.getByText('SIM-INV')).toHaveCount(0);
  await leaveDetail(page);

  await workspace(page).getByRole('button', { name: 'Create draft' }).click();
  await expect(workspace(page).getByText('SIM-INV-0004 · May 2026')).toBeVisible();

  // Examples belong to May, and every month says so.
  await period(page).selectOption('202606');
  await expect(matchingRecordCount(page)).toHaveText('0');
  await expect(workspace(page).getByText('It starts with example invoices in May 2026.')).toBeVisible();
  await resetButton(page).click();
  await confirmReset(page).click();
  await expect(resetNotice(page)).toContainText('3 example invoices in May 2026');
});

test('a reset restores the example invoices exactly after they have been changed', async ({ page }) => {
  await mockApi(page, { examples: true });
  await openSales(page);
  await invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0003' }).click();
  await collectionAmount(page, 'SIM-INV-0003').fill('105000');
  await recordButton(page, 'SIM-INV-0003').click();
  await expect(fact(issuedInvoice(page, 'SIM-INV-0003'), 'Status')).toHaveText('Paid');

  await resetButton(page).click();
  await confirmReset(page).click();
  await expect(resetNotice(page)).toContainText('3 example invoices');
  await expect(resetNotice(page)).toContainText('SIM-INV-0004');
  await expectExampleInvoices(page);
  await page.reload();
  await expectExampleInvoices(page);
});

test('reset returns to the example invoices, restarts references and leaves everything else alone', async ({ page }) => {
  const { mutations, requests } = await mockApi(page, { examples: true });
  await openSales(page);
  await page.evaluate(() => sessionStorage.setItem('unrelated.user.state', 'kept'));
  await issueMixedInvoice(page, 'SIM-INV-0004');
  await recordCollection(page, '2026-05-31', '40000', 'SIM-INV-0004');
  await leaveDetail(page);
  await workspace(page).getByRole('searchbox', { name: 'Search invoices by partner or account code' }).fill('296065');
  await startDraft(page, 'Stone Light Networks · Account 74050');
  await workspace(page).getByRole('searchbox', { name: 'Find a partner' }).fill('Stone');
  await page.waitForLoadState('networkidle');
  requests.length = 0;

  await resetButton(page).click();
  await expect(resetPanel(page)).toContainText('1 draft, 4 invoices and 3 collections');
  await expect(resetPanel(page)).toContainText('Recorded commission, payment and inventory evidence');
  await expect(matchingRecordCount(page)).toHaveText('1');
  await confirmReset(page).click();

  await expect(resetNotice(page)).toBeFocused();
  await expect(workspace(page).getByText('Select a trade partner to create a draft.')).toBeVisible();
  await expect(workspace(page).getByRole('radio', { checked: true })).toHaveCount(0);
  await expect(workspace(page).getByRole('searchbox', { name: 'Find a partner' })).toHaveValue('');
  await expect(workspace(page).getByRole('searchbox', { name: 'Search invoices by partner or account code' })).toHaveValue('');
  await expect(matchingRecordCount(page)).toHaveText('3');
  await expect(invoiceRow(page, 'SIM-INV-0004')).toHaveCount(0);

  await page.reload();
  await expect(workspace(page).getByText('Select a trade partner to create a draft.')).toBeVisible();
  await expect(matchingRecordCount(page)).toHaveText('3');
  expect(await page.evaluate(() => sessionStorage.getItem('unrelated.user.state'))).toBe('kept');
  await expect(page.getByRole('combobox', { name: /Reporting period/ })).toHaveValue('202605');

  await startDraft(page);
  await expect(workspace(page).getByText('SIM-INV-0004 · May 2026')).toBeVisible();
  await addLine(page, 'FBB-5G-ROUTER', '2');
  await previewButton(page).click();
  await workspace(page).getByRole('button', { name: 'Issue simulated invoice' }).click();
  await workspace(page).getByLabel('Amount in NGN').fill('1');
  await workspace(page).getByRole('button', { name: 'Record collection' }).click();
  await expect(workspace(page).getByText('Recorded SIM-PAY-0003 for NGN 1.00.')).toBeVisible();
  expect(mutations).toEqual([]);
  expect(requests.filter((path) => !['/periods', '/health'].includes(path))).toEqual([]);
});

test('keeping the simulation changes nothing, and resetting from an open detail returns to the start', async ({ page }) => {
  await mockApi(page, { examples: true });
  await openSales(page);
  await issueMixedInvoice(page, 'SIM-INV-0004');

  await resetButton(page).click();
  await resetPanel(page).getByRole('button', { name: 'Keep simulation' }).click();
  await expect(resetButton(page)).toBeFocused();
  await expect(fact(issuedInvoice(page, 'SIM-INV-0004'), 'Status')).toHaveText('Unpaid');

  await resetButton(page).click();
  await confirmReset(page).click();
  await expect(issuedInvoice(page, 'SIM-INV-0004')).toHaveCount(0);
  await expect(resetNotice(page)).toBeFocused();
  await choosePartner(page, 'Stone Light Networks · Account 74050');
  await expect(resetNotice(page)).toHaveCount(0);
});

test('a reset after an explanation does not reopen that account on refresh or revisit', async ({ page }) => {
  await mockApi(page, { reads: explanationReads([]), examples: true });
  await openSales(page);
  await openCommissionAccount(page, 'River Isle Ventures · Account 296065');
  await explanationLink(page, 'Explain settlement').click();
  await returnToSales(page).click();
  await expect(commissionAccount(page)).toBeVisible();

  await resetButton(page).click();
  await confirmReset(page).click();
  await expect(commissionAccount(page)).toHaveCount(0);

  await nav(page, 'Payments');
  await nav(page, 'Partner Sales');
  await expect(commissionAccount(page)).toHaveCount(0);
  await page.reload();
  await expect(workspace(page).getByText('Select a trade partner to create a draft.')).toBeVisible();
  await expect(commissionAccount(page)).toHaveCount(0);
});

test('a reset leaves an open explanation alone, and returning from it shows the same fictional statement', async ({ page }) => {
  await mockApi(page, { reads: explanationReads([]), examples: true });
  await openSales(page);
  await openCommissionAccount(page, 'River Isle Ventures · Account 296065');
  await explanationLink(page, 'Explain settlement').click();
  await returnToSales(page).click();
  await resetButton(page).click();
  await confirmReset(page).click();

  await nav(page, 'Payments');
  await expect(page.getByText('Opened from the Partner Sales simulation for exact account 296065, May 2026.')).toBeVisible();
  await returnToSales(page).click();
  await expect(statementFact(page, 'Closing outstanding')).toHaveText('NGN 822,582.53');
  await commissionAccount(page).getByRole('button', { name: 'Back to invoices' }).click();
  await expect(matchingRecordCount(page)).toHaveText('3');
  await expect(workspace(page).getByRole('radio', { checked: true })).toHaveCount(0);
});

test('a reset that fails says nothing changed, and succeeds on retry', async ({ page }) => {
  await mockApi(page, { examples: true });
  await openSales(page);
  await issueMixedInvoice(page, 'SIM-INV-0004');
  const resetting = `${API_BASE}/partner-sales/reset`;
  await page.route(resetting, (route) => route.abort());
  await resetButton(page).click();
  await confirmReset(page).click();
  await expect(resetPanel(page).getByRole('alert')).toContainText('nothing has changed');
  await expect(fact(issuedInvoice(page, 'SIM-INV-0004'), 'Status')).toHaveText('Unpaid');
  await page.unroute(resetting);
  await confirmReset(page).click();
  await expect(resetNotice(page)).toBeFocused();
  await expect(matchingRecordCount(page)).toHaveText('3');
});

// What another session does while this page still shows what it loaded earlier.
const salesApi = (path) => `${API_BASE}/partner-sales/${path}`;
const draftOf = async (page, accountCode) => (await (await page.request.get(salesApi('drafts'), { params: { account_code: accountCode, mon_period: '202605' } })).json()).draft;
const resetElsewhere = (page) => page.request.post(salesApi('reset'));
const editElsewhere = async (page, accountCode, lines) => {
  const draft = await draftOf(page, accountCode);
  const saved = await page.request.put(salesApi(`drafts/${draft.reference}`), { data: { token: draft.token, issue_date: draft.issue_date, due_date: draft.due_date, lines } });
  expect(saved.ok()).toBe(true);
  return saved.json();
};
const draftForAnotherAccount = async (page) => {
  const created = await page.request.post(salesApi('drafts'), { data: { account_code: '74050', mon_period: '202605' } });
  return editElsewhere(page, (await created.json()).account_code, [{ product_code: 'RCC-0500', quantity: '7' }]);
};
const refused = (page) => workspace(page).getByRole('alert').filter({ hasText: 'This changed elsewhere or the simulation was reset' });
const loadLatest = (page) => workspace(page).getByRole('button', { name: 'Load latest' });

test('a save from before a reset is refused and cannot touch another account’s draft with the same reference', async ({ page }) => {
  await mockApi(page, { examples: true });
  await openSales(page);
  await startDraft(page);
  await addLine(page, 'FBB-5G-ROUTER', '2');
  await draftSaved(page);
  await resetElsewhere(page);
  const theirs = await draftForAnotherAccount(page);

  await quantity(page, 'FBB-5G-ROUTER').fill('3');
  await expect(refused(page)).toBeVisible();
  await expect(quantity(page, 'FBB-5G-ROUTER')).toHaveValue('3');
  expect(await draftOf(page, '74050')).toEqual(theirs);

  await loadLatest(page).click();
  await expect(workspace(page).getByRole('button', { name: 'Create draft' })).toBeVisible();
  await expect(workspace(page).getByText('No draft for River Isle Ventures · Account 296065')).toBeFocused();
  await expect(refused(page)).toHaveCount(0);
  expect(await draftOf(page, '74050')).toEqual(theirs);
});

test('issuing from before a reset is refused and issues nothing', async ({ page }) => {
  await mockApi(page, { examples: true });
  await openSales(page);
  await buildMixedDraft(page);
  await draftSaved(page);
  await previewButton(page).click();
  await resetElsewhere(page);
  const theirs = await draftForAnotherAccount(page);

  await issueButton(page).click();
  await expect(refused(page)).toBeVisible();
  await expect(preview(page)).toBeVisible();
  expect(await draftOf(page, '74050')).toEqual(theirs);
  expect((await (await page.request.get(salesApi('status'))).json()).invoices).toBe(3);

  await loadLatest(page).click();
  await expect(workspace(page).getByRole('button', { name: 'Create draft' })).toBeVisible();
});

test('a draft changed in another session is refused, and Load latest shows that version in place of unsaved edits', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await startDraft(page);
  await addLine(page, 'FBB-5G-ROUTER', '2');
  await draftSaved(page);
  await editElsewhere(page, '296065', [{ product_code: 'RCC-0100', quantity: '9' }]);

  await quantity(page, 'FBB-5G-ROUTER').fill('3');
  await expect(refused(page)).toBeVisible();
  await expect(quantity(page, 'FBB-5G-ROUTER')).toHaveValue('3');
  expect((await draftOf(page, '296065')).lines).toEqual([{ product_code: 'RCC-0100', quantity: '9' }]);

  await loadLatest(page).click();
  await expect(quantity(page, 'RCC-0100')).toHaveValue('9');
  await expect(quantity(page, 'FBB-5G-ROUTER')).toHaveCount(0);
  await expect(refused(page)).toHaveCount(0);
  await expect(workspace(page).getByRole('heading', { name: /^Draft for / })).toBeFocused();

  await quantity(page, 'RCC-0100').fill('10');
  await draftSaved(page);
  expect((await draftOf(page, '296065')).lines).toEqual([{ product_code: 'RCC-0100', quantity: '10' }]);
});

test('previewing an older copy of a draft refuses the issue, so the invoice is never other than what was shown', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await buildMixedDraft(page);
  await draftSaved(page);
  await previewButton(page).click();
  await editElsewhere(page, '296065', [{ product_code: 'RCC-0100', quantity: '9' }]);

  await issueButton(page).click();
  await expect(refused(page)).toBeVisible();
  await expect(preview(page)).toBeVisible();
  await loadLatest(page).click();
  await expect(quantity(page, 'RCC-0100')).toHaveValue('9');
});

test('a collection from before a reset is refused, and Load latest shows the invoice now holding that reference', async ({ page }) => {
  await mockApi(page, { examples: true });
  await openSales(page);
  await invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0003' }).click();
  await expect(fact(issuedInvoice(page, 'SIM-INV-0003'), 'Status')).toHaveText('Unpaid');
  await resetElsewhere(page);

  await recordCollection(page, '2026-06-10', '100', 'SIM-INV-0003');
  await expect(refused(page)).toBeVisible();
  await loadLatest(page).click();
  await expect(fact(issuedInvoice(page, 'SIM-INV-0003'), 'Collected')).toHaveText('NGN 0.00');
  await expect(refused(page)).toHaveCount(0);
  await expect(issuedInvoice(page, 'SIM-INV-0003').getByRole('heading', { name: 'Simulated invoice SIM-INV-0003' })).toBeFocused();
  await recordCollection(page, '2026-06-10', '100', 'SIM-INV-0003');
  await expect(collections(page, 'SIM-INV-0003').getByRole('status')).toContainText('Recorded');
});

test('Load latest on an invoice a reset removed says it is gone', async ({ page }) => {
  await mockApi(page, { examples: true });
  await openSales(page);
  await issueMixedInvoice(page, 'SIM-INV-0004');
  await resetElsewhere(page);
  await recordCollection(page, '2026-06-10', '100', 'SIM-INV-0004');
  await expect(refused(page)).toBeVisible();
  await loadLatest(page).click();
  await expect(issuedInvoice(page, 'SIM-INV-0004').getByRole('alert')).toContainText('no longer in the simulation');
});

test('says when an account has more drafts than the obligations view lists', async ({ page }) => {
  await mockApi(page);
  const month = (index) => `${2015 + Math.floor(index / 12)}${String(index % 12 + 1).padStart(2, '0')}`;
  await seed(page, { ...EMPTY_SIMULATION, next_sequence: 102, drafts: Array.from({ length: 101 }, (_, index) => ({
    reference: `SIM-INV-${String(index + 1).padStart(4, '0')}`, token: `seeded-draft-${index}`, account_code: '296065', period: month(index),
    issue_date: `${month(index).slice(0, 4)}-${month(index).slice(4)}-01`, due_date: '', lines: [],
  })) });
  await openSales(page);
  await choosePartner(page, 'River Isle Ventures · Account 296065');
  await workspace(page).getByRole('button', { name: 'View purchase obligations for River Isle Ventures · Account 296065' }).click();
  const listed = workspace(page).getByRole('list', { name: 'Drafts excluded from outstanding' }).getByRole('listitem');
  await expect(listed).toHaveCount(100);
  await expect(workspace(page).getByText('Showing the newest 100 of 101 drafts')).toBeVisible();
});

test('a list that shrinks and regrows stays on the page it fell back to', async ({ page }) => {
  await mockApi(page);
  const simulation = seededSimulation();
  simulation.drafts = [];
  simulation.invoices = simulation.invoices.slice(0, 26);
  await seed(page, simulation);
  await openSales(page);
  await invoiceList(page).getByRole('button', { name: 'Next' }).click();
  await expect(rows(page)).toHaveCount(1);

  await seed(page, { ...simulation, invoices: simulation.invoices.slice(0, 5) });
  await startDraft(page, 'River Isle Ventures · Account 296065');
  await expect(summary(page, 'Matching records')).toHaveText('6');
  await expect(rows(page)).toHaveCount(6);

  await seed(page, simulation);
  await startDraft(page, 'River Isle Ventures · Account 353072');
  await expect(summary(page, 'Matching records')).toHaveText('27');
  await expect(rows(page)).toHaveCount(25);
  await expect(invoiceList(page).getByRole('button', { name: 'Previous' })).toBeDisabled();
});

test('an unsaved edit stays on screen through switching accounts, and the invoice is what the preview shows', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await startDraft(page);
  await addLine(page, 'RCC-0100', '1');
  await draftSaved(page);
  const saves = salesApi('drafts/*');
  await page.route(saves, (route) => (route.request().method() === 'PUT' ? route.abort() : route.fallback()));
  await quantity(page, 'RCC-0100').fill('5');
  const notSaved = workspace(page).getByRole('alert').filter({ hasText: 'could not be saved' });
  await expect(notSaved).toBeVisible();
  await page.unroute(saves);

  // Issuing elsewhere marks every record out of date, so the next look at this draft refills it from the server.
  await startDraft(page, 'River Isle Ventures · Account 353072');
  await addLine(page, 'FBB-MIFI', '1');
  await draftSaved(page);
  await previewButton(page).click();
  await issueButton(page).click();
  await leaveDetail(page);
  const refilled = page.waitForResponse((response) => response.url().includes('/partner-sales/drafts?') && response.url().includes('296065'));
  await choosePartner(page, 'River Isle Ventures · Account 296065');
  await refilled;
  await choosePartner(page, 'River Isle Ventures · Account 353072');
  await choosePartner(page, 'River Isle Ventures · Account 296065');

  await expect(quantity(page, 'RCC-0100')).toHaveValue('5');
  await expect(notSaved).toBeVisible();
  await workspace(page).getByRole('button', { name: 'Try saving again' }).click();
  await draftSaved(page);
  await previewButton(page).click();
  await expect(preview(page)).toContainText('NGN 500.00');
  await issueButton(page).click();
  await expect(issuedInvoice(page, 'SIM-INV-0001')).toContainText('NGN 500.00');
});

test('Load latest on an invoice leaves a draft’s unsaved edits and warning alone', async ({ page }) => {
  await mockApi(page, { examples: true });
  await openSales(page);
  await startDraft(page);
  await addLine(page, 'RCC-0100', '1');
  await draftSaved(page);
  const saves = salesApi('drafts/*');
  await page.route(saves, (route) => (route.request().method() === 'PUT' ? route.abort() : route.fallback()));
  await quantity(page, 'RCC-0100').fill('5');
  const notSaved = workspace(page).getByRole('alert').filter({ hasText: 'could not be saved' });
  await expect(notSaved).toBeVisible();
  await page.unroute(saves);

  await invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0003' }).click();
  await expect(fact(issuedInvoice(page, 'SIM-INV-0003'), 'Status')).toHaveText('Unpaid');
  const recording = salesApi('invoices/*/collections');
  await page.route(recording, (route) => route.fulfill({ status: 409, headers: cors, json: { detail: 'Refused' } }));
  await recordCollection(page, '2026-06-10', '100', 'SIM-INV-0003');
  await loadLatest(page).click();
  await expect(fact(issuedInvoice(page, 'SIM-INV-0003'), 'Status')).toHaveText('Unpaid');
  await page.unroute(recording);
  await leaveDetail(page);

  await expect(quantity(page, 'RCC-0100')).toHaveValue('5');
  await expect(notSaved).toBeVisible();
});

test('a refusal stays visible through editing another account and further typing, and sends nothing more', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await startDraft(page);
  await addLine(page, 'FBB-5G-ROUTER', '2');
  await draftSaved(page);
  await editElsewhere(page, '296065', [{ product_code: 'RCC-0100', quantity: '9' }]);
  await quantity(page, 'FBB-5G-ROUTER').fill('3');
  await expect(refused(page)).toBeVisible();

  await startDraft(page, 'River Isle Ventures · Account 353072');
  await addLine(page, 'FBB-MIFI', '1');
  await draftSaved(page);
  await choosePartner(page, 'River Isle Ventures · Account 296065');
  await expect(refused(page)).toBeVisible();
  await expect(quantity(page, 'FBB-5G-ROUTER')).toHaveValue('3');

  const saveAttempts = [];
  page.on('request', (request) => { if (request.method() === 'PUT' && request.url().includes('/partner-sales/drafts/')) saveAttempts.push(request.url()); });
  await quantity(page, 'FBB-5G-ROUTER').fill('4');
  await expect(quantity(page, 'FBB-5G-ROUTER')).toHaveValue('4');
  await expect(refused(page)).toBeVisible();
  expect(saveAttempts).toEqual([]);
  expect((await draftOf(page, '296065')).lines).toEqual([{ product_code: 'RCC-0100', quantity: '9' }]);
});

test('a save whose response was lost is saved by retrying, not reported as someone else’s change', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await startDraft(page);
  await addLine(page, 'RCC-0100', '1');
  await draftSaved(page);
  const saves = salesApi('drafts/*');
  await page.route(saves, async (route) => {
    if (route.request().method() !== 'PUT') return route.fallback();
    await route.fetch();
    return route.abort();
  });
  await quantity(page, 'RCC-0100').fill('5');
  await expect(workspace(page).getByRole('alert').filter({ hasText: 'could not be saved' })).toBeVisible();
  await page.unroute(saves);

  await workspace(page).getByRole('button', { name: 'Try saving again' }).click();
  await draftSaved(page);
  await expect(refused(page)).toHaveCount(0);
  await quantity(page, 'RCC-0100').fill('6');
  await draftSaved(page);
  expect((await draftOf(page, '296065')).lines).toEqual([{ product_code: 'RCC-0100', quantity: '6' }]);
});

test('an amount being typed survives the invoice changing underneath it, and is then refused', async ({ page }) => {
  await mockApi(page, { examples: true });
  await openSales(page);
  await invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0002' }).click();
  await expect(history(page, 'SIM-INV-0002').locator('tbody tr')).toHaveCount(1);
  await collectionAmount(page, 'SIM-INV-0002').fill('100');
  await resetElsewhere(page);

  const reread = page.waitForResponse((response) => response.url().includes('/partner-sales/invoices/SIM-INV-0002') && response.url().includes('limit=50'));
  await collections(page, 'SIM-INV-0002').getByLabel('Rows per page').selectOption('50');
  await reread;
  await expect(collectionAmount(page, 'SIM-INV-0002')).toHaveValue('100');
  await recordButton(page, 'SIM-INV-0002').click();
  await expect(refused(page)).toBeVisible();
  await expect(collectionAmount(page, 'SIM-INV-0002')).toHaveValue('100');
});

test('a reset reaches another session on its next refresh', async ({ page, browser }) => {
  await mockApi(page, { examples: true });
  await openSales(page);
  await issueMixedInvoice(page, 'SIM-INV-0004');
  await leaveDetail(page);
  const session = await browser.newContext({ baseURL: 'http://localhost:5199' });
  const other = await session.newPage();
  await signIn(other);
  await routeReads(other);
  await openSales(other);
  await expect(matchingRecordCount(other)).toHaveText('4');

  await resetButton(page).click();
  await confirmReset(page).click();
  await expect(resetNotice(page)).toBeVisible();
  await other.reload();
  await expect(matchingRecordCount(other)).toHaveText('3');
  await session.close();
});

test('an invoice removed by a reset elsewhere is gone from the list after a refresh', async ({ page }) => {
  await mockApi(page, { examples: true });
  await openSales(page);
  await issueMixedInvoice(page, 'SIM-INV-0004');
  await collections(page, 'SIM-INV-0004').waitFor();
  await page.request.post(`${API_BASE}/partner-sales/reset`);
  await page.reload();
  await expect(invoiceRow(page, 'SIM-INV-0004')).toHaveCount(0);
  await expect(matchingRecordCount(page)).toHaveText('3');
});

// The rehearsal in docs/PARTNER_SALES_REHEARSAL.md. Opening 250,000.00 + earnings
// 954,922.38 - settlements 382,339.85 closes at 822,582.53, whatever the invoice does.
const RIVER_ISLE = 'River Isle Ventures · Account 296065';
const expectStatementUnchanged = async (page) => {
  await expect(statementFact(page, 'Opening outstanding')).toHaveText('NGN 250,000.00');
  await expect(statementFact(page, 'Period earnings')).toHaveText('NGN 954,922.38');
  await expect(statementFact(page, 'Period settlements')).toHaveText('NGN 382,339.85');
  await expect(statementFact(page, 'Closing outstanding')).toHaveText('NGN 822,582.53');
  await expect(commissionAccount(page).getByText('SIM-INV')).toHaveCount(0);
  await expect(commissionAccount(page).getByText('SIM-PAY')).toHaveCount(0);
};
const expectFictional = async (page) => {
  await expect(workspace(page).getByText('Fictional simulation using sample partner identities')).toBeVisible();
  await expect(page.getByRole('status').filter({ hasText: 'Synthetic demonstration' })).toBeVisible();
  await expect(page.getByText('Live Presto')).toHaveCount(0);
  await expect(workspace(page).getByRole('button', { name: /offset|net balance|from commission|reserve|stock/i })).toHaveCount(0);
  await expect(workspace(page).getByText(/net balance|commission wallet|reserved stock|available stock/i)).toHaveCount(0);
};
// Actions move focus on the next frame. Waiting for it keeps the next key press from
// racing that move, which a person at a keyboard never does.
const pressOn = async (page, locator, key) => {
  await locator.focus();
  await page.keyboard.press(key);
  await page.evaluate(() => new Promise((resolve) => { requestAnimationFrame(resolve); }));
};
const pressEnter = (page, locator) => pressOn(page, locator, 'Enter');
const pressSpace = (page, locator) => pressOn(page, locator, 'Space');
const clickWithPointer = (_page, locator) => locator.click();
// Returning moves focus on the next frame, which would otherwise take the keys of whatever acts next.
async function leaveDetail(page) {
  await back(page).click();
  await page.evaluate(() => new Promise((settled) => requestAnimationFrame(() => requestAnimationFrame(settled))));
}
const noOverflow = (page) => workspace(page).evaluate((scroller) => [scroller.scrollWidth - scroller.clientWidth, document.documentElement.scrollWidth - document.documentElement.clientWidth]);

async function createAndCollect(page, act) {
  await act(page, workspace(page).getByRole('button', { name: 'Create draft' }));
  for (const [code, units] of [['FBB-5G-ROUTER', '2'], ['RCC-0100', '100']]) {
    await act(page, add(page, code));
    await expect(quantity(page, code)).toBeFocused();
    await quantity(page, code).fill(units);
  }
  await expect(draftTotal(page)).toContainText('NGN 110,000.00');
  await act(page, previewButton(page));
  await expect(preview(page).getByRole('heading', { name: 'Simulated invoice preview' })).toBeFocused();
  await expect(preview(page).getByRole('row', { name: /Total.*NGN 110,000\.00/ })).toBeVisible();
  await act(page, issueButton(page));

  const invoice = issuedInvoice(page, 'SIM-INV-0004');
  await expect(invoice.getByRole('heading', { level: 2 })).toBeFocused();
  await expect(fact(invoice, 'Status')).toHaveText('Unpaid');
  await expectFictional(page);

  await collectionAmount(page, 'SIM-INV-0004').fill('40000');
  await act(page, recordButton(page, 'SIM-INV-0004'));
  await expect(fact(invoice, 'Status')).toHaveText('Partially paid');
  await expect(fact(invoice, 'Outstanding as of 31 May 2026')).toHaveText('NGN 70,000.00');

  // A refresh keeps the obligation and returns to the list, where it can be reopened.
  await page.reload();
  await expect(invoiceRow(page, 'SIM-INV-0004')).toContainText('Partially paid');
  await expect(workspace(page).getByRole('radio', { name: RIVER_ISLE })).toBeChecked();
  await act(page, invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0004' }));
  await expect(invoice.getByRole('heading', { level: 2 })).toBeFocused();
  await expect(fact(invoice, 'Outstanding as of 31 May 2026')).toHaveText('NGN 70,000.00');

  await collectionAmount(page, 'SIM-INV-0004').fill('70000');
  await act(page, recordButton(page, 'SIM-INV-0004'));
  await expect(fact(invoice, 'Status')).toHaveText('Paid');
  await expect(fact(invoice, 'Collected')).toHaveText('NGN 110,000.00');
  await expect(fact(invoice, 'Outstanding as of 31 May 2026')).toHaveText('NGN 0.00');
  const rows = history(page, 'SIM-INV-0004').getByRole('row');
  await expect(rows.filter({ hasText: 'SIM-PAY-0003' })).toContainText('NGN 70,000.00');
  await expect(rows.filter({ hasText: 'SIM-PAY-0004' })).toContainText('NGN 0.00');
  await expectFictional(page);
}

async function runPresentation(page, act, keyboard = false) {
  const partner = workspace(page).getByRole('radio', { name: RIVER_ISLE });
  if (keyboard) await pressSpace(page, partner);
  else await partner.check();
  await expect(partner).toBeChecked();
  await createAndCollect(page, act);

  const invoice = issuedInvoice(page, 'SIM-INV-0004');
  await act(page, invoice.getByRole('button', { name: `View purchase obligations for ${RIVER_ISLE}` }));
  const obligations = workspace(page).getByRole('region', { name: /^Purchase obligations/ });
  await expect(obligations.getByRole('button', { name: /^Open invoice/ })).toHaveCount(1);
  await expect(obligations.getByRole('button', { name: 'Open invoice SIM-INV-0004' })).toBeVisible();
  await act(page, workspace(page).getByRole('button', { name: `View commission account for ${RIVER_ISLE}` }));
  await expect(commissionAccount(page).getByRole('heading', { level: 2 })).toBeFocused();
  await expectStatementUnchanged(page);
  await expectFictional(page);

  for (const name of ['Explain activation commission', 'Explain subscription commission', 'Explain settlement']) {
    await act(page, explanationLink(page, name));
    await expect(page.getByText(`Opened from the Partner Sales simulation for exact account 296065, May 2026.`)).toBeVisible();
    await expect(page.getByText('This workspace shows existing evidence, not the fictional statement.')).toBeVisible();
    await expect(page.getByRole('combobox', { name: /Reporting period/ }).first()).toHaveValue('202605');
    // The explanation takes focus once its detail opens, so let that land first.
    await expect(page.getByRole('main').locator(':focus')).toHaveCount(1);
    await act(page, returnToSales(page));
    await expect(explanationLink(page, name)).toBeFocused();
    await expectStatementUnchanged(page);
  }

  // The return entry names the account, so a refresh here still lands on it.
  await page.reload();
  await expect(commissionAccount(page)).toBeVisible();
  await expectStatementUnchanged(page);
  await act(page, commissionAccount(page).getByRole('button', { name: 'Back to invoices' }));

  const status = invoiceList(page).getByRole('combobox', { name: 'Status' });
  if (keyboard) {
    await status.focus();
    await page.keyboard.type('Pai');
  } else await status.selectOption('Paid');
  await expect(status).toHaveValue('Paid');
  await expect(invoiceRow(page, 'SIM-INV-0004')).toContainText('NGN 110,000.00');
  await expect(fact(invoiceList(page), 'Outstanding purchase obligation')).toHaveText('NGN 0.00');
  const opener = invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0004' });
  await act(page, opener);
  await act(page, issuedInvoice(page, 'SIM-INV-0004').getByRole('button', { name: 'Back to invoices' }));
  await expect(opener).toBeFocused();
  await expect(invoiceList(page).getByRole('combobox', { name: 'Status' })).toHaveValue('Paid');
  await expectFictional(page);
}

const resetBy = async (page, act) => {
  await act(page, resetButton(page));
  await act(page, confirmReset(page));
  await expect(resetNotice(page)).toBeFocused();
  await expect(matchingRecordCount(page)).toHaveText('3');
};

test('the complete presentation replays identically after a reset, with no writes beyond the simulation or agent calls', async ({ page }) => {
  const { mutations, requests } = await mockApi(page, { reads: explanationReads([]), examples: true });
  await openSales(page);
  await runPresentation(page, clickWithPointer);
  await resetBy(page, clickWithPointer);
  await runPresentation(page, clickWithPointer);
  expect(mutations).toEqual([]);
  expect(requests.filter((path) => path.includes('chat'))).toEqual([]);
});

test('the complete presentation works by keyboard on a narrow screen', async ({ page }) => {
  const { mutations } = await mockApi(page, { reads: explanationReads([]), examples: true });
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto('/?period=202605&view=partner-sales');
  await expect(workspace(page)).toBeVisible();
  await runPresentation(page, pressEnter, true);
  expect(await noOverflow(page)).toEqual([0, 0]);

  // Reached and operated by Tab alone, from the top of the workspace.
  await workspace(page).getByRole('heading', { name: 'Partner Sales', level: 1 }).focus();
  await page.keyboard.press('Tab');
  await expect(resetButton(page)).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(resetPanel(page).getByRole('button', { name: 'Keep simulation' })).toBeFocused();
  expect(await noOverflow(page)).toEqual([0, 0]);
  await page.keyboard.press('Shift+Tab');
  await expect(confirmReset(page)).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(resetNotice(page)).toBeFocused();
  expect(await noOverflow(page)).toEqual([0, 0]);
  expect(mutations).toEqual([]);
});

test('in live-read mode the invoice story runs, stays fictional and asks live sources nothing', async ({ page }) => {
  const { mutations, requests } = await mockApi(page, { health: { sample_data_mode: false }, reads: statementRead(), examples: true });
  await openSales(page);
  await choosePartner(page, RIVER_ISLE);
  await createAndCollect(page, clickWithPointer);
  await issuedInvoice(page, 'SIM-INV-0004').getByRole('button', { name: `View purchase obligations for ${RIVER_ISLE}` }).click();
  await workspace(page).getByRole('button', { name: `View commission account for ${RIVER_ISLE}` }).click();
  await expectStatementUnchanged(page);
  await expect(evidenceLinks(page)).toContainText('reading live data');
  await expect(evidenceLinks(page).getByRole('button')).toHaveCount(0);
  await expectFictional(page);
  await resetBy(page, clickWithPointer);
  await expectFictional(page);
  expect(requests.filter((path) => path.startsWith('/dealers') || path.startsWith('/commissions') || path.startsWith('/payments') || path.includes('chat'))).toEqual([]);
  expect(mutations).toEqual([]);
});

test('an explanation whose evidence fails stays on the exact account and can return or retry', async ({ page }) => {
  let failing = true;
  const reads = explanationReads([]);
  await mockApi(page, { reads: (pathname, params) => (failing && pathname === '/commissions/296065/detail' && params.get('stream') === 'activation' ? { status: 503, json: { detail: 'Unavailable' } } : reads(pathname, params)) });
  await openSales(page);
  await openCommissionAccount(page, RIVER_ISLE);
  await explanationLink(page, 'Explain activation commission').click();

  const commission = page.getByRole('main', { name: 'Commission intelligence' });
  await expect(page.getByText('Opened from the Partner Sales simulation for exact account 296065, May 2026.')).toBeVisible();
  await expect(commission.getByRole('alert').filter({ hasText: 'Requested account unavailable' })).toBeVisible();
  await expect(commission.getByRole('heading', { name: 'River Isle Ventures' })).toHaveCount(0);
  failing = false;
  await commission.getByRole('button', { name: 'Retry account' }).click();
  await expect(commission.getByRole('heading', { name: 'River Isle Ventures' })).toBeVisible();
  await returnToSales(page).click();
  await expect(explanationLink(page, 'Explain activation commission')).toBeFocused();
  await expectStatementUnchanged(page);
});

test('a simulation survives reporting periods being unavailable, and returns once a reload succeeds', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await buildMixedDraft(page);
  await page.route(`${API_BASE}/periods`, (route) => route.fulfill({ status: 503, headers: cors, json: { detail: 'Unavailable' } }));
  await page.reload();
  await expect(page.getByText('Reporting periods unavailable. Reload to retry.')).toBeVisible();
  await page.unroute(`${API_BASE}/periods`);
  await page.reload();
  await expectRestoredDraft(page);
});

test('a settlement explanation whose evidence fails stays on the exact account and can retry or return', async ({ page }) => {
  let failing = true;
  const reads = explanationReads([]);
  await mockApi(page, { reads: (pathname, params) => (failing && pathname === '/payments/accounts/296065' ? { status: 503, json: { detail: 'Unavailable' } } : reads(pathname, params)) });
  await openSales(page);
  await openCommissionAccount(page, RIVER_ISLE);
  await explanationLink(page, 'Explain settlement').click();

  await expect(page.getByText('Opened from the Partner Sales simulation for exact account 296065, May 2026.')).toBeVisible();
  const payments = page.getByRole('main').filter({ hasText: 'Payment Intelligence' });
  await expect(payments.getByRole('heading', { name: 'Account 296065' })).toBeVisible();
  await expect(payments.getByRole('alert').filter({ hasText: 'Payment position unavailable' })).toBeVisible();
  await expect(payments.getByRole('heading', { name: 'River Isle Ventures' })).toHaveCount(0);
  failing = false;
  await payments.getByRole('button', { name: 'Retry payment' }).click();
  await expect(payments.getByRole('heading', { name: 'River Isle Ventures' })).toBeVisible();
  await returnToSales(page).click();
  await expect(explanationLink(page, 'Explain settlement')).toBeFocused();
});

test('invoice filters survive an explanation handoff and its return', async ({ page }) => {
  await mockApi(page, { reads: explanationReads([]) });
  await openSales(page);
  await issueMixedInvoice(page);
  await leaveDetail(page);
  await invoiceList(page).getByRole('combobox', { name: 'Status' }).selectOption('Unpaid');
  await invoiceList(page).getByRole('searchbox', { name: 'Search invoices by partner or account code' }).fill('296065');

  await workspace(page).getByRole('button', { name: `View commission account for ${RIVER_ISLE}` }).click();
  await explanationLink(page, 'Explain settlement').click();
  await returnToSales(page).click();
  await commissionAccount(page).getByRole('button', { name: 'Back to invoices' }).click();

  await expect(invoiceList(page).getByRole('combobox', { name: 'Status' })).toHaveValue('Unpaid');
  await expect(invoiceList(page).getByRole('searchbox', { name: 'Search invoices by partner or account code' })).toHaveValue('296065');
  await expect(invoiceRow(page, 'SIM-INV-0001')).toContainText('Unpaid');
});
