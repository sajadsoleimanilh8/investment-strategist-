import { type FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { Field } from "../components/Field";
import { ProviderSignIn } from "../components/ProviderSignIn";
import { messageFor } from "../components/AsyncBoundary";
import { FormError } from "../components/FormError";
import { useAuth } from "../auth/AuthContext";

/** The reason codes `app/api/routes/oauth.py` redirects back with. */
const OAUTH_ERRORS: Record<string, string> = {
  cancelled: "That sign-in was cancelled.",
  state: "That sign-in link expired. Try again.",
  provider: "The provider could not sign you in. Try again, or use your email.",
  no_email: "That account gave us no verified email address, so we cannot use it here.",
};

export function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [params] = useSearchParams();
  // A failed provider sign-in comes back here with a reason code rather than
  // a message: what went wrong at Google is for the log, and the person needs
  // one sentence and a way to try again.
  const [error, setError] = useState<string | null>(
    OAUTH_ERRORS[params.get("error") ?? ""] ?? null);

  if (user) return <Navigate to={location.state?.from ?? "/dashboard"} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      navigate(location.state?.from ?? "/dashboard", { replace: true });
    } catch (caught) {
      setError(messageFor(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth stagger">
      {/* The only way back to the marketing page. Someone who arrives here
          from a bookmark otherwise has no route to "/" and no brand anchor. */}
      <Link to="/" className="auth__mark">FinMentor</Link>
      <section className="auth__card">
        <h2>Sign in</h2>
        <ProviderSignIn next={location.state?.from ?? "/dashboard"} />
        <form onSubmit={submit}>
          <Field label="Email" type="email" value={email} autoComplete="email" required
                 onChange={(e) => setEmail(e.target.value)} />
          <Field label="Password" type="password" value={password} required
                 autoComplete="current-password"
                 onChange={(e) => setPassword(e.target.value)} />
          <FormError message={error} />
          <div className="actions">
            <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
          </div>
        </form>
        <p className="auth__aside">
          <Link to="/forgot-password">Forgot your password?</Link>
        </p>
      </section>
      <p className="auth__alt">No account? <Link to="/signup">Create one</Link>.</p>
    </div>
  );
}
