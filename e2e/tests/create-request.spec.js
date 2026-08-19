const { test, expect } = require("@playwright/test");

test("requester can create and save a draft request", async ({ page }) => {
  await page.goto("/login");
  await page.fill("#email", "alice@example.com");
  await page.fill("#password", "password123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/requester/);

  await page.goto("/requester/new");

  const uniqueTitle = `E2E draft ${Date.now()}`;
  await page.fill("#title", uniqueTitle);
  await page.fill("#amount", "42.50");
  await page.selectOption("#category", "office_supplies");

  await page.getByRole("button", { name: "Save as draft" }).click();

  // shows a brief confirmation, then redirects to the new request's own detail page
  await expect(page.getByText("Saved. Redirecting…")).toBeVisible();
  await expect(page).toHaveURL(/\/requests\/[\w-]+$/);
  await expect(page.getByText(uniqueTitle)).toBeVisible();
});

test("submitting with a blank title shows a validation error, not a network error", async ({ page }) => {
  await page.goto("/login");
  await page.fill("#email", "alice@example.com");
  await page.fill("#password", "password123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/requester/);

  await page.goto("/requester/new");
  await page.fill("#amount", "10");
  await page.getByRole("button", { name: "Save as draft" }).click();

  await expect(page.getByText("Title is required.")).toBeVisible();
  // still on the form, nothing was actually submitted
  await expect(page).toHaveURL(/\/requester\/new/);
});
