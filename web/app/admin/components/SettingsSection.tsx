"use client";

import { buildAdminHeaders } from "../../lib/admin";
import { API_BASE_URL } from "../../lib/apiBase";
import { getErrorMessage, readApiError } from "../../lib/apiError";
import type { TFunction } from "../../lib/i18n";

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

type Props = {
  t: TFunction;
  settings: Settings;
  setSettings: (settings: Settings) => void;
  setMessage: (msg: string | null) => void;
  saving: boolean;
  setSaving: (saving: boolean) => void;
};

export default function SettingsSection({
  t,
  settings,
  setSettings,
  setMessage,
  saving,
  setSaving,
}: Props) {
  const updateField = (key: keyof Settings, value: string | number | boolean) => {
    setSettings({ ...settings, [key]: value });
  };

  const handleSave = async () => {
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

  return (
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
            min={1}
            max={3600}
            step={1}
            className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
            value={settings.sync_timeout}
            onChange={(e) => {
              const parsed = Number.parseInt(e.target.value, 10);
              if (Number.isNaN(parsed)) {
                updateField("sync_timeout", 1);
                return;
              }
              const normalized = Math.min(3600, Math.max(1, parsed));
              updateField("sync_timeout", normalized);
            }}
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
  );
}
