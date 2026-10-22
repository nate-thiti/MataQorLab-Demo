import { expect, test } from "@playwright/test";
import { authenticateE2e } from "./helpers/auth";

test("redirects / to a supported locale", async ({ page }) => {
  const response = await page.goto("/");
  expect(response?.ok()).toBeTruthy();
  await expect(page).toHaveURL(/\/(th|en)$/);
});

test("loads public marketing route", async ({ page }) => {
  await page.goto("/th/pricing");
  await expect(page).toHaveURL(/\/th\/pricing$/);
  await expect(page.locator("html")).toHaveAttribute("lang", "th");
  await expect(page.locator("body")).toBeVisible();
});

test("switches locale, preserves the current route/query, and remembers it", async ({
  page,
}) => {
  await page.goto("/th/pricing?source=i18n-check");
  await page.getByRole("button", { name: "เปลี่ยนเป็นภาษาอังกฤษ" }).click();

  await expect(page).toHaveURL(/\/en\/pricing\?source=i18n-check$/);
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(
    page.getByRole("navigation").getByRole("link", { name: "Documentation" }),
  ).toBeVisible();

  await page.goto("/");
  await expect(page).toHaveURL(/\/en$/);
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
});

test("Enterprise pricing is self-service with a two-user minimum", async ({ page }) => {
  await page.route("**/rest/v1/plans*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "10000000-0000-4000-8000-000000000001",
          name: "Enterprise",
          price_monthly: 99,
          price_yearly: 1188,
          included_seats: 2,
          additional_seat_price_monthly: 39,
          storage_limit_mb: 2000,
          message_limit: 2000000,
        },
      ]),
    });
  });

  await page.goto("/en/pricing");
  await expect(page.getByRole("tab", { name: /Individual/i })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.getByText("Enterprise", { exact: true })).toHaveCount(0);
  await page.getByRole("tab", { name: /Business/i }).click();
  await expect(page.getByText("Enterprise", { exact: true })).toBeVisible();
  await page.getByLabel("Organization name").fill("MataQor Labs");
  const seats = page.getByLabel("Team size (minimum 2)");
  await expect(seats).toHaveValue("2");
  await seats.fill("3");
  await expect(page.getByText("138 USD/month", { exact: false })).toBeVisible();
});

test("Register separates Individual and Business onboarding", async ({ page }) => {
  await page.goto("/en/register/step/1");
  await expect(page.getByRole("tab", { name: /Individual/i })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.getByLabel("Organization name")).toHaveCount(0);
  await page.getByRole("tab", { name: /Business/i }).click();
  await expect(page.getByLabel("Organization name")).toBeVisible();
  await page.getByLabel("Organization name").fill("MataQor Labs");
  await expect(page.getByLabel("Organization name")).toHaveValue("MataQor Labs");
});

test("shows custom not found page", async ({ page }) => {
  await page.goto("/th/this-route-does-not-exist");
  await expect(page.getByRole("heading", { name: "404" })).toBeVisible({
    timeout: 15000,
  });
});

test("redirects protected route to login when unauthenticated", async ({
  page,
}) => {
  await page.goto("/th/dashboard");
  await expect(page).toHaveURL(/\/th\/login$/);
});

test("redirects /th/register to step 1", async ({ page }) => {
  await page.goto("/th/register");
  await expect(page).toHaveURL(/\/th\/register\/step\/1$/);
});

test("redirects unauthenticated /th/chat to login", async ({ page }) => {
  await page.goto("/th/chat");
  await expect(page).toHaveURL(/\/th\/login$/);
});

test("login page renders email and password fields", async ({ page }) => {
  await page.goto("/th/login");
  await expect(page.getByLabel(/อีเมล|email/i)).toBeVisible();
  await expect(page.getByLabel(/รหัสผ่าน|password/i)).toBeVisible();
  await expect(page.getByRole("button", { name: "เข้าสู่ระบบ", exact: true })).toBeVisible();
});

test("login forgot-password route renders reset form", async ({ page }) => {
  await page.goto("/th/login/forgot");
  await expect(page).toHaveURL(/\/th\/login\/forgot$/);
  await expect(page.getByLabel(/อีเมล|email/i)).toBeVisible();
});

test("authenticated user reaches dashboard", async ({ page }) => {
  await authenticateE2e(page);
  await page.goto("/th/dashboard");
  await expect(page).toHaveURL(/\/th\/dashboard$/);
});

test("authenticated user reaches the end-to-end Customer Center", async ({ page }) => {
  await authenticateE2e(page);
  await page.route("**/api/v1/customer-experience/overview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        onboarding: {
          completed_steps: ["profile", "connect_data"],
          completion_percent: 25,
          next_step: "sample_data",
        },
        data_assets: [],
        lineage: [],
        collaboration: [],
        alerts: [
          {
            id: "rule-1",
            name: "Revenue changed",
            report_id: "report-1",
            metric_key: "revenue",
            enabled: true,
            last_status: "idle",
          },
        ],
        alert_events: [],
        available_reports: [
          {
            id: "report-1",
            title: "Monthly performance",
            dashboard_spec: {
              kpis: [
                { kind: "count", label: "Rows", field: null },
                { kind: "sum", label: "Total revenue", field: "revenue" },
              ],
            },
          },
        ],
        integrations: [],
        embeds: [],
        governance: { organizations: [], workspaces: [] },
        summary: {
          healthy_assets: 0,
          asset_issues: 0,
          open_collaboration: 0,
          enabled_alerts: 0,
          active_integrations: 0,
        },
      }),
    });
  });
  await page.route(
    "**/api/v1/customer-experience/alerts/rule-1/evaluate",
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          evaluation: { rule_id: "rule-1", status: "baseline" },
        }),
      });
    },
  );
  await page.goto("/en/customer-center");
  await expect(page).toHaveURL(/\/en\/customer-center$/);
  await expect(page.getByRole("heading", { name: "Customer Center" })).toBeVisible();
  await expect(page.getByText("Data Health Center")).toBeVisible();
  await expect(page.getByText("Guided activation")).toHaveCount(0);
  await expect(page.getByText("End-to-end capabilities")).toHaveCount(0);
  await expect(page.getByText("Organization Center", { exact: true })).toHaveCount(0);
  await expect(page.getByText("SAML SSO", { exact: true })).toHaveCount(0);
  await expect(page.getByText("SCIM provisioning", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Dashboard source")).toHaveValue("report-1");
  await page.getByRole("button", { name: "Test", exact: true }).click();
  await expect(page.getByText("Alert evaluation: baseline")).toBeVisible();
});

test("authenticated user cannot return to login", async ({ page }) => {
  await authenticateE2e(page);
  await page.goto("/th/login");
  await expect(page).toHaveURL(/\/th\/dashboard$/);
});

test("browser back cannot restore login for authenticated user", async ({
  page,
}) => {
  await page.goto("/th/login");
  await authenticateE2e(page);
  await page.goto("/th/dashboard");
  await page.goBack();
  await expect(page).toHaveURL(/\/th\/dashboard$/);
});

test("authenticated user cannot return to register", async ({ page }) => {
  await authenticateE2e(page);
  await page.goto("/th/register/step/1");
  await expect(page).toHaveURL(/\/th\/dashboard$/);
});

test("authenticated /th/chat redirects to /th/chat/new", async ({ page }) => {
  await authenticateE2e(page);
  await page.goto("/th/chat");
  await expect(page).toHaveURL(/\/th\/chat\/new$/);
});

test("authenticated user opens a saved Visualization report", async ({ page }) => {
  const reportId = "33333333-3333-4333-8333-333333333333";
  await page.route("**/api/v1/visualizations/reports", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        reports: [
          {
            id: reportId,
            user_id: "00000000-0000-4000-8000-000000000001",
            title: "Monthly performance",
            executive_summary: "Validated monthly trend.",
            status: "draft",
            created_via: "chat",
            created_at: "2026-07-24T10:00:00Z",
            updated_at: "2026-07-24T10:00:00Z",
            charts: [
              {
                id: "44444444-4444-4444-8444-444444444444",
                report_id: reportId,
                chart_type: "bar",
                title: "Revenue by month",
                config: { title: "Revenue by month", xAxis: "name" },
                data: [
                  { name: "Jan", revenue: 120 },
                  { name: "Feb", revenue: 150 },
                ],
                insight: "February increased.",
              },
            ],
          },
        ],
      }),
    });
  });
  await page.route("**/api/v1/visualizations/dashboard/generate", async (route) => {
    const requestBody = route.request().postDataJSON();
    const filtered = requestBody?.filters?.branch === "B";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        dashboard: {
          report_id: reportId,
          source: { type: "file", file_name: "monthly.csv" },
          row_count: 2,
          filtered_row_count: filtered ? 1 : 2,
          aggregation_scope: "full_dataset",
          schema: [
            { name: "month", kind: "date", distinct: 2, options: [] },
            { name: "branch", kind: "text", distinct: 2, options: ["A", "B"] },
            { name: "revenue", kind: "number", distinct: 2, options: [] },
          ],
          spec: {
            version: 1,
            title: "Monthly performance",
            filters: [{ field: "branch", kind: "text" }],
            kpis: [
              { kind: "count", label: "Rows", field: null },
              { kind: "sum", label: "Total revenue", field: "revenue" },
            ],
            widgets: [
              {
                id: "ranking",
                kind: "chart",
                chart_type: "bar",
                title: "Revenue by branch",
                dimension: "branch",
                measure: "revenue",
                aggregation: "sum",
                span: 12,
              },
            ],
          },
          kpis: [
            { kind: "count", label: "Rows", field: null, value: filtered ? 1 : 2 },
            { kind: "sum", label: "Total revenue", field: "revenue", value: filtered ? 150 : 270 },
          ],
          widgets: [
            {
              id: "ranking",
              kind: "chart",
              chart_type: "bar",
              title: "Revenue by branch",
              span: 12,
              data: filtered
                ? [{ name: "B", value: 150 }]
                : [
                    { name: "A", value: 120 },
                    { name: "B", value: 150 },
                  ],
            },
          ],
        },
      }),
    });
  });

  await authenticateE2e(page);
  await page.goto(`/th/visualizations/${reportId}`);
  await expect(page).toHaveURL(new RegExp(`/th/visualizations/${reportId}$`));
  await expect(page.getByRole("heading", { name: "Findings" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Monthly performance" })).toBeVisible();
  await expect(page.getByText("ตัวกรองทั้งรายงาน")).toBeVisible();
  await expect(page.getByText("Total revenue")).toBeVisible();
  await expect(page.getByText("Revenue by month")).toBeVisible();
  await page.getByRole("combobox", { name: "branch" }).selectOption("B");
  await expect(page.getByText("1 แถวที่ตรงตัวกรอง")).toBeVisible();
  await expect(page.getByText("150").first()).toBeVisible();
});

test("public read-only Visualization share renders without authentication", async ({ page }) => {
  const token = "55555555-5555-4555-8555-555555555555";
  await page.route(`**/api/v1/visualizations/shared/${token}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        report: {
          id: "33333333-3333-4333-8333-333333333333",
          title: "Shared performance",
          executive_summary: "Read-only summary.",
        },
        share: { expires_at: "2026-12-31T00:00:00Z", allow_detail_rows: false },
        dashboard: {
          report_id: "33333333-3333-4333-8333-333333333333",
          source: {},
          row_count: 2,
          schema: [
            { name: "branch", kind: "text", distinct: 2 },
            { name: "revenue", kind: "number", distinct: 2 },
          ],
          spec: {
            version: 3,
            title: "Shared performance",
            filters: [],
            kpis: [{ kind: "sum", label: "Revenue", field: "revenue" }],
            widgets: [{
              id: "shared-chart",
              kind: "chart",
              chart_type: "bar",
              title: "Revenue by branch",
              dimension: "branch",
              measure: "revenue",
              aggregation: "sum",
              span: 12,
            }],
          },
          kpis: [{ kind: "sum", label: "Revenue", field: "revenue", value: 270 }],
          widgets: [{
            id: "shared-chart",
            kind: "chart",
            chart_type: "bar",
            title: "Revenue by branch",
            dimension: "branch",
            measure: "revenue",
            aggregation: "sum",
            span: 12,
            data: [{ name: "A", value: 120 }, { name: "B", value: 150 }],
          }],
        },
      }),
    });
  });

  await page.goto(`/th/shared/visualizations/${token}`);
  await expect(page.getByRole("heading", { name: "Shared performance" })).toBeVisible();
  await expect(page.getByText("Decision packet แบบอ่านอย่างเดียว")).toBeVisible();
  await expect(page.getByRole("button", { name: "ปรับฟิลด์" })).toHaveCount(0);
});

test("scheduled delivery editor exposes SMTP, KPI and narration guardrails", async ({ page }) => {
  await page.route("**/api/v1/etl/recipes", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        recipes: [{
          id: "66666666-6666-4666-8666-666666666666",
          name: "Daily sales",
          dataset_key: "sales.csv",
          version: 1,
        }],
      }),
    });
  });
  await page.route("**/api/v1/etl/schedules", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        schedules: [],
        runs: [],
        automation_events: [],
        delivery_metrics: { delivered: 0, opened: 0, open_rate: null },
        schedule_limit: 10,
      }),
    });
  });

  await authenticateE2e(page);
  await page.goto("/en/files/schedules");
  await page.getByRole("button", { name: "New schedule" }).click();
  await expect(page.getByText("Minimum semantic KPI change (%)")).toBeVisible();
  await expect(page.getByText("Generate evidence-bounded narration")).toBeVisible();
  await expect(page.getByText("Also send by email (SMTP)", { exact: true })).toBeVisible();
});

test("memory panel exposes saved definitions and session preferences", async ({ page }) => {
  await page.route("**/api/v1/governance/context", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ organizations: [], workspaces: [] }),
    });
  });
  await page.route("**/api/v1/governance/memories?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ memories: [] }),
    });
  });
  await page.route("**/rest/v1/chat_memories*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await authenticateE2e(page);
  await page.goto("/en/chat/new");
  await page.getByRole("button", { name: /Memory/i }).click();
  await expect(page.getByText("Saved definitions")).toBeVisible();
  await expect(page.getByText(/Settings → Organization/)).toBeVisible();
  await expect(page.getByText(/reviewer approval/)).toBeVisible();
  await expect(page.getByText("Session & preferences")).toBeVisible();
});

test("switches chat conversations without a page reload", async ({ page }) => {
  const firstId = "11111111-1111-4111-8111-111111111111";
  const secondId = "22222222-2222-4222-8222-222222222222";
  const firstRoot = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const secondRoot = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  const secondVersion = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
  const conversations = [
    { id: firstId, title: "First regression chat", active_branch_id: firstRoot, created_at: "2026-07-18T10:00:00Z" },
    { id: secondId, title: "Second regression chat", active_branch_id: secondRoot, created_at: "2026-07-18T11:00:00Z" },
  ];

  await page.route("**/rest/v1/conversations*", async (route) => {
    const url = decodeURIComponent(route.request().url());
    if (url.includes("select=active_branch_id")) {
      const conversation = url.includes(secondId) ? conversations[1] : conversations[0];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ active_branch_id: conversation.active_branch_id }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(conversations),
    });
  });
  await page.route("**/rest/v1/chat_branches*", async (route) => {
    const url = decodeURIComponent(route.request().url());
    const isSecond = url.includes(secondId);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(isSecond ? [
        {
          id: secondRoot,
          conversation_id: secondId,
          branch_index: 1,
          title: "Main",
          is_root: true,
        },
        {
          id: secondVersion,
          conversation_id: secondId,
          branch_index: 2,
          title: "Regenerated answer",
          is_root: false,
        },
      ] : [{
        id: firstRoot,
        conversation_id: firstId,
        branch_index: 1,
        title: "Main",
        is_root: true,
      }]),
    });
  });
  await page.route("**/rest/v1/rpc/activate_chat_branch", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(secondVersion),
    });
  });
  await page.route("**/rest/v1/chat_messages*", async (route) => {
    const url = decodeURIComponent(route.request().url());
    const isSecond = url.includes(secondId);
    const isSecondVersion = url.includes(secondVersion);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: isSecond ? "message-second" : "message-first",
          conversation_id: isSecond ? secondId : firstId,
          role: "ai",
          content: isSecondVersion
            ? "SECOND_CHAT_REGENERATED_CONTENT"
            : isSecond ? "SECOND_CHAT_CONTENT" : "FIRST_CHAT_CONTENT",
          created_at: "2026-07-18T11:01:00Z",
        },
      ]),
    });
  });

  await authenticateE2e(page);
  await page.goto("/th/chat/new");
  await page.getByTitle("แสดงเมนู").click();
  await page.getByRole("button", { name: "First regression chat" }).click();
  await expect(page).toHaveURL(new RegExp(`/th/chat/${firstId}$`));
  await expect(page.getByText("FIRST_CHAT_CONTENT")).toBeVisible();

  await page.getByRole("button", { name: "Second regression chat" }).click();
  await expect(page).toHaveURL(new RegExp(`/th/chat/${secondId}$`));
  await expect(page.getByText("SECOND_CHAT_CONTENT")).toBeVisible();
  await expect(page.getByText("FIRST_CHAT_CONTENT")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "คัดลอกคำตอบ" })).toBeVisible();
  await expect(page.getByRole("button", { name: "อ่านออกเสียง" })).toBeVisible();
  await expect(page.getByRole("button", { name: "อธิบายให้ง่ายขึ้นอีกหน่อย" })).toBeVisible();

  await page.getByRole("button", { name: "เวอร์ชันแชท" }).click();
  await page.getByRole("menuitemradio", { name: "2. Regenerated answer" }).click();
  await expect(page.getByText("SECOND_CHAT_REGENERATED_CONTENT")).toBeVisible();
  await expect(page.getByText("SECOND_CHAT_CONTENT", { exact: true })).toHaveCount(0);
});

test("authenticated user reaches settings", async ({ page }) => {
  await authenticateE2e(page);
  await page.goto("/th/settings");
  await expect(page).toHaveURL(/\/th\/settings$/);
});
