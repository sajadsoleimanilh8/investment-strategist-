/**
 * The income panel, and mostly the sentence it shows.
 *
 * The suggestion must read as an observation the user can act on, never as a
 * change that has happened. These assert the wording as much as the wiring,
 * because the wording is the feature: the alternative design silently
 * rewrote "Is it steady?" and would have moved figures nobody asked to move.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { IncomeHistory, signalNote } from "./IncomeHistory";
import type { IncomeHistory as History, IncomeSignal } from "../api/types";

const api = vi.hoisted(() => ({
  asked: [] as number[],
  history: null as History | null,
  fail: null as Error | null,
}));

vi.mock("../api/income", () => ({
  getIncomeHistory: (months: number) => {
    api.asked.push(months);
    if (api.fail) return Promise.reject(api.fail);
    return Promise.resolve(api.history);
  },
}));

function signal(overrides: Partial<IncomeSignal> = {}): IncomeSignal {
  return {
    periods: 4, insufficient: false, mean: 3000, low: 2900, high: 3100,
    variation: 0.02, declared: "fixed", suggested: "fixed", disagrees: false,
    ...overrides,
  };
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <IncomeHistory />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.asked = [];
  api.fail = null;
  api.history = {
    months: 12,
    periods: [
      { period: "2026-01", amount: 3000 },
      { period: "2026-02", amount: 3100 },
    ],
    signal: signal(),
  };
});

describe("the series", () => {
  it("lists each recorded month", async () => {
    renderPanel();

    const row = (await screen.findByRole("rowheader", { name: "Jan 2026" }))
      .closest("tr") as HTMLElement;
    expect(within(row).getByText("3,000")).toBeInTheDocument();
  });

  it("re-reads when the window changes", async () => {
    renderPanel();
    await screen.findByRole("rowheader", { name: "Jan 2026" });

    fireEvent.change(screen.getByLabelText(/show/i), { target: { value: "6" } });

    await waitFor(() => expect(api.asked).toContain(6));
  });

  it("explains how the history fills when there is none", async () => {
    api.history = { months: 12, periods: [], signal: null };
    renderPanel();

    expect(await screen.findByText(/each time you save your profile/i))
      .toBeInTheDocument();
  });

  it("surfaces a failure", async () => {
    api.fail = new Error("the server is unreachable");
    renderPanel();

    expect(await screen.findByText(/unreachable/i)).toBeInTheDocument();
  });
});

describe("the suggestion", () => {
  it("says nothing when the records agree with what was declared", async () => {
    renderPanel();

    await screen.findByRole("rowheader", { name: "Jan 2026" });
    expect(screen.queryByText(/change it if the records are right/i)).toBeNull();
  });

  it("offers the change rather than making it", async () => {
    api.history!.signal = signal({
      declared: "fixed", suggested: "variable", disagrees: true, periods: 5,
    });
    renderPanel();

    const note = await screen.findByRole("status");
    expect(note).toHaveTextContent(/look variable/i);
    expect(note).toHaveTextContent(/set to steady/i);
    expect(note).toHaveTextContent(/nothing here changes it for you/i);
  });

  it("points at the field the user would change", async () => {
    api.history!.signal = signal({
      declared: "fixed", suggested: "variable", disagrees: true,
    });
    renderPanel();

    expect(await screen.findByRole("status"))
      .toHaveTextContent(/"Is it steady\?" above/i);
  });

  it("says how close it is to being able to tell", async () => {
    api.history!.signal = signal({ periods: 2, insufficient: true, suggested: null });
    renderPanel();

    expect(await screen.findByRole("status"))
      .toHaveTextContent(/2 months so far.*three is enough/i);
  });
});

describe("signalNote", () => {
  it("is silent without a signal", () => {
    expect(signalNote(null)).toBeNull();
    expect(signalNote(undefined)).toBeNull();
  });

  it("is silent when the two agree", () => {
    expect(signalNote(signal({ declared: "fixed", suggested: "fixed" }))).toBeNull();
  });

  it("counts one month in words a person would use", () => {
    const note = signalNote(signal({ periods: 1, insufficient: true, suggested: null }));
    expect(note).toContain("one month");
    expect(note).not.toContain("1 months");
  });

  it("never claims to have changed anything", () => {
    const note = signalNote(signal({
      declared: "variable", suggested: "fixed", disagrees: true,
    }))!;
    expect(note).toMatch(/change it if/i);
    expect(note).not.toMatch(/\b(updated|changed it|we have set|now set)\b/i);
  });

  it("translates every classification into plain words", () => {
    for (const [suggested, word] of [
      ["fixed", "steady"], ["variable", "variable"], ["mixed", "a mix"],
    ] as const) {
      const note = signalNote(signal({
        declared: suggested === "fixed" ? "variable" : "fixed",
        suggested, disagrees: true,
      }))!;
      expect(note).toContain(`look ${word}`);
    }
  });

  it("falls back to the raw value for a classification it does not know", () => {
    const note = signalNote(signal({
      declared: "fixed", suggested: "seasonal", disagrees: true,
    }))!;
    expect(note).toContain("look seasonal");
  });
});
