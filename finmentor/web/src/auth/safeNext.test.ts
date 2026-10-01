/**
 * The redirect guard, client side.
 *
 * The server sanitises `next` when it mints the OAuth state, and for the
 * normal flow that is the check that matters. It is not the only path: the
 * callback page reads `next` from its *own* query string, so a crafted
 * `/auth/callback?next=//evil.com` opened while a handoff cookie is live
 * would have been followed. `startsWith("/")` accepts `//evil.com`.
 *
 * The table below is the same one as
 * `tests/api/test_security_hardening.py::SAFE_NEXT_CASES`, and a test there
 * asserts the two have not drifted. A guard that holds on one side only is
 * not a guard.
 */
import { describe, expect, it } from "vitest";

import { DEFAULT_NEXT, safeNext } from "./safeNext";

describe("paths inside the app are kept", () => {
  it.each([
    "/dashboard",
    "/goals",
    "/learn?topic=budgeting",
    "/",
  ])("keeps %s", (path) => {
    expect(safeNext(path)).toBe(path);
  });
});

describe("anything that can resolve to another origin is refused", () => {
  it.each([
    // Protocol-relative: starts with a slash, goes to another host. This is
    // the one `startsWith("/")` let through.
    "//evil.com",
    "///evil.com",
    // Browsers normalise a backslash to a slash in the authority position,
    // so these are the same URL as the two above by the time anything
    // resolves them.
    "/\\evil.com",
    "/\\/evil.com",
    // Absolute.
    "https://evil.com",
    "http://evil.com",
    "javascript:alert(1)",
    // Not a path at all.
    "",
    "dashboard",
  ])("refuses %j", (path) => {
    expect(safeNext(path)).toBe(DEFAULT_NEXT);
  });

  it.each([
    ["tab", "/\t/evil.com"],
    ["newline", "/\n/evil.com"],
    ["carriage return", "/\r/evil.com"],
  ])("refuses a %s hiding a protocol-relative URL", (_name, path) => {
    // The browser strips these before resolving, which turns the string into
    // "//evil.com" *after* a naive check has already approved it.
    expect(safeNext(path)).toBe(DEFAULT_NEXT);
  });

  it("refuses a missing destination", () => {
    expect(safeNext(null)).toBe(DEFAULT_NEXT);
    expect(safeNext(undefined)).toBe(DEFAULT_NEXT);
  });
});
