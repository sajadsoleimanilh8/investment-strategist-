/**
 * Route guard. Three states, and the middle one matters:
 *
 * - still restoring a session -> render nothing, so a signed-in user reloading
 *   the page never sees the login screen flash past
 * - signed out -> redirect to /login, remembering where they were headed
 * - signed in but not onboarded -> push them through onboarding first, because
 *   every other page needs figures they have not given us yet
 */
import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import { useAuth } from "./AuthContext";

export function RequireAuth({ children, needsProfile = true }: {
  children: ReactNode;
  needsProfile?: boolean;
}) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <p aria-busy="true">Loading…</p>;
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  if (needsProfile && !user.onboarded) return <Navigate to="/onboarding" replace />;

  return <>{children}</>;
}
