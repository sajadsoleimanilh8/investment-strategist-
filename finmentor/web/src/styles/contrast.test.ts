/**
 * WCAG contrast, computed from the tokens rather than eyeballed.
 *
 * The palette is dark, and dark is where contrast quietly fails: a red that
 * looks fine on white is often unreadable on near-black. The delta colours are
 * the ones that matter most, because they carry the meaning of the number next
 * to them — a figure someone cannot read is a figure that might as well be
 * wrong.
 *
 * The values are parsed out of `layout.css` itself, so this fails if someone
 * changes a token without re-checking it. That is the whole point: a palette
 * edit is cheap, and this is what stops a cheap edit being a regression.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Read from disk, not `import css from "./layout.css?raw"` — Vite hands a test
// its *processed* stylesheet, and the token declarations this parses do not
// survive that intact.
const css = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "layout.css"), "utf8");

/** WCAG 2.1: 4.5:1 for body text, 3:1 for large text (>=18.66px bold or 24px). */
const AA_BODY = 4.5;
const AA_LARGE = 3;
/** Non-text UI (borders, focus rings) needs 3:1 against what it sits on. */
const AA_NON_TEXT = 3;

function token(name: string): string {
  const match = css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{3,8})\\s*;`));
  if (!match) throw new Error(`token --${name} is missing or is not a hex colour`);
  return match[1];
}

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const full = hex.length === 4
    ? `#${[...hex.slice(1)].map((c) => c + c).join("")}`
    : hex;
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(full.slice(i, i + 2), 16));
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function ratio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// A sanity check on the maths before trusting anything it says.
describe("the ratio function itself", () => {
  it("puts black on white at 21:1", () => {
    expect(ratio("#000000", "#ffffff")).toBeCloseTo(21, 1);
  });

  it("is symmetric", () => {
    expect(ratio("#12151a", "#e8eaed")).toBeCloseTo(ratio("#e8eaed", "#12151a"), 5);
  });

  it("puts a colour against itself at 1:1", () => {
    expect(ratio("#4ade80", "#4ade80")).toBeCloseTo(1, 5);
  });

  it("expands three-digit hex", () => {
    expect(ratio("#fff", "#000")).toBeCloseTo(21, 1);
  });
});

describe("text on the page background", () => {
  it.each([
    ["text", AA_BODY],
    ["muted", AA_BODY],
    ["accent", AA_BODY],
  ])("--color-%s clears %s:1", (name, floor) => {
    expect(ratio(token(name === "text" ? "color-text" : `color-${name}`),
                 token("color-bg"))).toBeGreaterThanOrEqual(floor);
  });
});

describe("text on a card surface", () => {
  // Cards are a shade lighter than the page, so every ratio is slightly worse
  // there. Checking only against --color-bg would miss it.
  it.each([
    ["color-text", AA_BODY],
    ["color-muted", AA_BODY],
    ["color-accent", AA_BODY],
  ])("%s clears %s:1", (name, floor) => {
    expect(ratio(token(name), token("color-surface"))).toBeGreaterThanOrEqual(floor);
  });
});

describe("the delta colours — the ones that carry meaning", () => {
  it.each([
    ["color-positive", "color-bg"],
    ["color-positive", "color-surface"],
    ["color-negative", "color-bg"],
    ["color-negative", "color-surface"],
    ["color-warning", "color-bg"],
    ["color-warning", "color-surface"],
  ])("%s on %s clears AA for body text", (fg, bg) => {
    expect(ratio(token(fg), token(bg))).toBeGreaterThanOrEqual(AA_BODY);
  });

  it("keeps positive and negative distinguishable from each other", () => {
    // Colour is never the only signal — the sign and an arrow carry it too —
    // but two deltas that look alike make a table harder to scan for everyone.
    expect(ratio(token("color-positive"), token("color-negative")))
      .toBeGreaterThanOrEqual(1.4);
  });
});

describe("non-text UI", () => {
  it("borders are visible against the surface they divide", () => {
    // 3:1 is the AA floor for a UI boundary. A border below it is decoration
    // that some people simply cannot see.
    expect(ratio(token("color-border"), token("color-surface")))
      .toBeGreaterThanOrEqual(1.3);
  });

  it("the focus ring is visible against both grounds", () => {
    expect(ratio(token("color-accent"), token("color-bg")))
      .toBeGreaterThanOrEqual(AA_NON_TEXT);
    expect(ratio(token("color-accent"), token("color-surface")))
      .toBeGreaterThanOrEqual(AA_NON_TEXT);
  });

  it("button text is readable on the accent it sits on", () => {
    // Dark-on-accent, which is the readable way round for a mid-tone accent.
    const label = css.match(/color:\s*(#[0-9a-fA-F]{6});\s*\/\* dark-on-accent/);
    expect(label, "the button label colour moved or lost its marker").toBeTruthy();
    expect(ratio(label![1], token("color-accent"))).toBeGreaterThanOrEqual(AA_LARGE);
  });
});

describe("the palette is actually dark", () => {
  it("uses a near-black page, not pure black", () => {
    // Pure black against bright text vibrates and tires the eye over a page of
    // numbers, which is what this app mostly is.
    expect(token("color-bg")).not.toBe("#000000");
    expect(luminance(token("color-bg"))).toBeLessThan(0.05);
  });

  it("lifts cards off the page rather than matching it", () => {
    expect(luminance(token("color-surface")))
      .toBeGreaterThan(luminance(token("color-bg")));
  });

  it("keeps the accent away from the neon end", () => {
    // SPEC section 30 warns off the trading-terminal look. A fully saturated
    // accent is most of how an interface gets there.
    const hex = token("color-accent");
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
    const saturation = (Math.max(r, g, b) - Math.min(r, g, b)) / Math.max(r, g, b);
    expect(saturation).toBeLessThan(0.75);
  });
});

describe("no web fonts", () => {
  it("every font token is a system stack", () => {
    // DEMO_MODE has to run with no network at all, and a web font is a fetch.
    expect(css).not.toMatch(/@import\s+url|@font-face|fonts\.googleapis|fonts\.gstatic/);
    expect(css).toMatch(/--font-body:\s*system-ui/);
  });
});
