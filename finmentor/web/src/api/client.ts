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

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const REFRESH_KEY = "finmentor.refresh_token";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

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

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length) {
      // FastAPI validation errors: surface the first field's message.
      return detail.map((item: { msg?: string }) => item.msg ?? "invalid").join(", ");
    }
  } catch {
    /* not JSON */
  }
  return response.statusText || "something went wrong";
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

  let response = await send(anonymous ? null : accessToken);

  if (response.status === 401 && !anonymous) {
    const fresh = await shareRefresh();
    if (fresh) response = await send(fresh);
  }

  if (response.status === 204) return undefined as T;
  if (!response.ok) throw new ApiError(response.status, await readError(response));
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
