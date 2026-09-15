/**
 * The page a reset link opens.
 *
 * The token is in the query string because that is where an emailed link can
 * carry it, and it never leaves this page: it is read once, posted in a body,
 * and the app navigates away. It is not stored, not logged, and not put back
 * into the URL.
 *
 * A successful reset returns a token pair, so this page signs the person in
 * and goes to the dashboard rather than bouncing them to a login form they
 * have just earned the right to skip.
 */
import { type FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { resetPassword } from "../api/auth";
import { Field } from "../components/Field";
import { messageFor } from "../components/AsyncBoundary";
import { FormError } from "../components/FormError";
import { useAuth } from "../auth/AuthContext";

const MIN_PASSWORD_LENGTH = 10;

export function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const { refreshUser } = useAuth();

  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Use at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await resetPassword(token, password);
      // The pair is already stored by `resetPassword`; this makes the context
      // notice, so the guarded route does not bounce us straight back out.
      await refreshUser();
      navigate("/dashboard", { replace: true });
    } catch (caught) {
      setError(messageFor(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth stagger">
      <Link to="/" className="auth__mark">FinMentor</Link>
      <section className="auth__card">
        <h2>Choose a new password</h2>
        {token === "" ? (
          // Reached without a token: a bookmarked page, or a link a mail
          // client cut in half. Saying so beats a form that cannot work.
          <>
            <p className="muted">
              This page needs the link from your email. It looks like the address
              lost the part after the question mark.
            </p>
            <p>
              <Link to="/forgot-password">Send a new link</Link>.
            </p>
          </>
        ) : (
          <form onSubmit={submit}>
            <Field
              label="New password"
              type="password"
              value={password}
              autoComplete="new-password"
              required
              hint={`At least ${MIN_PASSWORD_LENGTH} characters. Length beats punctuation.`}
              onChange={(e) => setPassword(e.target.value)}
            />
            <FormError message={error} />
            <div className="actions">
              <button type="submit" disabled={busy}>
                {busy ? "Saving…" : "Set password and sign in"}
              </button>
            </div>
          </form>
        )}
      </section>
      <p className="auth__alt">
        <Link to="/login">Back to sign in</Link>.
      </p>
    </div>
  );
}
