"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  buildAdminHeaders,
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
import PersonalizationSection from "./components/PersonalizationSection";

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
      const res = await fetch(`${API_BASE_URL}/settings`, {
        headers: buildAdminHeaders(),
      });
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
    return <AdminAuth t={t} onAuthenticated={() => setAuthenticated(true)} />;
  }

  if (loading || !settings) {
    return (
      <main className="min-h-screen px-6 py-10 lg:px-12">
        <section className="mx-auto max-w-4xl panel-muted p-8">
          <p className="text-sm text-soft">{t("loadingSettings")}</p>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen px-6 py-10 lg:px-12">
      <section className="mx-auto max-w-4xl space-y-6">
        <header className="hero-surface soft-elevated relative overflow-hidden rounded-[2.5rem] p-8">
          <div className="hero-orb hero-orb-moss" />
          <div className="hero-orb hero-orb-copper" />
          <div className="relative flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="section-kicker text-copper">{t("admin")}</p>
              <h1 className="mt-3 section-title text-3xl font-semibold">
                {t("adminPageTitle")}
              </h1>
              <p className="mt-2 text-sm text-soft">{t("adminPageSubtitle")}</p>
            </div>
            <button
              type="button"
              onClick={handleLogout}
              className="rounded-full btn-ios-secondary px-4 py-2 text-xs font-semibold tracking-[0.08em] hover:text-copper"
            >
              {t("logout")}
            </button>
          </div>
        </header>

        {message && (
          <div className="feedback-banner">
            <span className="feedback-icon" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium leading-6 text-ink">{message}</p>
            </div>
            <button
              type="button"
              onClick={() => setMessage(null)}
              className="rounded-full btn-ios-secondary px-3 py-1.5 text-[11px] font-semibold text-ink/70"
            >
              {t("hide")}
            </button>
          </div>
        )}

        <SyncSection t={t} setMessage={setMessage} />

        <ClassifySection t={t} setMessage={setMessage} />

        <FailedReposSection t={t} setMessage={setMessage} />

        <PersonalizationSection t={t} setMessage={setMessage} />

        <ExportSection t={t} setMessage={setMessage} />

        <SettingsSection
          t={t}
          settings={settings}
          setSettings={setSettings}
          setMessage={setMessage}
          saving={saving}
          setSaving={setSaving}
        />

        <div className="subtle-panel flex flex-wrap items-center gap-3">
          <Link
            href="/"
            className="rounded-full btn-ios-secondary px-5 py-2 text-sm font-semibold"
          >
            {t("back")}
          </Link>
          <Link
            href="/settings/"
            className="rounded-full btn-ios-secondary px-5 py-2 text-sm font-semibold"
          >
            {t("settings")}
          </Link>
        </div>
      </section>
    </main>
  );
}
