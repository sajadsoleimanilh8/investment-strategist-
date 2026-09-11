/**
 * Capture the two screenshots the docs reference.
 *
 * Generated rather than pasted in: a screenshot committed by hand is stale the
 * first time a token changes, and nobody notices. `npm run screenshots`
 * regenerates both from the running app, so what the README shows is what the
 * app currently looks like.
 *
 * These are captures, not assertions — the flow itself is tested in
 * `flow.spec.ts`. They still fail loudly if the page never reaches the state
 * being photographed, because a screenshot of a blank page is worse than none.
 */
import { expect, test } from "@playwright/test";

const PASSWORD = "a-long-enough-password";
//: Relative to `web/`, where Playwright runs — so up one level into the
//: repo's own docs folder, not a second copy inside the frontend.
const SHOTS = "../docs/screenshots";

const PROFILE = {
  income: "30000000",
  expenses: {
    housing: "8000000", food: "5000000", transportation: "2000000",
    bills: "1500000", education: "0", entertainment: "1000000",
    shopping: "1000000", other: "0",
  },
  savings: "45000000", debt: "12000000",
  debtPayment: "1500000", emergencyFund: "30000000",
};

test.describe("screenshots", () => {
  test("dashboard and a delta", async ({ page }) => {
    const email = `shot-${Date.now()}@example.com`;

    await page.goto("/signup");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: /create account/i }).click();
    await expect(page.getByRole("heading", { name: /set up your profile/i })).toBeVisible();

    await page.getByLabel("Monthly income").fill(PROFILE.income);
    await page.getByLabel(/is it steady/i).selectOption("mixed");
    await page.getByRole("button", { name: "Next" }).click();

    for (const [category, amount] of Object.entries(PROFILE.expenses)) {
      await page.getByLabel(category[0].toUpperCase() + category.slice(1), { exact: true })
        .fill(amount);
    }
    await page.getByRole("button", { name: "Next" }).click();

    await page.getByLabel("Total savings").fill(PROFILE.savings);
    await page.getByLabel("Total debt").fill(PROFILE.debt);
    await page.getByLabel("Monthly debt payment").fill(PROFILE.debtPayment);
    await page.getByLabel("Emergency fund").fill(PROFILE.emergencyFund);
    await page.getByRole("button", { name: "Next" }).click();

    await page.getByLabel(/what are you saving for/i).fill("Laptop");
    await page.getByLabel(/what does it cost/i).fill("60000000");
    await page.getByLabel(/put aside so far/i).fill("20000000");
    await page.getByRole("button", { name: "Finish" }).click();

    // --- 1. the dashboard -------------------------------------------------
    await expect(page.getByRole("heading", { name: /financial health: 62\.3 \/ 100/i }))
      .toBeVisible();
    await expect(page.getByText("Financial DNA")).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/dashboard.png`, fullPage: true });

    // --- 2. the delta colours ---------------------------------------------
    // The market watchlist, not the simulator: `.delta-positive` and
    // `.delta-negative` are only applied to the 7d/30d percentages, so this is
    // the one screen where green and red actually appear. A capture of the
    // before/after tables would show the theme but not the delta tokens, which
    // is the thing worth photographing.
    await page.getByRole("link", { name: "Market" }).click();
    await expect(page.getByRole("heading", { name: /everything i track/i })).toBeVisible();
    // Wait for the list itself, not just its heading: the heading renders while
    // the assets query is still in flight, and a loop that checks for buttons
    // before they exist simply adds nothing.
    await expect(page.getByRole("button", { name: "Add" }).first()).toBeVisible();

    // Clicking one re-renders the list, so each button is re-located rather
    // than held from a stale list.
    for (let added = 0; added < 4; added += 1) {
      await page.getByRole("button", { name: "Add" }).first().click();
      await expect(page.getByRole("button", { name: "Remove" })).toHaveCount(added + 1);
    }

    const watchlist = page.getByRole("table").filter({ hasText: "7 days" });
    await expect(watchlist).toBeVisible();
    await expect(watchlist.locator(".delta-positive, .delta-negative").first())
      .toBeVisible();

    await page.screenshot({ path: `${SHOTS}/deltas.png`, fullPage: true });
  });
});
