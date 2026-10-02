/**
 * The connect panel, driven through the DOM.
 *
 * Two of these are about copy rather than behaviour, and they are here on
 * purpose. Connecting merges data with this account winning, and
 * disconnecting does not give the merged data back. Both are surprising, and
 * a user who only finds out afterwards has no way to undo either, so the
 * warnings are part of what the component is for.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TelegramLink } from "./TelegramLink";
import type { LinkCode, TelegramStatus } from "../api/types";

const api = vi.hoisted(() => ({
  status: { linked: false, telegram_id: null } as TelegramStatus,
  issued: [] as number[],
  unlinked: 0,
  code: null as LinkCode | null,
  failCode: null as Error | null,
}));

vi.mock("../api/telegram", () => ({
  getTelegramStatus: () => Promise.resolve(api.status),
  createLinkCode: () => {
    api.issued.push(Date.now());
    if (api.failCode) return Promise.reject(api.failCode);
    return Promise.resolve(api.code);
  },
  unlinkTelegram: () => {
    api.unlinked += 1;
    api.status = { linked: false, telegram_id: null };
    return Promise.resolve(undefined);
  },
}));

function freshCode(overrides: Partial<LinkCode> = {}): LinkCode {
  return {
    code: "ABCD-EFGH-JKMN",
    expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
    ttl_minutes: 10,
    deep_link: "https://t.me/FinMentorBot?start=link_ABCDEFGHJKMN",
    ...overrides,
  };
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TelegramLink />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.status = { linked: false, telegram_id: null };
  api.issued = [];
  api.unlinked = 0;
  api.code = freshCode();
  api.failCode = null;
});

describe("before connecting", () => {
  it("says which side wins before the user acts, not after", async () => {
    renderPanel();

    expect(await screen.findByText(/this account wins/i)).toBeInTheDocument();
  });

  it("shows the code and both ways to use it", async () => {
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: /connect telegram/i }));

    expect(await screen.findByText("ABCD-EFGH-JKMN")).toBeInTheDocument();
    expect(screen.getByText(/\/link ABCD-EFGH-JKMN/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open telegram/i })).toHaveAttribute(
      "href",
      "https://t.me/FinMentorBot?start=link_ABCDEFGHJKMN",
    );
  });

  it("falls back to the typed code when there is no deep link", async () => {
    api.code = freshCode({ deep_link: null });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: /connect telegram/i }));

    expect(await screen.findByText("ABCD-EFGH-JKMN")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /open telegram/i })).toBeNull();
  });

  it("says how long the code lasts", async () => {
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: /connect telegram/i }));

    expect(await screen.findByText(/expires in about 9 minutes/i)).toBeInTheDocument();
  });

  it("says a code has expired rather than leaving it looking usable", async () => {
    api.code = freshCode({ expires_at: new Date(Date.now() - 1000).toISOString() });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: /connect telegram/i }));

    expect(await screen.findByText(/has expired/i)).toBeInTheDocument();
  });

  it("warns that a new code replaces the old one", async () => {
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: /connect telegram/i }));
    await screen.findByText("ABCD-EFGH-JKMN");
    fireEvent.click(screen.getByRole("button", { name: /generate a new code/i }));

    await waitFor(() => expect(api.issued).toHaveLength(2));
    expect(screen.getByText(/only the newest code works/i)).toBeInTheDocument();
  });

  it("announces a failure instead of showing nothing", async () => {
    api.failCode = new Error("too many codes at once");
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: /connect telegram/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/too many codes/i);
  });
});

describe("once connected", () => {
  beforeEach(() => {
    api.status = { linked: true, telegram_id: 4242 };
  });

  it("does not offer a code it would refuse", async () => {
    renderPanel();

    expect(await screen.findByRole("status")).toHaveTextContent(/^Connected\./);
    expect(screen.queryByRole("button", { name: /^connect telegram$/i })).toBeNull();
  });

  it("says the merged data stays here before offering to disconnect", async () => {
    renderPanel();

    expect(await screen.findByText(/already here stays here/i)).toBeInTheDocument();
  });

  it("asks before disconnecting", async () => {
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: /disconnect telegram/i }));

    expect(api.unlinked).toBe(0);
    expect(screen.getByRole("button", { name: /yes, disconnect/i })).toBeInTheDocument();
  });

  it("disconnects only after the confirmation", async () => {
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: /disconnect telegram/i }));
    fireEvent.click(screen.getByRole("button", { name: /yes, disconnect/i }));

    await waitFor(() => expect(api.unlinked).toBe(1));
  });

  it("leaves it connected when the confirmation is declined", async () => {
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: /disconnect telegram/i }));
    fireEvent.click(screen.getByRole("button", { name: /keep it connected/i }));

    expect(api.unlinked).toBe(0);
    expect(await screen.findByRole("button", { name: /disconnect telegram/i }))
      .toBeInTheDocument();
  });
});
