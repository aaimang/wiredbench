import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { ApiFailure, request, setCsrfToken, setSignedOutHandler, withQuery } from "./api";
import { h } from "./dom";
import { diffEntry } from "./update-dialog";

const HOSTILE = '<img src=x onerror="alert(1)">';

describe("untrusted text", () => {
  it("stays text in elements", () => {
    const element = h("div", {}, HOSTILE);
    expect(element.querySelector("img")).toBeNull();
    expect(element.textContent).toBe(HOSTILE);
  });

  it("stays text in the update diff, which shows Habbo's data", () => {
    const entry = diffEntry({
      classname: HOSTILE,
      change: "changed",
      is_wired: true,
      wired_type: "effect",
      name: HOSTILE,
      fields: [{ field: HOSTILE, old: HOSTILE, new: HOSTILE }],
    });
    expect(entry.querySelector("img")).toBeNull();
    expect(entry.textContent).toContain(HOSTILE);
  });

  it("source never uses HTML-string APIs", () => {
    const banned =
      /\.innerHTML|\.outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function/;
    const folder = join(process.cwd(), "src");
    for (const name of readdirSync(folder)) {
      if (!name.endsWith(".ts") || name.endsWith(".test.ts")) continue;
      expect(readFileSync(join(folder, name), "utf8"), name).not.toMatch(banned);
    }
  });
});

describe("api client", () => {
  it("builds query strings and drops empty values", () => {
    expect(withQuery("/a", { q: "x y", none: "", n: 0, u: undefined })).toBe("/a?q=x+y&n=0");
    expect(withQuery("/a")).toBe("/a");
  });

  it("sends the CSRF token on writes only", async () => {
    const fetcher = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetcher);
    setCsrfToken("token");
    await request("POST", "/x", {});
    await request("GET", "/x");
    const sent = fetcher.mock.calls as unknown as [string, { headers: Record<string, string> }][];
    const headers = sent.map(([, init]) => init.headers);
    expect(headers.map((h) => h["X-CSRF-Token"])).toEqual(["token", undefined]);
    vi.unstubAllGlobals();
  });

  it("turns error responses into ApiFailure and reports sign-out", async () => {
    const signedOut = vi.fn();
    setSignedOutHandler(signedOut);
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () => new Response('{"error":"not_logged_in","message":"Log in."}', { status: 401 }),
      ),
    );
    await expect(request("GET", "/x")).rejects.toMatchObject({
      code: "not_logged_in",
      status: 401,
    });
    expect(signedOut).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });

  it("reports an unreachable server clearly", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("network");
      }),
    );
    await expect(request("GET", "/x")).rejects.toBeInstanceOf(ApiFailure);
    vi.unstubAllGlobals();
  });
});
