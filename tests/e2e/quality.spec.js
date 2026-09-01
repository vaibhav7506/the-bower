const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;
const { preparePage } = require("./helpers");

test("cross-browser homepage and reservation controls render", async ({ page }) => {
  await preparePage(page);
  await expect(page.getByRole("heading", { name: /A quiet table/ })).toBeVisible();
  await expect(page.locator("[data-date=\"2026-09-08\"]")).toBeEnabled();
});

test("mobile booking controls remain usable without horizontal overflow", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile-chrome", "Runs in the mobile device project.");
  await preparePage(page);
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    page: document.documentElement.scrollWidth,
  }));
  expect(dimensions.page).toBeLessThanOrEqual(dimensions.viewport + 1);
  await page.locator("[data-date=\"2026-09-08\"]").click();
  await expect(page.locator("[data-time-slots] [data-time]").first()).toBeVisible();
});

test("homepage has no serious or critical automated accessibility violations", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "One deterministic axe scan is sufficient.");
  await preparePage(page);
  const results = await new AxeBuilder({ page }).analyze();
  const severe = results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact));
  expect(severe, JSON.stringify(severe, null, 2)).toEqual([]);
});
