import { useEffect } from "react";

import { useReducedMotion } from "./useReducedMotion";

/** Everything in this system that is shaped like a control. */
const CONTROL_SELECTOR =
  "button:not(:disabled), a.landing-btn, a.provider-button, a.landing-nav__cta";

/**
 * Everything that is already shaped like a card.
 *
 * `.app main > section` rather than a class the pages opt into, because
 * layout.css has *already* decided that a top-level `section` is a card — it is
 * the selector that gives them the surface, the radius and the halo. Matching
 * the same thing here means eleven pages gain the interaction without a single
 * one of them being edited, and a page that adds a twelfth panel gets it for
 * free. Only top-level: `section:has(> section)` is not a card in layout.css
 * either, and a card leaning inside a leaning card is a hall of mirrors.
 *
 * This selector and the one in cinema.css are the same list, deliberately. If
 * one grows the other has to, which is why both carry this note.
 */
const CARD_SELECTOR = ".tilt-card, .app main > section, .landing-market, .auth__card";

/** How far outside a control's own box the magnetic pull reaches. */
const HALO = 84;
/** The furthest a control will ever travel. See the note on the cap below. */
const STRENGTH = 6;
/** The most a card will ever lean. */
const MAX_DEG = 4;

type Box = {
  el: HTMLElement;
  /** Geometry in *document* space, so scrolling does not invalidate it. */
  left: number;
  top: number;
  width: number;
  height: number;
};

type Control = Box & { reach: number; engaged: boolean };
type Card = Box & { active: boolean };

/**
 * Pointer response for every control and every card on the page, from one
 * listener and one measurement.
 *
 * Mounted once, in the app shell and on the landing page. The alternative — a
 * ref on each of the roughly forty controls and twenty cards across eleven
 * screens — would mean sixty `pointermove` listeners and sixty
 * `getBoundingClientRect` calls per frame. A rect read inside a pointer
 * handler forces synchronous layout; sixty of them at 60fps is the single most
 * reliable way to lose the frame budget.
 *
 * So this measures instead of re-measuring. Every element's geometry is
 * recorded once in *document* coordinates and kept until the layout could
 * actually have changed: a resize, or a DOM mutation (a route change, a query
 * resolving, a row being added). Scrolling invalidates nothing, because a
 * document coordinate does not move when the viewport does — the scroll offset
 * is subtracted at compare time from a value the browser hands over for free.
 *
 * Per frame the cost is therefore two scroll reads and N comparisons against
 * numbers already in memory. No layout, no React render, no state.
 *
 * Both effects write CSS custom properties and stop there; cinema.css decides
 * what a lean or a pull looks like. The split is the same one the rest of the
 * project uses — behaviour in the hook, appearance in the stylesheet.
 */
export function useSurfaceField(enabled = true) {
  const reduced = useReducedMotion();

  useEffect(() => {
    if (!enabled || reduced) return;
    if (typeof window.matchMedia !== "function") return;
    // Touch opts out of both. `pointermove` only fires during a drag on a
    // touch screen, so a card would lean and a button would lurch while the
    // reader is scrolling past them — motion in response to an intent the
    // reader did not have.
    if (!window.matchMedia("(pointer: fine)").matches) return;

    let controls: Control[] = [];
    let cards: Card[] = [];
    let frame = 0;
    let measureFrame = 0;
    let pointer: { x: number; y: number } | null = null;

    const measure = () => {
      measureFrame = 0;
      const scrollX = window.scrollX;
      const scrollY = window.scrollY;

      const box = (el: HTMLElement): Box => {
        const rect = el.getBoundingClientRect();
        return {
          el,
          left: rect.left + scrollX,
          top: rect.top + scrollY,
          width: rect.width,
          height: rect.height,
        };
      };

      controls = Array.from(
        document.querySelectorAll<HTMLElement>(CONTROL_SELECTOR),
      ).map((el) => {
        const b = box(el);
        return {
          ...b,
          reach: HALO + Math.max(b.width, b.height) / 2,
          engaged: false,
        };
      });

      cards = Array.from(document.querySelectorAll<HTMLElement>(CARD_SELECTOR)).map(
        (el) => ({ ...box(el), active: false }),
      );
    };

    /** Coalesce re-measures: a route change fires many mutations at once. */
    const scheduleMeasure = () => {
      if (measureFrame) return;
      measureFrame = requestAnimationFrame(measure);
    };

    const apply = () => {
      frame = 0;
      if (!pointer) return;
      // Pointer events are in viewport space; the cached geometry is in
      // document space. One read of the scroll offset reconciles them, and it
      // is the only geometry read in the whole loop.
      const px = pointer.x + window.scrollX;
      const py = pointer.y + window.scrollY;

      for (const item of controls) {
        const dx = px - (item.left + item.width / 2);
        const dy = py - (item.top + item.height / 2);
        const distance = Math.hypot(dx, dy);

        if (distance > item.reach) {
          // Write the resting position once, on the way out, rather than on
          // every move for every control the pointer is nowhere near.
          if (!item.engaged) continue;
          item.engaged = false;
          item.el.style.setProperty("--magnet-x", "0px");
          item.el.style.setProperty("--magnet-y", "0px");
          continue;
        }

        item.engaged = true;
        // Falls off toward the edge of the halo: strongest under the pointer.
        const pull = (1 - distance / item.reach) * STRENGTH;
        const unit = distance || 1;
        item.el.style.setProperty("--magnet-x", `${((dx / unit) * pull).toFixed(2)}px`);
        item.el.style.setProperty("--magnet-y", `${((dy / unit) * pull).toFixed(2)}px`);
      }

      for (const card of cards) {
        // -0.5 .. 0.5 from the centre of the card.
        const rx = (px - card.left) / card.width - 0.5;
        const ry = (py - card.top) / card.height - 0.5;
        const inside = Math.abs(rx) <= 0.5 && Math.abs(ry) <= 0.5;

        if (!inside) {
          if (!card.active) continue;
          card.active = false;
          card.el.style.setProperty("--tilt-active", "0");
          card.el.style.setProperty("--tilt-x", "0deg");
          card.el.style.setProperty("--tilt-y", "0deg");
          continue;
        }

        card.active = true;
        card.el.style.setProperty("--tilt-active", "1");
        // Y drives rotateX and is negated: pushing the pointer *up* should tip
        // the top of the card away, which is a negative rotateX.
        card.el.style.setProperty("--tilt-x", `${(-ry * MAX_DEG).toFixed(3)}deg`);
        card.el.style.setProperty("--tilt-y", `${(rx * MAX_DEG).toFixed(3)}deg`);
        card.el.style.setProperty("--glare-x", `${((rx + 0.5) * 100).toFixed(2)}%`);
        card.el.style.setProperty("--glare-y", `${((ry + 0.5) * 100).toFixed(2)}%`);
      }
    };

    const onMove = (event: PointerEvent) => {
      pointer = { x: event.clientX, y: event.clientY };
      if (!frame) frame = requestAnimationFrame(apply);
    };

    /* A card can also be reached by keyboard, and a card that lights up for a
       mouse but not for Tab is two different components wearing one class.
       Focus lights the sheen from the top centre, without the lean: there is
       no pointer position to lean toward. Delegated, so this costs two
       listeners rather than one per card. */
    const onFocusIn = (event: FocusEvent) => {
      const card = (event.target as HTMLElement | null)?.closest<HTMLElement>(
        CARD_SELECTOR,
      );
      if (!card) return;
      card.style.setProperty("--tilt-active", "1");
      card.style.setProperty("--glare-x", "50%");
      card.style.setProperty("--glare-y", "0%");
    };
    const onFocusOut = (event: FocusEvent) => {
      const card = (event.target as HTMLElement | null)?.closest<HTMLElement>(
        CARD_SELECTOR,
      );
      // Only when focus is actually leaving the card, not when it moves
      // between two controls inside it.
      if (!card || card.contains(event.relatedTarget as Node | null)) return;
      card.style.setProperty("--tilt-active", "0");
    };

    measure();
    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("resize", scheduleMeasure);
    document.addEventListener("focusin", onFocusIn);
    document.addEventListener("focusout", onFocusOut);
    // Controls and cards come and go with routes, queries and list edits.
    const observer = new MutationObserver(scheduleMeasure);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      if (frame) cancelAnimationFrame(frame);
      if (measureFrame) cancelAnimationFrame(measureFrame);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("resize", scheduleMeasure);
      document.removeEventListener("focusin", onFocusIn);
      document.removeEventListener("focusout", onFocusOut);
      observer.disconnect();
      // Leave nothing behind: an element still holding an offset or a lean
      // when the hook unmounts would sit permanently off-centre.
      for (const item of controls) {
        item.el.style.removeProperty("--magnet-x");
        item.el.style.removeProperty("--magnet-y");
      }
      for (const card of cards) {
        card.el.style.removeProperty("--tilt-active");
        card.el.style.removeProperty("--tilt-x");
        card.el.style.removeProperty("--tilt-y");
      }
    };
  }, [enabled, reduced]);
}
