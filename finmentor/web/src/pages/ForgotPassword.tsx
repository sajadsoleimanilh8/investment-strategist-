/**
 * "I cannot get in."
 *
 * The confirmation is deliberately the same sentence whether or not the
 * address has an account. The API answers that way on purpose (it is an
 * account-existence oracle otherwise), and a page that said "we could not
 * find that email" would hand back exactly what the API just refused to say.
 *
 * So the screen changes state on *sent*, not on *found*, and the copy is
 * about the address rather than the account.
 */
import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { forgotPassword } from "../api/auth";
import { Field } from "../components/Field";
import { messageFor } from "../components/AsyncBoundary";
import { FormError } from "../components/FormError";

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await forgotPassword(email);
      setSent(true);
    } catch (caught) {
      // Only a transport failure reaches here: a rate limit, or no network.
      setError(messageFor(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth stagger">
      <Link to="/" className="auth__mark">FinMentor</Link>
      <section className="auth__card">
        <h2>Reset your password</h2>
        {sent ? (
          <div role="status">
            <p className="saved">Check your email.</p>
            <p className="muted">
              If {email} has an account, a link is on its way. It works once and
              expires in an hour.
            </p>
          </div>
        ) : (
          <form onSubmit={submit}>
            <Field
              label="Email"
              type="email"
              value={email}
              autoComplete="email"
              required
              hint="We will send a link that lets you set a new password."
              onChange={(e) => setEmail(e.target.value)}
            />
            <FormError message={error} />
            <div className="actions">
              <button type="submit" disabled={busy || !email.trim()}>
                {busy ? "Sending…" : "Send the link"}
              </button>
            </div>
          </form>
        )}
      </section>
      <p className="auth__alt">
        Remembered it? <Link to="/login">Sign in</Link>.
      </p>
    </div>
  );
}
