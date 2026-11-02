// Partner Sales simulation at the rendered workspace boundary. Backend reads
// are fixtures; any non-GET request is recorded so the suite can prove the
// simulation issues no financial mutations.
import { expect, test } from '@playwright/test';

const API = 'http://localhost:8000/**';
const cors = { 'access-control-allow-origin': '*' };

async function mockApi(page, { health = { sample_data_mode: true }, periods = ['202606', '202605'] } = {}) {
  const mutations = [];
  const requests = [];
  await page.route(API, async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    requests.push(pathname);
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { ...cors, 'access-control-allow-headers': '*' } });
    if (request.method() !== 'GET') {
      mutations.push(`${request.method()} ${pathname}`);
      return route.fulfill({ status: 503, headers: cors, json: { detail: 'Blocked by acceptance test' } });
    }
    if (pathname === '/periods') return periods ? route.fulfill({ headers: cors, json: { periods } }) : route.fulfill({ status: 503, headers: cors, json: { detail: 'Unavailable' } });
    if (pathname === '/health') return route.fulfill({ headers: cors, json: health });
    return route.fulfill({ status: 503, headers: cors, json: { detail: 'Unavailable in acceptance fixture' } });
  });
  return { mutations, requests };
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
};

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

test('drafts survive workspace navigation and same-tab refresh, per month and per tab', async ({ page, context }) => {
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

  // Session scope: another tab starts without this tab's drafts.
  const other = await context.newPage();
  await mockApi(other);
  await openSales(other);
  await expect(workspace(other).getByText('Select a trade partner to create a draft.')).toBeVisible();
  await other.close();
});

test('shows when the draft cannot be saved, keeps working and recovers on retry', async ({ page }) => {
  await page.addInitScript(() => {
    const setItem = Storage.prototype.setItem;
    window.__failWrites = true;
    Storage.prototype.setItem = function (...args) {
      if (this === window.sessionStorage && window.__failWrites) throw new DOMException('Full', 'QuotaExceededError');
      return setItem.apply(this, args);
    };
  });
  await mockApi(page);
  await openSales(page);
  await choosePartner(page, 'River Isle Ventures · Account 296065');

  const alert = workspace(page).getByRole('alert');
  await expect(alert).toContainText('could not be saved');
  await workspace(page).getByRole('button', { name: 'Create draft' }).click();
  await addLine(page, 'FBB-5G-ROUTER', '2');
  await expect(draftTotal(page)).toContainText('NGN 100,000.00');

  await workspace(page).getByRole('button', { name: 'Try saving again' }).click();
  await expect(alert).toContainText('could not be saved');
  await page.evaluate(() => { window.__failWrites = false; });
  await workspace(page).getByRole('button', { name: 'Try saving again' }).click();
  await expect(alert).toHaveCount(0);
  await page.reload();
  await expect(quantity(page, 'FBB-5G-ROUTER')).toHaveValue('2');
});

test('shows when session storage cannot be read and still works in this page', async ({ page }) => {
  await page.addInitScript(() => {
    Storage.prototype.getItem = function () { throw new DOMException('Denied', 'SecurityError'); };
    Storage.prototype.setItem = function () { throw new DOMException('Denied', 'SecurityError'); };
  });
  await mockApi(page);
  await openSales(page);
  await expect(workspace(page).getByRole('alert')).toContainText('could not be saved');
  await startDraft(page);
  await addLine(page, 'RCC-0100', '100');
  await expect(draftTotal(page)).toContainText('NGN 10,000.00');
});

for (const [label, saved] of [
  ['unreadable', 'not json'],
  ['from another version', '{"version":999}'],
  ['naming an unknown product', '{"version":3,"nextSequence":2,"nextCollectionSequence":1,"partnerCode":"296065","invoices":[],"collections":[],"drafts":{"296065|202605":{"reference":"SIM-INV-0001","partnerCode":"296065","period":"202605","issueDate":"2026-05-31","dueDate":"","lines":[{"productCode":"NOPE","quantity":"1"}]}}}'],
]) {
  test(`offers recovery when the saved simulation is ${label}`, async ({ page }) => {
    await mockApi(page);
    await openSales(page);
    await buildMixedDraft(page);
    await page.evaluate((value) => {
      for (let i = 0; i < sessionStorage.length; i++) sessionStorage.setItem(sessionStorage.key(i), value);
    }, saved);
    await page.reload();

    await expect(workspace(page).getByRole('alert')).toContainText('could not be restored');
    await expect(workspace(page).getByRole('radio')).toHaveCount(0);
    await workspace(page).getByRole('button', { name: 'Start a new simulation' }).click();
    await expect(workspace(page).getByRole('alert')).toHaveCount(0);
    await expect(workspace(page).getByText('Select a trade partner to create a draft.')).toBeVisible();
    await startDraft(page);
    await expect(workspace(page).getByText('SIM-INV-0001 · May 2026')).toBeVisible();
  });
}

test('completes draft, correction and preview in live-read mode without any backend request', async ({ page }) => {
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

  await back(page).click();
  await expect(invoiceRow(page, 'SIM-INV-0001')).toContainText('Unpaid');
  await expect(workspace(page).getByText('No draft for River Isle Ventures · Account 296065 in May 2026.')).toBeVisible();
});

const issueMixedInvoice = async (page) => {
  await buildMixedDraft(page);
  await previewButton(page).click();
  await issueButton(page).click();
  await expect(issuedInvoice(page, 'SIM-INV-0001').getByRole('heading', { name: 'Simulated invoice SIM-INV-0001' })).toBeFocused();
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
  await back(page).click();

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

  await back(page).click();
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
    seller: 'MTN',
    buyer,
    period: issueDate.slice(0, 7).replace('-', ''),
    issueDate,
    dueDate: '',
    currency: 'NGN',
    lines: [{ productCode: 'RCC-0100', description: 'Fictional NGN 100 physical recharge card', unit: 'card', quantity: 1, unitPriceMinor: 10000, lineTotalMinor: 10000 }],
    totalMinor: 10000,
  };
};
const seed = (page, simulation) => page.addInitScript((saved) => {
  sessionStorage.setItem('fbb.partner-sales.simulation', JSON.stringify(saved));
}, simulation);
const seededSimulation = () => ({
  version: 3,
  nextSequence: 208,
  nextCollectionSequence: 1,
  collections: [],
  partnerCode: '',
  drafts: { '296065|202605': { reference: 'SIM-INV-0207', partnerCode: '296065', period: '202605', issueDate: '2026-05-31', dueDate: '', lines: [{ productCode: 'FBB-5G-ROUTER', quantity: '1' }] } },
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
  expect(await firstReferences(page, 3)).toEqual(['SIM-INV-0207', 'SIM-INV-0205', 'SIM-INV-0204']);

  await invoiceList(page).getByRole('button', { name: 'Next' }).click();
  await expectWholeSet();
  // Row 26 of 207, 205, 204, ... is 206 - 25.
  expect(await firstReferences(page, 1)).toEqual(['SIM-INV-0181']);
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
  expect(await firstReferences(page, 1)).toEqual(['SIM-INV-0204']);
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
  expect(await firstReferences(page, 1)).toEqual(['SIM-INV-0181']);
  await invoiceList(page).getByRole('searchbox').fill('no such partner');
  await invoiceList(page).getByRole('button', { name: 'Clear filters' }).click();
  await expect(rows(page)).toHaveCount(25);
  expect(await firstReferences(page, 1)).toEqual(['SIM-INV-0207']);

  await next.click();
  await period(page).selectOption('202606');
  await expect(summary(page, 'Matching records')).toHaveText('1');
  await period(page).selectOption('202605');
  await expect(summary(page, 'Matching records')).toHaveText('206');
  expect(await firstReferences(page, 1)).toEqual(['SIM-INV-0207']);
});

test('a filter that shrinks the set shows its rows rather than an empty page, and labels draft dates as intended', async ({ page }) => {
  await mockApi(page);
  const simulation = seededSimulation();
  // One draft plus 25 May invoices fills page 1 and spills one row onto page 2.
  simulation.invoices = simulation.invoices.slice(0, 25);
  simulation.nextSequence = 208;
  await seed(page, simulation);
  await openSales(page);
  await expect(summary(page, 'Matching records')).toHaveText('26');
  await invoiceList(page).getByRole('button', { name: 'Next' }).click();
  await expect(rows(page)).toHaveCount(1);

  // The draft alone cannot fill a second page.
  await invoiceList(page).getByLabel('Status').selectOption('Draft');
  await expect(rows(page)).toHaveCount(1);
  expect(await firstReferences(page, 1)).toEqual(['SIM-INV-0207']);
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
  expect(await firstReferences(page, 1)).toEqual(['SIM-INV-0155']);

  const opener = invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0153' });
  await opener.click();
  await expect(issuedInvoice(page, 'SIM-INV-0153').getByRole('heading', { name: 'Simulated invoice SIM-INV-0153' })).toBeFocused();
  await expect(invoiceList(page)).toBeHidden();
  await workspace(page).getByRole('button', { name: 'Back to invoices' }).click();

  await expect(opener).toBeFocused();
  await expect(invoiceList(page).getByRole('searchbox')).toHaveValue('river isle');
  await expect(invoiceList(page).getByLabel('Status')).toHaveValue('Unpaid');
  expect(await firstReferences(page, 1)).toEqual(['SIM-INV-0155']);

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
  expect(await firstReferences(page, 1)).toEqual(['SIM-INV-0155']);
});

test('partner detail isolates the exact account and keeps obligations apart from commission and drafts', async ({ page }) => {
  await mockApi(page);
  await openSales(page);
  await issueMixedInvoice(page);
  await back(page).click();

  // Same-name account: nothing issued, so no balance to show.
  await choosePartner(page, 'River Isle Ventures · Account 353072');
  await workspace(page).getByRole('button', { name: 'Create draft' }).click();
  await addLine(page, 'RCC-0100', '1');
  await workspace(page).getByRole('button', { name: 'View purchase obligations for River Isle Ventures · Account 353072', exact: true }).click();
  const other = workspace(page).getByRole('region', { name: 'Purchase obligations for River Isle Ventures · Account 353072' });
  await expect(other).toContainText('No issued invoices for this account');
  await expect(other).not.toContainText('SIM-INV-0001');
  await expect(other.getByRole('list', { name: 'Drafts excluded from outstanding' })).toContainText('SIM-INV-0002 · intended May 2026 · NGN 100.00');
  await back(page).click();

  // A June invoice on the first account: its balance spans issue months.
  await choosePartner(page, 'River Isle Ventures · Account 296065');
  await period(page).selectOption('202606');
  await workspace(page).getByRole('button', { name: 'Create draft' }).click();
  await addLine(page, 'FBB-MIFI', '3');
  await previewButton(page).click();
  await issueButton(page).click();
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

test('issues and browses in live-read mode without any backend request', async ({ page }) => {
  const { mutations, requests } = await mockApi(page, { health: { sample_data_mode: false } });
  await page.goto('/?view=partner-sales&period=202605');
  await expect(page.getByRole('status').filter({ hasText: 'Synthetic demonstration' })).toBeVisible();
  await page.waitForLoadState('networkidle');
  requests.length = 0;

  await issueMixedInvoice(page);
  await expect(issuedInvoice(page, 'SIM-INV-0001')).toContainText('Fictional simulation');
  await back(page).click();
  await invoiceList(page).getByRole('searchbox').fill('296065');
  await invoiceList(page).getByRole('button', { name: /^View purchase obligations/ }).click();
  await expect(workspace(page).getByRole('region', { name: /^Purchase obligations/ })).toContainText('Fictional simulation');
  await page.waitForTimeout(200);

  expect(requests).toEqual([]);
  expect(mutations).toEqual([]);
});

test('issuing still works when the simulation cannot be saved, and says so', async ({ page }) => {
  await page.addInitScript(() => {
    Storage.prototype.setItem = function () { throw new DOMException('Full', 'QuotaExceededError'); };
  });
  await mockApi(page);
  await openSales(page);
  await issueMixedInvoice(page);
  await expect(workspace(page).getByRole('alert')).toContainText('could not be saved');
  await expect(fact(issuedInvoice(page, 'SIM-INV-0001'), 'Status')).toHaveText('Unpaid');
});

for (const [label, change] of [
  ['whose total does not reconcile with its lines', (saved) => { saved.invoices[0].totalMinor += 1; }],
  ['whose reference the next draft would reuse', (saved) => { saved.nextSequence = 1; }],
  ['issued and still drafted under one reference', (saved) => { saved.drafts['74050|202605'] = { reference: saved.invoices[0].reference, partnerCode: '74050', period: '202605', issueDate: '', dueDate: '', lines: [] }; }],
]) {
  test(`offers recovery from a saved invoice ${label}`, async ({ page }) => {
    await mockApi(page);
    await openSales(page);
    await issueMixedInvoice(page);
    await page.evaluate((source) => {
      const key = sessionStorage.key(0);
      const saved = JSON.parse(sessionStorage.getItem(key));
      new Function('saved', `(${source})(saved)`)(saved);
      sessionStorage.setItem(key, JSON.stringify(saved));
    }, change.toString());
    await page.reload();
    await expect(workspace(page).getByRole('alert')).toContainText('could not be restored');
    await expect(invoiceList(page)).toHaveCount(0);
  });
}

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
    await back(page).click();
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

test('rejects a five-digit collection year, so the saved simulation still restores', async ({ page }) => {
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
  await back(page).click();
  await startDraft(page, 'River Isle Ventures · Account 353072');
  await addLine(page, 'RCC-0100', '1');
  await previewButton(page).click();
  await issueButton(page).click();
  await expect(issuedInvoice(page, 'SIM-INV-0002')).toBeVisible();
  await back(page).click();

  await invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0001' }).click();
  await recordCollection(page, '2026-06-10', '40000');
  await back(page).click();

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
    await back(page).click();
  };

  await back(page).click();
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
  await back(page).click();
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
  await back(page).click();

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
  simulation.nextCollectionSequence = 31;
  simulation.collections = Array.from({ length: 30 }, (_, index) => ({ actionId: `seeded-${index}`, reference: `SIM-PAY-${String(index + 1).padStart(4, '0')}`, invoiceReference: 'SIM-INV-0001', date: '2026-06-01', amountMinor: 100 }));
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
  await back(page).click();

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
  await back(page).click();
  await invoiceList(page).getByRole('searchbox').fill('74050');
  await invoiceList(page).getByRole('button', { name: 'Open invoice SIM-INV-0204' }).click();
  await expect(fact(issuedInvoice(page, 'SIM-INV-0204'), 'Status')).toHaveText('Unpaid');
  await expect(collections(page, 'SIM-INV-0204')).toContainText('No collections recorded');
});

test('collects in live-read mode without any backend request, and says commission is unaffected', async ({ page }) => {
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

for (const [label, change] of [
  ['that overpays its invoice', (saved) => { saved.collections[0].amountMinor = saved.invoices[0].totalMinor + 1; }],
  ['dated before its invoice was issued', (saved) => { saved.collections[0].date = '2026-05-30'; }],
  ['that names no issued invoice', (saved) => { saved.collections[0].invoiceReference = 'SIM-INV-9999'; }],
  ['whose amount is not positive', (saved) => { saved.collections[0].amountMinor = 0; }],
  ['whose reference the next collection would reuse', (saved) => { saved.nextCollectionSequence = 1; }],
  ['repeating an action', (saved) => { saved.nextCollectionSequence = 3; saved.collections.push({ ...saved.collections[0], reference: 'SIM-PAY-0002', amountMinor: 1 }); }],
]) {
  test(`offers recovery from a saved collection ${label}`, async ({ page }) => {
    await mockApi(page);
    await openSales(page);
    await issueMixedInvoice(page);
    await recordCollection(page, '2026-06-10', '40000');
    await page.evaluate((source) => {
      const key = sessionStorage.key(0);
      const saved = JSON.parse(sessionStorage.getItem(key));
      new Function('saved', `(${source})(saved)`)(saved);
      sessionStorage.setItem(key, JSON.stringify(saved));
    }, change.toString());
    await page.reload();
    await expect(workspace(page).getByRole('alert')).toContainText('could not be restored');
    await expect(invoiceList(page)).toHaveCount(0);
  });
}

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
    await back(page).click();
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
