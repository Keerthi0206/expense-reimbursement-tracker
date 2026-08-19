const { test, expect } = require("@playwright/test");

test("login redirects a requester to the requester dashboard", async ({ page }) => {
  await page.goto("/login");
  await page.fill("#email", "alice@example.com");
  await page.fill("#password", "password123");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/requester/);
});

test("login redirects a reviewer to the reviewer dashboard", async ({ page }) => {
  await page.goto("/login");
  await page.fill("#email", "rachel@example.com");
  await page.fill("#password", "password123");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/reviewer/);
});

test("wrong password shows an error and does not redirect", async ({ page }) => {
  await page.goto("/login");
  await page.fill("#email", "alice@example.com");
  await page.fill("#password", "wrongpassword");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});
