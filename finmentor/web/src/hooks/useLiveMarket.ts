/**
 * The public live-price WebSocket (app/api/routes/market_live.py).
 *
 * Connection states are real, not decorative: "live" only appears once the
 * server has actually said so, and a dropped socket reconnects with backoff
 * instead of silently going stale. `status` is what the UI is required to
 * show truthfully — never claim "live" data that is not.
 */
import { useEffect, useRef, useState } from "react";

export type ConnectionStatus = "connecting" | "live" | "reconnecting" | "disconnected";

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
  const base: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
  return `${base.replace(/^http/, "ws")}/api/market/live`;
}

export function useLiveMarket() {
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
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
          if (payload.status === "live" || payload.status === "reconnecting") {
            setStatus(payload.status);
          }
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

  return { status, ticks, history };
}
