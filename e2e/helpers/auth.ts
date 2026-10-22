import type { Page } from "@playwright/test";

export async function authenticateE2e(page: Page) {
  const port = process.env.PLAYWRIGHT_PORT || "3000";
  await page.context().addCookies([
    {
      name: "e2e-authenticated",
      value: "1",
      url: `http://127.0.0.1:${port}`,
      sameSite: "Lax",
    },
  ]);
}
