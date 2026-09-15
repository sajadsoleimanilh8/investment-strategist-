/** Navigation and an outlet. Structure only — no visual decisions here. */
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
 * simulators that do not need to be read in order, Learn is a list beside the
 * lesson it opens, and Goals is a table beside the form that adds to it.
 * Market takes the width for its seven-column table but not a second column
 * beside it.
 *
 * Everything else keeps the measure, because a form or a page of
 * explanations is read rather than scanned. */
const WIDTH_CLASS: Record<string, string> = {
  "/dashboard": "wide cols",
  "/market": "wide",
  "/simulate": "wide cols",
  "/learn": "wide cols",
  "/goals": "wide cols",
};

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();

  async function signOut() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="app">
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
      <main key={pathname} className={`stagger ${WIDTH_CLASS[pathname] ?? ""}`.trimEnd()}>
        <Outlet />
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
