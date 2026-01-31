"use client";

import { useState } from "react";
import { setSessionToken } from "../../lib/admin";
import { API_BASE_URL } from "../../lib/apiBase";
import type { TFunction } from "../../lib/i18n";

type Props = {
  t: TFunction;
  onAuthenticated: () => void;
};

export default function AdminAuth({ t, onAuthenticated }: Props) {
  const [password, setPassword] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  const verifyPassword = async () => {
    if (!password.trim()) {
      setAuthError(t("passwordRequired"));
      return;
    }
    setVerifying(true);
    setAuthError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/auth/check`, {
        headers: { "X-Admin-Token": password },
      });
      if (res.ok) {
        setSessionToken(password);
        onAuthenticated();
      } else {
        setAuthError(t("passwordIncorrect"));
      }
    } catch {
      setAuthError(t("unknownError"));
    } finally {
      setVerifying(false);
    }
  };

  return (
    <main className="min-h-screen px-6 py-10 lg:px-12">
      <section className="mx-auto max-w-md space-y-6">
        <header className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft text-center">
          <p className="text-sm uppercase tracking-[0.2em] text-copper">
            {t("admin")}
          </p>
          <h1 className="mt-3 font-display text-3xl font-semibold">
            {t("adminPageTitle")}
          </h1>
          <p className="mt-2 text-sm text-ink/70">
            {t("enterPassword")}
          </p>
        </header>

        <div className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <label className="block text-sm">
            {t("password")}
            <input
              type="password"
              className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && verifyPassword()}
              placeholder="ADMIN_TOKEN"
            />
          </label>
          {authError && (
            <p className="mt-2 text-xs text-copper">{authError}</p>
          )}
          <button
            type="button"
            onClick={verifyPassword}
            disabled={verifying}
            className="mt-4 w-full rounded-full bg-moss px-5 py-2 text-sm font-semibold text-white disabled:opacity-60"
          >
            {verifying ? t("verifying") : t("login")}
          </button>
        </div>

        <div className="text-center">
          <a
            href="/"
            className="text-sm text-ink/60 hover:text-ink"
          >
            {t("back")}
          </a>
        </div>
      </section>
    </main>
  );
}
