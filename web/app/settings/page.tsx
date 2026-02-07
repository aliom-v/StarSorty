"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "../lib/apiBase";
import { getErrorMessage, readApiError } from "../lib/apiError";
import { useI18n } from "../lib/i18n";

type Settings = {
  github_username: string;
  github_target_username: string;
  github_usernames: string;
  github_include_self: boolean;
  github_mode: string;
  classify_mode: string;
  auto_classify_after_sync: boolean;
  rules_json: string;
  sync_cron: string;
  sync_timeout: number;
  github_token_set: boolean;
  ai_api_key_set: boolean;
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
      const res = await fetch(`${API_BASE_URL}/settings`);
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

  if (!settings) {
    return (
      <main className="min-h-screen px-6 py-10 lg:px-12">
        <section className="mx-auto max-w-4xl rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <p className="text-sm text-ink/70">
            {loading ? t("loadingRepos") : message || t("unknownError")}
          </p>
          {!loading && (
            <button
              type="button"
              onClick={loadSettings}
              className="mt-4 rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink"
            >
              {t("retry")}
            </button>
          )}
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen px-6 py-10 lg:px-12">
      <section className="mx-auto max-w-4xl space-y-6">
        <header className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <p className="text-sm uppercase tracking-[0.2em] text-copper">
            {t("settings")}
          </p>
          <h1 className="mt-3 font-display text-3xl font-semibold">
            {t("settingsPageTitle")}
          </h1>
          <p className="mt-2 text-sm text-ink/70">
            {t("settingsPageSubtitle")}
          </p>
          <div className="mt-4">
            <a
              href="/admin/"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex rounded-full bg-moss px-4 py-2 text-sm font-semibold text-white"
            >
              {t("goToAdmin")}
            </a>
          </div>
        </header>

        <div className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <h2 className="font-display text-lg font-semibold">{t("tokenStatus")}</h2>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border border-ink/10 bg-surface px-4 py-3">
              <div className="text-xs uppercase tracking-wider text-ink/60">
                {t("githubTokenSet")}
              </div>
              <div className={`mt-1 text-sm font-medium ${settings.github_token_set ? "text-moss" : "text-copper"}`}>
                {settings.github_token_set ? t("configured") : t("notConfigured")}
              </div>
            </div>
            <div className="rounded-2xl border border-ink/10 bg-surface px-4 py-3">
              <div className="text-xs uppercase tracking-wider text-ink/60">
                {t("aiApiKeySet")}
              </div>
              <div className={`mt-1 text-sm font-medium ${settings.ai_api_key_set ? "text-moss" : "text-copper"}`}>
                {settings.ai_api_key_set ? t("configured") : t("notConfigured")}
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <h2 className="font-display text-lg font-semibold">{t("currentConfig")}</h2>
          <div className="mt-4 space-y-3">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <div className="text-xs uppercase tracking-wider text-ink/60">
                  {t("githubUsername")}
                </div>
                <div className="mt-1 text-sm">
                  {settings.github_username || "-"}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-ink/60">
                  {t("githubTargetUsername")}
                </div>
                <div className="mt-1 text-sm">
                  {settings.github_target_username || "-"}
                </div>
              </div>
              <div className="md:col-span-2">
                <div className="text-xs uppercase tracking-wider text-ink/60">
                  {t("githubUsernames")}
                </div>
                <div className="mt-1 text-sm">
                  {settings.github_usernames || "-"}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-ink/60">
                  {t("githubMode")}
                </div>
                <div className="mt-1 text-sm">
                  {settings.github_mode}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-ink/60">
                  {t("githubIncludeSelf")}
                </div>
                <div className="mt-1 text-sm">
                  {settings.github_include_self ? "✓" : "-"}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-ink/60">
                  {t("classifyMode")}
                </div>
                <div className="mt-1 text-sm">
                  {settings.classify_mode}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-ink/60">
                  {t("autoClassifyAfterSync")}
                </div>
                <div className="mt-1 text-sm">
                  {settings.auto_classify_after_sync ? "✓" : "-"}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-ink/60">
                  {t("syncCron")}
                </div>
                <div className="mt-1 text-sm font-mono">
                  {settings.sync_cron}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-ink/60">
                  {t("syncTimeout")}
                </div>
                <div className="mt-1 text-sm">
                  {settings.sync_timeout}s
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <a
            href="/"
            className="rounded-full border border-ink/10 bg-surface px-5 py-2 text-sm font-semibold text-ink"
          >
            {t("back")}
          </a>
        </div>
      </section>
    </main>
  );
}
