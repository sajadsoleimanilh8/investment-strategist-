/**
 * The API client's two jobs: carry the token, and survive it expiring.
 *
 * The refresh-on-401 path is the one worth testing hardest. It is invisible
 * when it works and looks exactly like "logged out at random" when it does
 * not, so the cases here are the ones that produce that symptom: a single
 * retry, a shared refresh under concurrency, and no retry at all on the
 * endpoints that mint tokens in the first place.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError, OFFLINE_MESSAGE, api, getAccessToken, request, restoreSession, setTokens,
} from "./client";

const PAIR = {
  access_token: "access-1",
  refresh_token: "refresh-1",
  token_type: "bearer",
  expires_in: 1800,
};

const FRESH = { ...PAIR, access_token: "access-2", refresh_token: "refresh-2" };

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function emptyResponse(status: number): Response {
  return new Response(null, { status });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  localStorage.clear();
  setTokens(null);
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function urlOf(call: unknown[]): string {
  return String(call[0]);
}

function headersOf(call: unknown[]): Record<string, string> {
  return ((call[1] as RequestInit)?.headers ?? {}) as Record<string, string>;
}

describe("tokens", () => {
  it("keeps the access token in memory and the refresh token in storage", () => {
    setTokens(PAIR);

    expect(getAccessToken()).toBe("access-1");
    expect(localStorage.getItem("finmentor.refresh_token")).toBe("refresh-1");
  });

  it("clears both on sign out", () => {
    setTokens(PAIR);
    setTokens(null);

    expect(getAccessToken()).toBeNull();
    expect(localStorage.getItem("finmentor.refresh_token")).toBeNull();
  });

  it("never puts the access token in storage", () => {
    setTokens(PAIR);

    expect(JSON.stringify(localStorage)).not.toContain("access-1");
  });
});

describe("requests", () => {
  it("sends the bearer token", async () => {
    setTokens(PAIR);
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));

    await api.get("/api/auth/me");

    expect(headersOf(fetchMock.mock.calls[0]).Authorization).toBe("Bearer access-1");
  });

  it("sends no authorization header when signed out", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));

    await api.get("/api/learn");

    expect(headersOf(fetchMock.mock.calls[0]).Authorization).toBeUndefined();
  });

  it("returns undefined for a 204 rather than choking on an empty body", async () => {
    setTokens(PAIR);
    fetchMock.mockResolvedValue(emptyResponse(204));

    await expect(api.del("/api/market/watchlist/1/BTC")).resolves.toBeUndefined();
  });

  it("throws an ApiError carrying the status and the detail", async () => {
    setTokens(PAIR);
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: "you can only access your own data" }, 403),
    );

    // One call, both assertions: a `Response` body can only be read once, so
    // asking twice would be testing the mock rather than the client.
    const failure = await api.get("/api/users/2").catch((caught: unknown) => caught);

    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(403);
    expect((failure as ApiError).detail).toBe("you can only access your own data");
  });

  it("reads a FastAPI validation error into something a human can act on", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: [{ msg: "value is not a valid email address" }] }, 422),
    );

    await expect(api.post("/api/auth/signup", {}, true))
      .rejects.toThrow("value is not a valid email address");
  });

  it("falls back to the status text when the body is not JSON", async () => {
    fetchMock.mockResolvedValue(new Response("<html>502</html>", { status: 502 }));

    await expect(api.get("/api/learn")).rejects.toThrowError(ApiError);
  });
});

describe("refresh on 401", () => {
  it("refreshes once and retries the original request", async () => {
    setTokens(PAIR);
    fetchMock
      .mockResolvedValueOnce(emptyResponse(401))          // the original
      .mockResolvedValueOnce(jsonResponse(FRESH))         // the refresh
      .mockResolvedValueOnce(jsonResponse({ id: 1 }));    // the retry

    await expect(api.get<{ id: number }>("/api/auth/me")).resolves.toEqual({ id: 1 });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(urlOf(fetchMock.mock.calls[1])).toContain("/api/auth/refresh");
    expect(headersOf(fetchMock.mock.calls[2]).Authorization).toBe("Bearer access-2");
  });

  it("stores the rotated pair", async () => {
    setTokens(PAIR);
    fetchMock
      .mockResolvedValueOnce(emptyResponse(401))
      .mockResolvedValueOnce(jsonResponse(FRESH))
      .mockResolvedValueOnce(jsonResponse({}));

    await api.get("/api/auth/me");

    expect(getAccessToken()).toBe("access-2");
    expect(localStorage.getItem("finmentor.refresh_token")).toBe("refresh-2");
  });

  it("gives up and signs out when the refresh itself is refused", async () => {
    setTokens(PAIR);
    fetchMock
      .mockResolvedValueOnce(emptyResponse(401))
      .mockResolvedValueOnce(emptyResponse(401));

    await expect(api.get("/api/auth/me")).rejects.toThrowError(ApiError);
    expect(getAccessToken()).toBeNull();
    expect(localStorage.getItem("finmentor.refresh_token")).toBeNull();
  });

  it("does not retry more than once", async () => {
    setTokens(PAIR);
    fetchMock
      .mockResolvedValueOnce(emptyResponse(401))
      .mockResolvedValueOnce(jsonResponse(FRESH))
      .mockResolvedValueOnce(emptyResponse(401));         // still 401 after refresh

    await expect(api.get("/api/auth/me")).rejects.toThrowError(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("shares one refresh across concurrent 401s", async () => {
    // The dashboard fires several requests at once. If each starts its own
    // refresh they rotate the token out from under each other and all but the
    // last one fails — which looks like a random logout.
    setTokens(PAIR);
    fetchMock.mockImplementation((url: string) => {
      if (String(url).includes("/api/auth/refresh")) return Promise.resolve(jsonResponse(FRESH));
      const header = "Bearer access-2";
      return Promise.resolve(
        fetchMock.mock.calls.at(-1)?.[1]?.headers?.Authorization === header
          ? jsonResponse({ ok: true })
          : emptyResponse(401),
      );
    });

    await Promise.all([
      api.get("/api/me/summary").catch(() => null),
      api.get("/api/goals/1").catch(() => null),
      api.get("/api/learn").catch(() => null),
    ]);

    const refreshes = fetchMock.mock.calls.filter((call) =>
      urlOf(call).includes("/api/auth/refresh"));
    expect(refreshes).toHaveLength(1);
  });

  it("never refreshes on an anonymous request", async () => {
    // Login and signup 401 legitimately — wrong password is not an expired
    // session, and retrying it would hide the real error.
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "bad credentials" }, 401));

    await expect(api.post("/api/auth/login", { email: "a@b.c" }, true)).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not try to refresh with no stored token", async () => {
    fetchMock.mockResolvedValueOnce(emptyResponse(401));

    await expect(request("/api/auth/me")).rejects.toThrowError(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("restoreSession", () => {
  it("is false with nothing stored", async () => {
    await expect(restoreSession()).resolves.toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("recovers a session from the stored refresh token", async () => {
    setTokens(PAIR);
    setTokens({ ...PAIR, access_token: "" });      // simulate a reload: memory gone
    localStorage.setItem("finmentor.refresh_token", "refresh-1");
    fetchMock.mockResolvedValueOnce(jsonResponse(FRESH));

    await expect(restoreSession()).resolves.toBe(true);
    expect(getAccessToken()).toBe("access-2");
  });

  it("is false when the stored token has expired", async () => {
    localStorage.setItem("finmentor.refresh_token", "stale");
    fetchMock.mockResolvedValueOnce(emptyResponse(401));

    await expect(restoreSession()).resolves.toBe(false);
  });
});

describe("errors a person has to read", () => {
  it("reads the API's error envelope", async () => {
    setTokens(PAIR);
    fetchMock.mockResolvedValue(jsonResponse(
      { error: { code: "forbidden", message: "you can only access your own data",
                 request_id: "ab12cd34" } }, 403));

    await expect(api.get("/api/users/2"))
      .rejects.toThrow("you can only access your own data");
  });

  it("keeps the request id so a 500 can be quoted to support", async () => {
    setTokens(PAIR);
    fetchMock.mockResolvedValue(jsonResponse(
      { error: { code: "internal_error", message: "Something went wrong on our side.",
                 request_id: "deadbeef" } }, 500));

    const error = (await api.get("/api/me/summary").catch((e) => e)) as ApiError;

    expect(error.requestId).toBe("deadbeef");
    expect(error.userMessage).toContain("deadbeef");
  });

  it("prefers field-level messages, which a form can point at", async () => {
    fetchMock.mockResolvedValue(jsonResponse({
      error: {
        code: "invalid_request", message: "Some of that was not valid.",
        request_id: "aa11bb22",
        fields: [{ field: "email", message: "is not a valid email address" }],
      },
    }, 422));

    await expect(api.post("/api/auth/signup", {}, true))
      .rejects.toThrow("email: is not a valid email address");
  });

  it("still understands FastAPI's own shape from anything upstream of us", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Not Found" }, 404));

    await expect(api.get("/api/nope")).rejects.toThrow("Not Found");
  });

  it("falls back to the status text for a proxy's HTML error page", async () => {
    fetchMock.mockResolvedValue(new Response("<html>502 Bad Gateway</html>",
                                             { status: 502, statusText: "Bad Gateway" }));

    await expect(api.get("/api/me/summary")).rejects.toThrow("Bad Gateway");
  });
});

describe("the network being down", () => {
  it("becomes a readable message, not an unhandled TypeError", async () => {
    // An unhandled rejection here is what renders as a blank screen.
    setTokens(PAIR);
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    const error = (await api.get("/api/me/summary").catch((e) => e)) as ApiError;

    expect(error).toBeInstanceOf(ApiError);
    expect(error.isOffline).toBe(true);
    expect(error.userMessage).toBe(OFFLINE_MESSAGE);
  });

  it("does not mistake being offline for being signed out", async () => {
    // Clearing tokens here would log someone out every time their wifi
    // hiccups, and they would have to sign in again to find that out.
    setTokens(PAIR);
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await api.get("/api/me/summary").catch(() => null);

    expect(getAccessToken()).toBe("access-1");
  });

  it("handles the connection dropping during the retry after a refresh", async () => {
    setTokens(PAIR);
    fetchMock
      .mockResolvedValueOnce(emptyResponse(401))
      .mockResolvedValueOnce(jsonResponse(FRESH))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"));

    const error = (await api.get("/api/auth/me").catch((e) => e)) as ApiError;

    expect(error.isOffline).toBe(true);
  });
});
