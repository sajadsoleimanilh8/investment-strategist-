import { useEffect, useRef, useState } from "react";

/**
 * True while the observed element has scrolled off the *top* of the viewport.
 *
 * The sibling of `useInView`, and deliberately not the same hook: `useInView`
 * latches true and disconnects, because a section that has revealed itself is
 * done. This one has to keep answering, because it drives a state that has to
 * come back — the landing nav is transparent over the intro, opaque below it,
 * and transparent again when the reader scrolls back up.
 *
 * The direction check is the whole point. `!isIntersecting` alone is true both
 * above and below the viewport, so an element that has not been reached yet
 * would read the same as one already passed, and the nav would start out
 * opaque on a long page. `boundingClientRect.top < 0` is what separates them.
 *
 * Unlike a scroll listener this costs nothing per frame, so there is no
 * throttle to tune and no reduced-motion carve-out to make: the state change
 * is instantaneous either way, and whether it *animates* is CSS's decision.
 */
export function useScrolledPast<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [past, setPast] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    // The observer fires once on observe, so a page restored mid-scroll gets
    // the right answer on the first frame rather than after the first move.
    const observer = new IntersectionObserver(([entry]) => {
      setPast(!entry.isIntersecting && entry.boundingClientRect.top < 0);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return { ref, past };
}
