"use client";

import { useCallback, useEffect, useState } from "react";
import { buildAdminHeaders, getAdminToken, setAdminToken } from "../lib/admin";
import { API_BASE_URL } from "../lib/apiBase";
import { getErrorMessage, readApiError } from "../lib/apiError";

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
  const [form, setForm] = useState<Settings | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [adminTokenValue, setAdminTokenValue] = useState("");
  const hasAdminToken = adminTokenValue.trim().length > 0;

  const loadSettings = useCallback(async () => {
    setLoading(true);
    setMessage(null);
    try {
      const res = await fetch(`${API_BASE_URL}/settings`);
      if (!res.ok) {
        const detail = await readApiError(res, "Failed to load settings.");
        throw new Error(detail);
      }
      const data = await res.json();
      setForm(data);
    } catch (err) {
      const error = getErrorMessage(err, "Failed to load settings.");
      setForm(null);
      setMessage(error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  useEffect(() => {
    setAdminTokenValue(getAdminToken());
  }, []);

  const updateField = (key: keyof Settings, value: string | number | boolean) => {
    if (!form) return;
    setForm({ ...form, [key]: value });
  };

  const handleSave = async () => {
    if (!form) return;
    setSaving(true);
    setMessage(null);
    try {
      const payload = {
        github_username: form.github_username,
        github_target_username: form.github_target_username,
        github_usernames: form.github_usernames,
        github_include_self: form.github_include_self,
        github_mode: form.github_mode,
        classify_mode: form.classify_mode,
        auto_classify_after_sync: form.auto_classify_after_sync,
        rules_json: form.rules_json,
        sync_cron: form.sync_cron,
        sync_timeout: form.sync_timeout,
      };

      const res = await fetch(`${API_BASE_URL}/settings`, {
        method: "PATCH",
        headers: buildAdminHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const detail = await readApiError(res, "Save failed.");
        throw new Error(detail);
      }
      const data = await res.json();
      setForm(data);
      setMessage("Settings saved.");
    } catch (err) {
      const error = getErrorMessage(err, "Save failed.");
      setMessage(error);
    } finally {
      setSaving(false);
    }
  };

  if (!form) {
    return (
      <main className="min-h-screen px-6 py-10 lg:px-12">
        <section className="mx-auto max-w-4xl rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <p className="text-sm text-ink/70">
            {loading ? "Loading settings..." : message || "Failed to load settings."}
          </p>
          {!loading && (
            <button
              type="button"
              onClick={loadSettings}
              className="mt-4 rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink"
            >
              Retry
            </button>
          )}
          {!loading && (
            <p className="mt-3 text-xs text-ink/60">API: {API_BASE_URL}</p>
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
            Settings
          </p>
          <h1 className="mt-3 font-display text-3xl font-semibold">
            Configure sync + classification
          </h1>
          <p className="mt-2 text-sm text-ink/70">
            Secrets stay in <code className="rounded bg-clay px-2">.env</code>. This page
            controls non-sensitive values only.
          </p>
          <div className="mt-4 text-xs text-ink/60">
            Admin token (local): {hasAdminToken ? "set" : "missing"} / GitHub token:{" "}
            {form.github_token_set ? "set" : "missing"} / AI key:{" "}
            {form.ai_api_key_set ? "set" : "missing"}
          </div>
        </header>

        <div className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <h2 className="font-display text-lg font-semibold">Admin access</h2>
          <p className="mt-2 text-xs text-ink/60">
            Paste the <code className="rounded bg-clay px-2">ADMIN_TOKEN</code> from
            your server env to enable write actions. Stored locally in this browser.
          </p>
          {!hasAdminToken && (
            <div className="mt-3 rounded-2xl border border-copper/30 bg-surface px-3 py-2 text-xs text-copper">
              Admin token is missing. Saves may fail with 401 until it is set.
            </div>
          )}
          <label className="mt-4 block text-sm">
            Admin token (local only)
            <input
              className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
              value={adminTokenValue}
              onChange={(event) => {
                const value = event.target.value;
                setAdminTokenValue(value);
                setAdminToken(value);
              }}
              placeholder="X-Admin-Token"
            />
          </label>
          <p className="mt-2 text-xs text-ink/60">
            Clear the field to remove the token from local storage.
          </p>
        </div>

        <div className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <h2 className="font-display text-lg font-semibold">GitHub</h2>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <label className="text-sm">
              Username
              <input
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                value={form.github_username || ""}
                onChange={(event) => updateField("github_username", event.target.value)}
                placeholder="your-username"
              />
            </label>
            <label className="text-sm">
              Target username (public stars)
              <input
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                value={form.github_target_username || ""}
                onChange={(event) =>
                  updateField("github_target_username", event.target.value)
                }
                placeholder="someone-else"
              />
            </label>
            <label className="text-sm md:col-span-2">
              Usernames (comma separated)
              <input
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                value={form.github_usernames || ""}
                onChange={(event) => updateField("github_usernames", event.target.value)}
                placeholder="user1, user2, user3"
              />
            </label>
            <label className="text-sm">
              Include token account
              <div className="mt-2 flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={form.github_include_self}
                  onChange={(event) =>
                    updateField("github_include_self", event.target.checked)
                  }
                />
                <span className="text-xs text-ink/60">
                  Sync private stars with token
                </span>
              </div>
            </label>
            <label className="text-sm">
              Mode
              <select
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                value={form.github_mode || "merge"}
                onChange={(event) => updateField("github_mode", event.target.value)}
              >
                <option value="merge">Merge</option>
                <option value="group">Group</option>
              </select>
            </label>
          </div>
        </div>

        <div className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <h2 className="font-display text-lg font-semibold">AI</h2>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <p className="text-xs text-ink/60 md:col-span-2">
              AI provider, model, base URL, and keys are configured in the server{" "}
              <code className="rounded bg-clay px-2">.env</code> only.
            </p>
            <label className="text-sm md:col-span-2">
              Classification mode
              <select
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                value={form.classify_mode || "ai_only"}
                onChange={(event) => updateField("classify_mode", event.target.value)}
              >
                <option value="rules_then_ai">Rules then AI</option>
                <option value="ai_only">AI only</option>
                <option value="rules_only">Rules only</option>
              </select>
              <p className="mt-2 text-xs text-ink/60">
                Choose AI for full coverage or rules for fast keyword matching.
              </p>
            </label>
            <label className="text-sm md:col-span-2">
              Rules (JSON)
              <textarea
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-xs"
                rows={6}
                value={form.rules_json || ""}
                onChange={(event) => updateField("rules_json", event.target.value)}
                placeholder='{"rules":[{"keywords":["music","spotify"],"category":"media","subcategory":"music","tags":["music"]}]}'
              />
            </label>
          </div>
        </div>

        <div className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <h2 className="font-display text-lg font-semibold">Scheduler</h2>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <label className="text-sm">
              Sync cron
              <input
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                value={form.sync_cron || ""}
                onChange={(event) => updateField("sync_cron", event.target.value)}
                placeholder="0 */6 * * *"
              />
            </label>
            <label className="text-sm">
              Sync timeout
              <input
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                type="number"
                value={form.sync_timeout}
                onChange={(event) =>
                  updateField("sync_timeout", Number(event.target.value))
                }
              />
            </label>
            <label className="text-sm md:col-span-2">
              Auto classify after sync
              <div className="mt-2 flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={!!form.auto_classify_after_sync}
                  onChange={(event) =>
                    updateField("auto_classify_after_sync", event.target.checked)
                  }
                />
                <span className="text-xs text-ink/60">
                  Runs background classification right after syncing.
                </span>
              </div>
            </label>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="rounded-full bg-moss px-5 py-2 text-sm font-semibold text-white disabled:opacity-60"
          >
            {saving ? "Saving..." : "Save settings"}
          </button>
          {!hasAdminToken && (
            <span className="text-xs text-copper">
              Admin token missing; writes may fail if the API requires it.
            </span>
          )}
          <a
            href="/"
            className="rounded-full border border-ink/10 bg-surface px-5 py-2 text-sm font-semibold text-ink"
          >
            Back to dashboard
          </a>
          {message && <span className="text-xs text-ink/70">{message}</span>}
        </div>
      </section>
    </main>
  );
}
