/**
 * The four things you can do to a goal that already exists.
 *
 * None of them were possible: the page created goals and read them back, so
 * `current_amount` was fixed at creation, progress never moved, and the
 * goal-progress component of the health score was frozen at whatever the
 * first save produced.
 *
 * These assert on the request payloads, because that is where the behaviour
 * is. "Archive" sending `is_active: false` and "Edit" *not* sending it are
 * the same distinction the server draws between absence and a value, and
 * getting it backwards would silently un-archive a goal on every correction.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Goals } from "./Goals";
import type { Goal, Me } from "../api/types";

const USER: Me = {
  id: 1, email: "sam@example.com", telegram_id: null,
  locale: "en", risk_profile: "moderate", onboarded: true,
};

const LAPTOP: Goal = {
  id: 7, name: "Laptop", target_amount: 60_000_000, current_amount: 20_000_000,
  deadline: null, priority: 1, is_active: true,
  progress_pct: 33.3, estimated_completion: "2027-01-15",
};

const api = vi.hoisted(() => ({
  goals: [] as Goal[],
  updated: [] as { id: number; draft: Record<string, unknown> }[],
  deleted: [] as number[],
  created: [] as Record<string, unknown>[],
  listedActiveOnly: [] as (boolean | undefined)[],
}));

vi.mock("../api/goals", () => ({
  listGoals: (_id: number, options: { activeOnly?: boolean } = {}) => {
    api.listedActiveOnly.push(options.activeOnly);
    return Promise.resolve(
      options.activeOnly === false ? api.goals : api.goals.filter((g) => g.is_active),
    );
  },
  createGoal: (_id: number, draft: Record<string, unknown>) => {
    api.created.push(draft);
    return Promise.resolve({ ...LAPTOP, ...draft });
  },
  updateGoal: (id: number, draft: Record<string, unknown>) => {
    api.updated.push({ id, draft });
    return Promise.resolve({ ...LAPTOP, ...draft });
  },
  deleteGoal: (id: number) => {
    api.deleted.push(id);
    return Promise.resolve(undefined);
  },
}));

vi.mock("../auth/AuthContext", () => ({ useAuth: () => ({ user: USER }) }));

function renderGoals() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Goals />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function goalRow(name = "Laptop") {
  const cell = await screen.findByRole("rowheader", { name: new RegExp(name) });
  return within(cell.closest("tr") as HTMLElement);
}

beforeEach(() => {
  api.goals = [{ ...LAPTOP }];
  api.updated = [];
  api.deleted = [];
  api.created = [];
  api.listedActiveOnly = [];
  vi.restoreAllMocks();
});

describe("recording progress", () => {
  it("adds to what is already saved rather than replacing it", async () => {
    renderGoals();
    const row = await goalRow();

    fireEvent.change(row.getByPlaceholderText("Add saved"),
                     { target: { value: "5000000" } });
    fireEvent.click(row.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(api.updated).toHaveLength(1));
    // 20M already saved plus 5M, not 5M outright. The question arrives as
    // "what did I just put aside", not "what is the total now".
    expect(api.updated[0].draft).toMatchObject({ current_amount: 25_000_000 });
  });

  it("never records more than the target", async () => {
    renderGoals();
    const row = await goalRow();

    fireEvent.change(row.getByPlaceholderText("Add saved"),
                     { target: { value: "999000000" } });
    fireEvent.click(row.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(api.updated).toHaveLength(1));
    expect(api.updated[0].draft).toMatchObject({ current_amount: 60_000_000 });
  });

  it("does not send is_active, so the goal stays where it is", async () => {
    renderGoals();
    const row = await goalRow();

    fireEvent.change(row.getByPlaceholderText("Add saved"),
                     { target: { value: "1000000" } });
    fireEvent.click(row.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(api.updated).toHaveLength(1));
    expect(api.updated[0].draft).not.toHaveProperty("is_active");
  });

  it("refuses to submit nothing", async () => {
    renderGoals();
    const row = await goalRow();

    expect(row.getByRole("button", { name: "Add" })).toBeDisabled();
  });
});

describe("archiving", () => {
  it("sends is_active false", async () => {
    renderGoals();
    const row = await goalRow();

    fireEvent.click(row.getByRole("button", { name: "Archive" }));

    await waitFor(() => expect(api.updated).toHaveLength(1));
    expect(api.updated[0].draft).toMatchObject({ is_active: false });
  });

  it("offers to restore an archived goal instead", async () => {
    api.goals = [{ ...LAPTOP, is_active: false }];
    renderGoals();

    fireEvent.click(await screen.findByRole("checkbox", { name: /archived/i }));
    const row = await goalRow();

    fireEvent.click(row.getByRole("button", { name: "Restore" }));

    await waitFor(() => expect(api.updated).toHaveLength(1));
    expect(api.updated[0].draft).toMatchObject({ is_active: true });
  });

  it("says the word as well as dimming the row", async () => {
    api.goals = [{ ...LAPTOP, is_active: false }];
    renderGoals();

    fireEvent.click(await screen.findByRole("checkbox", { name: /archived/i }));

    // Opacity alone does not communicate state to everybody.
    expect(await screen.findByText(/archived/i, { selector: ".tag" })).toBeInTheDocument();
  });

  it("hides archived goals until asked", async () => {
    renderGoals();
    await goalRow();

    expect(api.listedActiveOnly.at(-1)).not.toBe(false);

    fireEvent.click(screen.getByRole("checkbox", { name: /archived/i }));

    await waitFor(() => expect(api.listedActiveOnly.at(-1)).toBe(false));
  });
});

describe("deleting", () => {
  it("asks before removing anything", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderGoals();
    const row = await goalRow();

    fireEvent.click(row.getByRole("button", { name: "Delete" }));

    expect(confirm).toHaveBeenCalled();
    expect(api.deleted).toEqual([]);
  });

  it("deletes once confirmed", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderGoals();
    const row = await goalRow();

    fireEvent.click(row.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(api.deleted).toEqual([7]));
  });

  it("points at archiving, which is the reversible one", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderGoals();
    const row = await goalRow();

    fireEvent.click(row.getByRole("button", { name: "Delete" }));

    expect(confirm.mock.calls[0][0]).toMatch(/archive/i);
    expect(confirm.mock.calls[0][0]).toMatch(/cannot be undone/i);
  });
});

describe("editing", () => {
  it("opens a form seeded with the goal", async () => {
    renderGoals();
    const row = await goalRow();

    fireEvent.click(row.getByRole("button", { name: "Edit" }));

    expect(await screen.findByRole("heading", { name: /edit laptop/i })).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveValue("Laptop");
    expect(screen.getByLabelText("Target amount")).toHaveValue("60000000");
  });

  it("sends the edited fields and no is_active", async () => {
    renderGoals();
    fireEvent.click((await goalRow()).getByRole("button", { name: "Edit" }));

    fireEvent.change(await screen.findByLabelText("Name"),
                     { target: { value: "Laptop (2026)" } });
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(api.updated).toHaveLength(1));
    expect(api.updated[0].draft).toMatchObject({ name: "Laptop (2026)" });
    expect(api.updated[0].draft).not.toHaveProperty("is_active");
  });

  it("can be abandoned", async () => {
    renderGoals();
    fireEvent.click((await goalRow()).getByRole("button", { name: "Edit" }));

    fireEvent.click(await screen.findByRole("button", { name: /cancel/i }));

    expect(await screen.findByRole("heading", { name: /add a goal/i })).toBeInTheDocument();
    expect(api.updated).toEqual([]);
  });

  it("refuses a target of zero", async () => {
    renderGoals();
    fireEvent.click((await goalRow()).getByRole("button", { name: "Edit" }));

    fireEvent.change(await screen.findByLabelText("Target amount"),
                     { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/target above zero/i);
    expect(api.updated).toEqual([]);
  });
});

describe("adding", () => {
  it("still works, with an unreadable amount treated as zero", async () => {
    renderGoals();
    await goalRow();

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Phone" } });
    fireEvent.change(screen.getByLabelText("Target amount"),
                     { target: { value: "10,000,000" } });
    fireEvent.change(screen.getByLabelText("Saved so far"),
                     { target: { value: "12a" } });
    fireEvent.click(screen.getByRole("button", { name: /add goal/i }));

    await waitFor(() => expect(api.created).toHaveLength(1));
    expect(api.created[0]).toMatchObject({
      name: "Phone", target_amount: 10_000_000, current_amount: 0,
    });
  });
});
