"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "../lib/apiBase";
import { getErrorMessage, readApiError } from "../lib/apiError";
import { useI18n } from "../lib/i18n";

type Settings = {
  github_mode: string;
  classify_mode: string;
  auto_classify_after_sync: boolean;
};

export default function SettingsPage() {
  const { t } = useI18n();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const settingsRequestIdRef = useRef(0);

  const loadSettings = useCallback(async () => {
    const requestId = settingsRequestIdRef.current + 1;
    settingsRequestIdRef.current = requestId;
    setLoading(true);
    setMessage(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/config/client-settings`);
      if (settingsRequestIdRef.current !== requestId) return;
      if (!res.ok) {
        const detail = await readApiError(res, t("unknownError"));
        throw new Error(detail);
      }
      const data = await res.json();
      if (settingsRequestIdRef.current !== requestId) return;
      setSettings(data);
    } catch (err) {
      if (settingsRequestIdRef.current !== requestId) return;
      const error = getErrorMessage(err, t("unknownError"));
      setSettings(null);
      setMessage(error);
    } finally {
      if (settingsRequestIdRef.current !== requestId) return;
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  return (
    <main className="min-h-screen px-4 py-8 md:px-12 md:py-12 bg-transparent">
      <div className="mx-auto max-w-4xl space-y-12 animate-fade-in">
        <header className="hero-surface soft-elevated relative overflow-hidden rounded-[2.5rem] p-7 md:p-8">
          <div className="hero-orb hero-orb-moss" />
          <div className="hero-orb hero-orb-copper" />
          <div className="relative flex flex-col gap-8 md:flex-row md:items-end md:justify-between">
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <span className="h-2 w-8 bg-copper rounded-full" />
              <p className="section-kicker text-copper">
                {t("settings")}
              </p>
            </div>
            <h1 className="section-title text-4xl font-extrabold md:text-5xl">
              {t("settingsPageTitle")}
            </h1>
            <p className="max-w-2xl text-base leading-relaxed text-soft md:text-lg">
              {t("settingsPageSubtitle")}
            </p>
          </div>
          <div className="flex items-center gap-3 shrink-0">
             <Link
              href="/"
              className="flex items-center gap-2 rounded-full btn-ios-secondary px-6 py-2.5 text-xs font-semibold tracking-[0.08em]"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              {t("back")}
            </Link>
            <Link
              href="/admin/"
              className="flex items-center gap-2 rounded-full btn-ios-primary px-6 py-2.5 text-xs font-semibold tracking-[0.08em]"
            >
              {t("goToAdmin")}
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </Link>
          </div>
          </div>
        </header>

        {!settings ? (
          <section className="panel-muted p-12 text-center">
             {loading ? (
              <div className="flex flex-col items-center gap-4">
                <svg className="w-8 h-8 animate-spin text-moss" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <p className="text-sm font-bold text-ink/40">{t("loadingSettings")}</p>
              </div>
            ) : (
              <div className="space-y-4">
                 <p className="text-sm font-bold text-copper">{message || t("unknownError")}</p>
                 <button
                  type="button"
                  onClick={loadSettings}
                  className="rounded-full btn-ios-secondary px-6 py-2 text-xs font-semibold tracking-[0.08em]"
                >
                  {t("retry")}
                </button>
              </div>
            )}
          </section>
        ) : (
          <div className="admin-section">
            <h2 className="panel-title mb-8">
              {t("currentConfig")}
            </h2>
            <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-3">
              <div className="info-tile space-y-2 p-6">
                <span className="info-label">
                  {t("githubMode")}
                </span>
                <p className="text-lg font-bold text-ink">
                  {settings.github_mode}
                </p>
              </div>
              <div className="info-tile space-y-2 p-6 bg-moss/5 dark:bg-moss/10">
                <span className="info-label text-moss/45">
                  {t("classifyMode")}
                </span>
                <p className="text-lg font-bold text-moss">
                  {settings.classify_mode}
                </p>
              </div>
              <div className="info-tile space-y-2 p-6 bg-copper/5 dark:bg-copper/10">
                <span className="info-label text-copper/45">
                  {t("autoClassifyAfterSync")}
                </span>
                <div className="flex items-center gap-2">
                   {settings.auto_classify_after_sync ? (
                      <svg className="w-5 h-5 text-copper" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                      </svg>
                   ) : (
                      <svg className="w-5 h-5 text-ink/20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                   )}
                   <p className={`text-lg font-bold ${settings.auto_classify_after_sync ? "text-copper" : "text-ink/20"}`}>
                    {settings.auto_classify_after_sync ? "Enabled" : "Disabled"}
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
