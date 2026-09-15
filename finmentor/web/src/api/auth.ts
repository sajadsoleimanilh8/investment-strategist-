import { api, setTokens, type TokenPair } from "./client";
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
