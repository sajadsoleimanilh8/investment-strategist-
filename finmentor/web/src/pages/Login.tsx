import { type FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { Field } from "../components/Field";
import { messageFor } from "../components/AsyncBoundary";
import { FormError } from "../components/FormError";
import { useAuth } from "../auth/AuthContext";

export function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
