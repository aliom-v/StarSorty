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
        fetch(`${API_BASE_URL}/preferences/${encodeURIComponent(activeUserId)}`, {
          headers: buildAdminHeaders(),
        }),
        fetch(`${API_BASE_URL}/interest/${encodeURIComponent(activeUserId)}`, {
          headers: buildAdminHeaders(),
        }),
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
    <div className="admin-section">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <h2 className="panel-title">{t("personalizationSettings")}</h2>
          <p className="text-sm text-ink/60">
            {t("userId")}: <span className="font-medium text-ink">{activeUserId}</span>
          </p>
        </div>
        <button
          type="button"
          className="rounded-full btn-ios-secondary px-4 py-2 text-xs font-semibold text-ink disabled:opacity-60"
          onClick={loadPreference}
          disabled={loading}
        >
          {loading ? t("loadingRepos") : t("loadProfile")}
        </button>
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-[minmax(0,1.3fr)_minmax(0,0.7fr)]">
        <label className="block space-y-2">
          <span className="info-label">{t("userId")}</span>
          <input
            className="form-input mt-0"
            value={userIdInput}
            onChange={(event) => setUserIdInput(event.target.value)}
            placeholder="global"
          />
        </label>

        <div className="info-tile space-y-2 p-5">
          <span className="info-label">{t("interestProfile")}</span>
          <p className="text-sm text-ink/65">
            {t("lastSyncWithValue", { value: updatedAt || t("never") })}
          </p>
          {profile?.updated_at && (
            <p className="text-sm text-moss">
              {t("updatedWithValue", { date: profile.updated_at })}
            </p>
          )}
        </div>
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <label className="block space-y-2">
          <span className="info-label">{t("tagMapping")}</span>
          <textarea
            className="form-textarea mt-0 h-36 text-xs"
            value={mappingText}
            onChange={(event) => setMappingText(event.target.value)}
            placeholder={"source_tag_id=target_tag_id"}
          />
        </label>
        <label className="block space-y-2">
          <span className="info-label">{t("rulePriority")}</span>
          <textarea
            className="form-textarea mt-0 h-36 text-xs"
            value={priorityText}
            onChange={(event) => setPriorityText(event.target.value)}
            placeholder={"rule_id=2"}
          />
        </label>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="rounded-full btn-ios-moss px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-60"
        >
          {saving ? t("saving") : t("savePreferences")}
        </button>
        <button
          type="button"
          className={`rounded-full btn-ios-secondary px-4 py-2 text-xs font-semibold ${showSamples ? "text-moss" : "text-ink"}`}
          onClick={() => setShowSamples((prev) => !prev)}
        >
          {showSamples ? t("hide") : t("trainingSamples")}
        </button>
        <button
          type="button"
          className={`rounded-full btn-ios-secondary px-4 py-2 text-xs font-semibold ${showFewshot ? "text-moss" : "text-ink"}`}
          onClick={() => setShowFewshot((prev) => !prev)}
        >
          {showFewshot ? t("hide") : t("fewshotData")}
        </button>
      </div>

      {localError && (
        <div className="feedback-banner feedback-banner-error mt-4">
          <span className="feedback-icon" aria-hidden="true" />
          <p className="text-xs leading-6 text-copper">{localError}</p>
        </div>
      )}

      <div className="subtle-panel mt-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="info-label">{t("interestProfile")}</p>
          {!!profile?.top_topics?.length && (
            <span className="pill-accent px-3 py-1 text-[11px]">
              {profile.top_topics.length}
            </span>
          )}
        </div>
        {profile?.top_topics?.length ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {profile.top_topics.slice(0, 20).map((item) => (
              <span
                key={item.topic}
                className="pill-muted px-3 py-1 text-[11px] text-ink/75"
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
        <div className="subtle-panel mt-4">
          <p className="info-label">{t("trainingSamples")}</p>
          <div className="mt-3 space-y-2">
            {samples.length === 0 ? (
              <p className="text-xs text-ink/60">{t("noData")}</p>
            ) : (
              samples.slice(0, 20).map((sample) => (
                <div
                  key={sample.id}
                  className="subtle-panel border-ink/5 bg-surface/80 text-xs text-ink/70"
                >
                  <div className="font-medium text-ink">{sample.full_name}</div>
                  <div className="mt-1 leading-6">
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
        <div className="subtle-panel mt-4">
          <p className="info-label">{t("fewshotData")}</p>
          <div className="mt-3 space-y-2">
            {fewshotItems.length === 0 ? (
              <p className="text-xs text-ink/60">{t("noData")}</p>
            ) : (
              fewshotItems.slice(0, 10).map((item, idx) => (
                <div
                  key={`${item.input.full_name || "repo"}-${idx}`}
                  className="subtle-panel border-ink/5 bg-surface/80 text-xs text-ink/70"
                >
                  <div className="font-medium text-ink">
                    {item.input.full_name}
                  </div>
                  <div className="mt-1 leading-6">
                    {item.output.category}/{item.output.subcategory}
                  </div>
                  {item.output.tag_ids && item.output.tag_ids.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {item.output.tag_ids.map((tagId) => (
                        <span
                          key={`${item.input.full_name || "repo"}-${idx}-${tagId}`}
                          className="pill-muted px-2.5 py-1 text-[11px]"
                        >
                          {tagId}
                        </span>
                      ))}
                    </div>
                  )}
                  {item.note && (
                    <p className="mt-2 text-xs text-ink/55">{item.note}</p>
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
