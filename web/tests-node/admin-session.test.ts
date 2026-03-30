import assert from "node:assert/strict";
import test from "node:test";

import {
  adminFetch,
  buildAdminHeaders,
  clearAdminClientState,
  getAdminCsrfToken,
} from "../app/lib/admin";

type StorageMap = Map<string, string>;

function createStorage(initial: Record<string, string> = {}) {
  const values: StorageMap = new Map(Object.entries(initial));
  return {
    getItem(key: string) {
      return values.has(key) ? values.get(key)! : null;
    },
    setItem(key: string, value: string) {
      values.set(key, String(value));
    },
    removeItem(key: string) {
      values.delete(key);
    },
  };
}

function createDocument(initial: Record<string, string> = {}) {
  const cookies: StorageMap = new Map(Object.entries(initial));
  return {
    get cookie() {
      return Array.from(cookies.entries())
        .map(([key, value]) => `${key}=${value}`)
        .join("; ");
    },
    set cookie(value: string) {
      const [pair] = value.split(";");
      const separatorIndex = pair.indexOf("=");
      const key = pair.slice(0, separatorIndex).trim();
      const cookieValue = pair.slice(separatorIndex + 1).trim();
      if (/max-age=0/i.test(value) || cookieValue === "") {
        cookies.delete(key);
        return;
      }
      cookies.set(key, cookieValue);
    },
  };
}

async function withBrowser(
  windowValue: typeof globalThis.window,
  documentValue: Document,
  fetchValue: typeof globalThis.fetch,
  fn: () => void | Promise<void>
) {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const originalFetch = globalThis.fetch;
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: windowValue,
  });
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: documentValue,
  });
  Object.defineProperty(globalThis, "fetch", {
    configurable: true,
    value: fetchValue,
  });
  try {
    await fn();
  } finally {
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: originalWindow,
    });
    Object.defineProperty(globalThis, "document", {
      configurable: true,
      value: originalDocument,
    });
    Object.defineProperty(globalThis, "fetch", {
      configurable: true,
      value: originalFetch,
    });
  }
}

test("admin helpers read csrf cookie and clear legacy browser token state", async () => {
  const localStorage = createStorage({
    "starsorty.admin_token": "legacy-token",
  });
  const sessionStorage = createStorage({
    "starsorty.admin_session": "legacy-session-token",
  });
  const document = createDocument({
    starsorty_admin_csrf: "csrf-token",
  }) as Document;

  await withBrowser(
    { localStorage, sessionStorage } as typeof globalThis.window,
    document,
    globalThis.fetch,
    () => {
      assert.equal(getAdminCsrfToken(), "csrf-token");
      assert.equal(localStorage.getItem("starsorty.admin_token"), null);
      assert.equal(sessionStorage.getItem("starsorty.admin_session"), null);
      assert.deepEqual(buildAdminHeaders(), {
        "X-CSRF-Token": "csrf-token",
      });

      clearAdminClientState();
      assert.equal(getAdminCsrfToken(), "");
      assert.deepEqual(buildAdminHeaders(), {});
    }
  );
});

test("adminFetch includes credentials and csrf header for admin requests", async () => {
  const calls: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
  const document = createDocument({
    starsorty_admin_csrf: "csrf-token",
  }) as Document;

  await withBrowser(
    { localStorage: createStorage(), sessionStorage: createStorage() } as typeof globalThis.window,
    document,
    async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ input, init });
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    },
    async () => {
      await adminFetch("/api/protected", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
    }
  );

  assert.equal(calls.length, 1);
  assert.equal(calls[0].input, "/api/protected");
  assert.equal(calls[0].init?.credentials, "include");
  assert.deepEqual(calls[0].init?.headers, {
    "Content-Type": "application/json",
    "X-CSRF-Token": "csrf-token",
  });
});
