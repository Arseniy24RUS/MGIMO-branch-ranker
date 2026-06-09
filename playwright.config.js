// @ts-check
const { defineConfig, devices } = require('@playwright/test');
const port = 4273;
module.exports = defineConfig({
  testDir: './tests',
  workers: 1,
  timeout: 45000,
  expect: { timeout: 10000 },
  reporter: [['list'], ['html', { open: 'never' }], ['json', { outputFile: 'test-results/playwright-summary.json' }]],
  use: { baseURL: `http://127.0.0.1:${port}`, trace: 'on-first-retry' },
  webServer: { command: `npx http-server docs -p ${port} -c-1`, url: `http://127.0.0.1:${port}`, reuseExistingServer: false, timeout: 120000 },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
    { name: 'mobile-chromium', use: { ...devices['Pixel 7'] } },
    { name: 'mobile-webkit', use: { ...devices['iPhone 13'] } }
  ]
});
