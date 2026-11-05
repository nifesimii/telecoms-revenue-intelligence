import { randomBytes } from 'node:crypto';
import { defineConfig } from '@playwright/test';

// Rendered-workspace acceptance tests. Partner Sales and login run against the real
// API on its own port, with generated credentials; every other read is fixture-routed
// in the spec, so no Presto or model provider is needed. One worker, because tests
// share that server's simulation. Starts its own Vite server and uses the installed
// Chrome, so no browser download is required.
const port = 5199;
const apiPort = 8199;
const origin = `http://localhost:${port}`;

// Workers inherit this, so they know the password the server was started with.
process.env.ACCEPTANCE_PASSWORD ??= randomBytes(24).toString('base64url');

export default defineConfig({
  testDir: './tests/acceptance',
  forbidOnly: true,
  workers: 1,
  use: {
    baseURL: origin,
    channel: 'chrome',
    headless: true,
  },
  webServer: [
    {
      command: `npx vite --port ${port} --strictPort`,
      url: origin,
      reuseExistingServer: false,
      env: { VITE_API_URL: `http://localhost:${apiPort}` },
    },
    {
      command: `.venv/bin/python -m uvicorn backend.tests.acceptance_server:app --host localhost --port ${apiPort} --log-level warning`,
      cwd: '..',
      url: `http://localhost:${apiPort}/health`,
      reuseExistingServer: false,
      env: { ACCEPTANCE_ORIGIN: origin, ACCEPTANCE_PASSWORD: process.env.ACCEPTANCE_PASSWORD },
    },
  ],
});
