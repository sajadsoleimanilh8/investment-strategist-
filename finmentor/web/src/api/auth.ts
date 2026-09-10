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
