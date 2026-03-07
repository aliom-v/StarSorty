"use client";

import Link from "next/link";
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
        <header className="hero-surface soft-elevated relative overflow-hidden rounded-[2.5rem] p-8 text-center">
          <div className="hero-orb hero-orb-moss" />
          <div className="hero-orb hero-orb-copper" />
          <div className="relative">
          <p className="section-kicker text-copper">
            {t("admin")}
          </p>
          <h1 className="mt-3 section-title text-3xl font-semibold">
            {t("adminPageTitle")}
          </h1>
          <p className="mt-2 text-sm text-soft">
            {t("enterPassword")}
          </p>
          </div>
        </header>

        <div className="admin-section">
          <label className="block text-sm">
            {t("password")}
            <input
              type="password"
              className="form-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && verifyPassword()}
              placeholder="ADMIN_TOKEN"
            />
          </label>
          {authError && (
            <div className="feedback-banner feedback-banner-error mt-4">
              <span className="feedback-icon" aria-hidden="true" />
              <p className="text-xs leading-6 text-copper">{authError}</p>
            </div>
          )}
          <button
            type="button"
            onClick={verifyPassword}
            disabled={verifying}
            className="mt-4 w-full rounded-full btn-ios-moss px-5 py-2.5 text-sm font-semibold disabled:opacity-60"
          >
            {verifying ? t("verifying") : t("login")}
          </button>
        </div>

        <div className="text-center">
          <Link
            href="/"
            className="text-sm text-ink/60 hover:text-ink"
          >
            {t("back")}
          </Link>
        </div>
      </section>
    </main>
  );
}
