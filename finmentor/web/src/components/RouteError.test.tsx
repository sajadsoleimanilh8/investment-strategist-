/**
 * The white screen, and the link that stops it.
 *
 * `AsyncBoundary` catches a query that rejects. It cannot catch a component
 * that throws while rendering: React unmounts the tree above it and the page
 * goes blank. That was reachable — a figure the TypeScript types as `number`
 * arriving as `null` reaches `.toFixed()` and throws — and a blank page is
 * what people mean when they say an app is broken.
 */
import { render, screen } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { Layout } from "./Layout";
import { RouteError } from "./RouteError";

function Exploding(): JSX.Element {
  throw new Error("the internal detail nobody should read");
}

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: null, logout: vi.fn() }),
}));

function renderThrowing() {
  // React logs the caught error; that is expected here and only noise.
  vi.spyOn(console, "error").mockImplementation(() => {});
  const router = createMemoryRouter(
    [{ path: "/", element: <Exploding />, errorElement: <RouteError /> }],
    { initialEntries: ["/"] },
  );
  return render(<RouterProvider router={router} />);
}

describe("a page that throws", () => {
  it("shows something instead of nothing", () => {
    renderThrowing();

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /something broke/i }))
      .toBeInTheDocument();
  });

  it("does not put the error message in front of the reader", () => {
    renderThrowing();

    // A stack trace describes this app's internals and the reader can act on
    // none of it. The console keeps the detail; the page says so.
    expect(screen.queryByText(/internal detail nobody should read/i)).toBeNull();
    expect(screen.getByText(/browser console/i)).toBeInTheDocument();
  });

  it("offers a way out rather than only an apology", () => {
    renderThrowing();

    expect(screen.getByRole("button", { name: /reload/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /dashboard/i })).toBeInTheDocument();
  });

  it("says the data is untouched, because that is the first question", () => {
    renderThrowing();

    expect(screen.getByText(/data is untouched/i)).toBeInTheDocument();
  });
});

describe("a 404 from the router", () => {
  it("does not read as a crash", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const router = createMemoryRouter(
      [{ path: "/", element: <p>home</p>, errorElement: <RouteError /> }],
      { initialEntries: ["/nowhere"] },
    );
    render(<RouterProvider router={router} />);

    expect(screen.getByRole("heading", { name: /does not exist/i })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("the skip link", () => {
  function renderLayout() {
    const router = createMemoryRouter(
      [{ path: "/dashboard", element: <Layout /> }],
      { initialEntries: ["/dashboard"] },
    );
    return render(<RouterProvider router={router} />);
  }

  it("is the first focusable thing on the page", () => {
    const { container } = renderLayout();

    const first = container.querySelector("a, button, input, select, textarea");
    expect(first).toHaveTextContent(/skip to main content/i);
  });

  it("points at a main element that can actually take focus", () => {
    const { container } = renderLayout();

    const link = screen.getByRole("link", { name: /skip to main content/i });
    expect(link).toHaveAttribute("href", "#main");

    // Without tabIndex the anchor scrolls but focus stays at the top, so the
    // next Tab goes back through the navigation the link just skipped.
    const main = container.querySelector("main");
    expect(main).toHaveAttribute("id", "main");
    expect(main).toHaveAttribute("tabindex", "-1");
  });
});
