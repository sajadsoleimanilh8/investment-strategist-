/**
 * Signing out has to work when the network does not.
 *
 * The server call is what ends the session on every other device, and it is
 * worth making. But it is not what signs you out *here*: the tokens are held
 * by this tab, and a failed request must not leave a person looking at a
 * dashboard whose every subsequent call will 401.
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "./AuthContext";
import { getAccessToken, setTokens } from "../api/client";

const api = vi.hoisted(() => ({ logoutFails: false, logoutCalls: 0 }));

vi.mock("../api/auth", () => ({
  logout: () => {
    api.logoutCalls += 1;
    // The real module clears tokens itself; this double deliberately does
    // not, so the test is about what AuthContext guarantees on its own.
    return api.logoutFails
      ? Promise.reject(new Error("offline"))
      : Promise.resolve(undefined);
  },
  me: () => Promise.resolve({
    id: 1, email: "sam@example.com", telegram_id: null,
    locale: "en", risk_profile: "moderate", onboarded: true,
  }),
  signup: () => Promise.resolve(undefined),
  login: () => Promise.resolve(undefined),
}));

function renderAuth() {
  return renderHook(() => useAuth(), { wrapper: AuthProvider });
}

beforeEach(() => {
  api.logoutFails = false;
  api.logoutCalls = 0;
  localStorage.clear();
  // AuthProvider tries the stored refresh token once on mount. jsdom has no
  // server to answer it, and an unhandled rejection there would fail the test
  // for a reason that has nothing to do with signing out.
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(
    new Response(JSON.stringify({
      access_token: "access", refresh_token: "refresh",
      token_type: "bearer", expires_in: 1800,
    }), { status: 200, headers: { "Content-Type": "application/json" } }),
  )));
  setTokens({
    access_token: "access", refresh_token: "refresh",
    token_type: "bearer", expires_in: 1800,
  });
});

describe("logout", () => {
  it("clears the tokens when the server answers", async () => {
    const { result } = renderAuth();
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(() => result.current.logout());

    expect(api.logoutCalls).toBe(1);
    expect(getAccessToken()).toBeNull();
    expect(localStorage.getItem("finmentor.refresh_token")).toBeNull();
    expect(result.current.user).toBeNull();
  });

  it("clears them anyway when the request fails", async () => {
    api.logoutFails = true;
    const { result } = renderAuth();
    await waitFor(() => expect(result.current.loading).toBe(false));

    // It still rejects, because the caller may want to say so. What it must
    // not do is skip the clearing on the way out.
    await act(async () => {
      await expect(result.current.logout()).rejects.toThrow("offline");
    });

    expect(getAccessToken()).toBeNull();
    expect(localStorage.getItem("finmentor.refresh_token")).toBeNull();
    expect(result.current.user).toBeNull();
  });
});
