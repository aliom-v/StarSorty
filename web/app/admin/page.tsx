"use client";

import { useCallback, useEffect, useState } from "react";
import {
  buildAdminHeaders,
  clearSessionToken,
  isSessionAuthenticated,
  setSessionToken,
} from "../lib/admin";
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

type Stats = {
  total: number;
  unclassified: number;
};

type BackgroundStatus = {
  running: boolean;
  processed: number;
  failed: number;
  remaining: number;
  batch_size: number;
  concurrency: number;
  task_id?: string | null;
  last_error?: string | null;
};

type FailedRepo = {
  full_name: string;
  name: string;
  owner: string;
  description: string | null;
  language: string | null;
  classify_fail_count: number;
};

export default function AdminPage() {
  const { t } = useI18n();
  const [authenticated, setAuthenticated] = useState(false);
  const [password, setPassword] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [classifying, setClassifying] = useState(false);
  const [classifyLimit, setClassifyLimit] = useState("20");
  const [concurrency, setConcurrency] = useState("3");
  const [forceReclassify, setForceReclassify] = useState(false);
  const [backgroundStatus, setBackgroundStatus] = useState<BackgroundStatus | null>(null);
  const [failedRepos, setFailedRepos] = useState<FailedRepo[]>([]);
  const [showFailedRepos, setShowFailedRepos] = useState(false);

  useEffect(() => {
    if (isSessionAuthenticated()) {
      setAuthenticated(true);
    }
  }, []);

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
        setAuthenticated(true);
      } else {
        setAuthError(t("passwordIncorrect"));
      }
    } catch {
      setAuthError(t("unknownError"));
    } finally {
      setVerifying(false);
    }
  };

  const handleLogout = () => {
    clearSessionToken();
    setAuthenticated(false);
    setPassword("");
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

  const loadStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/stats`);
      if (res.ok) {
        const data = await res.json();
        setStats({ total: data.total ?? 0, unclassified: data.unclassified ?? 0 });
      }
    } catch {
      // ignore
    }
  }, []);

  const loadBackgroundStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/classify/status`);
      if (res.ok) {
        const data = await res.json();
        setBackgroundStatus(data);
      }
    } catch {
      // ignore
    }
  }, []);

  const loadFailedRepos = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/repos/failed`);
      if (res.ok) {
        const data = await res.json();
        setFailedRepos(data.items ?? []);
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (authenticated) {
      loadSettings();
      loadStats();
      loadBackgroundStatus();
    }
  }, [authenticated, loadSettings, loadStats, loadBackgroundStatus]);

  useEffect(() => {
    if (!authenticated) return;
    const interval = setInterval(() => {
      loadBackgroundStatus();
      loadStats();
    }, 5000);
    return () => clearInterval(interval);
  }, [authenticated, loadBackgroundStatus, loadStats]);

  const updateField = (key: keyof Settings, value: string | number | boolean) => {
    if (!settings) return;
    setSettings({ ...settings, [key]: value });
  };

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    setMessage(null);
    try {
      const payload = {
        github_username: settings.github_username,
        github_target_username: settings.github_target_username,
        github_usernames: settings.github_usernames,
        github_include_self: settings.github_include_self,
        github_mode: settings.github_mode,
        classify_mode: settings.classify_mode,
        auto_classify_after_sync: settings.auto_classify_after_sync,
        rules_json: settings.rules_json,
        sync_cron: settings.sync_cron,
        sync_timeout: settings.sync_timeout,
      };
      const res = await fetch(`${API_BASE_URL}/settings`, {
        method: "PATCH",
        headers: buildAdminHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const detail = await readApiError(res, t("saveFailed"));
        throw new Error(detail);
      }
      const data = await res.json();
      setSettings(data);
      setMessage(t("saved"));
    } catch (err) {
      setMessage(getErrorMessage(err, t("saveFailed")));
    } finally {
      setSaving(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setMessage(null);
    try {
      const res = await fetch(`${API_BASE_URL}/sync`, {
        method: "POST",
        headers: buildAdminHeaders(),
      });
      if (!res.ok) {
        const detail = await readApiError(res, t("syncFailed"));
        throw new Error(detail);
      }
      setMessage(t("syncQueued"));
    } catch (err) {
      setMessage(getErrorMessage(err, t("syncFailed")));
    } finally {
      setSyncing(false);
    }
  };

  const parseClassifyLimit = () => {
    const parsed = parseInt(classifyLimit, 10);
    if (Number.isNaN(parsed)) return 20;
    return Math.max(1, Math.min(500, parsed));
  };

  const handleClassify = async (limit?: number) => {
    setClassifying(true);
    setMessage(null);
    try {
      const payload: { limit?: number; force?: boolean } = {};
      if (typeof limit === "number") {
        payload.limit = limit;
      }
      if (forceReclassify) {
        payload.force = true;
      }
      const res = await fetch(`${API_BASE_URL}/classify`, {
        method: "POST",
        headers: buildAdminHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const detail = await readApiError(res, t("classifyFailed"));
        throw new Error(detail);
      }
      const data = await res.json();
      const classified = data.classified ?? 0;
      const total = data.total ?? 0;
      const failed = data.failed ?? 0;
      setMessage(t("classifiedWithValue", { classified, total, failed }));
      await loadStats();
    } catch (err) {
      setMessage(getErrorMessage(err, t("classifyFailed")));
    } finally {
      setClassifying(false);
    }
  };

  const handleClassifyBatch = () => handleClassify(parseClassifyLimit());
  const handleClassifyAll = () => handleClassify(0);

  const parseConcurrency = () => {
    const parsed = parseInt(concurrency, 10);
    if (Number.isNaN(parsed)) return 3;
    return Math.max(1, Math.min(10, parsed));
  };

  const handleBackgroundStart = async () => {
    setMessage(null);
    try {
      const payload: { limit?: number; force?: boolean; concurrency?: number } = {
        limit: parseClassifyLimit(),
        concurrency: parseConcurrency(),
      };
      if (forceReclassify) {
        payload.force = true;
      }
      const res = await fetch(`${API_BASE_URL}/classify/background`, {
        method: "POST",
        headers: buildAdminHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const detail = await readApiError(res, t("classifyFailed"));
        throw new Error(detail);
      }
      await loadBackgroundStatus();
      setMessage(t("backgroundClassify"));
    } catch (err) {
      setMessage(getErrorMessage(err, t("classifyFailed")));
    }
  };

  const handleBackgroundStop = async () => {
    setMessage(null);
    try {
      const res = await fetch(`${API_BASE_URL}/classify/stop`, {
        method: "POST",
        headers: buildAdminHeaders(),
      });
      if (!res.ok) {
        const detail = await readApiError(res, t("classifyFailed"));
        throw new Error(detail);
      }
      await loadBackgroundStatus();
      setMessage(t("stopped"));
    } catch (err) {
      setMessage(getErrorMessage(err, t("classifyFailed")));
    }
  };

  const handleResetFailed = async () => {
    setMessage(null);
    try {
      const res = await fetch(`${API_BASE_URL}/repos/failed/reset`, {
        method: "POST",
        headers: buildAdminHeaders(),
      });
      if (!res.ok) {
        const detail = await readApiError(res, t("unknownError"));
        throw new Error(detail);
      }
      const data = await res.json();
      setMessage(t("resetFailedWithValue", { count: data.reset_count ?? 0 }));
      await loadFailedRepos();
    } catch (err) {
      setMessage(getErrorMessage(err, t("unknownError")));
    }
  };

  const backgroundRunning = backgroundStatus?.running ?? false;

  if (!authenticated) {
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

  if (loading || !settings) {
    return (
      <main className="min-h-screen px-6 py-10 lg:px-12">
        <section className="mx-auto max-w-4xl rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <p className="text-sm text-ink/70">{t("loadingRepos")}</p>
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

        <div className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <h2 className="font-display text-lg font-semibold">{t("syncOperations")}</h2>
          <div className="mt-4">
            <button
              type="button"
              onClick={handleSync}
              disabled={syncing}
              className="rounded-full bg-moss px-5 py-2 text-sm font-semibold text-white disabled:opacity-60"
            >
              {syncing ? t("syncing") : t("syncNow")}
            </button>
          </div>
        </div>

        <div className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <h2 className="font-display text-lg font-semibold">{t("classifyOperations")}</h2>
          {stats && (
            <p className="mt-2 text-sm text-ink/70">
              {t("unclassifiedWithValue", { count: stats.unclassified })} / {t("totalWithValue", { count: stats.total })}
            </p>
          )}

          {backgroundStatus && (
            <div className="mt-4 rounded-2xl border border-ink/10 bg-surface/70 px-4 py-3">
              <p className="text-xs uppercase tracking-[0.2em] text-ink/60">{t("backgroundStatus")}</p>
              <div className="mt-2 flex flex-wrap gap-3 text-xs text-ink/70">
                <span>{backgroundRunning ? t("backgroundRunning") : t("backgroundIdle")}</span>
                <span>{t("processedWithValue", { count: backgroundStatus.processed })}</span>
                <span>{t("failedWithValue", { count: backgroundStatus.failed })}</span>
                <span>{t("remainingWithValue", { count: backgroundStatus.remaining })}</span>
                <span>{t("batchSize")}: {backgroundStatus.batch_size}</span>
                <span>{t("concurrency")}: {backgroundStatus.concurrency}</span>
              </div>
              {backgroundStatus.last_error && backgroundStatus.last_error !== "Stopped by user" && (
                <p className="mt-2 text-xs text-copper">{backgroundStatus.last_error}</p>
              )}
            </div>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2 rounded-full border border-ink/10 bg-surface px-3 py-2 text-xs text-ink/70">
              <span>{t("batchSize")}</span>
              <input
                type="number"
                min={1}
                max={500}
                value={classifyLimit}
                onChange={(e) => {
                  const value = e.target.value;
                  if (/^\d*$/.test(value)) {
                    setClassifyLimit(value);
                  }
                }}
                className="w-14 bg-transparent text-right text-ink outline-none"
              />
            </div>
            <div className="flex items-center gap-2 rounded-full border border-ink/10 bg-surface px-3 py-2 text-xs text-ink/70">
              <span>{t("concurrency")}</span>
              <input
                type="number"
                min={1}
                max={10}
                value={concurrency}
                onChange={(e) => {
                  const value = e.target.value;
                  if (/^\d*$/.test(value)) {
                    setConcurrency(value);
                  }
                }}
                className="w-12 bg-transparent text-right text-ink outline-none"
              />
            </div>
            <label className="flex items-center gap-2 rounded-full border border-ink/10 bg-surface px-3 py-2 text-xs text-ink/70">
              <input
                type="checkbox"
                checked={forceReclassify}
                onChange={(e) => setForceReclassify(e.target.checked)}
                className="accent-moss"
              />
              <span>{t("forceReclassify")}</span>
            </label>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleClassifyBatch}
              disabled={classifying}
              className="rounded-full bg-moss px-5 py-2 text-sm font-semibold text-white disabled:opacity-60"
            >
              {classifying ? t("classifying") : t("backgroundClassify")}
            </button>
            <button
              type="button"
              onClick={handleClassifyAll}
              disabled={classifying}
              className="rounded-full border border-ink/10 bg-surface px-5 py-2 text-sm font-semibold text-ink disabled:opacity-60"
            >
              {t("classifyAll")}
            </button>
            <button
              type="button"
              onClick={handleBackgroundStart}
              disabled={backgroundRunning}
              className="rounded-full border border-ink/10 bg-surface px-5 py-2 text-sm font-semibold text-ink disabled:opacity-60"
            >
              {t("startBackground")}
            </button>
            <button
              type="button"
              onClick={handleBackgroundStop}
              disabled={!backgroundRunning}
              className="rounded-full border border-ink/10 bg-surface px-5 py-2 text-sm font-semibold text-ink disabled:opacity-60"
            >
              {t("stop")}
            </button>
          </div>
          {message && <p className="mt-3 text-xs text-ink/70">{message}</p>}
        </div>

        <div className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-lg font-semibold">{t("failedRepos")}</h2>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => {
                  setShowFailedRepos(!showFailedRepos);
                  if (!showFailedRepos) loadFailedRepos();
                }}
                className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink"
              >
                {showFailedRepos ? t("hide") : t("show")}
              </button>
              <button
                type="button"
                onClick={handleResetFailed}
                className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink hover:border-copper hover:text-copper"
              >
                {t("resetFailed")}
              </button>
            </div>
          </div>
          {showFailedRepos && (
            <div className="mt-4 space-y-2">
              {failedRepos.length === 0 ? (
                <p className="text-sm text-ink/70">{t("noFailedRepos")}</p>
              ) : (
                failedRepos.map((repo) => (
                  <div key={repo.full_name} className="rounded-2xl border border-ink/10 bg-surface px-4 py-3">
                    <div className="flex items-center justify-between">
                      <a
                        href={`https://github.com/${repo.full_name}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm font-medium text-ink hover:text-moss"
                      >
                        {repo.full_name}
                      </a>
                      <span className="text-xs text-copper">{t("failCountWithValue", { count: repo.classify_fail_count })}</span>
                    </div>
                    {repo.description && (
                      <p className="mt-1 text-xs text-ink/60 line-clamp-2">{repo.description}</p>
                    )}
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        <div className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <h2 className="font-display text-lg font-semibold">{t("configSettings")}</h2>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <label className="text-sm">
              {t("githubUsername")}
              <input
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                value={settings.github_username || ""}
                onChange={(e) => updateField("github_username", e.target.value)}
              />
            </label>
            <label className="text-sm">
              {t("githubTargetUsername")}
              <input
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                value={settings.github_target_username || ""}
                onChange={(e) => updateField("github_target_username", e.target.value)}
              />
            </label>
            <label className="text-sm md:col-span-2">
              {t("githubUsernames")}
              <input
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                value={settings.github_usernames || ""}
                onChange={(e) => updateField("github_usernames", e.target.value)}
              />
            </label>
            <label className="text-sm">
              {t("githubIncludeSelf")}
              <div className="mt-2 flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={settings.github_include_self}
                  onChange={(e) => updateField("github_include_self", e.target.checked)}
                />
              </div>
            </label>
            <label className="text-sm">
              {t("githubMode")}
              <select
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                value={settings.github_mode || "merge"}
                onChange={(e) => updateField("github_mode", e.target.value)}
              >
                <option value="merge">Merge</option>
                <option value="group">Group</option>
              </select>
            </label>
            <label className="text-sm">
              {t("classifyMode")}
              <select
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                value={settings.classify_mode || "ai_only"}
                onChange={(e) => updateField("classify_mode", e.target.value)}
              >
                <option value="rules_then_ai">Rules then AI</option>
                <option value="ai_only">AI only</option>
                <option value="rules_only">Rules only</option>
              </select>
            </label>
            <label className="text-sm">
              {t("autoClassifyAfterSync")}
              <div className="mt-2 flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={!!settings.auto_classify_after_sync}
                  onChange={(e) => updateField("auto_classify_after_sync", e.target.checked)}
                />
              </div>
            </label>
            <label className="text-sm">
              {t("syncCron")}
              <input
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                value={settings.sync_cron || ""}
                onChange={(e) => updateField("sync_cron", e.target.value)}
              />
            </label>
            <label className="text-sm">
              {t("syncTimeout")}
              <input
                type="number"
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                value={settings.sync_timeout}
                onChange={(e) => updateField("sync_timeout", Number(e.target.value))}
              />
            </label>
            <label className="text-sm md:col-span-2">
              {t("rulesJson")}
              <textarea
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-xs font-mono"
                rows={4}
                value={settings.rules_json || ""}
                onChange={(e) => updateField("rules_json", e.target.value)}
              />
            </label>
          </div>
          <div className="mt-4">
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="rounded-full bg-moss px-5 py-2 text-sm font-semibold text-white disabled:opacity-60"
            >
              {saving ? t("saving") : t("save")}
            </button>
          </div>
        </div>

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
