const { test, expect } = require("@playwright/test");
const fs = require("fs");
const path = require("path");
const os = require("os");

function makeFakeJpeg() {
  // same minimal-but-valid JPEG magic-byte pattern used in the backend's
  // own test suite -- just enough for the file-type check to pass
  const bytes = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff]), Buffer.alloc(20, 0x30)]);
  const filePath = path.join(os.tmpdir(), `e2e-receipt-${Date.now()}.jpg`);
  fs.writeFileSync(filePath, bytes);
  return filePath;
}

test("requester submits a request and a reviewer approves it end to end", async ({ page }) => {
  const uniqueTitle = `E2E approval test ${Date.now()}`;
  const receiptPath = makeFakeJpeg();

  await page.goto("/login");
  await page.fill("#email", "alice@example.com");
  await page.fill("#password", "password123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/requester/);

  await page.goto("/requester/new");
  await page.fill("#title", uniqueTitle);
  await page.fill("#amount", "35.00");
  await page.selectOption("#category", "office_supplies");
  await page.setInputFiles("#receipt", receiptPath);

  await page.getByRole("button", { name: "Submit for review" }).click();
  await expect(page).toHaveURL(/\/requests\/[\w-]+$/, { timeout: 5000 });

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login/);

  await page.goto("/login");
  await page.fill("#email", "rachel@example.com");
  await page.fill("#password", "password123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/reviewer/);

  await page.getByText(uniqueTitle).click();
  await expect(page.getByRole("heading", { name: uniqueTitle })).toBeVisible();

  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Request approved.")).toBeVisible();

  fs.unlinkSync(receiptPath);
});
