import { type FormEvent, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { Field } from "../components/Field";
import { messageFor } from "../components/AsyncBoundary";
import { FormError } from "../components/FormError";
import { useAuth } from "../auth/AuthContext";

const MIN_PASSWORD_LENGTH = 10;

export function Signup() {
  const { user, signup } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/onboarding" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Use at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await signup(email, password);
      navigate("/onboarding", { replace: true });
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
        <h2>Create an account</h2>
        <form onSubmit={submit}>
          <Field label="Email" type="email" value={email} autoComplete="email" required
                 onChange={(e) => setEmail(e.target.value)} />
          <Field label="Password" type="password" value={password} required
                 autoComplete="new-password"
                 hint={`At least ${MIN_PASSWORD_LENGTH} characters. Length beats punctuation.`}
                 onChange={(e) => setPassword(e.target.value)} />
          <FormError message={error} />
          <div className="actions">
            <button type="submit" disabled={busy}>{busy ? "Creating…" : "Create account"}</button>
          </div>
        </form>
      </section>
      <p className="auth__alt">Already have one? <Link to="/login">Sign in</Link>.</p>
    </div>
  );
}
