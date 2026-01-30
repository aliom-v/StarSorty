"use client";

import { useCallback, useEffect, useState } from "react";
import {
  clearSessionToken,
  isSessionAuthenticated,
} from "../lib/admin";
import { API_BASE_URL } from "../lib/apiBase";
import { getErrorMessage, readApiError } from "../lib/apiError";
import { useI18n } from "../lib/i18n";

import AdminAuth from "./components/AdminAuth";
import SyncSection from "./components/SyncSection";
import ClassifySection from "./components/ClassifySection";
import FailedReposSection from "./components/FailedReposSection";
import ExportSection from "./components/ExportSection";
import SettingsSection from "./components/SettingsSection";

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

export default function AdminPage() {
  const { t } = useI18n();
  const [authenticated, setAuthenticated] = useState(false);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (isSessionAuthenticated()) {
      setAuthenticated(true);
    }
  }, []);

  const handleLogout = () => {
    clearSessionToken();
    setAuthenticated(false);
  };

  const loadSettings = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/settings`);
      if (!res.ok) {
        const detail = await readApiError(res, t("unknownError"));
        throw new Error(detail);
      }
      const data = await res.json();
      setSettings(data);
    } catch (err) {
      setMessage(getErrorMessage(err, t("unknownError")));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (authenticated) {
      loadSettings();
    }
  }, [authenticated, loadSettings]);

  if (!authenticated) {
    return (
      <AdminAuth
        t={t}
        onAuthenticated={() => setAuthenticated(true)}
      />
    );
  }

  if (loading || !settings) {
    return (
      <main className="min-h-screen px-6 py-10 lg:px-12">
        <section className="mx-auto max-w-4xl rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <p className="text-sm text-ink/70">{t("loadingSettings")}</p>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen px-6 py-10 lg:px-12">
      <section className="mx-auto max-w-4xl space-y-6">
        <header className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm uppercase tracking-[0.2em] text-copper">
                {t("admin")}
              </p>
              <h1 className="mt-3 font-display text-3xl font-semibold">
                {t("adminPageTitle")}
              </h1>
              <p className="mt-2 text-sm text-ink/70">
                {t("adminPageSubtitle")}
              </p>
            </div>
            <button
              type="button"
              onClick={handleLogout}
              className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink hover:border-copper hover:text-copper"
            >
              {t("logout")}
            </button>
          </div>
        </header>

        <SyncSection t={t} setMessage={setMessage} />

        <ClassifySection t={t} message={message} setMessage={setMessage} />

        <FailedReposSection t={t} setMessage={setMessage} />

        <ExportSection t={t} setMessage={setMessage} />

        <SettingsSection
          t={t}
          settings={settings}
          setSettings={setSettings}
          setMessage={setMessage}
          saving={saving}
          setSaving={setSaving}
        />

        <div className="flex flex-wrap items-center gap-3">
          <a
            href="/"
            className="rounded-full border border-ink/10 bg-surface px-5 py-2 text-sm font-semibold text-ink"
          >
            {t("back")}
          </a>
          <a
            href="/settings/"
            className="rounded-full border border-ink/10 bg-surface px-5 py-2 text-sm font-semibold text-ink"
          >
            {t("settings")}
          </a>
        </div>
      </section>
    </main>
  );
}
