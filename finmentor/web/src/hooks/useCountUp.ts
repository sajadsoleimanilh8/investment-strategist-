import { useEffect, useRef, useState } from "react";

/**
 * Count a figure up to its value once, on arrival.
 *
 * Borrowed from Wise, and used for the same reason: a headline number that
 * counts reads as something that was *computed*, which is exactly what every
 * figure in this app is. A number that is simply printed reads as something
 * that was looked up.
 *
 * Three things keep it honest.
 *
 * It always lands on the exact value. The final frame assigns `to` directly
 * rather than whatever the easing produced at t=1, because a rounding error in
 * a money figure is not a rounding error, it is a wrong number on screen.
 *
 * It counts on the way *in* only. Once a figure has been shown, a later change
 * to it is a change the reader needs to see happen, not a two-second animation
 * they have to sit through — that is the tick flash's job, not this one.
 *
 * It does not run at all under prefers-reduced-motion, and a media query
 * cannot stop a rAF loop, so that is checked here in JS rather than left to
 * motion.css.
 */
export function useCountUp(to: number, durationMs = 900): number {
  const [value, setValue] = useState(to);
  // Only the first arrival animates; after that the figure tracks `to`.
  const hasCounted = useRef(false);

  useEffect(() => {
    if (hasCounted.current) {
      setValue(to);
      return;
    }
    hasCounted.current = true;

    if (
      !Number.isFinite(to) ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      setValue(to);
      return;
    }

    const from = 0;
    const start = performance.now();
    let frame = 0;

    const tick = (now: number) => {
      const elapsed = now - start;
      if (elapsed >= durationMs) {
        setValue(to);           // exact, not eased
        return;
      }
      // Decelerating, to match --ease-out: fast at first, settling at the end.
      const progress = 1 - (1 - elapsed / durationMs) ** 3;
      setValue(from + (to - from) * progress);
      frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [to, durationMs]);

  return value;
}
