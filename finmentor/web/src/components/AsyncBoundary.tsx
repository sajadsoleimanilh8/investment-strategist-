/**
 * Loading / error / empty, in one place.
 *
 * Every page has these three states and none of them is interesting enough to
 * write eleven times. `empty` is opt-in: an empty watchlist is a real screen,
 * an empty health score is a bug.
 */
import type { ReactNode } from "react";

interface AsyncBoundaryProps {
  isLoading: boolean;
  error: unknown;
  isEmpty?: boolean;
  emptyMessage?: string;
  children: ReactNode;
}

export function AsyncBoundary({
  isLoading, error, isEmpty = false, emptyMessage = "Nothing here yet.", children,
}: AsyncBoundaryProps) {
  if (isLoading) return <p aria-busy="true">Loading…</p>;
  if (error) {
    const message = error instanceof Error ? error.message : "Something went wrong.";
    return <p role="alert">{message}</p>;
  }
  if (isEmpty) return <p>{emptyMessage}</p>;
  return <>{children}</>;
}
