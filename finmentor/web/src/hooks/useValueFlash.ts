import { useEffect, useRef, useState } from "react";

/**
 * Light a value up in its own direction when it changes.
 *
 * This is the one device every trading surface shares — Robinhood, Bloomberg,
 * every broker terminal — and it exists because a number that updates in place
 * is a number nobody sees update. The flash is not decoration; it is the only
 * signal that the figure you are looking at is not the figure you read.
 *
 * The direction is carried by colour *and* by the fact that the value itself
 * changed, so nothing here is colour-only: the new number is on screen either
 * way, and the flash only says "look".
 *
 * Returns the class for motion.css to animate, or "" when nothing has changed
 * yet — the class is removed after the beat so a later change re-triggers it
 * rather than being swallowed by an animation that is already running.
 */
export function useValueFlash(value: number, durationMs = 420): string {
  const previous = useRef(value);
  const [direction, setDirection] = useState<"up" | "down" | null>(null);

  useEffect(() => {
    const before = previous.current;
    if (before === value) return;
    previous.current = value;

    setDirection(value > before ? "up" : "down");
    const id = window.setTimeout(() => setDirection(null), durationMs);
    return () => window.clearTimeout(id);
  }, [value, durationMs]);

  return direction ? `flash-${direction}` : "";
}
