/**
 * The spending history panel.
 *
 * The one that matters is the gap note. The API leaves unrecorded months out
 * rather than sending zeros, so a reader who assumes a dense series will read
 * a missing month as a month of no spending. The note is the only thing
 * standing between the data and that misreading, and `hasGaps` decides
 * whether it appears.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ExpenseHistory, hasGaps, monthLabel } from "./ExpenseHistory";
import type { ExpenseHistory as History, ExpensePeriod } from "../api/types";

const api = vi.hoisted(() => ({
  asked: [] as number[],
  history: null as History | null,
  fail: null as Error | null,
}));

vi.mock("../api/expenses", () => ({
  getExpenseHistory: (months: number) => {
    api.asked.push(months);
    if (api.fail) return Promise.reject(api.fail);
    return Promise.resolve(api.history);
  },
}));

const BLANK = {
  housing: 0, food: 0, transportation: 0, education: 0,
  bills: 0, entertainment: 0, shopping: 0, other: 0,
};

function period(name: string, total: number, essential = total): ExpensePeriod {
  return {
    period: name,
    expenses: { ...BLANK, food: total },
    total,
    essential_total: essential,
  };
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ExpenseHistory />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.asked = [];
  api.fail = null;
  api.history = {
    months: 12,
    periods: [period("2026-01", 1200, 900), period("2026-02", 1400, 1000)],
  };
});

describe("the series", () => {
  it("names each month in a form a person reads", async () => {
    renderPanel();

    expect(await screen.findByRole("rowheader", { name: "Jan 2026" })).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "Feb 2026" })).toBeInTheDocument();
  });

  it("shows the total and the essentials for each month", async () => {
    renderPanel();

    const row = (await screen.findByRole("rowheader", { name: "Jan 2026" }))
      .closest("tr") as HTMLElement;
    expect(within(row).getByText("1,200")).toBeInTheDocument();
    expect(within(row).getByText("900")).toBeInTheDocument();
  });

  it("asks for twelve months until told otherwise", async () => {
    renderPanel();

    await waitFor(() => expect(api.asked).toEqual([12]));
  });

  it("re-reads when the window changes", async () => {
    renderPanel();
    await screen.findByRole("rowheader", { name: "Jan 2026" });

    fireEvent.change(screen.getByLabelText(/show/i), { target: { value: "3" } });

    await waitFor(() => expect(api.asked).toContain(3));
  });

  it("says what to do when there is nothing yet", async () => {
    api.history = { months: 12, periods: [] };
    renderPanel();

    expect(await screen.findByText(/save your expenses/i)).toBeInTheDocument();
  });

  it("surfaces a failure rather than an empty table", async () => {
    api.fail = new Error("the server is unreachable");
    renderPanel();

    expect(await screen.findByText(/unreachable/i)).toBeInTheDocument();
  });
});

describe("gaps in the record", () => {
  it("warns when a month inside the span is missing", async () => {
    api.history = {
      months: 12,
      periods: [period("2026-01", 1200), period("2026-03", 1300)],
    };
    renderPanel();

    expect(await screen.findByText(/gap in the record/i)).toBeInTheDocument();
  });

  it("stays quiet when the months are consecutive", async () => {
    renderPanel();

    await screen.findByRole("rowheader", { name: "Jan 2026" });
    expect(screen.queryByText(/gap in the record/i)).toBeNull();
  });

  it("does not call a short history a gap", async () => {
    /** A user three months in has not "missed" the nine before they joined. */
    api.history = { months: 12, periods: [period("2026-02", 1200)] };
    renderPanel();

    await screen.findByRole("rowheader", { name: "Feb 2026" });
    expect(screen.queryByText(/gap in the record/i)).toBeNull();
  });
});

describe("hasGaps", () => {
  it.each([
    [["2026-01", "2026-02", "2026-03"], false],
    [["2026-01", "2026-03"], true],
    [["2025-11", "2025-12", "2026-01"], false],
    [["2025-11", "2026-01"], true],
    [["2026-01"], false],
    [[], false],
  ])("%s -> %s", (periods, expected) => {
    expect(hasGaps(periods as string[])).toBe(expected);
  });

  it("counts a December to January step as consecutive", () => {
    /** Year arithmetic on a `YYYY-MM` string is where this would break. */
    expect(hasGaps(["2025-12", "2026-01"])).toBe(false);
  });
});

describe("monthLabel", () => {
  it.each([
    ["2026-01", "Jan 2026"],
    ["2026-12", "Dec 2026"],
    ["2026-09", "Sep 2026"],
  ])("%s -> %s", (period, expected) => {
    expect(monthLabel(period)).toBe(expected);
  });

  it("returns the raw value rather than undefined for something unexpected", () => {
    expect(monthLabel("2026-13")).toBe("2026-13");
  });
});
