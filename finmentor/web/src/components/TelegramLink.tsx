/**
 * Connecting a Telegram account to this one.
 *
 * Two things in this panel are stated before the user acts rather than after,
 * because both are surprising and one of them is irreversible:
 *
 * - connecting *merges* the bot's data into this account, and where the two
 *   disagree this account wins;
 * - disconnecting leaves that merged data here. There is nothing to hand back,
 *   because the row it came from was deleted when the two were joined.
 *
 * The code is a credential with a few minutes of life. It is shown once, it is
 * never put in the URL, and the panel says when it stops working rather than
 * letting the user discover that in Telegram.
 */
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createLinkCode, getTelegramStatus, unlinkTelegram } from "../api/telegram";
import { AsyncBoundary, messageFor } from "./AsyncBoundary";
import { FormError } from "./FormError";

/** Whole minutes left, floored, never negative. */
function minutesLeft(expiresAt: string, now: number): number {
  const remaining = new Date(expiresAt).getTime() - now;
  return remaining > 0 ? Math.floor(remaining / 60_000) : 0;
}

function expiryNote(expiresAt: string, now: number): string {
  if (new Date(expiresAt).getTime() <= now) {
    return "This code has expired. Generate a new one.";
  }
  const minutes = minutesLeft(expiresAt, now);
  if (minutes < 1) return "This code expires in under a minute.";
  if (minutes === 1) return "This code expires in about a minute.";
  return `This code expires in about ${minutes} minutes.`;
}

export function TelegramLink() {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ["telegram"], queryFn: getTelegramStatus });
  const [error, setError] = useState("");
  const [confirming, setConfirming] = useState(false);

  /** Drives the countdown. One tick a second only while a code is on screen. */
  const [now, setNow] = useState(() => Date.now());

  const code = useMutation({
    mutationFn: createLinkCode,
    onMutate: () => setError(""),
    onSuccess: () => setNow(Date.now()),
    onError: (err) => setError(messageFor(err)),
  });

  const unlink = useMutation({
    mutationFn: unlinkTelegram,
    onMutate: () => setError(""),
    onSuccess: () => {
      setConfirming(false);
      code.reset();
      void queryClient.invalidateQueries({ queryKey: ["telegram"] });
    },
    onError: (err) => {
      setConfirming(false);
      setError(messageFor(err));
    },
  });

  const issued = code.data;

  useEffect(() => {
    if (!issued) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [issued]);

  return (
    <section aria-labelledby="telegram-heading" className="stack">
      <h3 id="telegram-heading">Telegram</h3>

      <AsyncBoundary isLoading={status.isLoading} error={status.error}>
        {status.data?.linked ? (
          <>
            <p role="status">
              Connected. The bot and this account are the same account, so
              anything you change in one shows up in the other.
            </p>
            <p className="muted">
              Disconnecting stops the bot from reaching this account. Everything
              already here stays here, including anything that came over from
              the bot when you connected.
            </p>
            {confirming ? (
              <div className="actions">
                <button
                  type="button"
                  className="primary"
                  onClick={() => unlink.mutate()}
                  disabled={unlink.isPending}
                >
                  {unlink.isPending ? "Disconnecting…" : "Yes, disconnect"}
                </button>
                <button type="button" onClick={() => setConfirming(false)}>
                  Keep it connected
                </button>
              </div>
            ) : (
              <div className="actions">
                <button type="button" onClick={() => setConfirming(true)}>
                  Disconnect Telegram
                </button>
              </div>
            )}
          </>
        ) : (
          <>
            <p className="muted">
              Connect the Telegram bot to this account so both show the same
              numbers. If you have been using the bot already, what is in it
              moves here. Where the two disagree, this account wins.
            </p>

            {issued ? (
              <>
                <p className="field">
                  <label htmlFor="link-code">Send this code to the bot</label>
                  <output id="link-code" className="link-code">
                    {issued.code}
                  </output>
                  <small>{expiryNote(issued.expires_at, now)}</small>
                </p>
                <ol className="muted link-steps">
                  <li>Open Telegram.</li>
                  <li>
                    Send the bot <code>/link {issued.code}</code>
                  </li>
                </ol>
                {issued.deep_link && (
                  <div className="actions">
                    <a
                      className="button-link"
                      href={issued.deep_link}
                      rel="noreferrer noopener"
                    >
                      Open Telegram and connect
                    </a>
                  </div>
                )}
                <div className="actions">
                  <button
                    type="button"
                    onClick={() => code.mutate()}
                    disabled={code.isPending}
                  >
                    {code.isPending ? "Generating…" : "Generate a new code"}
                  </button>
                </div>
                <p className="muted">
                  A new code replaces this one, so only the newest code works.
                </p>
              </>
            ) : (
              <div className="actions">
                <button
                  type="button"
                  className="primary"
                  onClick={() => code.mutate()}
                  disabled={code.isPending}
                >
                  {code.isPending ? "Generating…" : "Connect Telegram"}
                </button>
              </div>
            )}
          </>
        )}

        <FormError message={error} />
      </AsyncBoundary>
    </section>
  );
}
