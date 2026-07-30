import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch, setCsrfToken } from "./api";

describe("apiFetch session security", () => {
  afterEach(() => {
    setCsrfToken();
    vi.unstubAllGlobals();
  });

  it("includes cookies and the in-memory CSRF token on mutations", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("csrf-current");

    await apiFetch("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ enabled: true }),
    });

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(options.credentials).toBe("include");
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe(
      "csrf-current"
    );
  });

  it("refreshes a stale CSRF token from the persisted cookie and retries", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "Invalid CSRF token" }), {
          status: 403,
          headers: { "Content-Type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ csrf_token: "csrf-refreshed" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("csrf-stale");

    const response = await apiFetch("/api/settings", { method: "PUT" });

    expect(response.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toContain("/api/auth/me");
    const retryOptions = fetchMock.mock.calls[2][1] as RequestInit;
    expect(new Headers(retryOptions.headers).get("X-CSRF-Token")).toBe(
      "csrf-refreshed"
    );
  });
});
