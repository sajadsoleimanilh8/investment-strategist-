import { useEffect, useRef, useState } from "react";

/** A minimal inline-SVG line, built from real accumulated ticks — no charting
 * library needed for what is, at bottom, one polyline. It draws itself in
 * once (stroke-dashoffset animated to 0) rather than appearing instantly. */
export function Sparkline({ points, positive }: { points: number[]; positive: boolean }) {
  const width = 240;
  const height = 56;
  const pathRef = useRef<SVGPolylineElement>(null);
  const [length, setLength] = useState(0);
  const [drawn, setDrawn] = useState(false);

  const hasData = points.length >= 2;

  useEffect(() => {
    if (!hasData || !pathRef.current) return;
    const total = pathRef.current.getTotalLength();
    setLength(total);
    setDrawn(false);
    // Two frames: the browser needs to paint the full-length dash-offset
    // once before transitioning it to 0, or there is nothing to animate.
    const raf1 = requestAnimationFrame(() => {
      const raf2 = requestAnimationFrame(() => setDrawn(true));
      return () => cancelAnimationFrame(raf2);
    });
    return () => cancelAnimationFrame(raf1);
    // Re-draw whenever the series actually changes shape, not on every tick's
    // tiny y-shift — points.length is a fine proxy since it only changes when
    // a new point lands (the buffer is append-only up to its cap).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasData, points.length]);

  if (!hasData) {
    return (
      <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label="Not enough data yet">
        <line x1={0} y1={height / 2} x2={width} y2={height / 2} stroke="var(--color-border)" strokeWidth={1} />
      </svg>
    );
  }

  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const coords = points.map((p, i) => {
    const x = i * step;
    const y = height - ((p - min) / span) * (height - 8) - 4;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      role="img"
      aria-label={`Recent price trend, ${positive ? "up" : "down"}`}
    >
      <polyline
        ref={pathRef}
        className="sparkline-path"
        points={coords.join(" ")}
        fill="none"
        stroke={positive ? "var(--color-positive)" : "var(--color-negative)"}
        strokeWidth={1.75}
        strokeLinejoin="round"
        strokeLinecap="round"
        strokeDasharray={length || undefined}
        strokeDashoffset={length ? (drawn ? 0 : length) : undefined}
      />
    </svg>
  );
}
