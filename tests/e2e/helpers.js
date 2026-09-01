const { expect } = require("@playwright/test");

const FIXED_CLOCK = `
  const FixedDate = class extends Date {
    constructor(...args) { super(...(args.length ? args : ["2026-09-01T04:30:00.000Z"])); }
    static now() { return new Date("2026-09-01T04:30:00.000Z").valueOf(); }
  };
  Date = FixedDate;
`;

async function preparePage(page) {
  await page.addInitScript(FIXED_CLOCK);
  await page.goto("/");
  await page.evaluate(() => sessionStorage.setItem("bower_loader_seen", "true"));
  await page.reload();
  await expect(page.locator("[data-reservation-widget]")).toBeVisible();
}

async function prepareBooking(page, { date, partySize = "4", table = null }) {
  await preparePage(page);
  await page.locator("[data-party-size]").selectOption(partySize);
  await page.locator(`[data-date="${date}"]`).click();
  const firstTime = page.locator("[data-time-slots] [data-time]").first();
  await expect(firstTime).toBeVisible();
  await firstTime.click();
  if (table) {
    await page.getByLabel(/Select a table/).check();
    const tableButton = page.locator(`[data-table-name="${table}"]`);
    await expect(tableButton).toBeEnabled();
    await tableButton.click();
  }
  await expect(page.locator("[data-reservation-form]")).toBeVisible();
}

async function submitGuest(page, name, email) {
  const form = page.locator("[data-reservation-form]");
  await form.getByLabel("Name").fill(name);
  await form.getByLabel("Email").fill(email);
  await form.getByRole("button", { name: "Confirm reservation" }).click();
}

module.exports = { FIXED_CLOCK, preparePage, prepareBooking, submitGuest };
