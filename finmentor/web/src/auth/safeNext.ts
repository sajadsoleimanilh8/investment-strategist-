/**
 * Where a sign-in is allowed to send you afterwards.
 *
 * The server sanitises `next` when it mints the OAuth state
 * (`app/api/routes/oauth.py::_safe_next`), and that is the check that matters
 * for the normal flow. It is not the only path to a redirect: `AuthCallback`
 * reads `next` from its *own* query string, so a crafted
 * `/auth/callback?next=//evil.com` opened with a live handoff cookie would
 * have been followed. The window is narrow — sixty seconds, and it needs a
 * valid cookie — but a redirect out of a sign-in flow is the highest-value
 * place in an app to have one.
 *
 * This is the same rule as the server's, deliberately. A guard that holds on
 * one side only is not a guard, and `safeNext.test.ts` and
 * `tests/api/test_oauth_routes.py` share a table of cases so the two cannot
 * drift apart.
 */

/** The fallback when a destination cannot be trusted. */
export const DEFAULT_NEXT = "/dashboard";

/** Characters a browser strips from a URL before resolving it.
 *
 * They have to go before the string is judged. `/<TAB>/evil.com` passes a
 * check for "does not start with //" and then becomes `//evil.com` in the
 * address bar: approved as a path, resolved as a host. */
const IGNORED = /[\t\r\n]/g;

/**
 * `next` if it is a path inside this app, otherwise the dashboard.
 *
 * Three ways a string that looks like a path is not one:
 *
 * - `//evil.com` is protocol-relative. It starts with a slash and goes to
 *   another host.
 * - `/\evil.com` is the same thing. Browsers normalise a backslash to a
 *   forward slash in the authority position, so a check for `//` alone lets
 *   it through and the browser resolves it off-site anyway.
 * - `/<TAB>/evil.com` becomes `//evil.com` once the ignored characters are
 *   removed, which the browser does after any check here would have run.
 */
export function safeNext(next: string | null | undefined): string {
  const candidate = (next ?? "").replace(IGNORED, "");
  if (!candidate.startsWith("/")) return DEFAULT_NEXT;
  if (candidate.length > 1 && (candidate[1] === "/" || candidate[1] === "\\")) {
    return DEFAULT_NEXT;
  }
  return candidate;
}
