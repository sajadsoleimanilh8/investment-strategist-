/**
 * The whole flow, in a real browser.
 *
 * The HTTP-level test already proves the API answers correctly. This proves
 * the *app* does: that the router guards what it should, the onboarding wizard
 * advances, TanStack Query invalidates the caches a mutation invalidates, and
 * the numbers the engine sent actually reach the screen.
 *
 * It runs against browser-default styling, which is the point of this phase —
 * so every locator here is by role, label or text, never by class. When the
 * visual design lands, none of these should need to change.
 */
import { expect, test } from "@playwright/test";

const PASSWORD = "a-long-enough-password";

/** A fresh account per run: signup is once-per-email, and this is not idempotent. */
const email = () => `e2e-${Date.now()}-${Math.floor(Math.random() * 1e4)}@example.com`;

const PROFILE = {
  income: "30000000",
  expenses: {
    housing: "8000000", food: "5000000", transportation: "2000000",
    bills: "1500000", education: "0", entertainment: "1000000",
    shopping: "1000000", other: "0",
  },
  savings: "45000000",
  debt: "12000000",
  debtPayment: "1500000",
  emergencyFund: "30000000",
};

test.describe("signup to dashboard", () => {
  test("a new user can sign up, onboard, and act on their numbers", async ({ page }) => {
    const address = email();

    // --- the guard, before anything else ---------------------------------
    // "/" is now the public landing page; the guard lives on "/dashboard".
    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();

    // --- signup ----------------------------------------------------------
    await page.getByRole("link", { name: /create one/i }).click();
    await page.getByLabel("Email").fill(address);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: /create account/i }).click();

    // Signing up lands on onboarding, not the dashboard: there are no numbers yet.
    await expect(page.getByRole("heading", { name: /set up your profile/i }))
      .toBeVisible();

    // --- onboarding: income ----------------------------------------------
    await page.getByLabel("Monthly income").fill(PROFILE.income);
    await page.getByLabel(/is it steady/i).selectOption("mixed");
    await page.getByRole("button", { name: "Next" }).click();

    // --- onboarding: spending --------------------------------------------
    await expect(page.getByText(/what goes out each month/i)).toBeVisible();
    for (const [category, amount] of Object.entries(PROFILE.expenses)) {
      const label = category[0].toUpperCase() + category.slice(1);
      await page.getByLabel(label, { exact: true }).fill(amount);
    }
    await page.getByRole("button", { name: "Next" }).click();

    // --- onboarding: position --------------------------------------------
    await expect(page.getByText(/where you stand/i)).toBeVisible();
    await page.getByLabel("Total savings").fill(PROFILE.savings);
    await page.getByLabel("Total debt").fill(PROFILE.debt);
    await page.getByLabel("Monthly debt payment").fill(PROFILE.debtPayment);
    await page.getByLabel("Emergency fund").fill(PROFILE.emergencyFund);
    await page.getByRole("button", { name: "Next" }).click();

    // --- onboarding: first goal ------------------------------------------
    await expect(page.getByText(/something to aim at/i)).toBeVisible();
    await page.getByLabel(/what are you saving for/i).fill("Laptop");
    await page.getByLabel(/what does it cost/i).fill("60000000");
    await page.getByLabel(/put aside so far/i).fill("20000000");
    await page.getByRole("button", { name: "Finish" }).click();

    // --- the dashboard ----------------------------------------------------
    // 62.3 is what the engine scores this exact profile — the same number the
    // API test and the bot flow assert. If the client ever starts computing
    // its own, this is where it shows.
    await expect(page.getByRole("heading", { name: /financial health\s+62\.3\s*\/ 100/i }))
      .toBeVisible();

    for (const component of ["Savings rate", "Emergency fund", "Debt load",
                             "Budget stability", "Goal progress"]) {
      await expect(page.getByRole("rowheader", { name: component })).toBeVisible();
    }

    await expect(page.getByText("Financial DNA")).toBeVisible();
    await expect(page.getByText("Laptop")).toBeVisible();

    // --- an action: what would a purchase do? -----------------------------
    await page.getByRole("link", { name: "Simulate" }).click();
    await page.getByLabel(/what it costs/i).fill("60000000");
    await page.getByRole("button", { name: /show me/i }).click();

    const purchase = page.getByRole("table").filter({ hasText: "Emergency cover" });
    await expect(purchase.getByRole("rowheader", { name: "Savings" })).toBeVisible();
    // Savings before -> after, from the engine: 45,000,000 -> 0.
    await expect(purchase.getByRole("cell", { name: "45,000,000" })).toBeVisible();

    // Consequences, never a verdict. The API sends none and the UI invents none.
    const body = (await page.locator("main").innerText()).toLowerCase();
    for (const verdict of ["you should buy", "do not buy", "advisable",
                           "i recommend", "good idea", "bad idea"]) {
      expect(body, `the decision view leaked a verdict: ${verdict}`)
        .not.toContain(verdict);
    }

    // --- a second action: the what-if -------------------------------------
    await page.getByLabel(/extra saved each month/i).fill("5000000");
    await page.getByRole("button", { name: /run it/i }).click();

    const whatIf = page.getByRole("table").filter({ hasText: "Saving each month" });
    await expect(whatIf.getByRole("cell", { name: "10,000,000" })).toBeVisible();
    await expect(whatIf.getByRole("cell", { name: "15,000,000" })).toBeVisible();

    // --- market, with no external API -------------------------------------
    await page.getByRole("link", { name: "Market" }).click();
    await expect(page.getByRole("heading", { name: /everything i track/i })).toBeVisible();
    await expect(page.getByRole("button", { name: "Add" }).first()).toBeVisible();
    await page.getByRole("button", { name: "Add" }).first().click();
    await expect(page.getByRole("button", { name: "Remove" })).toHaveCount(1);

    const market = page.getByRole("table").filter({ hasText: "7 days" });
    await expect(market).toBeVisible();
    await expect(market.locator(".delta-positive, .delta-negative").first()).toBeVisible();
    await expect(page.getByText(/not a prediction or personalised/i).first()).toBeVisible();

    // --- ask, with the model unreachable ----------------------------------
    // The API's webServer points OLLAMA_HOST at a closed port, so this is the
    // Phase 5 guarantee seen from a browser: the model is gone and the user
    // still gets their real figures, labelled as the deterministic answer.
    await page.getByRole("link", { name: "Ask" }).click();
    await page.getByLabel(/your question/i).fill("why is my health score what it is?");
    await page.getByRole("button", { name: "Ask" }).click();

    const answer = page.getByRole("article").first();
    await expect(answer).toBeVisible({ timeout: 30_000 });
    await expect(answer).toContainText("62.3");
    await expect(answer).toContainText(/model was unavailable/i);
  });

  test("a session survives a reload", async ({ page }) => {
    // The refresh token is the only thing in storage; if recovering from it
    // breaks, a reload logs the user out and this is the test that says so.
    const address = email();

    await page.goto("/signup");
    await page.getByLabel("Email").fill(address);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: /create account/i }).click();
    await expect(page.getByRole("heading", { name: /set up your profile/i }))
      .toBeVisible();

    await page.reload();

    await expect(page.getByRole("heading", { name: /set up your profile/i }))
      .toBeVisible();
    await expect(page.getByRole("heading", { name: /sign in/i })).not.toBeVisible();
  });

  test("signing out returns to the login page and stays there", async ({ page }) => {
    const address = email();

    await page.goto("/signup");
    await page.getByLabel("Email").fill(address);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: /create account/i }).click();
    await expect(page.getByRole("heading", { name: /set up your profile/i }))
      .toBeVisible();

    await page.getByRole("button", { name: /sign out/i }).click();
    await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();

    // The dashboard still demands a session; the public landing page at "/"
    // doesn't, so that's not a useful place to re-check the guard.
    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
  });
});
