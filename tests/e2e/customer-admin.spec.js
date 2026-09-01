const { test, expect } = require("@playwright/test");
const { prepareBooking, submitGuest } = require("./helpers");

test("customer booking appears in admin and completes with an audit trail", async ({ page }) => {
  await prepareBooking(page, { date: "2026-09-08", partySize: "4", table: "Table 03" });
  await page.getByLabel(/Special requests/).fill("Phase I window-side dinner");
  await submitGuest(page, "Phase I Guest", "phase-i@example.com");

  const success = page.locator("[data-reservation-success]");
  await expect(success).toBeVisible();
  const code = (await page.locator("[data-confirmation-code]").textContent()).trim();
  expect(code).toMatch(/^BWR-[A-Z0-9]{8}$/);

  await page.goto("/admin/login");
  await page.getByLabel("Email").fill("admin@example.com");
  await page.getByLabel("Password").fill("a-secure-admin-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByLabel("Date").fill("2026-09-08");
  await page.getByLabel("Search").fill(code);
  await page.getByRole("button", { name: "Find" }).click();
  await expect(page.getByText("Phase I Guest")).toBeVisible();
  await page.getByRole("link", { name: "Open" }).click();

  await page.getByRole("button", { name: "Mark checked in" }).click();
  await expect(page.locator(".admin-page-heading .admin-status")).toHaveText("CHECKED IN");
  await page.getByRole("button", { name: "Mark completed" }).click();
  await expect(page.locator(".admin-page-heading .admin-status")).toHaveText("COMPLETED");
  const history = page.getByRole("heading", { name: "Event history" }).locator("xpath=..");
  await expect(history.getByText("CHECKED IN", { exact: true })).toBeVisible();
  await expect(history.getByText("COMPLETED", { exact: true })).toBeVisible();
});
