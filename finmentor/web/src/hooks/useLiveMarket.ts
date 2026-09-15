/**
 * The public live-price WebSocket (app/api/routes/market_live.py).
 *
 * Connection states are real, not decorative: "live" only appears once the
 * server has actually said so, a dropped socket reconnects with backoff
 * instead of silently going stale, and "off" is a state the server declares
 * rather than one the client infers from silence. `status` and `source` are
 * what the UI is required to show truthfully — never claim "live" data that
 * is not, and never render a synthetic price without saying so.
 *
 * The chart's history comes from two places, kept apart on purpose. Live
 * ticks accumulate here as they arrive. The shape *before* the first tick is
 * seeded once from the cached daily series, so a first-time visitor sees a
 * real line instead of watching an empty chart for twenty seconds. Nothing
 * interpolates between the two: the seed is closes, the tail is ticks, and a
 * gap between them stays a gap.
 */
import { useEffect, useRef, useState } from "react";

import { API_BASE_URL } from "../api/client";
import { getPublicSeries } from "../api/market";

export type ConnectionStatus =
  | "connecting"
  | "live"
  | "reconnecting"
  | "disconnected"
  /** The server has no feed configured (DEMO_MODE, or MARKET_LIVE_SOURCE=off). */
  | "off";

/** Where the prices come from. `mock` must be labelled wherever it renders. */
export type FeedSource = "live" | "mock" | "off";

export interface Tick {
  symbol: string;
  price_usd: number;
  change_24h_pct: number | null;
  as_of: number;
}

const MAX_HISTORY = 120;
const RECONNECT_BASE_MS = 1500;
const RECONNECT_MAX_MS = 20_000;

function wsUrl(): string {
  // Same base as every other request (see API_BASE_URL): http becomes ws and
  // https becomes wss. An empty base means this origin, and the WebSocket
  // constructor wants an absolute URL, so that case is spelled out rather
  // than left to the browser to resolve.
  const base = API_BASE_URL
    || `${window.location.protocol === "https:" ? "https:" : "http:"}//${window.location.host}`;
  return `${base.replace(/^http/, "ws")}/api/market/live`;
}

export function useLiveMarket(symbols: readonly string[] = []) {
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [source, setSource] = useState<FeedSource>("live");
  const [ticks, setTicks] = useState<Record<string, Tick>>({});
  const [history, setHistory] = useState<Record<string, Tick[]>>({});

  const socketRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  const reconnectTimerRef = useRef<number | undefined>(undefined);
  const disposedRef = useRef(false);

  useEffect(() => {
    disposedRef.current = false;

    function applyTicks(incoming: Record<string, Tick>) {
      setTicks((prev) => ({ ...prev, ...incoming }));
      setHistory((prev) => {
        const next = { ...prev };
        for (const [symbol, tick] of Object.entries(incoming)) {
          const existing = next[symbol] ?? [];
          next[symbol] = [...existing, tick].slice(-MAX_HISTORY);
        }
        return next;
      });
    }

    function connect() {
      if (disposedRef.current) return;
      setStatus((s) => (s === "live" ? s : attemptRef.current === 0 ? "connecting" : "reconnecting"));

      let socket: WebSocket;
      try {
        socket = new WebSocket(wsUrl());
      } catch {
        setStatus("disconnected");
        return;
      }
      socketRef.current = socket;

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data as string);
          if (payload.status === "live" || payload.status === "reconnecting"
              || payload.status === "off") {
            setStatus(payload.status);
          }
          if (payload.source) setSource(payload.source);
          if (payload.ticks) applyTicks(payload.ticks);
        } catch {
          // A malformed frame is dropped, not fatal — the next one just works.
        }
      };

      socket.onclose = () => {
        if (disposedRef.current) return;
        attemptRef.current += 1;
        setStatus("reconnecting");
        const delay = Math.min(RECONNECT_BASE_MS * 2 ** (attemptRef.current - 1), RECONNECT_MAX_MS);
        reconnectTimerRef.current = window.setTimeout(connect, delay);
      };

      socket.onerror = () => {
        socket.close();
      };
    }

    connect();

    return () => {
      disposedRef.current = true;
      window.clearTimeout(reconnectTimerRef.current);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, []);

  // The seed. Once, and only once the server has confirmed a feed: `off` is
  // not the only status that means "no chart to seed", and neither is it the
  // first one seen — the hook starts at "connecting", so a guard against
  // `off` alone fires the request before the server has said anything, which
  // is how DEMO_MODE ended up fetching a series for a panel that renders no
  // chart. Waiting for "live" is the only status that actually answers the
  // question being asked.
  //
  // The dependency is the joined symbols rather than the array, because a
  // caller that maps its assets inline passes a new array every render, and
  // a re-render between the request and its response would otherwise run the
  // cleanup below and discard a seed that had already been paid for.
  const seededRef = useRef(false);
  const seedKey = symbols.join(",");
  useEffect(() => {
    if (seededRef.current || status !== "live" || seedKey === "") return;
    seededRef.current = true;

    let cancelled = false;
    Promise.all(
      seedKey.split(",").map(async (symbol) => {
        try {
          const series = await getPublicSeries(symbol);
          return [symbol, series.points] as const;
        } catch {
          return [symbol, []] as const;
        }
      }),
    ).then((seeds) => {
      if (cancelled) return;
      setHistory((prev) => {
        const next = { ...prev };
        for (const [symbol, points] of seeds) {
          if (points.length === 0) continue;
          const asTicks: Tick[] = points.map((point) => ({
            symbol,
            price_usd: point.close,
            change_24h_pct: null,
            as_of: Date.parse(point.date) / 1000,
          }));
          // Live ticks that arrived while this was in flight keep the tail:
          // the seed is history, and history goes in front.
          next[symbol] = [...asTicks, ...(next[symbol] ?? [])].slice(-MAX_HISTORY);
        }
        return next;
      });
    });

    return () => {
      cancelled = true;
    };
  }, [status, seedKey]);

  return { status, source, ticks, history };
}
