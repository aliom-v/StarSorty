"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { adminFetch } from "../../lib/admin";
import { API_BASE_URL } from "../../lib/apiBase";
import { getErrorMessage, readApiError } from "../../lib/apiError";
import type { TFunction } from "../../lib/i18n";
import { buildRepoDetailHref } from "../../lib/repoRoutes";

type ReviewRepo = {
  full_name: string;
  name: string;
  owner: string;
  description?: string | null;
  language?: string | null;
  stargazers_count?: number | null;
  category?: string | null;
  subcategory?: string | null;
  ai_category?: string | null;
  ai_subcategory?: string | null;
  ai_confidence?: number | null;
  ai_reason?: string | null;
  ai_decision_source?: string | null;
  ai_rule_candidates?: Array<{
    rule_id?: string;
    score?: number;
    category?: string;
    subcategory?: string;
    evidence?: string[];
  }>;
  readme_summary?: string | null;
  updated_at?: string | null;
};

type ReviewQueueItem = {
  repo: ReviewRepo;
  review_reason: string;
};

type ReviewQueueResponse = {
  total?: number;
  confidence_threshold?: number;
  items?: ReviewQueueItem[];
};

type Props = {
  t: TFunction;
  setMessage: (msg: string | null) => void;
};

const formatConfidence = (value?: number | null) => {
  if (value === null || value === undefined) return "—";
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
};

const reasonLabelKey = (reason: string) => {
  if (reason === "missing_classification") return "reviewReasonMissingClassification";
  if (reason === "manual_review") return "reviewReasonManualReview";
  if (reason === "missing_confidence") return "reviewReasonMissingConfidence";
  if (reason === "rule_fallback") return "reviewReasonRuleFallback";
  if (reason === "ambiguous_rule_candidates") return "reviewReasonAmbiguousRules";
  return "reviewReasonLowConfidence";
};

export default function ReviewQueueSection({ t, setMessage }: Props) {
  const [items, setItems] = useState<ReviewQueueItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [threshold, setThreshold] = useState("0.62");
  const [expanded, setExpanded] = useState<string | null>(null);

  const parsedThreshold = useMemo(() => {
    const parsed = Number.parseFloat(threshold);
    if (Number.isNaN(parsed)) return 0.62;
    return Math.max(0, Math.min(1, parsed));
  }, [threshold]);

  const loadQueue = useCallback(async () => {
    setLoading(true);
    setLocalError(null);
    try {
      const params = new URLSearchParams({
        confidence_threshold: String(parsedThreshold),
        limit: "24",
      });
      const res = await adminFetch(`${API_BASE_URL}/repos/review/low-confidence?${params}`);
      if (!res.ok) {
        const detail = await readApiError(res, t("loadReviewQueueError"));
        throw new Error(detail);
      }
      const data = (await res.json()) as ReviewQueueResponse;
      setItems(data.items ?? []);
      if ((data.items ?? []).length === 0) {
        setExpanded(null);
      }
    } catch (err) {
      setLocalError(getErrorMessage(err, t("loadReviewQueueError")));
    } finally {
      setLoading(false);
    }
  }, [parsedThreshold, t]);

  useEffect(() => {
    void loadQueue();
  }, [loadQueue]);

  return (
    <div className="admin-section">
      <div className="panel-header flex-wrap items-start">
        <div className="space-y-2">
          <h2 className="panel-title">{t("reviewQueue")}</h2>
          <p className="text-sm leading-6 text-subtle">
            {t("reviewQueueDesc")}
          </p>
          <div className="flex flex-wrap gap-2">
            <span className="pill-copper px-3 py-1">
              {t("reviewQueueCountWithValue", { count: items.length })}
            </span>
            <span className="pill-muted px-3 py-1">
              {t("confidenceBelowWithValue", {
                value: formatConfidence(parsedThreshold),
              })}
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label className="flex h-9 items-center gap-2 rounded-md border border-ink/10 bg-surface-muted px-2.5 text-xs font-semibold text-ink/65">
            <span>{t("threshold")}</span>
            <input
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={threshold}
              onChange={(event) => setThreshold(event.target.value)}
              className="w-16 bg-transparent text-right text-ink outline-none"
            />
          </label>
          <button
            type="button"
            onClick={loadQueue}
            disabled={loading}
            className="btn-ios-secondary h-9 px-3 text-xs font-semibold"
          >
            {loading ? t("loadingRepos") : t("refresh")}
          </button>
        </div>
      </div>

      {localError && (
        <div className="feedback-banner feedback-banner-error mt-4">
          <span className="feedback-icon" aria-hidden="true" />
          <p className="text-sm leading-6 text-copper">{localError}</p>
        </div>
      )}

      {!localError && items.length === 0 && !loading && (
        <div className="subtle-panel mt-4">
          <p className="text-sm font-medium text-soft">{t("reviewQueueEmpty")}</p>
        </div>
      )}

      {items.length > 0 && (
        <div className="mt-5 grid gap-3">
          {items.map((item) => {
            const repo = item.repo;
            const isExpanded = expanded === repo.full_name;
            const classification = repo.category
              ? `${repo.category}${repo.subcategory ? ` / ${repo.subcategory}` : ""}`
              : t("unknown");
            const candidates = repo.ai_rule_candidates ?? [];

            return (
              <article
                key={repo.full_name}
                className="rounded-lg border border-ink/10 bg-surface p-4 transition hover:border-copper/25 hover:bg-copper/5"
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="pill-copper">
                        {t(reasonLabelKey(item.review_reason))}
                      </span>
                      {repo.language && <span className="pill-muted">{repo.language}</span>}
                      <span className="pill-muted">
                        {t("confidenceWithValue", {
                          value: formatConfidence(repo.ai_confidence),
                        })}
                      </span>
                    </div>
                    <h3 className="mt-3 break-words font-display text-lg font-semibold text-ink">
                      {repo.full_name}
                    </h3>
                    <p className="mt-1 text-sm font-medium leading-6 text-soft line-clamp-2">
                      {repo.description || repo.readme_summary || t("noDescription")}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs font-semibold text-subtle">
                      <span>{t("classification")}: {classification}</span>
                      {repo.ai_decision_source && (
                        <span>{t("decisionSourceWithValue", { value: repo.ai_decision_source })}</span>
                      )}
                    </div>
                  </div>

                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setExpanded(isExpanded ? null : repo.full_name)}
                      className="btn-ios-secondary h-9 px-3 text-xs font-semibold"
                    >
                      {isExpanded ? t("hideEvidence") : t("showEvidence")}
                    </button>
                    <Link
                      href={buildRepoDetailHref(repo.full_name)}
                      className="btn-ios-primary h-9 px-3 text-xs font-semibold"
                      onClick={() => setMessage(null)}
                    >
                      {t("review")}
                    </Link>
                  </div>
                </div>

                {isExpanded && (
                  <div className="mt-4 grid gap-3 border-t border-ink/10 pt-4 lg:grid-cols-2">
                    <div className="subtle-panel bg-surface-muted">
                      <span className="info-label">{t("aiReason")}</span>
                      <p className="mt-2 text-sm leading-6 text-soft">
                        {repo.ai_reason || t("noData")}
                      </p>
                    </div>
                    <div className="subtle-panel bg-surface-muted">
                      <span className="info-label">{t("ruleCandidates")}</span>
                      <div className="mt-2 space-y-2">
                        {candidates.length === 0 ? (
                          <p className="text-sm text-soft">{t("noData")}</p>
                        ) : (
                          candidates.slice(0, 3).map((candidate, index) => (
                            <div key={`${candidate.rule_id || index}`} className="text-xs leading-5 text-soft">
                              <span className="font-semibold text-ink">
                                {candidate.rule_id || t("unknown")}
                              </span>
                              <span className="text-subtle">
                                {" "}
                                {candidate.category || t("unknown")} / {candidate.subcategory || t("unknown")}
                                {" "}
                                {formatConfidence(candidate.score)}
                              </span>
                              {candidate.evidence?.length ? (
                                <p className="mt-1 text-[11px] text-subtle">
                                  {candidate.evidence.join(" · ")}
                                </p>
                              ) : null}
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
