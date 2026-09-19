import { expect, test } from "@playwright/test";

const login = async (page) => {
  await page.goto("/");
  await page.getByPlaceholder("user").fill("user");
  await page.getByPlaceholder("password").fill("password");
  await page.getByRole("button", { name: /sign in/i }).click();
};

const getColumnByTitle = (page, title: string) =>
  page.locator('[data-testid^="column-"]').filter({
    has: page.locator(`input[aria-label="Column title"][value="${title}"]`),
  });

test("loads the kanban board", async ({ page }) => {
  await login(page);
  await expect(page.getByRole("heading", { name: "Kanban Studio" })).toBeVisible();
  await expect(page.locator('[data-testid^="column-"]')).toHaveCount(5);
});

test("adds a card to a column", async ({ page }) => {
  await login(page);
  const firstColumn = getColumnByTitle(page, "Backlog");
  await firstColumn.getByRole("button", { name: /add a card/i }).click();
  await firstColumn.getByPlaceholder("Card title").fill("Playwright card");
  await firstColumn.getByPlaceholder("Details").fill("Added via e2e.");
  await firstColumn.getByRole("button", { name: /add card/i }).click();
  await expect(firstColumn.getByText("Playwright card").first()).toBeVisible();
});

test("moves a card between columns", async ({ page }) => {
  await login(page);
  const card = page.locator("article", { hasText: "Align roadmap themes" }).first();
  const targetColumn = getColumnByTitle(page, "Review");
  await expect(card).toBeVisible();
  const cardBox = await card.boundingBox();
  const columnBox = await targetColumn.boundingBox();
  if (!cardBox || !columnBox) {
    throw new Error("Unable to resolve drag coordinates.");
  }

  await page.mouse.move(
    cardBox.x + cardBox.width / 2,
    cardBox.y + cardBox.height / 2
  );
  await page.mouse.down();
  await page.mouse.move(
    columnBox.x + columnBox.width / 2,
    columnBox.y + 120,
    { steps: 12 }
  );
  await page.mouse.up();
  await expect(targetColumn.getByText("Align roadmap themes")).toBeVisible();
});

test("edits a card", async ({ page }) => {
  await login(page);
  const card = page.locator("article", { hasText: "Align roadmap themes" }).first();
  const testId = await card.getAttribute("data-testid");
  await card.getByRole("button", { name: /edit align roadmap themes/i }).click();

  // Re-locate by the stable data-testid: once editing starts, "Align roadmap
  // themes" moves into an <input value>, which isn't part of textContent, so
  // the hasText-filtered locator above would never resolve again.
  const editingCard = page.locator(`[data-testid="${testId}"]`);
  await editingCard.getByLabel("Card title").fill("Edited roadmap themes");
  await editingCard.getByLabel("Card details").fill("Updated from e2e.");
  await editingCard.getByRole("button", { name: /^save$/i }).click();
  await expect(page.getByText("Edited roadmap themes")).toBeVisible();
  await expect(page.getByText("Updated from e2e.")).toBeVisible();
});
