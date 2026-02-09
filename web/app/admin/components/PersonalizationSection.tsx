"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { buildAdminHeaders } from "../../lib/admin";
import { API_BASE_URL } from "../../lib/apiBase";
import { getErrorMessage, readApiError } from "../../lib/apiError";
import type { TFunction } from "../../lib/i18n";

type PreferenceResponse = {
  user_id: string;
  tag_mapping: Record<string, string>;
  rule_priority: Record<string, number>;
  updated_at?: string | null;
};

type InterestTopic = {
  topic: string;
  score: number;
};

type InterestProfileResponse = {
  user_id: string;
  top_topics: InterestTopic[];
  updated_at?: string | null;
};

type TrainingSample = {
  id: number;
  full_name: string;
  before_category?: string | null;
  before_subcategory?: string | null;
  after_category?: string | null;
  after_subcategory?: string | null;
  after_tag_ids?: string[];
  source?: string | null;
  created_at: string;
};

type TrainingSamplesResponse = {
  items: TrainingSample[];
  total: number;
};

type FewShotItem = {
  input: {
    full_name?: string;
    name?: string;
    description?: string;
  };
  output: {
    category?: string;
    subcategory?: string;
    tag_ids?: string[];
  };
  note?: string | null;
};

type FewShotResponse = {
  items: FewShotItem[];
  total: number;
};

type Props = {
  t: TFunction;
  setMessage: (msg: string | null) => void;
};

const toMappingText = (value: Record<string, string>) =>
  Object.entries(value)
    .map(([source, target]) => `${source}=${target}`)
    .join("\n");

const toPriorityText = (value: Record<string, number>) =>
  Object.entries(value)
    .map(([ruleId, priority]) => `${ruleId}=${priority}`)
    .join("\n");

const parseMappingText = (raw: string): Record<string, string> => {
  const output: Record<string, string> = {};
  raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line) => {
      const index = line.indexOf("=");
      if (index <= 0) return;
      const key = line.slice(0, index).trim();
      const value = line.slice(index + 1).trim();
      if (key && value) {
        output[key] = value;
      }
    });
  return output;
};

const parsePriorityText = (raw: string): Record<string, number> => {
  const output: Record<string, number> = {};
  raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line) => {
      const index = line.indexOf("=");
      if (index <= 0) return;
      const key = line.slice(0, index).trim();
      const value = Number(line.slice(index + 1).trim());
      if (key && Number.isFinite(value)) {
        output[key] = value;
      }
    });
  return output;
};

export default function PersonalizationSection({ t, setMessage }: Props) {
  const [userIdInput, setUserIdInput] = useState("global");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showSamples, setShowSamples] = useState(false);
  const [showFewshot, setShowFewshot] = useState(false);

  const [mappingText, setMappingText] = useState("");
  const [priorityText, setPriorityText] = useState("");
  const [profile, setProfile] = useState<InterestProfileResponse | null>(null);
  const [samples, setSamples] = useState<TrainingSample[]>([]);
  const [fewshotItems, setFewshotItems] = useState<FewShotItem[]>([]);
  const [localError, setLocalError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  const activeUserId = useMemo(
    () => userIdInput.trim() || "global",
    [userIdInput]
  );

  const loadPreference = useCallback(async () => {
    setLoading(true);
    setLocalError(null);
    try {
      const [prefRes, profileRes] = await Promise.all([
        fetch(`${API_BASE_URL}/preferences/${encodeURIComponent(activeUserId)}`),
        fetch(`${API_BASE_URL}/interest/${encodeURIComponent(activeUserId)}`),
      ]);
      if (!prefRes.ok) {
        const detail = await readApiError(prefRes, t("unknownError"));
        throw new Error(detail);
      }
      if (!profileRes.ok) {
        const detail = await readApiError(profileRes, t("unknownError"));
        throw new Error(detail);
      }
      const prefData = (await prefRes.json()) as PreferenceResponse;
      const profileData = (await profileRes.json()) as InterestProfileResponse;
      setMappingText(toMappingText(prefData.tag_mapping || {}));
      setPriorityText(toPriorityText(prefData.rule_priority || {}));
      setProfile(profileData);
      setUpdatedAt(prefData.updated_at || null);
      if (showSamples) {
        const sampleRes = await fetch(
          `${API_BASE_URL}/training/samples?user_id=${encodeURIComponent(activeUserId)}&limit=50`,
          { headers: buildAdminHeaders() }
        );
        if (sampleRes.ok) {
          const sampleData = (await sampleRes.json()) as TrainingSamplesResponse;
          setSamples(sampleData.items || []);
        }
      }
      if (showFewshot) {
        const fewshotRes = await fetch(
          `${API_BASE_URL}/training/fewshot?user_id=${encodeURIComponent(activeUserId)}&limit=30`,
          { headers: buildAdminHeaders() }
        );
        if (fewshotRes.ok) {
          const fewshotData = (await fewshotRes.json()) as FewShotResponse;
          setFewshotItems(fewshotData.items || []);
        }
      }
    } catch (err) {
      setLocalError(getErrorMessage(err, t("unknownError")));
    } finally {
      setLoading(false);
    }
  }, [activeUserId, showFewshot, showSamples, t]);

  useEffect(() => {
    loadPreference();
  }, [loadPreference]);

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    setLocalError(null);
    try {
      const payload = {
        tag_mapping: parseMappingText(mappingText),
        rule_priority: parsePriorityText(priorityText),
      };
      const res = await fetch(
        `${API_BASE_URL}/preferences/${encodeURIComponent(activeUserId)}`,
        {
          method: "PATCH",
          headers: buildAdminHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify(payload),
        }
      );
      if (!res.ok) {
        const detail = await readApiError(res, t("saveFailed"));
        throw new Error(detail);
      }
      setMessage(t("saved"));
      await loadPreference();
    } catch (err) {
      const detail = getErrorMessage(err, t("saveFailed"));
      setLocalError(detail);
      setMessage(detail);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-lg font-semibold">
          {t("personalizationSettings")}
        </h2>
        <button
          type="button"
          className="rounded-full border border-ink/10 px-4 py-2 text-xs font-semibold text-ink transition hover:border-moss hover:text-moss disabled:opacity-60"
          onClick={loadPreference}
          disabled={loading}
        >
          {loading ? t("loadingRepos") : t("loadProfile")}
        </button>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <label className="text-sm">
          {t("userId")}
          <input
            className="mt-2 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-sm"
            value={userIdInput}
            onChange={(event) => setUserIdInput(event.target.value)}
            placeholder="global"
          />
        </label>

        <div className="text-xs text-ink/60">
          <p>{t("lastSyncWithValue", { value: updatedAt || t("never") })}</p>
          {profile?.updated_at && (
            <p className="mt-1">
              {t("updatedWithValue", { date: profile.updated_at })}
            </p>
          )}
        </div>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <label className="text-sm">
          {t("tagMapping")}
          <textarea
            className="mt-2 h-36 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-xs"
            value={mappingText}
            onChange={(event) => setMappingText(event.target.value)}
            placeholder={"source_tag_id=target_tag_id"}
          />
        </label>
        <label className="text-sm">
          {t("rulePriority")}
          <textarea
            className="mt-2 h-36 w-full rounded-2xl border border-ink/10 bg-surface px-3 py-2 text-xs"
            value={priorityText}
            onChange={(event) => setPriorityText(event.target.value)}
            placeholder={"rule_id=2"}
          />
        </label>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="rounded-full bg-moss px-5 py-2 text-sm font-semibold text-white disabled:opacity-60"
        >
          {saving ? t("saving") : t("savePreferences")}
        </button>
        <button
          type="button"
          className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-moss hover:text-moss"
          onClick={() => setShowSamples((prev) => !prev)}
        >
          {showSamples ? t("hide") : t("trainingSamples")}
        </button>
        <button
          type="button"
          className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-moss hover:text-moss"
          onClick={() => setShowFewshot((prev) => !prev)}
        >
          {showFewshot ? t("hide") : t("fewshotData")}
        </button>
      </div>

      {localError && <p className="mt-3 text-xs text-copper">{localError}</p>}

      <div className="mt-6 rounded-2xl border border-ink/10 bg-surface/70 p-4">
        <p className="text-xs uppercase tracking-[0.2em] text-ink/60">
          {t("interestProfile")}
        </p>
        {profile?.top_topics?.length ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {profile.top_topics.slice(0, 20).map((item) => (
              <span
                key={item.topic}
                className="rounded-full border border-ink/10 bg-surface px-3 py-1 text-xs text-ink/70"
              >
                {item.topic} ({item.score.toFixed(2)})
              </span>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-xs text-ink/60">{t("noData")}</p>
        )}
      </div>

      {showSamples && (
        <div className="mt-4 rounded-2xl border border-ink/10 bg-surface/70 p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-ink/60">
            {t("trainingSamples")}
          </p>
          <div className="mt-3 space-y-2">
            {samples.length === 0 ? (
              <p className="text-xs text-ink/60">{t("noData")}</p>
            ) : (
              samples.slice(0, 20).map((sample) => (
                <div
                  key={sample.id}
                  className="rounded-xl border border-ink/10 bg-surface px-3 py-2 text-xs text-ink/70"
                >
                  <div className="font-medium">{sample.full_name}</div>
                  <div className="mt-1">
                    {sample.before_category || "?"}/{sample.before_subcategory || "?"}{" "}
                    → {sample.after_category || "?"}/{sample.after_subcategory || "?"}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {showFewshot && (
        <div className="mt-4 rounded-2xl border border-ink/10 bg-surface/70 p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-ink/60">
            {t("fewshotData")}
          </p>
          <div className="mt-3 space-y-2">
            {fewshotItems.length === 0 ? (
              <p className="text-xs text-ink/60">{t("noData")}</p>
            ) : (
              fewshotItems.slice(0, 10).map((item, idx) => (
                <div
                  key={`${item.input.full_name || "repo"}-${idx}`}
                  className="rounded-xl border border-ink/10 bg-surface px-3 py-2 text-xs text-ink/70"
                >
                  <div className="font-medium">{item.input.full_name}</div>
                  <div className="mt-1">
                    {item.output.category}/{item.output.subcategory}
                  </div>
                  {item.output.tag_ids && item.output.tag_ids.length > 0 && (
                    <div className="mt-1">{item.output.tag_ids.join(", ")}</div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
