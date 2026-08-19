// @ts-check
const { defineConfig, devices } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests",
  // parallel workers are fine against a local dev server, but a real
  // deployed backend has login rate limiting -- several tests logging in
  // at once from the same IP can trip it, so run serially against anything
  // other than localhost
  fullyParallel: !process.env.E2E_BASE_URL,
  workers: process.env.E2E_BASE_URL ? 1 : undefined,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
