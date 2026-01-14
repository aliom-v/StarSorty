"use client";

import { useEffect, useState } from "react";
import { buildAdminHeaders, getAdminToken, setAdminToken } from "../lib/admin";

type Settings = {
  github_username: string;
  github_target_username: string;
  github_usernames: string;
  github_include_self: boolean;
  github_mode: string;
  ai_provider: string;
  ai_model: string;
  ai_base_url: string;
  ai_headers_json: string;
  ai_temperature: number;
  ai_max_tokens: number;
  ai_timeout: number;
  ai_taxonomy_path: string;
  rules_json: string;
  sync_cron: string;
  sync_timeout: number;
  github_token_set: boolean;
  ai_api_key_set: boolean;
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function SettingsPage() {
  const [form, setForm] = useState<Settings | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [adminTokenValue, setAdminTokenValue] = useState("");

  useEffect(() => {
    const load = async () => {
      const res = await fetch(`${API_BASE_URL}/settings`);
      if (!res.ok) {
        setMessage("Failed to load settings.");
        return;
      }
      const data = await res.json();
      setForm(data);
    };
    load();
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
        ai_provider: form.ai_provider,
        ai_model: form.ai_model,
        ai_base_url: form.ai_base_url,
        ai_headers_json: form.ai_headers_json,
        ai_temperature: form.ai_temperature,
        ai_max_tokens: form.ai_max_tokens,
        ai_timeout: form.ai_timeout,
        ai_taxonomy_path: form.ai_taxonomy_path,
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
        const detail = await res.text();
        throw new Error(detail || "Save failed.");
      }
      const data = await res.json();
      setForm(data);
      setMessage("Settings saved.");
    } catch (err) {
      const error = err instanceof Error ? err.message : "Save failed.";
      setMessage(error);
    } finally {
      setSaving(false);
    }
  };

  if (!form) {
    return (
      <main className="min-h-screen px-6 py-10 lg:px-12">
        <section className="mx-auto max-w-4xl rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <p className="text-sm text-ink/70">Loading settings...</p>
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
            GitHub token: {form.github_token_set ? "set" : "missing"} / AI key:{" "}
            {form.ai_api_key_set ? "set" : "missing"}
          </div>
          <div className="mt-4 grid gap-2">
            <label className="text-sm">
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
            <p className="text-xs text-ink/60">
              Stored locally for demo writes.
            </p>
          </div>
        </header>

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
            <label className="text-sm">
              Provider
              <input
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                value={form.ai_provider || ""}
                onChange={(event) => updateField("ai_provider", event.target.value)}
                placeholder="openai / anthropic / custom"
              />
            </label>
            <label className="text-sm">
              Model
              <input
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                value={form.ai_model || ""}
                onChange={(event) => updateField("ai_model", event.target.value)}
                placeholder="gpt-4o-mini / glm-4.7"
              />
            </label>
            <label className="text-sm md:col-span-2">
              Base URL
              <input
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                value={form.ai_base_url || ""}
                onChange={(event) => updateField("ai_base_url", event.target.value)}
                placeholder="https://your-host/v1"
              />
            </label>
            <label className="text-sm md:col-span-2">
              Extra headers (JSON)
              <input
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                value={form.ai_headers_json || ""}
                onChange={(event) => updateField("ai_headers_json", event.target.value)}
                placeholder='{"X-Header":"value"}'
              />
            </label>
            <label className="text-sm">
              Temperature
              <input
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                type="number"
                step="0.1"
                value={form.ai_temperature}
                onChange={(event) =>
                  updateField("ai_temperature", Number(event.target.value))
                }
              />
            </label>
            <label className="text-sm">
              Max tokens
              <input
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                type="number"
                value={form.ai_max_tokens}
                onChange={(event) =>
                  updateField("ai_max_tokens", Number(event.target.value))
                }
              />
            </label>
            <label className="text-sm">
              Timeout (seconds)
              <input
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                type="number"
                value={form.ai_timeout}
                onChange={(event) =>
                  updateField("ai_timeout", Number(event.target.value))
                }
              />
            </label>
            <label className="text-sm md:col-span-2">
              Taxonomy path
              <input
                className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
                value={form.ai_taxonomy_path || ""}
                onChange={(event) =>
                  updateField("ai_taxonomy_path", event.target.value)
                }
                placeholder="api/config/taxonomy.yaml"
              />
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
