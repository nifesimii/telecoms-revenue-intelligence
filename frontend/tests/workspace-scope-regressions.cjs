// Isolated, read-only browser checks for retained workspaces across month changes.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const origin = process.env.FRONTEND_URL || 'http://localhost:5173';
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const failures = [];
  async function check(name, test) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.setDefaultTimeout(15000);
    const errors = [], writes = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('http://localhost:8000/**', route => {
      if (route.request().method() === 'GET') return route.continue();
      writes.push(route.request().url());
      return route.fulfill({ status: 503, body: 'Writes and providers blocked by regression' });
    });
    try {
      await test(page);
      assert.deepEqual(errors, []); assert.deepEqual(writes, []);
      console.log(`PASS: ${name}`);
    } catch (error) { failures.push(name); console.error(`FAIL: ${name}: ${error.message}`); }
    finally { await page.close(); }
  }
  const month = (page, period) => page.getByRole('combobox', { name: /Reporting period/ }).selectOption(period);
  const settle = async page => { await page.waitForTimeout(400); await page.waitForLoadState('networkidle'); };
  try {
    await check('audit acknowledgement is scoped to module and period without writes', async page => {
      await page.goto(`${origin}/?view=audit&period=202603`);
      await page.getByText('Run a new assessment', { exact: true }).click();
      const acknowledge = page.getByRole('checkbox', { name: /I understand this replaces/ });
      const run = page.getByRole('button', { name: 'Run and replace saved trails' });
      await acknowledge.check(); assert(await run.isEnabled());
      await month(page, '202604'); await settle(page);
      assert(!await acknowledge.isChecked(), 'Changing month must clear acknowledgement');
      assert(await run.isDisabled());
      await acknowledge.check();
      await page.getByRole('combobox', { name: 'Module', exact: true }).selectOption('inventory_mismatch');
      assert(!await acknowledge.isChecked()); assert(await run.isDisabled());
    });
    await check('Activation automatic comparison follows month; explicit choices survive', async page => {
      await page.goto(`${origin}/?view=activation&period=202603`);
      const comparison = page.getByRole('combobox', { name: /Compare/ });
      await comparison.waitFor(); assert.equal(await comparison.inputValue(), '202602');
      await month(page, '202604'); await settle(page);
      assert.equal(await comparison.inputValue(), '202603', 'Automatic comparison advances');
      await comparison.selectOption('202602'); await month(page, '202605'); await settle(page);
      assert.equal(await comparison.inputValue(), '202602', 'Valid manual choice is retained');
      await comparison.selectOption(''); await month(page, '202606'); await settle(page);
      assert.equal(await comparison.inputValue(), '', 'Explicit no comparison is retained');
      const earliest = await page.getByRole('combobox', { name: /Reporting period/ }).locator('option').evaluateAll(options => options.map(option => option.value).filter(Boolean).sort()[0]);
      await page.goto(`${origin}/?view=activation&period=${earliest}`);
      await comparison.waitFor(); assert.equal(await comparison.inputValue(), '');
      await month(page, '202604'); await settle(page);
      assert.equal(await comparison.inputValue(), '202603', 'Automatic empty comparison does not become explicit none');
    });
    await check('Inventory searches bounded pages for exact subject and establishes exhaustion', async page => {
      let selected;
      const reads = [];
      await page.route('**/inventory/comparison-page?*', async route => {
        const params = new URL(route.request().url()).searchParams;
        const period = params.get('mon_period'), offset = Number(params.get('offset')), limit = Number(params.get('limit'));
        assert(limit <= 100);
        if (period === '202603') {
          const response = await route.fetch(); const data = await response.json();
          selected = { ...data.items[0], scenario_id: 'navigation-fixture', scenario_label: 'Synthetic navigation fixture' };
          return route.fulfill({ json: { ...data, items: [selected], pagination: { ...data.pagination, total: 1, returned: 1, has_more: false } } });
        }
        reads.push({ period, offset, limit });
        const total = period === '202604' ? 101 : 205;
        const items = Array.from({ length: Math.min(limit, total - offset) }, (_, index) => {
          const position = offset + index;
          return period === '202604' && position === 100 ? { ...selected, activation_count: 777 }
            : { ...selected, dealer_id: `${selected.dealer_id}-substring-${position}`, product_code: `other-${position}` };
        });
        return route.fulfill({ json: { items, pagination: { limit, offset, total, returned: items.length, has_more: offset + items.length < total } } });
      });
      await page.goto(`${origin}/?view=inventory&period=202603`);
      await page.getByRole('button', { name: /View evidence for dealer/ }).first().click();
      await month(page, '202604'); await settle(page);
      assert.deepEqual(reads.filter(read => read.period === '202604').map(read => read.offset), [0, 100]);
      assert(await page.getByRole('heading', { name: 'Observed comparison', exact: true }).isVisible(), 'Exact subject beyond first 100 remains selected');
      assert(await page.getByText('777', { exact: true }).isVisible());
      assert.equal(await page.locator('tbody tr').count(), 0, 'Selection lookup never renders collected pages');
      await month(page, '202605'); await settle(page);
      assert.deepEqual(reads.filter(read => read.period === '202605').map(read => read.offset), [0, 100, 200]);
      assert(await page.getByText(/This dealer-product was not found/).isVisible());
      assert.equal(await page.getByRole('heading', { name: 'Observed comparison', exact: true }).count(), 0);
      assert(await page.getByRole('button', { name: /Back to comparison/ }).isVisible());
    });
  } finally { await browser.close(); }
  assert.deepEqual(failures, [], 'All scope regressions must pass');
})().catch(error => { console.error(error); process.exitCode = 1; });
