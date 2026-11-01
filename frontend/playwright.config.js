import { defineConfig } from '@playwright/test';

// Rendered-workspace acceptance tests. Every backend read is fixture-routed in
// the spec, so no API server, Presto or model provider is needed. Starts its own
// Vite server and uses the installed Chrome, so no browser download is required.
const port = 5199;

export default defineConfig({
  testDir: './tests/acceptance',
  forbidOnly: true,
  use: {
    baseURL: `http://localhost:${port}`,
    channel: 'chrome',
    headless: true,
  },
  webServer: {
    command: `npx vite --port ${port} --strictPort`,
    url: `http://localhost:${port}`,
    reuseExistingServer: false,
  },
});
