import { useEffect, useState } from "react";

/**
 * Whether the reader has asked for less movement.
 *
 * Every JS-driven device in the cinematic layer has to check this, because a
 * media query cannot stop a rAF loop, a pointer listener or a timer. The
 * existing hooks each read `matchMedia` once at mount; this one also *listens*,
 * so a reader who flips the OS setting mid-session gets the change without a
 * reload. That matters more now than it did: before, the only thing the
 * preference switched off was a handful of entrances. Now it switches off an
 * ambient field that never stops on its own.
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() =>
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(query.matches);
    onChange();
    // Safari < 14 only has the deprecated spelling.
    if (query.addEventListener) {
      query.addEventListener("change", onChange);
      return () => query.removeEventListener("change", onChange);
    }
    query.addListener(onChange);
    return () => query.removeListener(onChange);
  }, []);

  return reduced;
}
