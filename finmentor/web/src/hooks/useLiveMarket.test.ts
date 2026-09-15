/**
 * The client half of the live feed: reconnecting, and seeding the chart.
 *
 * The hub is covered on the server (tests/unit/test_market_live.py) and the
 * three feed states are covered through the page (Landing.test.tsx). What
 * neither of those touches is what this hook does when the connection drops,
 * which is the failure a long-running tab actually meets: a laptop that slept,
 * a proxy that timed the socket out, an API that restarted under it.
 *
 * The socket is a stub driven by hand. `fetch` is stubbed too, because the
 * seed is a real request through the API client and its failure path is one
 * of the things being asserted.
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useLiveMarket } from "./useLiveMarket";

let sockets: FakeSocket[] = [];

class FakeSocket {
  static readonly OPEN = 1;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn(() => this.onclose?.());

  constructor(readonly url: string) {
    sockets.push(this);
  }

  deliver(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }

  /** The server going away, as the browser reports it. */
  drop() {
    this.onclose?.();
  }
}

const tick = (symbol: string, price: number) => ({
  symbol, price_usd: price, change_24h_pct: 1, as_of: 1,
});

const SNAPSHOT = {
  type: "snapshot",
  status: "live",
  source: "live",
  ticks: { BTC: tick("BTC", 61000) },
};

/** A series the public endpoint would return. */
function seedResponse(points: { date: string; close: number }[]) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ symbol: "BTC", points, disclaimer: "not advice" }),
  };
}

beforeEach(() => {
  sockets = [];
  vi.stubGlobal("WebSocket", FakeSocket);
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("no api in this test")));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("connecting", () => {
  it("derives the socket URL from the page's own origin", () => {
    renderHook(() => useLiveMarket());

    // With no VITE_API_BASE_URL the API is this origin (the dev proxy in
    // development, FastAPI serving the SPA in production), and http becomes
    // ws. jsdom serves the app from localhost:5173.
    expect(sockets[0].url).toBe("ws://localhost:5173/api/market/live");
  });

  it("reports live only once the server has said so", () => {
    const { result } = renderHook(() => useLiveMarket());
    expect(result.current.status).toBe("connecting");

    act(() => sockets[0].deliver(SNAPSHOT));

    expect(result.current.status).toBe("live");
    expect(result.current.ticks.BTC.price_usd).toBe(61000);
  });

  it("appends later ticks to the history it is building", () => {
    const { result } = renderHook(() => useLiveMarket());

    act(() => sockets[0].deliver(SNAPSHOT));
    act(() => sockets[0].deliver({
      type: "ticks", status: "live", source: "live", ticks: { BTC: tick("BTC", 61500) },
    }));

    expect(result.current.history.BTC.map((point) => point.price_usd))
      .toEqual([61000, 61500]);
  });

  it("drops a malformed frame instead of falling over", () => {
    const { result } = renderHook(() => useLiveMarket());
    act(() => sockets[0].deliver(SNAPSHOT));

    act(() => sockets[0].onmessage?.({ data: "{not json" }));

    expect(result.current.status).toBe("live");
    expect(result.current.ticks.BTC.price_usd).toBe(61000);
  });
});

describe("reconnecting", () => {
  beforeEach(() => vi.useFakeTimers());

  it("comes back after a drop, and says so while it is away", () => {
    const { result } = renderHook(() => useLiveMarket());
    act(() => sockets[0].deliver(SNAPSHOT));

    act(() => sockets[0].drop());
    expect(result.current.status).toBe("reconnecting");
    expect(sockets).toHaveLength(1);           // waits first, does not hammer

    act(() => vi.advanceTimersByTime(1500));
    expect(sockets).toHaveLength(2);

    act(() => sockets[1].deliver(SNAPSHOT));
    expect(result.current.status).toBe("live");
  });

  it("backs off, so a server that is down is not hammered", () => {
    renderHook(() => useLiveMarket());

    // 1.5s, then 3s, then 6s: each attempt waits twice as long as the last.
    act(() => sockets[0].drop());
    act(() => vi.advanceTimersByTime(1500));
    expect(sockets).toHaveLength(2);

    act(() => sockets[1].drop());
    act(() => vi.advanceTimersByTime(1500));
    expect(sockets, "second retry waited only the first delay").toHaveLength(2);
    act(() => vi.advanceTimersByTime(1500));
    expect(sockets).toHaveLength(3);

    act(() => sockets[2].drop());
    act(() => vi.advanceTimersByTime(5999));
    expect(sockets).toHaveLength(3);
    act(() => vi.advanceTimersByTime(1));
    expect(sockets).toHaveLength(4);
  });

  it("caps the wait, so a tab left open overnight still recovers", () => {
    renderHook(() => useLiveMarket());

    for (let attempt = 0; attempt < 8; attempt += 1) {
      act(() => sockets[sockets.length - 1].drop());
      act(() => vi.advanceTimersByTime(60_000));
    }
    const settled = sockets.length;

    act(() => sockets[settled - 1].drop());
    // 20s is the ceiling: without one, doubling would put the ninth retry
    // minutes away and the tab would look dead long after the server was back.
    act(() => vi.advanceTimersByTime(20_000));

    expect(sockets).toHaveLength(settled + 1);
  });

  it("stops entirely once the page is gone", () => {
    const { unmount } = renderHook(() => useLiveMarket());
    const socket = sockets[0];

    unmount();

    expect(socket.close).toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(60_000));
    expect(sockets, "a closed socket reconnected after unmount").toHaveLength(1);
  });
});

describe("seeding the chart", () => {
  it("puts the cached series in front of the ticks that arrived meanwhile", async () => {
    vi.mocked(fetch).mockResolvedValue(
      seedResponse([{ date: "2026-09-01", close: 60000 }]) as unknown as Response);

    const { result } = renderHook(() => useLiveMarket(["BTC"]));
    act(() => sockets[0].deliver(SNAPSHOT));

    await waitFor(() =>
      expect(result.current.history.BTC?.map((point) => point.price_usd))
        .toEqual([60000, 61000]));
  });

  it("asks once, however many times the hook re-renders", async () => {
    vi.mocked(fetch).mockResolvedValue(seedResponse([]) as unknown as Response);

    const { rerender } = renderHook(() => useLiveMarket(["BTC"]));
    act(() => sockets[0].deliver(SNAPSHOT));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));

    rerender();
    rerender();

    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("does not ask at all when the server says the feed is off", async () => {
    const { result } = renderHook(() => useLiveMarket(["BTC"]));

    act(() => sockets[0].deliver({
      type: "snapshot", status: "off", source: "off", ticks: {},
    }));

    await waitFor(() => expect(result.current.status).toBe("off"));
    // With no feed the panel draws no chart, so a series for it is a request
    // nobody reads.
    expect(fetch).not.toHaveBeenCalled();
  });

  it("is silent when the seed fails", async () => {
    // fetch rejects by default here, which is the offline path in the client.
    const { result } = renderHook(() => useLiveMarket(["BTC"]));
    act(() => sockets[0].deliver(SNAPSHOT));

    await waitFor(() => expect(fetch).toHaveBeenCalled());

    // The chart is an enhancement; the price above it is the thing that
    // matters, and it is still there.
    expect(result.current.status).toBe("live");
    expect(result.current.history.BTC.map((point) => point.price_usd)).toEqual([61000]);
  });
});
