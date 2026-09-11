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

  if (user) return <Navigate to={location.state?.from ?? "/"} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      navigate(location.state?.from ?? "/", { replace: true });
    } catch (caught) {
      setError(messageFor(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
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
      <p>No account? <Link to="/signup">Create one</Link>.</p>
    </section>
  );
}
