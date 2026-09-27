/** Navigation and an outlet. Structure only — no visual decisions here. */
import type { ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

const LINKS = [
  ["/dashboard", "Dashboard"],
  ["/goals", "Goals"],
  ["/simulate", "Simulate"],
  ["/market", "Market"],
  ["/learn", "Learn"],
  ["/ask", "Ask"],
  ["/profile", "Profile"],
] as const;

/** The pages that are not a column of prose.
 *
 * `wide` lifts the 68ch reading measure; `cols` adds the two-column grid on
 * top of it. The dashboard is a grid of independent panels, Simulate is three
 * simulators that do not need to be read in order, and Learn is a list beside
 * the lesson it opens. Market takes the width for its seven-column table but
 * not a second column beside it.
 *
 * Goals used to be `cols` too, on the reasoning that the table and the form
 * that adds to it belong side by side. That stopped being true once the table
 * grew per-row controls: six columns plus an action group in half the page is
 * a horizontal scrollbar over the thing you are trying to press. The form
 * moved below, where it is no narrower than any other form in the app.
 *
 * Everything else keeps the measure, because a form or a page of
 * explanations is read rather than scanned. */
const WIDTH_CLASS: Record<string, string> = {
  "/dashboard": "wide cols",
  "/market": "wide",
  "/simulate": "wide cols",
  "/learn": "wide cols",
  "/goals": "wide",
};

export function Layout({ children }: { children?: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();

  async function signOut() {
    // Same reasoning as `AuthContext.logout`: the tokens are gone either way,
    // so staying on a dashboard whose every request will 401 is the one
    // outcome that helps nobody.
    try {
      await logout();
    } finally {
      navigate("/login");
    }
  }

  return (
    <div className="app">
      {/* The first focusable thing on every page. Seven navigation links sit
          between the top of the document and the content, on every
          navigation; without this a keyboard or screen-reader user tabs
          through all of them every time. Visible only while focused, which is
          what `.skip-link` does. */}
      <a className="skip-link" href="#main">Skip to main content</a>
      <header>
        <Link to="/dashboard"><h1>FinMentor</h1></Link>
        <nav aria-label="Main">
          <ul>
            {LINKS.map(([to, label]) => (
              <li key={to}>
                <NavLink to={to} end={to === "/dashboard"}>{label}</NavLink>
              </li>
            ))}
          </ul>
        </nav>
        {user && (
          <p className="whoami">
            {user.email} <button type="button" onClick={signOut}>Sign out</button>
          </p>
        )}
      </header>

      {/* Keyed on the path so the entrance replays on every navigation rather
          than only the first mount. Every page is already a list of top-level
          `section`s, so staggering main's children *is* the route transition —
          the page resolves card by card instead of the whole screen blinking
          over at once, and a one-section page still gets a clean fade. */}
      {/* `tabIndex={-1}` so the skip link can move focus here: a heading or
          a landmark is not focusable by default, and a link that scrolls
          without moving focus leaves the next Tab back at the top. */}
      <main id="main" tabIndex={-1} key={pathname}
            className={`stagger ${WIDTH_CLASS[pathname] ?? ""}`.trimEnd()}>
        {children ?? <Outlet />}
      </main>

      <footer>
        <small>
          Every figure here is calculated from your data. FinMentor explains;
          it never tells you what to buy or sell.
        </small>
      </footer>
    </div>
  );
}
