/**
 * The public landing page, with the market feed switched off.
 *
 * That is not an edge case here: the suite's API runs with
 * `MARKET_LIVE_SOURCE=off` (see playwright.config.ts) for the same reason
 * everything else in it runs with the model unreachable. The degraded path is
 * the one a demo, a cold start and a rate-limited provider all land on, and
 * it is the one this project can test without a paid key. The live path stays
 * a pre-deploy manual check (docs/PRE_DEPLOY.md).
 *
 * What it is checking is a promise rather than a layout: with no feed, the
 * page says so and shows no price. A synthetic number under a headline
 * reading "real prices, not a mockup" is the single worst thing this page
 * could do, so it is worth a test that would fail loudly if one appeared.
 *
 * Locators are by role and text, never by class, so a visual change does not
 * break them.
 */
import { expect, test } from "@playwright/test";

test.describe("landing", () => {
  test("says the feed is off instead of waiting forever", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: /understand the structure/i }))
      .toBeVisible();

    // The status line reports what the server said, and the server said off.
    await expect(page.getByRole("status")).toContainText(/feed off/i);
    await expect(page.getByText(/no market connection/i)).toBeVisible();

    // No price, and no asset switcher for prices that are not coming.
    await expect(page.getByRole("tablist", { name: /asset/i })).toHaveCount(0);
    await expect(page.locator(".live-price")).toHaveCount(0);

    // The disclaimer describes this state rather than a feed that is running.
    await expect(page.getByText(/no market data is shown here/i)).toBeVisible();
    await expect(page.getByText(/polled every 20s/i)).toHaveCount(0);
  });

  test("never shows a figure it did not receive", async ({ page }) => {
    await page.goto("/");

    const panel = page.getByRole("region", { name: /real prices|demo prices/i });
    await expect(panel).toBeVisible();
    // A dollar amount anywhere in the market panel with no feed connected
    // would mean something invented one.
    await expect(panel).not.toContainText(/\$\s?\d/);
  });

  test("both calls to action reach signup", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("link", { name: /^sign up$/i })).toBeVisible();
    await page.getByRole("link", { name: /create an account/i }).first().click();

    await expect(page).toHaveURL(/\/signup$/);
    await expect(page.getByRole("heading", { name: /create an account/i })).toBeVisible();
  });

  test("the signed-out pages offer a way back", async ({ page }) => {
    await page.goto("/login");

    await page.getByRole("link", { name: "FinMentor" }).click();

    await expect(page).toHaveURL(/\/$/);
  });
});
