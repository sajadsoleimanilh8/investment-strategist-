/**
 * The route guard's three states.
 *
 * The middle one is why this file exists: while a session is being restored
 * from the stored refresh token there is no user *yet*, and a naive guard
 * redirects a signed-in person to the login page for a frame. That flash is
 * the bug this test would catch.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { RequireAuth } from "./RequireAuth";
import type { Me } from "../api/types";

const SIGNED_IN: Me = {
  id: 1, email: "sam@example.com", telegram_id: null,
  locale: "en", risk_profile: "moderate", onboarded: true,
};

const authState = vi.hoisted(() => ({
  current: { user: null as Me | null, loading: false },
}));

vi.mock("./AuthContext", () => ({
  useAuth: () => authState.current,
}));

function renderGuard(needsProfile = true) {
  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <Routes>
        <Route
          path="/dashboard"
          element={
            <RequireAuth needsProfile={needsProfile}>
              <p>the dashboard</p>
            </RequireAuth>
          }
        />
        <Route path="/login" element={<p>the login page</p>} />
        <Route path="/onboarding" element={<p>the onboarding wizard</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RequireAuth", () => {
  it("renders the page for a signed-in, onboarded user", () => {
    authState.current = { user: SIGNED_IN, loading: false };

    renderGuard();

    expect(screen.getByText("the dashboard")).toBeInTheDocument();
  });

  it("sends a signed-out user to the login page", () => {
    authState.current = { user: null, loading: false };

    renderGuard();

    expect(screen.getByText("the login page")).toBeInTheDocument();
    expect(screen.queryByText("the dashboard")).not.toBeInTheDocument();
  });

  it("shows neither page while the session is still being restored", () => {
    // A reload has a refresh token but no user yet. Redirecting here would
    // flash the login screen at somebody who is actually signed in.
    authState.current = { user: null, loading: true };

    renderGuard();

    expect(screen.queryByText("the login page")).not.toBeInTheDocument();
    expect(screen.queryByText("the dashboard")).not.toBeInTheDocument();
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("sends a user without a profile through onboarding first", () => {
    authState.current = { user: { ...SIGNED_IN, onboarded: false }, loading: false };

    renderGuard();

    expect(screen.getByText("the onboarding wizard")).toBeInTheDocument();
  });

  it("lets the onboarding page itself through without a profile", () => {
    // Otherwise the page that creates the profile requires one: a redirect loop.
    authState.current = { user: { ...SIGNED_IN, onboarded: false }, loading: false };

    renderGuard(false);

    expect(screen.getByText("the dashboard")).toBeInTheDocument();
  });
});
