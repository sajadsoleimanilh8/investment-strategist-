import { API_BASE_URL, api, setTokens, type TokenPair } from "./client";
import type { Me } from "./types";

export async function signup(email: string, password: string): Promise<TokenPair> {
  const pair = await api.post<TokenPair>("/api/auth/signup", { email, password }, true);
  setTokens(pair);
  return pair;
}

export async function login(email: string, password: string): Promise<TokenPair> {
  const pair = await api.post<TokenPair>("/api/auth/login", { email, password }, true);
  setTokens(pair);
  return pair;
}

export async function logout(): Promise<void> {
  await api.post<void>("/api/auth/logout").catch(() => undefined);
  setTokens(null);
}

export const me = () => api.get<Me>("/api/auth/me");

/** Ask for a reset link. Answers the same whether or not the address has an
 * account, so there is nothing here for the caller to branch on. */
export const forgotPassword = (email: string) =>
  api.post<{ message: string }>("/api/auth/forgot-password", { email }, true);

/** Spend a reset link. Returns a pair: the person has just proved they hold
 * the address and chosen a password, so a login form would prove nothing
 * further. */
export async function resetPassword(token: string, password: string): Promise<TokenPair> {
  const pair = await api.post<TokenPair>(
    "/api/auth/reset-password", { token, password }, true);
  setTokens(pair);
  return pair;
}


/** Which third-party buttons this deployment can actually offer. A provider
 * without credentials is absent rather than disabled: a button that leads to
 * Google's error page reads as this product being broken. */
export const oauthProviders = () =>
  api.get<{ providers: string[] }>("/api/auth/oauth/providers");

/** Where the button goes. A full page navigation, not fetch: the provider
 * has to see the browser, not an XHR. */
export const oauthStartUrl = (provider: string, next: string) =>
  `${API_BASE_URL}/api/auth/oauth/${provider}/start?next=${encodeURIComponent(next)}`;

/**
 * Trade the handoff cookie the callback set for a real token pair.
 *
 * `credentials: "include"` because the cookie is the credential here, and it
 * is HttpOnly so this code cannot read it to send any other way. That also
 * means the exchange has to be same-origin with the API: SameSite=Lax is not
 * sent on a cross-site request. Production serves both from one origin and
 * the dev proxy reproduces that; see the note in app/api/routes/oauth.py.
 */
export async function exchangeOAuth(): Promise<TokenPair> {
  const response = await fetch(`${API_BASE_URL}/api/auth/oauth/exchange`, {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok) throw new Error("That sign-in did not complete. Try again.");
  const pair = (await response.json()) as TokenPair;
  setTokens(pair);
  return pair;
}
