import { useEffect, useRef } from "react";

import { usePointerLight } from "../hooks/usePointerLight";
import { useReducedMotion } from "../hooks/useReducedMotion";

/**
 * The atmosphere the whole product sits on.
 *
 * One fixed layer behind every route, mounted once above the router so it
 * survives navigation: the background does not restart when the page changes,
 * which is most of what makes a route change read as moving *within* something
 * rather than as loading a new document.
 *
 * It is built out of four things and no images, no video and no WebGL:
 *
 *   · three drifting fields of light, at durations that do not divide into each
 *     other (37s / 53s / 43s), so the composition never visibly repeats. Each
 *     is a single radial gradient moved by `transform` alone, which stays on
 *     the compositor and never repaints.
 *   · a light that follows the cursor, at the same low alpha, so the page
 *     answers the pointer without announcing that it is doing so.
 *   · a grain plate. Static, generated once by an SVG turbulence filter and
 *     rasterised by the browser, it is what stops large soft gradients from
 *     banding on a matte black canvas.
 *   · a vignette, which is the part that keeps all of the above from costing
 *     anything in legibility: the edges carry the colour and the centre, where
 *     the type is, stays near-black.
 *
 * Every colour comes from the existing tokens (ember and the navigation blue)
 * at alphas between 0.03 and 0.10. Nothing here introduces a hue the system did
 * not already have, and nothing here sits behind text at a strength that could
 * move a contrast ratio: the tokens' own AA margins are untouched.
 *
 * It costs nothing when nobody is looking. The drift pauses on
 * `visibilitychange`, so a backgrounded tab is not animating three composited
 * layers forever, and the whole element is not rendered at all under
 * `prefers-reduced-motion`.
 */
export function AmbientField() {
  const reduced = useReducedMotion();
  const ref = usePointerLight<HTMLDivElement>();
  const pausedRef = useRef<HTMLDivElement | null>(null);

  // A hidden tab keeps running its compositor animations. Pausing them is the
  // difference between an idle background tab costing nothing and costing a
  // steady trickle of GPU for a page nobody is looking at.
  useEffect(() => {
    if (reduced) return;
    const onVisibility = () => {
      pausedRef.current?.toggleAttribute("data-paused", document.hidden);
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [reduced]);

  // Under reduced motion there is nothing to render. Not a static version of
  // the field: the whole point of it is the drift, and a frozen gradient is
  // just an unexplained smudge behind the content.
  if (reduced) return null;

  return (
    <div
      className="ambient"
      aria-hidden="true"
      ref={(node) => {
        ref.current = node;
        pausedRef.current = node;
      }}
    >
      <div className="ambient__orb ambient__orb--ember" />
      <div className="ambient__orb ambient__orb--azure" />
      <div className="ambient__orb ambient__orb--deep" />
      <div className="ambient__cursor" />
      <div className="ambient__grain" />
      <div className="ambient__vignette" />
    </div>
  );
}
