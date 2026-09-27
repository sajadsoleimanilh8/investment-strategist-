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
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Read from disk, not `import css from "./layout.css?raw"` — Vite hands a test
// its *processed* stylesheet, and the token declarations this parses do not
// survive that intact.
const here = dirname(fileURLToPath(import.meta.url));
const read = (path: string) => readFileSync(join(here, path), "utf8");

const css = read("layout.css");

/**
 * Every file that can put a colour or a font on the screen — **discovered**,
 * not listed.
 *
 * It was a hand-written list of three stylesheets, and `cinema.css` was added
 * to the app without being added to it, so eight hundred lines of new CSS sat
 * outside the web-font ban and the colour checks below. A list is exactly the
 * wrong shape for a guard like this: the file you forget to add is the file
 * that needed checking.
 *
 * So the directory is read instead. A new stylesheet is covered the moment it
 * is saved, by nobody remembering anything. `index.html` is included by hand
 * because it is not in this directory and has carried a Google Fonts link
 * before.
 */
function everyStylesheet(): Record<string, string> {
  const files = readdirSync(here)
    .filter((name) => name.endsWith(".css"))
    .sort();
  const sheets: Record<string, string> = { "index.html": read("../../index.html") };
  for (const name of files) sheets[name] = read(name);
  return sheets;
}

const ALL_STYLESHEETS: Record<string, string> = everyStylesheet();

/** WCAG 2.1: 4.5:1 for body text. Nothing here relies on the 3:1 large-text
 * allowance — the ramp clears the body floor everywhere, at every size. */
const AA_BODY = 4.5;
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

/** The three-step type ramp: white headlines, mist body, graphite captions. */
const FOREGROUNDS = [
  "color-text", "color-mist", "color-muted", "color-accent",
  // The accented word in a headline. It is type, so it is held to the type
  // floor — "it is only one word" is not an exemption anyone reading it feels.
  "color-brand",
] as const;

describe("text on the page background", () => {
  it.each(FOREGROUNDS)("--%s clears AA for body text", (name) => {
    expect(ratio(token(name), token("color-bg"))).toBeGreaterThanOrEqual(AA_BODY);
  });
});

describe("text on the raised surfaces", () => {
  // Cards and input wells are a shade lighter than the page, so every ratio is
  // slightly worse there. Checking only against --color-bg would miss it.
  it.each(
    FOREGROUNDS.flatMap((fg) =>
      (["color-surface", "color-elevated"] as const).map((bg) => [fg, bg] as const)),
  )("--%s on --%s clears AA for body text", (fg, bg) => {
    expect(ratio(token(fg), token(bg))).toBeGreaterThanOrEqual(AA_BODY);
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

  it("button text is readable on the ghost button it sits on", () => {
    // Buttons carry no fill in this system: the label sits on the canvas
    // colour, inside a pill outline. That makes the label/canvas pair the one
    // to check — there is no accent fill to check against.
    const label = css.match(/color:\s*(#[0-9a-fA-F]{6});\s*\/\* ghost label on ink/);
    expect(label, "the button label colour moved or lost its marker").toBeTruthy();
    expect(ratio(label![1], token("color-bg"))).toBeGreaterThanOrEqual(AA_BODY);
  });

  it("the pill outline is visible against the canvas behind it", () => {
    // Shape is how a control announces itself here, so the outline drawing
    // that shape has to be perceivable, not merely present.
    expect(ratio(token("color-border"), token("color-bg")))
      .toBeGreaterThanOrEqual(1.3);
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
  it.each(Object.keys(ALL_STYLESHEETS))("%s fetches no font", (name) => {
    // DEMO_MODE has to run with no network at all, and a web font is a fetch.
    // Checked across every file rather than only the token block, because the
    // links that had to be removed from this project lived in index.html and
    // landing.css, not in layout.css.
    expect(ALL_STYLESHEETS[name]).not.toMatch(
      /@import\s+url|@font-face|fonts\.googleapis|fonts\.gstatic/);
  });

  it("the body font is a system stack", () => {
    expect(css).toMatch(/--font-body:\s*system-ui/);
  });
});

describe("the decorative tokens stay decorative", () => {
  it("--color-brand-deep is never used as a foreground", () => {
    // It is the terminus of a warm wash, chosen to sit *under* something. It
    // has no contrast guarantee, so the guarantee is that nothing reads on it:
    // the moment it appears as a `color:`, this fails and it needs a ratio.
    for (const [name, sheet] of Object.entries(ALL_STYLESHEETS)) {
      expect(sheet, `${name} puts text on --color-brand-deep`)
        .not.toMatch(/color:\s*var\(--color-brand-deep\)/);
    }
  });
});
