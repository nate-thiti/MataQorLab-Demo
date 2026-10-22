import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.STAGING_APP_URL;
if (!baseURL) throw new Error('STAGING_APP_URL is required');

export default defineConfig({
  testDir: './e2e/staging',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  retries: 1,
  workers: 1,
  reporter: [['html', { outputFolder: 'playwright-report-staging' }], ['list']],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [{
    name: 'staging-chromium',
    use: { ...devices['Desktop Chrome'] },
  }],
});
