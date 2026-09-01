const { defineConfig, devices } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:5052",
    timezoneId: "Asia/Kolkata",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "python -m scripts.e2e_server",
    url: "http://127.0.0.1:5052/",
    reuseExistingServer: false,
    timeout: 30_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], contextOptions: { timezoneId: "Asia/Kolkata" } },
    },
    {
      name: "firefox",
      testMatch: /quality\.spec\.js/,
      grep: /cross-browser/,
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "webkit",
      testMatch: /quality\.spec\.js/,
      grep: /cross-browser/,
      use: { ...devices["Desktop Safari"] },
    },
    {
      name: "mobile-chrome",
      testMatch: /quality\.spec\.js/,
      grep: /mobile/,
      use: { ...devices["Pixel 7"] },
    },
  ],
});
