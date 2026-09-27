/**
 * Routes.
 *
 * "/" is public: RootGate shows the marketing Landing page to a signed-out
 * visitor, or sends a signed-in one straight to "/dashboard" (the old index
 * route). Signup and login sit outside the layout: someone who is not signed
 * in has no navigation to show. Onboarding sits inside `RequireAuth` but with
 * `needsProfile` off — it is the page that *creates* the profile, so requiring
 * one would be a redirect loop.
 */
import { createBrowserRouter } from "react-router-dom";

import { Layout } from "./components/Layout";
import { RouteError } from "./components/RouteError";
import { RequireAuth } from "./auth/RequireAuth";
import { Ask } from "./pages/Ask";
import { Dashboard } from "./pages/Dashboard";
import { Goals } from "./pages/Goals";
import { AuthCallback } from "./pages/AuthCallback";
import { ForgotPassword } from "./pages/ForgotPassword";
import { Landing } from "./pages/Landing";
import { Learn } from "./pages/Learn";
import { Login } from "./pages/Login";
import { Market } from "./pages/Market";
import { NotFound } from "./pages/NotFound";
import { Onboarding } from "./pages/Onboarding";
import { Profile } from "./pages/Profile";
import { ResetPassword } from "./pages/ResetPassword";
import { RootGate } from "./pages/RootGate";
import { Signup } from "./pages/Signup";
import { Simulate } from "./pages/Simulate";

const guarded = (element: JSX.Element) => <RequireAuth>{element}</RequireAuth>;

export const router = createBrowserRouter([
  // `errorElement` on every top-level route, not only on the layout: a throw
  // in Login or the landing page has no layout above it to be caught by, and
  // those are the two pages a first-time visitor sees.
  { path: "/", element: <RootGate><Landing /></RootGate>, errorElement: <RouteError /> },
  { path: "/signup", element: <Signup />, errorElement: <RouteError /> },
  { path: "/login", element: <Login />, errorElement: <RouteError /> },
  // Both sit outside the layout with signup and login, and for the same
  // reason: everyone who reaches them is signed out by definition.
  { path: "/forgot-password", element: <ForgotPassword />, errorElement: <RouteError /> },
  { path: "/reset-password", element: <ResetPassword />, errorElement: <RouteError /> },
  // Where a provider sign-in lands. Outside the layout for the same reason:
  // whoever is here has no session yet.
  { path: "/auth/callback", element: <AuthCallback />, errorElement: <RouteError /> },
  {
    // A pathless layout route: it contributes no URL segment of its own, so
    // every child keeps its existing absolute path (no "/app/..." migration).
    element: <Layout />,
    // Caught here rather than per child, so the navigation survives the
    // failure: someone whose Goals page threw can still reach the dashboard
    // without using the browser's back button.
    errorElement: <Layout><RouteError /></Layout>,
    children: [
      { path: "dashboard", element: guarded(<Dashboard />) },
      {
        path: "onboarding",
        element: (
          <RequireAuth needsProfile={false}>
            <Onboarding />
          </RequireAuth>
        ),
      },
      { path: "goals", element: guarded(<Goals />) },
      { path: "simulate", element: guarded(<Simulate />) },
      { path: "market", element: guarded(<Market />) },
      { path: "learn", element: guarded(<Learn />) },
      { path: "ask", element: guarded(<Ask />) },
      { path: "profile", element: guarded(<Profile />) },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
