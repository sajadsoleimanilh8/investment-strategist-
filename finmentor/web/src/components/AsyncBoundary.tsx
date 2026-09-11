/**
 * Loading / error / empty, in one place.
 *
 * Every page has these three states and none of them is interesting enough to
 * write eleven times. `empty` is opt-in: an empty watchlist is a real screen,
 * an empty health score is a bug.
 *
 * The error branch is the one that earns its keep. A rejected query that
 * renders nothing is the blank screen people mean when they say an app is
 * broken — so this always says something, and for an `ApiError` it says the
 * thing the API actually reported rather than a generic apology.
 */
import type { ReactNode } from "react";

import { ApiError } from "../api/client";

interface AsyncBoundaryProps {
  isLoading: boolean;
  error: unknown;
  isEmpty?: boolean;
  emptyMessage?: string;
  /** Re-run the failed query. Offered on anything that might be transient. */
  onRetry?: () => void;
  children: ReactNode;
}

/** What to put in front of someone for a failure of unknown provenance. */
export function messageFor(error: unknown): string {
  if (error instanceof ApiError) return error.userMessage;
  if (error instanceof Error && error.message) return error.message;
  return "Something went wrong.";
}

/** Offline and server errors are worth retrying; a 403 never is. */
function worthRetrying(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true;
  return error.isOffline || error.status >= 500 || error.status === 429;
}

export function AsyncBoundary({
  isLoading, error, isEmpty = false, emptyMessage = "Nothing here yet.",
  onRetry, children,
}: AsyncBoundaryProps) {
  if (isLoading) return <p aria-busy="true">Loading…</p>;

  if (error) {
    return (
      <div role="alert">
        <p>{messageFor(error)}</p>
        {onRetry && worthRetrying(error) && (
          <button type="button" onClick={onRetry}>Try again</button>
        )}
      </div>
    );
  }

  if (isEmpty) return <p>{emptyMessage}</p>;
  return <>{children}</>;
}
