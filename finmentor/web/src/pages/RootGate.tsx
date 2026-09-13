/**
 * "/" itself. A signed-in visitor has no reason to see the marketing page
 * every time they open the app, so they're sent straight to the dashboard.
 * Everyone else sees whatever this wraps (the Landing page).
 */
import { Navigate } from "react-router-dom";
import type { ReactNode } from "react";

import { useAuth } from "../auth/AuthContext";

export function RootGate({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) return null;
  if (user) return <Navigate to="/dashboard" replace />;

  return <>{children}</>;
}
