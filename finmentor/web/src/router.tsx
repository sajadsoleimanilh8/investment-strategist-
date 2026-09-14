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
import { RequireAuth } from "./auth/RequireAuth";
import { Ask } from "./pages/Ask";
import { Dashboard } from "./pages/Dashboard";
import { Goals } from "./pages/Goals";
import { Landing } from "./pages/Landing";
import { Learn } from "./pages/Learn";
import { Login } from "./pages/Login";
import { Market } from "./pages/Market";
import { NotFound } from "./pages/NotFound";
import { Onboarding } from "./pages/Onboarding";
import { Profile } from "./pages/Profile";
import { RootGate } from "./pages/RootGate";
import { Signup } from "./pages/Signup";
import { Simulate } from "./pages/Simulate";

const guarded = (element: JSX.Element) => <RequireAuth>{element}</RequireAuth>;

export const router = createBrowserRouter([
  { path: "/", element: <RootGate><Landing /></RootGate> },
  { path: "/signup", element: <Signup /> },
  { path: "/login", element: <Login /> },
  {
    // A pathless layout route: it contributes no URL segment of its own, so
    // every child keeps its existing absolute path (no "/app/..." migration).
    element: <Layout />,
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
