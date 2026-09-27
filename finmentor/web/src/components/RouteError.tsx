/**
 * What the reader sees when a page throws.
 *
 * `AsyncBoundary` already handles a query that *rejects*, which is the common
 * case and the one with a useful message attached. It cannot catch a render
 * error: a component that throws while React is building the tree unmounts
 * everything above it, and what is left is a white screen. That is the thing
 * people mean when they say an app is broken, and it was reachable here — a
 * figure typed as `number` arriving as `null` reaches `.toFixed()` and throws.
 *
 * Two rules about what this shows.
 *
 * It does not print the error. A stack trace is a description of this app's
 * internals, and the person reading it can act on none of it. The one useful
 * thing is that the console has the detail, so the sentence says so.
 *
 * It offers a way out rather than only an apology: reloading fixes a
 * transient failure, and the dashboard link is there because the page that
 * broke may not be the one worth retrying.
 */
import { Link, isRouteErrorResponse, useRouteError } from "react-router-dom";

export function RouteError() {
  const error = useRouteError();

  // A 404 from the router is not a crash and should not read as one.
  if (isRouteErrorResponse(error) && error.status === 404) {
    return (
      <section>
        <h2>That page does not exist</h2>
        <p>
          Check the address, or <Link to="/dashboard">go back to your dashboard</Link>.
        </p>
      </section>
    );
  }

  return (
    <section role="alert">
      <h2>Something broke on this page</h2>
      <p>
        This is a fault in FinMentor, not in anything you did. Your data is
        untouched.
      </p>
      <p className="muted">
        Reloading usually clears it. If it keeps happening, the browser console
        has the technical detail.
      </p>
      <div className="actions">
        <button type="button" onClick={() => window.location.reload()}>
          Reload the page
        </button>
        <Link to="/dashboard">Back to the dashboard</Link>
      </div>
    </section>
  );
}
