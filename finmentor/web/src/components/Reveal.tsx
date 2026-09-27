import type { CSSProperties, ElementType, ReactNode } from "react";

import { useInView } from "../hooks/useInView";

type RevealProps = {
  /** What to render. Defaults to `section`, which is what a page band is. */
  as?: ElementType;
  /** Stagger this block behind its siblings, in 70ms steps. */
  index?: number;
  /** Stagger the block's own children instead of moving it as one piece. */
  group?: boolean;
  className?: string;
  children?: ReactNode;
} & Record<string, unknown>;

/**
 * A block that resolves as the reader arrives at it.
 *
 * There are two implementations of this and the component only picks which
 * *markup* to emit — cinema.css decides which one actually runs. Where the
 * browser has `animation-timeline: view()` the reveal is scroll-linked, so the
 * reader's own scroll speed is the animation's clock and scrolling back up runs
 * it backwards. Where it does not, the `is-in` class this component sets from
 * an IntersectionObserver plays the same motion as a one-shot.
 *
 * Both paths are driven by attributes rather than by a class name, because the
 * stylesheet needs to distinguish "this block moves as one piece"
 * (`data-reveal`) from "this block's children arrive in sequence"
 * (`data-reveal-group`), and an attribute says which without inventing two
 * components that differ by one word.
 *
 * `as` exists because a reveal is not always a `section`. On the landing page
 * every band is one; inside the app a reveal is often a `div` wrapping a table,
 * and emitting a `section` there would add a card to a page that already has
 * one and a landmark to a screen reader that does not need another.
 */
export function Reveal({
  as: Tag = "section",
  index = 0,
  group = false,
  className = "",
  children,
  ...rest
}: RevealProps) {
  const { ref, inView } = useInView<HTMLElement>();
  const attribute = group ? "data-reveal-group" : "data-reveal";

  return (
    <Tag
      ref={ref}
      {...{ [attribute]: "" }}
      className={`${inView ? "is-in" : ""} ${className}`.trim()}
      style={index ? ({ "--reveal-index": index } as CSSProperties) : undefined}
      {...rest}
    >
      {children}
    </Tag>
  );
}
