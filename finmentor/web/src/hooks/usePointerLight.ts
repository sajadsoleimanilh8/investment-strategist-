import { useEffect, useRef } from "react";

import { useReducedMotion } from "./useReducedMotion";

/**
 * An ambient light that follows the cursor.
 *
 * Writes `--pointer-x` / `--pointer-y` as viewport pixels onto the element, and
 * `--pointer-idle` as 1/0 so the glow can fade out when the pointer leaves the
 * window rather than freezing wherever it was last seen.
 *
 * Separate from `useSurfaceField` because it is a different shape of problem:
 * that hook compares the pointer against many cached boxes, this one just
 * forwards the pointer itself to a single fixed element. It shares the two
 * rules that matter, though — the pointer never touches React state, and every
 * write is coalesced into one frame — because a `setState` on `pointermove`
 * re-renders a subtree sixty times a second and would make the cheapest effect
 * on the page the most expensive one.
 *
 * Coarse pointers are excluded. On a touch screen `pointermove` only fires
 * *during* a drag, so a cursor glow there is a light that appears under the
 * reader's thumb while they scroll and then stays there, which is worse than
 * not having it at all.
 */
export function usePointerLight<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const el = ref.current;
    if (!el || reduced) return;
    if (typeof window.matchMedia !== "function") return;
    if (!window.matchMedia("(pointer: fine)").matches) return;

    let frame = 0;
    let next: { x: number; y: number } | null = null;

    const write = () => {
      frame = 0;
      if (!next) return;
      el.style.setProperty("--pointer-x", `${next.x}px`);
      el.style.setProperty("--pointer-y", `${next.y}px`);
      el.style.setProperty("--pointer-idle", "1");
    };

    const onMove = (event: PointerEvent) => {
      next = { x: event.clientX, y: event.clientY };
      if (!frame) frame = requestAnimationFrame(write);
    };
    const onLeave = () => el.style.setProperty("--pointer-idle", "0");

    window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerleave", onLeave);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
    };
  }, [reduced]);

  return ref;
}
