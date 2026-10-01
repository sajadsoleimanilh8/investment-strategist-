/**
 * Where a provider sign-in lands, for the half-second it takes to finish.
 *
 * The API has already decided who signed in and left a one-minute handoff
 * cookie. This page trades it for a token pair and moves on. It exists at all
 * because the alternative — the API redirecting straight to the dashboard
 * with tokens in the URL — writes a credential into browser history, into the
 * referrer of the next request, and into every log that records a path.
 *
 * There is nothing to read here on purpose: a screen that says "signing you
 * in" and then leaves is better than one that invites a click it will
 * discard.
 */
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { exchangeOAuth } from "../api/auth";
import { messageFor } from "../components/AsyncBoundary";
import { useAuth } from "../auth/AuthContext";
import { safeNext } from "../auth/safeNext";

export function AuthCallback() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { refreshUser } = useAuth();
  const [error, setError] = useState<string | null>(null);
  // StrictMode mounts effects twice in development, and the handoff is single
  // use: the second call would fail and show an error for a sign-in that
  // actually worked.
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    (async () => {
      try {
        await exchangeOAuth();
        await refreshUser();
        // `safeNext`, not `startsWith("/")`. This page reads `next` from its
        // own query string rather than from the signed state, so the check
        // here is the only thing standing between a crafted callback URL and
        // a redirect off-site. `//evil.com` starts with a slash.
        navigate(safeNext(params.get("next")), { replace: true });
      } catch (caught) {
        setError(messageFor(caught));
      }
    })();
  }, [navigate, params, refreshUser]);

  return (
    <div className="auth">
      <span className="auth__mark">FinMentor</span>
      <section className="auth__card">
        {error === null ? (
          <p aria-busy="true">Signing you in…</p>
        ) : (
          <>
            <h2>That did not finish</h2>
            <p className="muted">{error}</p>
            <p><Link to="/login">Back to sign in</Link>.</p>
          </>
        )}
      </section>
    </div>
  );
}
