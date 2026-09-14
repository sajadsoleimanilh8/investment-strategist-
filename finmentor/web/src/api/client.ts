/**
 * The one place a request leaves this app.
 *
 * Two things live here that would otherwise be scattered across every page:
 *
 * 1. **The access token.** It is held in memory only. A token in localStorage
 *    is readable by any script that gets injected into the page; a token in a
 *    variable dies with the tab, which is the right trade for a 30-minute
 *    credential. Only the refresh token is persisted, so a reload can recover
 *    a session without a second login.
 *
 * 2. **Refresh-on-401.** When the access token expires mid-session the request
 *    is retried once, transparently. Concurrent 401s share a single refresh
 *    (`refreshInFlight`) — six widgets on the dashboard expiring together must
 *    not fire six refreshes and rotate the token out from under each other.
 */

/**
 * Where the API is.
 *
 * `VITE_API_BASE_URL` wins when it is set, which is how a split-origin build
 * (nginx serving the SPA, the API on another host) is configured. Without it
 * the fallback differs by build, because the two cases are genuinely
 * different: in dev the page is on Vite's port and the API is on another, so
 * it has to be named; in a production build the SPA is served from the API's
 * own origin, and hard-coding localhost there is a page that only works on
 * the machine it was built on.
 *
 * Exported because the live-market WebSocket has to resolve to the same
 * place. Two bases that can disagree is a bug waiting for a deploy.
 */
export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? "http://localhost:8000" : window.location.origin);

const BASE_URL = API_BASE_URL;
const REFRESH_KEY = "finmentor.refresh_token";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    /** The id the API logged this under. Worth showing on a 500. */
    readonly requestId?: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }

  /** True when the request never reached the API at all. */
  get isOffline(): boolean {
    return this.status === 0;
  }

  /** What to actually put in front of someone. */
  get userMessage(): string {
    if (this.isOffline) return OFFLINE_MESSAGE;
    if (this.status >= 500) {
      return this.requestId
        ? `${this.detail} (reference ${this.requestId})`
        : this.detail;
    }
    return this.detail;
  }
}

export const OFFLINE_MESSAGE =
  "Can't reach FinMentor. Check your connection and try again.";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

let accessToken: string | null = null;
let refreshInFlight: Promise<string | null> | null = null;
const listeners = new Set<() => void>();

export function onAuthChange(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function announce(): void {
  listeners.forEach((listener) => listener());
}

export function setTokens(pair: TokenPair | null): void {
  accessToken = pair?.access_token ?? null;
  try {
    if (pair) localStorage.setItem(REFRESH_KEY, pair.refresh_token);
    else localStorage.removeItem(REFRESH_KEY);
  } catch {
    // A browser with site data blocked still works for this tab; the session
    // just will not survive a reload.
  }
  announce();
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function getRefreshToken(): string | null {
  try {
    return localStorage.getItem(REFRESH_KEY);
  } catch {
    return null;
  }
}

export function isSignedIn(): boolean {
  return accessToken !== null;
}

/** Trade the stored refresh token for a new pair. Null means "log in again". */
async function refresh(): Promise<string | null> {
  const token = getRefreshToken();
  if (!token) return null;

  const response = await fetch(`${BASE_URL}/api/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: token }),
  });

  if (!response.ok) {
    setTokens(null);
    return null;
  }
  const pair = (await response.json()) as TokenPair;
  setTokens(pair);
  return pair.access_token;
}

function shareRefresh(): Promise<string | null> {
  // One refresh at a time. Without this, every in-flight request that 401s
  // starts its own, and the last one to finish wins while the others hold
  // tokens that were just rotated away.
  if (!refreshInFlight) {
    refreshInFlight = refresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/** What the API sends for every failure. See `app/api/errors.py`. */
interface ErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
    fields?: { field: string; message: string }[];
  };
  /** FastAPI's own shape, still produced by anything upstream of our handlers. */
  detail?: string | { msg?: string }[];
}

/** A message a person can act on, plus the id they would quote to support. */
async function readError(response: Response): Promise<{ detail: string; requestId?: string }> {
  try {
    const body = (await response.json()) as ErrorEnvelope;

    if (body?.error) {
      // Field errors first: "Email is not a valid address" beats "Some of that
      // was not valid" when a form can point at the input.
      const fields = body.error.fields;
      const detail = fields?.length
        ? fields.map((f) => `${f.field}: ${f.message}`).join("; ")
        : body.error.message ?? "Something went wrong.";
      return { detail, requestId: body.error.request_id };
    }

    const legacy = body?.detail;
    if (typeof legacy === "string") return { detail: legacy };
    if (Array.isArray(legacy) && legacy.length) {
      return { detail: legacy.map((item) => item.msg ?? "invalid").join(", ") };
    }
  } catch {
    /* not JSON — a proxy error page, or an empty body */
  }
  return { detail: response.statusText || "Something went wrong." };
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  /** Set for signup/login/refresh, which must not carry or retry a token. */
  anonymous?: boolean;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, anonymous = false } = options;

  const send = (token: string | null): Promise<Response> =>
    fetch(`${BASE_URL}${path}`, {
      method,
      headers: {
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

  // A failed `fetch` rejects rather than resolving — no server, DNS gone,
  // request blocked. That is a different thing to a 500 and deserves a
  // different sentence, so it becomes status 0 rather than an unhandled
  // TypeError that renders as a blank screen.
  let response: Response;
  try {
    response = await send(anonymous ? null : accessToken);
  } catch {
    throw new ApiError(0, OFFLINE_MESSAGE);
  }

  if (response.status === 401 && !anonymous) {
    const fresh = await shareRefresh();
    if (fresh) {
      try {
        response = await send(fresh);
      } catch {
        throw new ApiError(0, OFFLINE_MESSAGE);
      }
    }
  }

  if (response.status === 204) return undefined as T;
  if (!response.ok) {
    const { detail, requestId } = await readError(response);
    throw new ApiError(response.status, detail, requestId);
  }
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown, anonymous = false) =>
    request<T>(path, { method: "POST", body, anonymous }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

/** Called once at start-up: recover a session from the stored refresh token. */
export async function restoreSession(): Promise<boolean> {
  if (!getRefreshToken()) return false;
  return (await shareRefresh()) !== null;
}
