"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { buildAdminHeaders } from "../lib/admin";
import { API_BASE_URL } from "../lib/apiBase";
import { getErrorMessage, readApiError } from "../lib/apiError";
import { useI18n } from "../lib/i18n";

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

const formatDate = (value?: string | null) => {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "n/a";
  return date.toLocaleDateString();
};

const formatTime = (value?: string | null) => {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "n/a";
  return date.toLocaleString();
};

export default function RepoDetailClient() {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const fullName = (searchParams.get("full_name") || "").trim();
  const [repo, setRepo] = useState<RepoDetail | null>(null);
  const [history, setHistory] = useState<OverrideHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [fetchingReadme, setFetchingReadme] = useState(false);

  const encodedFullName = useMemo(
    () => encodeURIComponent(fullName),
    [fullName]
  );

  const loadRepo = useCallback(async () => {
    if (!fullName) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/repos/${encodedFullName}`);
      if (!res.ok) {
        const detail = await readApiError(res, `Repo fetch failed (${res.status})`);
        throw new Error(detail);
      }
      const data = await res.json();
      setRepo(data);
    } catch (err) {
      const messageText = getErrorMessage(err, t("unknownError"));
      setError(messageText);
    } finally {
      setLoading(false);
    }
  }, [encodedFullName, fullName, t]);

  const loadHistory = useCallback(async () => {
    if (!fullName) return;
    try {
      const res = await fetch(`${API_BASE_URL}/repos/${encodedFullName}/overrides`);
      if (!res.ok) {
        return;
      }
      const data = await res.json();
      setHistory(data.items || []);
    } catch {
      setHistory([]);
    }
  }, [encodedFullName, fullName]);

  useEffect(() => {
    if (!fullName) {
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
    try {
      const res = await fetch(`${API_BASE_URL}/repos/${encodedFullName}/readme`, {
        method: "POST",
        headers: buildAdminHeaders(),
      });
      if (!res.ok) {
        const detail = await readApiError(res, t("readmeUpdateFailed"));
        throw new Error(detail);
      }
      setMessage(t("readmeUpdated"));
      await loadRepo();
    } catch (err) {
      const messageText = getErrorMessage(err, t("readmeUpdateFailed"));
      setMessage(messageText);
    } finally {
      setFetchingReadme(false);
    }
  };

  if (!fullName) {
    return (
      <main className="min-h-screen px-6 py-10 lg:px-12">
        <section className="mx-auto max-w-4xl rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <p className="text-sm text-ink/70">{t("noRepos")}</p>
          <a
            href="/"
            className="mt-4 inline-flex rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink"
          >
            {t("back")}
          </a>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen px-6 py-10 lg:px-12">
      <section className="mx-auto max-w-4xl space-y-6">
        <header className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm uppercase tracking-[0.2em] text-copper">
                {t("details")}
              </p>
              <h1 className="mt-2 font-display text-3xl font-semibold">
                {repo?.name || fullName}
              </h1>
              <p className="mt-2 text-sm text-ink/70 break-words">
                {repo?.description || t("noDescription")}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <a
                href="/"
                className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink"
              >
                {t("back")}
              </a>
              {repo?.html_url && (
                <a
                  href={repo.html_url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink"
                >
                  {t("viewOnGithub")}
                </a>
              )}
            </div>
          </div>
          {error && <p className="mt-4 text-sm text-copper">{error}</p>}
          {loading && (
            <p className="mt-4 text-sm text-ink/60">{t("loadingRepos")}</p>
          )}
        </header>

        {repo && (
          <section className="grid gap-6">
            <div className="rounded-3xl border border-ink/10 bg-surface/80 p-6 shadow-soft">
              <h2 className="font-display text-lg font-semibold">
                {t("status")}
              </h2>
              <div className="mt-4 flex flex-wrap gap-4 text-sm text-ink/70">
                <span>
                  {t("starsWithValue", { count: repo.stargazers_count ?? 0 })}
                </span>
                <span>
                  {t("forksWithValue", { count: repo.forks_count ?? 0 })}
                </span>
                <span>
                  {t("updatedWithValue", {
                    date: formatDate(repo.updated_at),
                  })}
                </span>
                <span>
                  {t("pushedWithValue", { date: formatDate(repo.pushed_at) })}
                </span>
                <span>
                  {t("starredWithValue", { date: formatDate(repo.starred_at) })}
                </span>
                <span>{repo.language || t("unknown")}</span>
              </div>
              {repo.topics?.length > 0 && (
                <div className="mt-4 text-sm text-ink/70">
                  <div className="text-xs uppercase tracking-[0.2em] text-ink/60">
                    {t("topics")}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {repo.topics.map((topic) => (
                      <span
                        key={topic}
                        className="rounded-full bg-clay px-2 py-1 text-xs"
                      >
                        {topic}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="rounded-3xl border border-ink/10 bg-surface/80 p-6 shadow-soft">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="font-display text-lg font-semibold">
                  {t("readmeSummary")}
                </h2>
                <button
                  type="button"
                  onClick={handleFetchReadme}
                  disabled={fetchingReadme}
                  className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-moss hover:text-moss disabled:opacity-60"
                >
                  {fetchingReadme ? t("fetching") : t("fetchReadme")}
                </button>
              </div>
              {message && <p className="mt-2 text-xs text-ink/70">{message}</p>}
              <p className="mt-3 text-sm text-ink/80 whitespace-pre-wrap">
                {repo.readme_summary || t("noReadmeSummary")}
              </p>
              {repo.readme_fetched_at && (
                <p className="mt-2 text-xs text-ink/60">
                  {t("updatedWithValue", {
                    date: formatTime(repo.readme_fetched_at),
                  })}
                </p>
              )}
            </div>

            <div className="rounded-3xl border border-ink/10 bg-surface/80 p-6 shadow-soft">
              <h2 className="font-display text-lg font-semibold">
                {t("aiClassification")}
              </h2>
              <div className="mt-4 space-y-2 text-sm text-ink/70">
                <div>
                  {t("category")}: {repo.ai_category || t("unknown")}
                </div>
                <div>
                  {t("subcategory")}: {repo.ai_subcategory || t("unknown")}
                </div>
                <div>
                  {t("confidenceWithValue", {
                    value:
                      repo.ai_confidence !== null && repo.ai_confidence !== undefined
                        ? repo.ai_confidence.toFixed(2)
                        : "n/a",
                  })}
                </div>
                <div>
                  {t("providerWithValue", { value: repo.ai_provider || "n/a" })}
                </div>
                <div>
                  {t("modelWithValue", { value: repo.ai_model || "n/a" })}
                </div>
                {repo.ai_tags && repo.ai_tags.length > 0 && (
                  <div className="mt-3">
                    <div className="text-xs uppercase tracking-[0.2em] text-ink/60">
                      {t("tags")}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {repo.ai_tags.map((tag) => (
                        <span
                          key={tag}
                          className="rounded-full border border-ink/10 bg-surface px-2 py-1 text-xs"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-3xl border border-ink/10 bg-surface/80 p-6 shadow-soft">
              <h2 className="font-display text-lg font-semibold">
                {t("manualOverrides")}
              </h2>
              <div className="mt-4 space-y-2 text-sm text-ink/70">
                <div>
                  {t("category")}: {repo.override_category || t("unknown")}
                </div>
                <div>
                  {t("subcategory")}: {repo.override_subcategory || t("unknown")}
                </div>
                {repo.override_tags && repo.override_tags.length > 0 && (
                  <div className="mt-3">
                    <div className="text-xs uppercase tracking-[0.2em] text-ink/60">
                      {t("tags")}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {repo.override_tags.map((tag) => (
                        <span
                          key={tag}
                          className="rounded-full border border-ink/10 bg-surface px-2 py-1 text-xs"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {repo.override_note && (
                  <div className="mt-3">
                    <div className="text-xs uppercase tracking-[0.2em] text-ink/60">
                      {t("overrideNote")}
                    </div>
                    <p className="mt-1 text-sm text-ink/80">
                      {repo.override_note}
                    </p>
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-3xl border border-ink/10 bg-surface/80 p-6 shadow-soft">
              <h2 className="font-display text-lg font-semibold">
                {t("overrideHistory")}
              </h2>
              {history.length === 0 ? (
                <p className="mt-3 text-sm text-ink/70">
                  {t("noOverrideHistory")}
                </p>
              ) : (
                <div className="mt-4 space-y-3 text-sm text-ink/70">
                  {history.map((item, index) => (
                    <div
                      key={`${item.updated_at || "history"}-${index}`}
                      className="rounded-2xl border border-ink/10 bg-surface px-4 py-3"
                    >
                      <div>
                        {t("category")}: {item.category || t("unknown")}
                      </div>
                      <div>
                        {t("subcategory")}: {item.subcategory || t("unknown")}
                      </div>
                      {item.tags && item.tags.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {item.tags.map((tag) => (
                            <span
                              key={tag}
                              className="rounded-full border border-ink/10 bg-surface px-2 py-1 text-xs"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                      {item.note && (
                        <div className="mt-2 text-xs text-ink/70">
                          {t("overrideNote")}: {item.note}
                        </div>
                      )}
                      <div className="mt-2 text-xs text-ink/60">
                        {formatTime(item.updated_at)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        )}
      </section>
    </main>
  );
}
