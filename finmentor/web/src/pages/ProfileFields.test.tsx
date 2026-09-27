/**
 * Two fields the profile form used to lose, asserted on the payload it sends.
 *
 * Asserting what is rendered is not enough here. Both defects were about what
 * the form *transmitted*: `income_type` was seeded from a hard-coded "fixed"
 * rather than from the API, and `planned_budget` was never in the payload at
 * all, so the server's replace semantics erased it. Both look completely
 * normal on screen. So these tests capture the request body.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Profile } from "./Profile";
import type { FinancialTwin, Me } from "../api/types";

const USER: Me = {
  id: 1, email: "sam@example.com", telegram_id: null,
  locale: "en", risk_profile: "moderate", onboarded: true,
};

const TWIN: FinancialTwin = {
  income: 30_000_000,
  income_type: "variable",
  expenses: {
    housing: 8_000_000, food: 5_000_000, transportation: 2_000_000,
    education: 0, bills: 0, entertainment: 0, shopping: 0, other: 0,
  },
  planned_budget: null,
  monthly_expenses: 15_000_000,
  essential_monthly_expenses: 15_000_000,
  monthly_savings: 15_000_000,
  current_savings: 45_000_000,
  debt: 0,
  monthly_debt_payment: 0,
  emergency_fund: 30_000_000,
  savings_rate: 0.5,
  emergency_months: 2,
  risk_profile: "moderate",
};

const api = vi.hoisted(() => ({
  twin: null as FinancialTwin | null,
  saved: [] as unknown[],
}));

vi.mock("../api/profile", () => ({
  getProfile: () => Promise.resolve(api.twin),
  saveProfile: (_id: number, payload: unknown) => {
    api.saved.push(payload);
    return Promise.resolve(api.twin);
  },
}));

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: USER }),
}));

function renderProfile() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Profile />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function save() {
  fireEvent.click(screen.getByRole("button", { name: /save/i }));
  await waitFor(() => expect(api.saved.length).toBeGreaterThan(0));
  return api.saved.at(-1) as Record<string, unknown>;
}

beforeEach(() => {
  api.twin = { ...TWIN };
  api.saved = [];
});

describe("income_type", () => {
  it("seeds the select from the API rather than defaulting to fixed", async () => {
    renderProfile();

    const select = await screen.findByLabelText(/is it steady/i);
    expect(select).toHaveValue("variable");
  });

  it("sends back the value it was given when nothing is touched", async () => {
    renderProfile();
    await screen.findByLabelText(/is it steady/i);

    // The exact defect: opening the page and pressing Save, with no edits,
    // used to write "fixed" over whatever the user had chosen.
    expect(await save()).toMatchObject({ income_type: "variable" });
  });

  it("sends a changed value", async () => {
    renderProfile();
    const select = await screen.findByLabelText(/is it steady/i);

    fireEvent.change(select, { target: { value: "mixed" } });

    expect(await save()).toMatchObject({ income_type: "mixed" });
  });
});

describe("planned_budget", () => {
  it("is off when the user has no plan", async () => {
    renderProfile();

    const toggle = await screen.findByRole("checkbox", { name: /monthly plan/i });
    expect(toggle).not.toBeChecked();
    expect(screen.queryByLabelText("Housing")).toBeTruthy();   // the spending field
  });

  it("sends null when there is no plan, which leaves the stored one alone", async () => {
    renderProfile();
    await screen.findByRole("checkbox", { name: /monthly plan/i });

    // `null` is explicit, not absent: the repository reads the two
    // differently, and this form always has an opinion about the plan.
    expect(await save()).toMatchObject({ planned_budget: null });
  });

  it("seeds a new plan from what the user actually spends", async () => {
    renderProfile();
    const toggle = await screen.findByRole("checkbox", { name: /monthly plan/i });

    fireEvent.click(toggle);

    const payload = await save();
    expect(payload.planned_budget).toMatchObject({
      housing: 8_000_000, food: 5_000_000, transportation: 2_000_000,
    });
  });

  it("sends an edited plan", async () => {
    renderProfile();
    fireEvent.click(await screen.findByRole("checkbox", { name: /monthly plan/i }));

    fireEvent.change(screen.getByLabelText("Housing", { selector: "#plan-housing" }), {
      target: { value: "7000000" },
    });

    const payload = await save();
    expect(payload.planned_budget).toMatchObject({ housing: 7_000_000 });
  });

  it("shows an existing plan and keeps it on save", async () => {
    api.twin = {
      ...TWIN,
      planned_budget: { ...TWIN.expenses, housing: 7_000_000 },
    };
    renderProfile();

    const toggle = await screen.findByRole("checkbox", { name: /monthly plan/i });
    expect(toggle).toBeChecked();
    expect(await save()).toMatchObject({
      planned_budget: expect.objectContaining({ housing: 7_000_000 }),
    });
  });

  it("clears the plan when the user turns it off", async () => {
    api.twin = { ...TWIN, planned_budget: { ...TWIN.expenses } };
    renderProfile();

    fireEvent.click(await screen.findByRole("checkbox", { name: /monthly plan/i }));

    expect(await save()).toMatchObject({ planned_budget: null });
  });
});

describe("numeric input", () => {
  it("treats an unreadable amount as zero rather than sending NaN", async () => {
    renderProfile();
    const housing = await screen.findByLabelText("Housing", {
      selector: "#field-housing",
    });

    fireEvent.change(housing, { target: { value: "12a" } });

    // NaN serialises as null, and the API answers 422 "Input should be a
    // valid number" for a typo — an error about a field the user cannot see
    // a problem with.
    const payload = await save() as { expenses: Record<string, number> };
    expect(payload.expenses.housing).toBe(0);
  });
});
