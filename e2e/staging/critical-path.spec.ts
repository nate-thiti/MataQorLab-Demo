import { expect, test } from '@playwright/test';

const email = process.env.STAGING_TEST_USER_EMAIL;
const password = process.env.STAGING_TEST_USER_PASSWORD;
const apiURL = process.env.STAGING_API_URL;

test.beforeEach(async ({ page }) => {
  if (!email || !password) {
    throw new Error('STAGING_TEST_USER_EMAIL and STAGING_TEST_USER_PASSWORD are required');
  }
  await page.goto('/en/login');
  await page.locator('#email').fill(email);
  await page.locator('#password').fill(password);
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(/\/en\/dashboard(?:[/?#]|$)/);
});

test('real staging backend is healthy', async ({ request }) => {
  if (!apiURL) throw new Error('STAGING_API_URL is required');
  const response = await request.get(`${apiURL}/health/ready`);
  expect(response.ok()).toBeTruthy();
});

test('authenticated file inventory loads through the real backend', async ({ page }) => {
  const inventoryResponse = page.waitForResponse(
    (response) => response.url().includes('/api/v1/files?'),
  );
  await page.goto('/en/files');
  expect((await inventoryResponse).status()).toBe(200);
  await expect(page).toHaveURL(/\/en\/files(?:[/?#]|$)/);
});

test('chat loads owner-scoped connections without auth bypass', async ({ page }) => {
  const connectionsResponse = page.waitForResponse(
    (response) => response.url().includes('/api/v1/connections'),
  );
  await page.goto('/en/chat/new');
  expect((await connectionsResponse).status()).toBe(200);
  await expect(page.locator('textarea')).toBeVisible();
});
