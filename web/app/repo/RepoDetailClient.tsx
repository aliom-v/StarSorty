"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { buildAdminHeaders } from "../lib/admin";
import { API_BASE_URL } from "../lib/apiBase";
import { getErrorMessage, readApiError } from "../lib/apiError";
import { useI18n } from "../lib/i18n";
import { createRequestTracker } from "../lib/requestTracker";

type RepoDetail = {
  full_name: string;
  name: string;
  owner: string;
  html_url: string;
  description?: string | null;
  language?: string | null;
  stargazers_count?: number | null;
  forks_count?: number | null;
  topics: string[];
  star_users?: string[];
  category?: string | null;
  subcategory?: string | null;
  tags?: string[];
  ai_category?: string | null;
  ai_subcategory?: string | null;
  ai_confidence?: number | null;
  ai_tags?: string[];
  ai_provider?: string | null;
  ai_model?: string | null;
  ai_updated_at?: string | null;
  override_category?: string | null;
  override_subcategory?: string | null;
  override_tags?: string[];
  override_note?: string | null;
  readme_summary?: string | null;
  readme_fetched_at?: string | null;
  pushed_at?: string | null;
  updated_at?: string | null;
  starred_at?: string | null;
};

type OverrideHistoryItem = {
  category?: string | null;
  subcategory?: string | null;
  tags?: string[];
  note?: string | null;
  updated_at?: string | null;
};

const formatDate = (value?: string | null, fallback = "—") => {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return date.toLocaleDateString();
};

const formatTime = (value?: string | null, fallback = "—") => {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return date.toLocaleString();
};

const formatStars = (value?: number | null) => {
  const count = value ?? 0;
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(count);
};

const StarIcon = () => (
  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
    <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
  </svg>
);

export default function RepoDetailClient() {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const fullName = (searchParams.get("full_name") || "").trim();
  const [repo, setRepo] = useState<RepoDetail | null>(null);
  const [history, setHistory] = useState<OverrideHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [messageStatus, setMessageStatus] = useState<"success" | "error">("success");
  const [fetchingReadme, setFetchingReadme] = useState(false);
  const repoRequestTrackerRef = useRef(createRequestTracker());
  const historyRequestTrackerRef = useRef(createRequestTracker());
  const aiConfidencePercent =
    repo?.ai_confidence !== null && repo?.ai_confidence !== undefined
      ? Math.max(0, Math.min(100, Math.round(repo.ai_confidence * 100)))
      : null;

  const encodedFullName = useMemo(
    () => encodeURIComponent(fullName),
    [fullName]
  );

  const loadRepo = useCallback(async () => {
    if (!fullName) return;
    const requestId = repoRequestTrackerRef.current.begin();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/repos/${encodedFullName}`);
      if (!repoRequestTrackerRef.current.isCurrent(requestId)) return;
      if (!res.ok) {
        const detail = await readApiError(res, `Repo fetch failed (${res.status})`);
        throw new Error(detail);
      }
      const data = await res.json();
      if (!repoRequestTrackerRef.current.isCurrent(requestId)) return;
      setRepo(data);
    } catch (err) {
      if (!repoRequestTrackerRef.current.isCurrent(requestId)) return;
      const messageText = getErrorMessage(err, t("unknownError"));
      setError(messageText);
    } finally {
      if (!repoRequestTrackerRef.current.isCurrent(requestId)) return;
      setLoading(false);
    }
  }, [encodedFullName, fullName, t]);

  const loadHistory = useCallback(async () => {
    if (!fullName) return;
    const requestId = historyRequestTrackerRef.current.begin();
    try {
      const res = await fetch(`${API_BASE_URL}/repos/${encodedFullName}/overrides`);
      if (!historyRequestTrackerRef.current.isCurrent(requestId)) return;
      if (!res.ok) {
        return;
      }
      const data = await res.json();
      if (!historyRequestTrackerRef.current.isCurrent(requestId)) return;
      setHistory(data.items || []);
    } catch {
      if (!historyRequestTrackerRef.current.isCurrent(requestId)) return;
      setHistory([]);
    }
  }, [encodedFullName, fullName]);

  useEffect(() => {
    if (!fullName) {
      repoRequestTrackerRef.current.reset();
      historyRequestTrackerRef.current.reset();
      setRepo(null);
      setHistory([]);
      setError(null);
      setMessage(null);
      setMessageStatus("success");
      setLoading(false);
      return;
    }
    loadRepo();
    loadHistory();
  }, [fullName, loadHistory, loadRepo]);

  const handleFetchReadme = async () => {
    if (!fullName) return;
    setFetchingReadme(true);
    setMessage(null);
    setMessageStatus("success");
    try {
      const res = await fetch(`${API_BASE_URL}/repos/${encodedFullName}/readme`, {
        method: "POST",
        headers: buildAdminHeaders(),
      });
      if (!res.ok) {
        const detail = await readApiError(res, t("readmeUpdateFailed"));
        throw new Error(detail);
      }
      setMessageStatus("success");
      setMessage(t("readmeUpdated"));
      await loadRepo();
    } catch (err) {
      const messageText = getErrorMessage(err, t("readmeUpdateFailed"));
      setMessageStatus("error");
      setMessage(messageText);
    } finally {
      setFetchingReadme(false);
    }
  };

  if (!fullName) {
    return (
      <main className="min-h-screen px-6 py-12">
        <div className="mx-auto flex min-h-[70vh] max-w-xl items-center justify-center animate-fade-in">
          <section className="panel-muted w-full p-8 text-center md:p-10">
            <div className="mx-auto mb-6 flex h-[4.5rem] w-[4.5rem] items-center justify-center rounded-[1.75rem] bg-ink/5 text-ink/25">
              <svg className="h-9 w-9" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <h1 className="section-title text-2xl font-bold">{t("noRepos")}</h1>
            <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-soft">
              {t("noDescription")}
            </p>
            <div className="mt-6 flex justify-center">
              <Link
                href="/"
                className="inline-flex items-center gap-2 rounded-full btn-ios-primary px-6 py-3 text-xs font-semibold tracking-[0.08em]"
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                </svg>
                {t("back")}
              </Link>
            </div>
          </section>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen px-4 py-8 md:px-12 md:py-12 bg-transparent">
      <div className="mx-auto max-w-5xl space-y-10 animate-fade-in">
        <header className="hero-surface soft-elevated relative overflow-hidden rounded-[2.5rem] p-7 md:p-8">
          <div className="hero-orb hero-orb-moss" />
          <div className="hero-orb hero-orb-copper" />
          <div className="relative flex flex-col gap-8 md:flex-row md:items-end md:justify-between">
          <div className="space-y-4 flex-1 min-w-0">
             <div className="flex items-center gap-2">
              <span className="h-2 w-8 bg-copper rounded-full" />
              <p className="section-kicker text-copper">
                {t("repoDetails")}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold text-subtle">
              <span className="pill-muted max-w-full truncate">{fullName}</span>
              {repo?.language && <span className="pill-accent">{repo.language}</span>}
              {repo?.category && (
                <span className="pill-muted">
                  {repo.category}
                  {repo.subcategory ? ` / ${repo.subcategory}` : ""}
                </span>
              )}
            </div>
            <h1 className="section-title text-3xl font-extrabold break-words md:text-4xl">
              {repo?.name || fullName}
            </h1>
            <p className="max-w-3xl text-base leading-relaxed text-soft md:text-lg">
              {repo?.description || t("noDescription")}
            </p>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <Link
              href="/"
              className="flex items-center gap-2 rounded-full btn-ios-secondary px-5 py-2.5 text-xs font-semibold tracking-[0.08em]"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              {t("back")}
            </Link>
            {repo?.html_url && (
              <a
                href={repo.html_url}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-2 rounded-full btn-ios-primary px-5 py-2.5 text-xs font-semibold tracking-[0.08em]"
              >
                {t("viewOnGithub")}
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
              </a>
            )}
          </div>
          </div>
        </header>

        {error && (
          <div className="feedback-banner feedback-banner-error">
            <span className="feedback-icon" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium leading-6 text-copper">{error}</p>
            </div>
          </div>
        )}

        {message && (
          <div
            className={`feedback-banner ${
              messageStatus === "error"
                ? "feedback-banner-error"
                : "feedback-banner-success"
            }`}
          >
            <span className="feedback-icon" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p
                className={`text-sm font-medium leading-6 ${
                  messageStatus === "error" ? "text-copper" : "text-moss"
                }`}
              >
                {message}
              </p>
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

        {loading && (
          <div className="panel-muted p-12 text-center">
            <div className="flex flex-col items-center gap-4">
              <svg className="h-8 w-8 animate-spin text-moss" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <p className="text-sm font-semibold text-soft">{t("loadingRepos")}</p>
            </div>
          </div>
        )}

        {repo && (
          <div className="grid gap-8">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              <div className="md:col-span-2 space-y-8">
                 <section className="panel p-8">
                  <div className="panel-header">
                    <h2 className="panel-title">
                      {t("readmeSummary")}
                    </h2>
                    <button
                      type="button"
                      onClick={handleFetchReadme}
                      disabled={fetchingReadme}
                      className="rounded-full btn-ios-secondary px-5 py-2 text-xs font-semibold tracking-[0.08em] disabled:opacity-30"
                    >
                      {fetchingReadme ? (
                        <span className="flex items-center gap-2">
                          <svg className="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                             <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                          {t("fetching")}
                        </span>
                      ) : t("fetchReadme")}
                    </button>
                  </div>
                  {repo.readme_summary ? (
                    <div className="prose prose-sm max-w-none whitespace-pre-wrap leading-relaxed text-soft">
                      {repo.readme_summary}
                    </div>
                  ) : (
                    <div className="subtle-panel">
                      <p className="text-sm text-soft">{t("noReadmeSummary")}</p>
                    </div>
                  )}
                  {repo.readme_fetched_at && (
                    <div className="mt-8 pt-6 border-t border-ink/5 text-[10px] font-bold uppercase tracking-wider text-ink/40">
                      {t("lastFetchedWithValue", { value: formatTime(repo.readme_fetched_at, t("noData")) })}
                    </div>
                  )}
                </section>

                <section className="panel p-8">
                  <h2 className="panel-title mb-8">
                    {t("overrideHistory")}
                  </h2>
                  {history.length === 0 ? (
                    <div className="subtle-panel">
                      <p className="text-sm text-soft">{t("noOverrideHistory")}</p>
                    </div>
                  ) : (
                    <div className="space-y-6">
                      {history.map((item, index) => (
                        <div
                          key={`${item.updated_at || "history"}-${index}`}
                          className="relative pl-6 before:absolute before:left-0 before:top-0 before:bottom-0 before:w-px before:bg-ink/10"
                        >
                          <div className="absolute left-[-4px] top-1.5 h-2 w-2 rounded-full bg-ink/20" />
                          <div className="flex flex-wrap items-center gap-2 mb-2">
                             <span className="text-[10px] font-bold uppercase tracking-wider text-ink/30">
                              {formatTime(item.updated_at, t("noData"))}
                            </span>
                          </div>
                          <div className="flex flex-wrap gap-2 text-sm text-soft">
                            <span className="font-bold">{item.category || t("unknown")}</span>
                            <span className="text-ink/30">/</span>
                            <span>{item.subcategory || t("unknown")}</span>
                          </div>
                          {item.tags && item.tags.length > 0 && (
                            <div className="mt-3 flex flex-wrap gap-2">
                              {item.tags.map((tag) => (
                                <span key={tag} className="pill-accent text-[10px]">
                                  #{tag}
                                </span>
                              ))}
                            </div>
                          )}
                          {item.note && (
                            <p className="mt-3 text-xs text-subtle leading-relaxed italic">
                              &ldquo;{item.note}&rdquo;
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              </div>

              <aside className="space-y-8">
                <section className="panel p-8">
                  <h2 className="section-kicker mb-6">
                    {t("status")}
                  </h2>
                  <div className="space-y-6">
                    <div className="grid grid-cols-2 gap-3">
                      <div className="info-tile border border-moss/10 bg-moss/5 dark:border-moss/15 dark:bg-moss/12">
                        <span className="info-label text-moss/60">{t("starsLabel")}</span>
                        <div className="mt-2 flex items-center gap-2 text-moss">
                          <StarIcon />
                          <span className="text-2xl font-black">{formatStars(repo.stargazers_count)}</span>
                        </div>
                      </div>
                      <div className="info-tile border border-ink/10 text-right dark:border-transparent">
                         <span className="info-label">{t("forksLabel")}</span>
                         <span className="mt-2 block text-2xl font-black text-ink">{repo.forks_count ?? 0}</span>
                      </div>
                    </div>

                    <div className="grid gap-4 border-t border-ink/5 pt-6 dark:border-white/5">
                      <div>
                         <span className="section-kicker mb-2 block">{t("language")}</span>
                         <span className="pill-muted text-sm text-ink/70">
                           {repo.language || t("unknown")}
                         </span>
                      </div>
                      <div>
                         <span className="section-kicker mb-2 block">{t("topics")}</span>
                         <div className="flex flex-wrap gap-2">
                           {repo.topics && repo.topics.length > 0 ? (
                           repo.topics.map((topic) => (
                              <span key={topic} className="pill-muted text-[11px] dark:bg-white/[0.06] dark:text-ink/70">
                                {topic}
                              </span>
                           ))
                         ) : (
                           <span className="pill-muted text-[11px]">{t("noData")}</span>
                         )}
                         </div>
                      </div>
                    </div>

                    <div className="grid gap-3 border-t border-ink/5 pt-6 text-[11px] dark:border-white/5 sm:grid-cols-3">
                      <div className="info-tile p-3.5">
                        <span className="info-label">{t("updatedLabel")}</span>
                        <span className="mt-2 block font-semibold text-ink/70">{formatDate(repo.updated_at, t("noData"))}</span>
                      </div>
                      <div className="info-tile p-3.5">
                        <span className="info-label">{t("pushedLabel")}</span>
                        <span className="mt-2 block font-semibold text-ink/70">{formatDate(repo.pushed_at, t("noData"))}</span>
                      </div>
                      <div className="info-tile p-3.5">
                        <span className="info-label">{t("starredLabel")}</span>
                        <span className="mt-2 block font-semibold text-ink/70">{formatDate(repo.starred_at, t("noData"))}</span>
                      </div>
                    </div>
                  </div>
                </section>

                <section className="panel p-8 dark:border-moss/15 dark:bg-moss/10">
                  <h2 className="panel-title mb-6 text-moss">
                    {t("aiClassification")}
                  </h2>
                  <div className="space-y-5">
                    <div>
                      <span className="info-label text-moss/45">{t("classification")}</span>
                      <p className="text-base font-bold text-moss">
                        {repo.ai_category || t("unknown")} / {repo.ai_subcategory || t("unknown")}
                      </p>
                    </div>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between gap-4 text-sm font-bold text-moss">
                        <span>{t("confidenceLabel")}</span>
                        <span>{aiConfidencePercent !== null ? `${aiConfidencePercent}%` : t("noData")}</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-moss/10">
                        <div
                          className="h-full rounded-full bg-moss transition-all duration-500"
                          style={{ width: `${aiConfidencePercent ?? 0}%` }}
                        />
                      </div>
                    </div>
                    {(repo.ai_provider || repo.ai_model || repo.ai_updated_at) && (
                      <div className="grid gap-3 text-[11px] sm:grid-cols-2">
                        {repo.ai_provider && (
                          <div className="info-tile bg-surface/60 p-3.5 dark:bg-white/[0.06]">
                            <span className="info-label text-moss/45">{t("providerLabel")}</span>
                            <span className="mt-2 block font-semibold text-moss/80">{repo.ai_provider}</span>
                          </div>
                        )}
                        {repo.ai_model && (
                          <div className="info-tile bg-surface/60 p-3.5 dark:bg-white/[0.06]">
                            <span className="info-label text-moss/45">{t("modelLabel")}</span>
                            <span className="mt-2 block font-semibold text-moss/80">{repo.ai_model}</span>
                          </div>
                        )}
                        {repo.ai_updated_at && (
                          <div className="info-tile bg-surface/60 p-3.5 dark:bg-white/[0.06] sm:col-span-2">
                            <span className="info-label text-moss/45">{t("updatedLabel")}</span>
                            <span className="mt-2 block font-semibold text-moss/80">{formatTime(repo.ai_updated_at, t("noData"))}</span>
                          </div>
                        )}
                      </div>
                    )}
                    {repo.ai_tags && repo.ai_tags.length > 0 && (
                      <div>
                        <span className="info-label mb-2 text-moss/45">{t("aiTags")}</span>
                        <div className="flex flex-wrap gap-2">
                          {repo.ai_tags.map((tag) => (
                            <span key={tag} className="pill-accent">
                              {tag}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </section>

                <section className="panel p-8 dark:border-copper/15 dark:bg-copper/10">
                  <h2 className="panel-title mb-6 text-copper">
                    {t("manualOverrides")}
                  </h2>
                   <div className="space-y-4">
                    <div>
                      <span className="info-label text-copper/45">{t("classification")}</span>
                      <p className="text-base font-bold text-copper">
                        {repo.override_category || t("unknown")} / {repo.override_subcategory || t("unknown")}
                      </p>
                    </div>
                    {repo.override_tags && repo.override_tags.length > 0 && (
                      <div>
                        <span className="info-label mb-2 text-copper/45">{t("tags")}</span>
                        <div className="flex flex-wrap gap-2">
                          {repo.override_tags.map((tag) => (
                            <span key={tag} className="pill-copper">
                              #{tag}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    {repo.override_note && (
                      <div className="info-tile border border-copper/10 bg-surface/60 dark:border-copper/10 dark:bg-white/[0.06]">
                        <span className="info-label mb-2 text-copper/45">{t("overrideNote")}</span>
                        <p className="text-sm italic leading-relaxed text-copper/80">
                          {repo.override_note}
                        </p>
                      </div>
                    )}
                  </div>
                </section>
              </aside>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
