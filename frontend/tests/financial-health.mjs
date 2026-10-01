// Real Financial Health UI/API, provider response mocked: no billed AI calls.
import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.setDefaultTimeout(15000);
const errors = [], requests = [];
page.on('pageerror', (error) => errors.push(error.message));
try {
  await page.route('**/chat/stream', async (route) => {
    requests.push(route.request().postDataJSON());
    await route.fulfill({ contentType: 'application/x-ndjson', body: JSON.stringify({
      type: 'complete', response: 'Synthetic financial statement explanation for this reporting period.',
      tools_called: ['get_financial_health_report'], raw_data: {}, error: null,
    }) + '\n' });
  });
  await page.route('**/chat', (route) => route.abort());
  await page.goto(`${process.env.APP_URL || 'http://localhost:5173'}/?view=financial-health&period=202603`);
  const main = page.getByRole('main', { name: 'Dealer financial health' });
  await main.getByText('20 matching businesses', { exact: false }).waitFor();
  await main.getByRole('button', { name: 'Ask Atlas to compare dealers' }).click();
  const atlas = main.getByRole('region', { name: 'Atlas', exact: true });
  const input = atlas.getByRole('textbox');
  const ask = async (question) => {
    const count = requests.length;
    await input.fill(question);
    await atlas.getByRole('button', { name: 'Send question' }).click();
    await page.waitForFunction(() => !document.querySelector('textarea:disabled'));
    assert.equal(requests.length, count + 1);
  };
  await ask('Compare operating cash flow across the cohort.');
  assert.match(requests.at(-1).investigation_context, /20-dealer.*synthetic/s);
  assert.equal(requests.at(-1).message, 'Compare operating cash flow across the cohort.');
  await main.getByRole('searchbox', { name: 'Find a dealer' }).fill('74050');
  await main.getByText('1 matching businesses', { exact: false }).waitFor();
  await main.getByRole('button', { name: 'Review Stone Light Networks' }).click();
  await main.getByRole('heading', { name: 'Financial health at a glance' }).waitFor();
  assert.equal(await atlas.getByText('Synthetic financial statement explanation for this reporting period.', { exact: true }).count(), 0);
  await ask('Explain these financial statements.');
  await ask('Why does cash differ from profit?');
  assert.match(requests.at(-1).investigation_context, /Exact dealer account code 74050/);
  assert.match(requests.at(-1).investigation_context, /202603/);
  assert.equal(requests.at(-1).message, 'Why does cash differ from profit?');
  for (const statement of ['Balance sheet', 'Cash flow statement', 'Income statement']) {
    await main.getByRole('button', { name: statement, exact: true }).click();
    await main.getByRole('heading', { name: statement, exact: true }).waitFor();
  }
  const downloadPromise = page.waitForEvent('download');
  await main.getByRole('button', { name: 'Export financial report' }).click();
  const download = await downloadPromise;
  assert.match(download.suggestedFilename(), /synthetic_financial_statements_74050_202603/);
  await page.getByLabel('Reporting period').selectOption('202604');
  await main.getByText('Apr 2026 compared with Mar 2026', { exact: true }).waitFor();
  assert.equal(await atlas.getByText('Synthetic financial statement explanation for this reporting period.', { exact: true }).count(), 0);
  await ask('Explain the change since last month.');
  assert.match(requests.at(-1).investigation_context, /202604/);
  assert.equal(requests.at(-1).conversation_history.length, 0);
  await main.getByRole('button', { name: 'All dealers' }).click();
  await main.getByRole('searchbox', { name: 'Find a dealer' }).fill('19649');
  await main.getByRole('button', { name: 'Review Silver Valley Ventures' }).click();
  await main.getByText('Repayment schedule unavailable.', { exact: true }).waitFor();
  await ask('Explain the missing evidence.');
  assert.match(requests.at(-1).investigation_context, /Exact dealer account code 19649/);
  assert.equal(requests.at(-1).conversation_history.length, 0);
  await atlas.scrollIntoViewIfNeeded();
  await page.screenshot({ path: '/tmp/financial-health-desktop.png' });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  await atlas.getByRole('heading', { name: 'Atlas', exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: '/tmp/financial-health-mobile.png' });
  await main.getByRole('button', { name: 'Hide Atlas' }).click();
  await main.getByRole('heading', { name: 'Financial health at a glance' }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: '/tmp/financial-health-statements-mobile.png' });
  assert.deepEqual(errors, []);
  console.log('Financial Health: 20 dealers, statements/export, scoped Atlas follow-ups, dealer/month isolation, missing evidence and mobile layout passed.');
} finally { await browser.close(); }
