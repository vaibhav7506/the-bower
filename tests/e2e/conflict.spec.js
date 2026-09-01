const { test, expect } = require("@playwright/test");
const { FIXED_CLOCK, prepareBooking, submitGuest } = require("./helpers");

test("two browser contexts cannot reserve the same scarce table", async ({ browser }) => {
  const firstContext = await browser.newContext({ timezoneId: "Asia/Kolkata" });
  const secondContext = await browser.newContext({ timezoneId: "Asia/Kolkata" });
  await firstContext.addInitScript(FIXED_CLOCK);
  await secondContext.addInitScript(FIXED_CLOCK);
  const first = await firstContext.newPage();
  const second = await secondContext.newPage();

  await Promise.all([
    prepareBooking(first, { date: "2026-09-09", partySize: "8", table: "Table 07" }),
    prepareBooking(second, { date: "2026-09-09", partySize: "8", table: "Table 07" }),
  ]);
  const firstForm = first.locator("[data-reservation-form]");
  const secondForm = second.locator("[data-reservation-form]");
  await firstForm.getByLabel("Name").fill("First Contender");
  await firstForm.getByLabel("Email").fill("first@example.com");
  await secondForm.getByLabel("Name").fill("Second Contender");
  await secondForm.getByLabel("Email").fill("second@example.com");
  await Promise.all([
    firstForm.getByRole("button", { name: "Confirm reservation" }).click(),
    secondForm.getByRole("button", { name: "Confirm reservation" }).click(),
  ]);

  await expect.poll(async () => Number(await first.locator("[data-reservation-success]").isVisible())
    + Number(await second.locator("[data-reservation-success]").isVisible())).toBe(1);
  const conflictMessages = await Promise.all([
    first.locator("[data-reservation-status]").textContent(),
    second.locator("[data-reservation-status]").textContent(),
  ]);
  expect(conflictMessages.filter((message) => message.includes("just been reserved"))).toHaveLength(1);
  const conflictedPage = conflictMessages[0].includes("just been reserved") ? first : second;
  await expect(conflictedPage.locator("[data-time-slots] [data-time]").first()).toBeVisible();

  await Promise.all([firstContext.close(), secondContext.close()]);
});
