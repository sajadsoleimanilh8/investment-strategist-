/**
 * The asset switcher, from the keyboard.
 *
 * It is tested here rather than in Playwright because the e2e suite runs with
 * `MARKET_LIVE_SOURCE=off`, where there is deliberately no switcher to press.
 * The feed is a stubbed WebSocket: the page's own socket, driven by hand, so
 * what is under test is the real component reacting to a real frame.
 *
 * The regression this exists for: the tabs looked like a tab widget and
 * behaved like three unrelated buttons. Every one was in the page's tab
 * order, the arrow keys did nothing, and nothing claimed to be the panel they
 * controlled.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Landing } from "./Landing";

let sockets: FakeSocket[] = [];

class FakeSocket {
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();

  constructor() {
    sockets.push(this);
  }

  /** Stand in for the server pushing a frame. */
  deliver(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
}

const SNAPSHOT = {
  type: "snapshot",
  status: "live",
  source: "live",
  ticks: {
    BTC: { symbol: "BTC", price_usd: 61000, change_24h_pct: 1.2, as_of: 1 },
    ETH: { symbol: "ETH", price_usd: 2400, change_24h_pct: -0.4, as_of: 1 },
    SOL: { symbol: "SOL", price_usd: 140, change_24h_pct: 3.1, as_of: 1 },
  },
};

beforeEach(() => {
  sockets = [];
  vi.stubGlobal("WebSocket", FakeSocket);
  // The sparkline seed is an enhancement and fails silently by design.
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("no api in this test")));
  vi.stubGlobal("IntersectionObserver", class {
    observe() {}
    disconnect() {}
    unobserve() {}
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function renderLive() {
  render(<MemoryRouter><Landing /></MemoryRouter>);
  // The frame arrives from outside React, exactly as it does in the browser;
  // `act` is what tells the test renderer to flush what it caused.
  act(() => sockets[0].deliver(SNAPSHOT));
  await waitFor(() => expect(screen.getAllByRole("tab")).toHaveLength(3));
  return screen.getAllByRole("tab");
}

describe("the asset switcher", () => {
  it("puts one tab stop in the page, not three", async () => {
    const tabs = await renderLive();

    // Roving tabindex: Tab moves past the whole group, and the arrows move
    // inside it. Three stops would mean tabbing through the switcher to get
    // to the rest of the page.
    expect(tabs.map((tab) => tab.tabIndex)).toEqual([0, -1, -1]);
  });

  it("names the panel each tab controls", async () => {
    const tabs = await renderLive();
    const panel = screen.getByRole("tabpanel");

    expect(tabs[0]).toHaveAttribute("aria-controls", panel.id);
    expect(panel).toHaveAttribute("aria-labelledby", tabs[0].id);
  });

  it("moves with the arrow keys, and the price moves with it", async () => {
    const tabs = await renderLive();
    tabs[0].focus();

    fireEvent.keyDown(document.activeElement!, { key: "ArrowRight" });

    const afterRight = screen.getAllByRole("tab");
    expect(afterRight[1]).toHaveAttribute("aria-selected", "true");
    expect(afterRight[1]).toHaveFocus();
    expect(screen.getByText(/2,400/)).toBeInTheDocument();
  });

  it("wraps at both ends", async () => {
    const tabs = await renderLive();
    tabs[0].focus();

    fireEvent.keyDown(document.activeElement!, { key: "ArrowLeft" });
    expect(screen.getAllByRole("tab")[2]).toHaveFocus();

    fireEvent.keyDown(document.activeElement!, { key: "ArrowRight" });
    expect(screen.getAllByRole("tab")[0]).toHaveFocus();
  });

  it("jumps to the ends with Home and End", async () => {
    const tabs = await renderLive();
    tabs[0].focus();

    fireEvent.keyDown(document.activeElement!, { key: "End" });
    expect(screen.getAllByRole("tab")[2]).toHaveFocus();

    fireEvent.keyDown(document.activeElement!, { key: "Home" });
    expect(screen.getAllByRole("tab")[0]).toHaveFocus();
  });
});

describe("the market panel", () => {
  it("shows no price at all when the server says the feed is off", async () => {
    render(<MemoryRouter><Landing /></MemoryRouter>);
    act(() => sockets[0].deliver({ type: "snapshot", status: "off", source: "off", ticks: {} }));

    await waitFor(() =>
      expect(screen.getByText(/no market connection/i)).toBeInTheDocument());
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
    expect(screen.getByText(/no market data is shown here/i)).toBeInTheDocument();
  });

  it("labels a synthetic feed as demo data", async () => {
    render(<MemoryRouter><Landing /></MemoryRouter>);
    act(() => sockets[0].deliver({ ...SNAPSHOT, source: "mock" }));

    await waitFor(() => expect(screen.getByText("Demo data")).toBeInTheDocument());
    // And the headline stops promising something it is not showing.
    expect(screen.getByRole("heading", { name: /demo prices, clearly labelled/i }))
      .toBeInTheDocument();
    expect(screen.getByText(/synthetic prices/i)).toBeInTheDocument();
  });
});
