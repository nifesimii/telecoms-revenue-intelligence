// Public useChat output + persisted v1 threads + real client transport in isolated
// Chrome. Run with Vite and PLAYWRIGHT_MODULE as in tests/README.md; no backend.
import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
const origin = process.env.APP_URL || 'http://localhost:5173';
const payment = 'Reporting period 202606. Comparison period 202605. Exact dealer account code 001 (Fixture account); do not combine other accounts with the same name. Payment settlement investigation. Use recorded payment and commission evidence; do not infer causes from aggregate differences.';
const subscription = 'Reporting period 202606. No comparison period selected. Portfolio-level investigation. Subscription review: subscription revenue is separate from recorded upstream subscription commission, settlement and outstanding amounts. Use get_orsc_summary for available evidence. Do not infer a commission rate or eligibility policy; the actual calculation policy has not been supplied. Missing commission evidence is unavailable, not zero.';
const activation = 'Reporting period 202606. No comparison period selected. Portfolio-level investigation. Activation commission.';
const inventory = 'Inventory investigation for reporting period 202606, exact dealer 001 (Fixture account), product P1 (Fixture product). Use only this dealer/product scope. Confirm invoice coverage, purchase window and documented Inventory KB explanations; missing evidence does not prove missing purchases or commission owed. ';
const finding = 'Findings investigation for reporting period 202606. Exact dealer account code 001 (Fixture account); do not combine other accounts with the same name. Finding module inventory, type INVENTORY_MISMATCH. Exact product code P1. Use the evidence and documented rules; distinguish missing evidence from confirmed discrepancies.';
const question = 'Explain this account.\n\nKeep my second paragraph.';
const cases = [
  ['payment', '202606.202605.payment.001', payment, true],
  ['subscription', '202606.none.orsc.all', subscription, true],
  ['activation', '202606.none.activation.all', activation, true],
  ['inventory', 'inventory.202606.001.P1', inventory, true],
  ['purchase scenario', 'inventory.202606.001.P1', inventory + 'Purchase scenario: Example; scenario purchase quantities are not verified operational evidence.', true],
  ['synthetic scenario', 'inventory.202606.001.P1', inventory + 'Synthetic scenario: Example; fictional purchase evidence is not verified operational evidence.', true],
  ['finding', 'findings.["202606","001","inventory","INVENTORY_MISMATCH","P1"]', finding, true],
  ['finding without product', 'findings.["202606","001","inventory","INVENTORY_MISMATCH",null]', finding.replace(' Exact product code P1.', ''), true],
  ['wrong inventory product', 'inventory.202606.001.P2', inventory, false],
  ['wrong finding type', 'findings.["202606","001","inventory","ZERO_COMMISSION","P1"]', finding, false],
  ['wrong account', '202606.202605.payment.002', payment, false],
  ['wrong period', '202605.202605.payment.001', payment, false],
  ['wrong comparison', '202606.none.payment.001', payment, false],
  ['wrong stream', '202606.202605.activation.001', payment, false],
  ['financial never prefixed', '202606.202605.financial.001', payment, false],
  ['partial prose', '202606.202605.payment.001', 'Reporting period 202606. Explain my own accounting notes.', false],
  ['quoted context', '202606.202605.payment.001', 'My quotation: ' + payment, false],
  ['edited template', '202606.202605.payment.001', payment.replace('do not infer causes', 'please infer causes'), false],
];
const currentContext = 'Current scope is supplied separately on every request.';
let passed = 0;
try {
  for (const [name, scope, prefix, recognized] of cases) {
    const page = await browser.newPage();
    page.setDefaultTimeout(8000);
    const errors = [];
    page.on('pageerror', (error) => { errors.push(error.message); console.error(error.message); });
    const key = `fbb.chat.thread.${scope}`;
    const text = `${prefix}\n\n${question}`;
    const expected = recognized ? question : text;
    const metadata = { tools_called: ['evidence'], raw_data: { evidence: 'retain' }, mon_period: '202606' };
    const messages = [
      { role: 'user', content: text, ...metadata },
      { role: 'assistant', content: text, ...metadata, status: 'complete' },
      { role: 'user', content: text, ...metadata },
      { role: 'assistant', content: 'Partial evidence', ...metadata, status: 'streaming', incomplete: true,
        request: { text, monPeriod: '202606', explanation: null } },
    ];
    await page.addInitScript(({ key, messages }) => {
      if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify({ version: 1, messages }));
    }, { key, messages });
    const requests = [];
    await page.route('**/*', async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === '/chat/stream') {
        requests.push(route.request().postDataJSON());
        return route.fulfill({ contentType: 'application/x-ndjson', body: JSON.stringify({ type: 'complete', response: 'Complete answer', tools_called: [], raw_data: {}, error: null }) + '\n' });
      }
      if (url.origin !== new URL(origin).origin) return route.abort();
      if (url.pathname !== '/legacy-chat-test') return route.continue();
      return route.fulfill({ contentType: 'text/html', body: `<div id="root"></div><script type="module">
        import React from '/node_modules/.vite/deps/react.js';
        import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';
        import useChat from '/src/hooks/useChat.js';
        function Fixture() {
          const chat = useChat({ scope: ${JSON.stringify(scope)}, investigationContext: ${JSON.stringify(currentContext)} });
          return React.createElement('main', null,
            React.createElement('pre', { id: 'messages' }, JSON.stringify(chat.messages)),
            React.createElement('button', { disabled: !chat.canRetry, onClick: chat.retryMessage }, 'Retry'),
            React.createElement('button', { disabled: chat.isLoading, onClick: () => chat.sendMessage(${JSON.stringify(text)}, '202606') }, 'Send verbatim'));
        }
        ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(Fixture));
      </script>` });
    });
    await page.goto(`${origin}/legacy-chat-test`);
    const readMessages = async () => JSON.parse(await page.locator('#messages').innerText());
    let displayed = await readMessages();
    assert.equal(displayed.length, 4, name);
    assert.equal(displayed[0].content, expected, `${name}: display`);
    assert.equal(displayed[1].content, text, `${name}: assistant prose unchanged`);
    assert.deepEqual(displayed[0], { ...messages[0], content: expected });
    assert.deepEqual(displayed[1], messages[1]);
    assert.deepEqual(await page.evaluate((key) => JSON.parse(localStorage.getItem(key)).messages, key), messages, 'Restoring a thread must not eagerly overwrite its stored data');
    assert.equal(displayed[3].status, 'interrupted');
    assert.equal(displayed[3].request.text, expected, `${name}: retry payload`);
    assert.equal(requests.length, 0, 'Loading stored threads must not submit');
    await page.getByRole('button', { name: 'Retry', exact: true }).click();
    await page.waitForFunction(() => JSON.parse(document.querySelector('#messages').textContent).at(-1).status === 'complete');
    assert.equal(requests.length, 1);
    assert.deepEqual(requests[0], { message: expected, mon_period: '202606', investigation_context: currentContext,
      conversation_history: [{ role: 'user', content: expected }, { role: 'assistant', content: text }] });
    displayed = await readMessages();
    assert.equal(displayed.length, 4, 'Retry replaces only incomplete turn');
    assert.equal(displayed[2].content, expected);
    await page.reload();
    assert.equal((await readMessages())[0].content, expected, 'Normalized thread survives reload');
    assert.equal(requests.length, 1);
    await page.getByRole('button', { name: 'Send verbatim' }).click();
    await page.waitForFunction(() => JSON.parse(document.querySelector('#messages').textContent).length === 6 && JSON.parse(document.querySelector('#messages').textContent).at(-1).status === 'complete');
    assert.equal(requests[1].message, text, 'New user prose must never be normalized at submission');
    assert.equal(requests[1].conversation_history[0].content, expected);
    await page.reload();
    assert.equal((await readMessages())[4].content, text, 'New literal prose survives reload without legacy normalization');
    assert.equal(await page.evaluate((key) => JSON.parse(localStorage.getItem(key)).version, key), 2);
    assert.deepEqual(errors, []);
    await page.close();
    console.log(`PASS ${name}: persisted display, transport history, retry, reload, untouched new prose`);
    passed++;
  }
  console.log(`${passed} legacy chat scenarios passed; no provider calls.`);
} finally { await browser.close(); }
