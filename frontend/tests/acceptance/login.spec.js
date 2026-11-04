// Login and role-appropriate navigation at the rendered application boundary. The
// API is a small stateful fixture; backend/tests/test_auth_access.py proves the
// server enforces the same rules.
import { expect, test } from '@playwright/test';

const API = 'http://localhost:8000/**';
const cors = { 'access-control-allow-origin': 'http://localhost:5199', 'access-control-allow-credentials': 'true' };
const PASSWORD = 'fixture-password';
const LOGINS = {
  finance: { username: 'finance', role: 'internal', account_code: null },
  'partner-296065': { username: 'partner-296065', role: 'partner', account_code: '296065' },
};

async function mockApi(page, { signedInAs = null, reachable = true, configured = true } = {}) {
  const state = { session: signedInAs && LOGINS[signedInAs], requests: [] };
  await page.route(API, async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { ...cors, 'access-control-allow-headers': 'content-type,accept', 'access-control-allow-methods': 'GET,POST' } });
    state.requests.push(pathname);
    if (!reachable) return route.abort();
    if (pathname === '/auth/login') {
      if (!configured) return route.fulfill({ status: 503, headers: cors, json: { detail: 'Sign-in is not configured.' } });
      const { username, password } = request.postDataJSON();
      if (!LOGINS[username] || password !== PASSWORD) return route.fulfill({ status: 401, headers: cors, json: { detail: 'Incorrect username or password.' } });
      state.session = LOGINS[username];
      return route.fulfill({ headers: cors, json: state.session });
    }
    if (pathname === '/auth/logout') {
      state.session = null;
      return route.fulfill({ status: 204, headers: cors });
    }
    if (pathname === '/health') return route.fulfill({ headers: cors, json: { sample_data_mode: true } });
    if (!state.session) return route.fulfill({ status: 401, headers: cors, json: { detail: 'Authentication required.' } });
    if (pathname === '/auth/session') return route.fulfill({ headers: cors, json: state.session });
    if (state.session.role !== 'internal') return route.fulfill({ status: 403, headers: cors, json: { detail: 'Not available for this login.' } });
    if (pathname === '/periods') return route.fulfill({ headers: cors, json: { periods: ['202605'] } });
    return route.fulfill({ status: 503, headers: cors, json: { detail: 'Unavailable in acceptance fixture' } });
  });
  return state;
}

const login = (page) => page.getByRole('main', { name: 'Sign in' });
const submit = async (page, username, password = PASSWORD) => {
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
};
const workspaces = (page) => page.getByRole('navigation', { name: 'Workspace' });

test('shows only the login page before sign-in, and identifies the demonstration', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
  await expect(login(page)).toBeVisible();
  await expect(login(page).getByText('Demonstration only', { exact: false })).toBeVisible();
  await expect(workspaces(page)).toHaveCount(0);
  await expect(page.getByLabel('Username')).toBeFocused();
});

test('an internal user can sign in by keyboard and reach every workspace', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
  await expect(page.getByLabel('Username')).toBeFocused();
  await page.keyboard.type('finance');
  await page.keyboard.press('Tab');
  await page.keyboard.type(PASSWORD);
  await page.keyboard.press('Enter');
  await expect(page.getByText('Signed in as Internal · finance')).toBeVisible();
  for (const name of ['Overview', 'Commission', 'Payments', 'Partner Sales', 'Financial Health', 'Audit Trails']) {
    await expect(workspaces(page).getByRole('button', { name, exact: true })).toBeVisible();
  }
});

test('a partner sees only their own account and requests nothing internal', async ({ page }) => {
  const api = await mockApi(page);
  await page.goto('/?view=payment');
  await submit(page, 'partner-296065');
  const main = page.getByRole('main', { name: 'Partner Sales' });
  await expect(main.getByText('fictional account 296065')).toBeVisible();
  await expect(page.getByText('Signed in as Partner account 296065')).toBeVisible();
  await expect(page.getByText('Synthetic demonstration')).toBeVisible();
  await expect(workspaces(page)).toHaveCount(0);
  await expect(page.getByRole('combobox', { name: /Reporting period/ })).toHaveCount(0);
  expect(api.requests.filter((path) => !path.startsWith('/auth/'))).toEqual([]);
});

test('failed sign-in explains itself without saying which field was wrong', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
  await submit(page, 'finance', 'wrong');
  await expect(page.getByRole('alert')).toHaveText('Incorrect username or password.');
  await expect(page.getByLabel('Password')).toHaveValue('');
  await expect(page.getByLabel('Username')).toHaveValue('finance');
  await submit(page, 'finance');
  await expect(page.getByText('Signed in as Internal · finance')).toBeVisible();
});

test('unconfigured sign-in is explained and stays closed', async ({ page }) => {
  await mockApi(page, { configured: false });
  await page.goto('/');
  await submit(page, 'finance');
  await expect(page.getByRole('alert')).toContainText('not configured');
  await expect(workspaces(page)).toHaveCount(0);
});

test('a session survives refresh, and sign-out ends it', async ({ page }) => {
  await mockApi(page, { signedInAs: 'finance' });
  await page.goto('/');
  await expect(page.getByText('Signed in as Internal · finance')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Signed in as Internal · finance')).toBeVisible();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(login(page)).toBeVisible();
  await expect(login(page).getByRole('status')).toHaveCount(0);
  await page.reload();
  await expect(login(page)).toBeVisible();
});

test('an ended session returns to login with an explanation', async ({ page }) => {
  const api = await mockApi(page, { signedInAs: 'finance' });
  await page.goto('/');
  await expect(page.getByText('Signed in as Internal · finance')).toBeVisible();
  api.session = null;
  // A retrying background read may end the session before this click lands.
  await workspaces(page).getByRole('button', { name: 'Payments', exact: true }).click({ timeout: 3000 }).catch(() => {});
  await expect(login(page)).toBeVisible();
  await expect(login(page).getByRole('status')).toHaveText('Your session has ended. Sign in again to continue.');
  await submit(page, 'finance');
  await expect(page.getByText('Signed in as Internal · finance')).toBeVisible();
});

test('an unreachable server is not presented as being signed out', async ({ page }) => {
  await mockApi(page, { reachable: false });
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('could not be reached');
  await expect(login(page)).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible();
});

test('login and the partner view fit a narrow screen', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 700 });
  await mockApi(page);
  await page.goto('/');
  await expect(login(page)).toBeVisible();
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(await overflow()).toBeLessThanOrEqual(0);
  await submit(page, 'partner-296065');
  await expect(page.getByText('Signed in as Partner account 296065')).toBeVisible();
  expect(await overflow()).toBeLessThanOrEqual(0);
});
