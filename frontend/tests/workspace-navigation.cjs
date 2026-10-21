// Run against the existing sample-mode dev servers with Playwright available
// through PLAYWRIGHT_MODULE or NODE_PATH. Uses an isolated Chrome profile; blocks provider/write paths.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const origin = process.env.FRONTEND_URL || 'http://localhost:5173';

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.setDefaultTimeout(15000);
    const errors = [], requests = [], resources = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      resources.push(request.url());
      if (request.url().includes('localhost:8000')) requests.push(new URL(request.url()));
    });
    await page.route('http://localhost:8000/**', async route => {
      if (route.request().method() !== 'GET') return route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Provider calls blocked by navigation regression"}' });
      if (new URL(route.request().url()).pathname === '/periods') await new Promise(resolve => setTimeout(resolve, 300));
      return route.continue();
    });
    const nav = name => page.getByRole('navigation', { name: 'Workspace' }).getByRole('button', { name, exact: true }).click();
    const settle = async () => { await page.waitForTimeout(400); await page.waitForLoadState('networkidle'); };
    const month = value => page.getByRole('combobox', { name: /Reporting period/ }).selectOption(value);
    const commission = page.getByRole('main', { name: 'Commission intelligence' });

    await page.goto(`${origin}/?view=commission&period=202603`);
    const first = page.getByRole('button', { name: /View breakdown for account/ }).first();
    await first.waitFor();
    assert(requests.filter(url => url.pathname === '/commissions').every(url => url.searchParams.get('prior_period') === '202602'), 'Initial Commission reads must wait for period metadata');
    assert(!resources.some(url => /\/CommissionAssistant(?:-|\.)/.test(url)), 'Atlas code is deferred until its section is mounted');
    const dealer = (await first.getAttribute('aria-label')).match(/account (.+)/)[1];
    await commission.getByPlaceholder('Dealer name or account code').fill(dealer);
    await settle();
    await commission.getByRole('combobox', { name: /Compare/ }).selectOption('');
    await settle();
    await page.getByRole('button', { name: `View breakdown for account ${dealer}` }).click();
    await commission.getByRole('button', { name: /Back to accounts/ }).waitFor();
    await nav('Payments');
    await settle();
    requests.length = 0;
    await month('202604');
    await settle();
    assert(requests.some(url => url.pathname === '/payments' && url.searchParams.get('mon_period') === '202604'), 'Visible workspace must read the new month');
    assert(!requests.some(url => url.pathname.startsWith('/commissions')), 'Hidden Commission must not fetch on month changes');
    console.log('Visible Payments month-change reads:', requests.map(url => url.pathname + url.search));
    await nav('Commission');
    await settle();
    assert(await commission.getByRole('button', { name: /Back to accounts/ }).isVisible(), 'Selected dealer survives returning in another month');
    assert((await commission.innerText()).includes(`Account ${dealer}`));
    assert.equal(await commission.getByRole('combobox', { name: /Compare/ }).inputValue(), '', 'Explicit no-comparison choice survives');
    assert(requests.some(url => url.pathname.includes(`/commissions/${dealer}`) && url.searchParams.get('mon_period') === '202604'), 'Returned detail reads the current month');
    await commission.getByRole('button', { name: /Back to accounts/ }).click();
    assert.equal(await commission.getByPlaceholder('Dealer name or account code').inputValue(), dealer);
    await page.goBack(); await settle();
    assert(await page.getByRole('main', { name: 'Payment intelligence' }).isVisible());
    await page.goForward(); await settle();
    assert.equal(await commission.getByPlaceholder('Dealer name or account code').inputValue(), dealer);

    // First-visit code loads must not replace a visible workspace with a hidden
    // sibling's Suspense fallback when navigation overtakes the import.
    await page.route(/\/FinancialHealthWorkspace(?:-[^/]+\.js|\.jsx)(?:\?|$)/, async route => {
      await new Promise(resolve => setTimeout(resolve, 400)); await route.continue();
    });
    await nav('Financial Health'); await nav('Commission');
    assert(await commission.isVisible());
    assert.equal(await page.getByText('Loading workspace…', { exact: true }).filter({ visible: true }).count(), 0);
    await settle();

    await nav('Inventory'); await settle();
    const inventory = page.getByRole('main', { name: 'Inventory intelligence' });
    const inventoryButton = inventory.getByRole('button', { name: /View evidence for dealer/ }).first();
    await inventoryButton.click();
    await inventory.getByRole('button', { name: /Ask Atlas about this comparison/ }).click();
    await page.getByRole('region', { name: /Atlas/ }).waitFor();
    assert(new URL(page.url()).searchParams.get('view') === 'commission');
    await nav('Inventory'); await settle();
    assert(await inventory.getByRole('button', { name: /Back to comparison/ }).isVisible());
    await nav('Payments'); await month('202605'); await settle();
    requests.length = 0;
    await nav('Inventory'); await settle();
    assert(requests.some(url => url.pathname === '/inventory/comparison-page' && url.searchParams.get('mon_period') === '202605'));
    assert(await inventory.getByRole('button', { name: /Back to comparison/ }).isVisible());
    await nav('Overview'); await settle();
    const overview = page.getByRole('main');
    const evidence = page.getByRole('button', { name: /View commission evidence for dealer/ }).first();
    await evidence.click(); await settle();
    await page.getByRole('button', { name: /Open this audit in workspace/ }).click();
    await page.getByRole('heading', { name: /Saved evidence/ }).waitFor();
    await page.getByRole('button', { name: /Return to investigation/ }).click();
    await settle();
    assert.equal(new URL(page.url()).searchParams.get('view'), 'overview');
    assert(await page.getByRole('button', { name: /Open this audit in workspace/ }).isVisible(), 'Audit return preserves expanded investigation');
    await nav('Payments'); await settle(); requests.length = 0;
    await month('202606'); await settle();
    assert(!requests.some(url => ['/overview', '/audit/records', '/commissions', '/inventory/comparison-page', '/financial-health'].includes(url.pathname)), 'All hidden workspace reads remain disabled');
    assert.equal(errors.length, 0, errors.join('\n'));
    // A failed optional Atlas chunk leaves the ledger and workspace navigation usable.
    const failure = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    await failure.route(/\/CommissionAssistant(?:-[^/]+\.js|\.jsx)(?:\?|$)/, route => route.abort());
    await failure.goto(`${origin}/?view=commission&period=202603`);
    await failure.getByRole('button', { name: /View breakdown for account/ }).first().waitFor();
    await failure.getByRole('button', { name: 'Ask Atlas', exact: true }).click();
    await failure.getByRole('alert').filter({ hasText: 'Atlas could not load' }).waitFor();
    assert(await failure.getByRole('region', { name: 'Dealer accounts', exact: true }).isVisible());
    await failure.close();
    console.log('PASS: audit return, hidden workspace suppression, failed optional chunk, initial comparison gate, hidden reads, dealer/filter continuity, no comparison, back/forward, hidden fallback, inventory refresh and Atlas handoff');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
