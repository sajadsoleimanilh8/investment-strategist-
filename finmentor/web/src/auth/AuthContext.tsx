/**
 * Who is signed in, for the whole app.
 *
 * The token itself lives in `api/client.ts`; this holds the *user* and the
 * loading state a router needs to avoid flashing the login page at someone who
 * is actually signed in. On mount it tries the stored refresh token once —
 * that is what makes a reload keep the session.
 */
import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
  type ReactNode,
} from "react";

import * as authApi from "../api/auth";
import { restoreSession, setTokens } from "../api/client";
import type { Me } from "../api/types";

interface AuthState {
  user: Me | null;
  /** True until the initial refresh attempt settles. */
  loading: boolean;
  signup: (email: string, password: string) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    try {
      setUser(await authApi.me());
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const restored = await restoreSession();
      if (restored && !cancelled) await refreshUser();
      if (!cancelled) setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshUser]);

  const signup = useCallback(async (email: string, password: string) => {
    await authApi.signup(email, password);
    await refreshUser();
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    await authApi.login(email, password);
    await refreshUser();
  }, [refreshUser]);

  const logout = useCallback(async () => {
    await authApi.logout();
    setTokens(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, signup, login, logout, refreshUser }),
    [user, loading, signup, login, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside an AuthProvider");
  return context;
}
