"use client";

import { useEffect, useMemo, useState } from "react";
import { useI18n } from "./lib/i18n";
import { useTheme } from "./lib/theme";

type Repo = {
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
  pushed_at?: string | null;
  updated_at?: string | null;
  starred_at?: string | null;
};

type Status = {
  last_sync_at?: string | null;
  last_result?: string | null;
  last_message?: string | null;
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const STAR_FILTERS = [100, 500, 1000, 5000];

const formatStars = (value?: number | null) => {
  const count = value ?? 0;
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(count);
};

const formatDate = (value?: string | null) => {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "n/a";
  return date.toLocaleDateString();
};

export default function Home() {
  const { t, locale, setLocale } = useI18n();
  const { theme, toggleTheme } = useTheme();
  const [repos, setRepos] = useState<Repo[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<"success" | "error" | null>(
    null
  );
  const [syncing, setSyncing] = useState(false);
  const [classifying, setClassifying] = useState(false);
  const [classifyLimit, setClassifyLimit] = useState("20");
  const [classifyLooping, setClassifyLooping] = useState(false);
  const [forceReclassify, setForceReclassify] = useState(false);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [language, setLanguage] = useState<string | null>(null);
  const [minStars, setMinStars] = useState<number | null>(null);
  const [sourceUser, setSourceUser] = useState<string | null>(null);
  const [groupMode, setGroupMode] = useState(false);
  const unknownErrorMessage = t("unknownError");

  const loadStatus = async () => {
    try {
      const statusRes = await fetch(`${API_BASE_URL}/status`);
      const statusData = statusRes.ok ? await statusRes.json() : null;
      setStatus(statusData);
    } catch (err) {
      const message = err instanceof Error ? err.message : unknownErrorMessage;
      setError(message);
    }
  };

  const loadRepos = async () => {
    setLoading(true);
    setError(null);
    try {
      const pageSize = 200;
      const params = new URLSearchParams({ limit: String(pageSize), offset: "0" });
      if (query) params.set("q", query);
      if (language) params.set("language", language);
      if (minStars) params.set("min_stars", String(minStars));
      if (sourceUser) params.set("star_user", sourceUser);

      const firstRes = await fetch(`${API_BASE_URL}/repos?${params}`);
      if (!firstRes.ok) {
        throw new Error(`Repos fetch failed (${firstRes.status})`);
      }
      const firstData = await firstRes.json();
      const total = Number(firstData.total || 0);
      const items: Repo[] = firstData.items || [];

      let offset = items.length;
      while (offset < total) {
        const nextParams = new URLSearchParams(params);
        nextParams.set("offset", String(offset));
        const nextRes = await fetch(`${API_BASE_URL}/repos?${nextParams}`);
        if (!nextRes.ok) {
          throw new Error(`Repos fetch failed (${nextRes.status})`);
        }
        const nextData = await nextRes.json();
        const nextItems: Repo[] = nextData.items || [];
        if (nextItems.length === 0) {
          break;
        }
        items.push(...nextItems);
        offset += nextItems.length;
      }

      setTotalCount(total || items.length);
      setRepos(items);
    } catch (err) {
      const message = err instanceof Error ? err.message : unknownErrorMessage;
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const load = async () => {
      await loadStatus();
      try {
        const settingsRes = await fetch(`${API_BASE_URL}/settings`);
        if (settingsRes.ok) {
          const settingsData = await settingsRes.json();
          setGroupMode(String(settingsData.github_mode || "merge") === "group");
        }
      } catch {
        setGroupMode(false);
      }
    };
    load();
  }, []);

  useEffect(() => {
    loadRepos();
  }, [query, language, minStars, sourceUser]);

  useEffect(() => {
    if (!actionMessage) return;
    const timer = setTimeout(() => {
      setActionMessage(null);
      setActionStatus(null);
    }, 5000);
    return () => clearTimeout(timer);
  }, [actionMessage]);

  const handleSync = async () => {
    setSyncing(true);
    setActionMessage(null);
    setActionStatus(null);
    try {
      const response = await fetch(`${API_BASE_URL}/sync`, { method: "POST" });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || t("syncFailed"));
      }
      const data = await response.json();
      setActionMessage(t("syncedWithValue", { count: data.count }));
      setActionStatus("success");
      await loadStatus();
      setSourceUser(null);
      await loadRepos();
    } catch (err) {
      const message = err instanceof Error ? err.message : t("syncFailed");
      setActionMessage(message);
      setActionStatus("error");
    } finally {
      setSyncing(false);
    }
  };

  const parseClassifyLimit = () => {
    const parsed = parseInt(classifyLimit, 10);
    if (Number.isNaN(parsed)) return 20;
    return Math.max(1, Math.min(500, parsed));
  };

  const requestClassify = async (limit?: number) => {
    const payload: { limit?: number } = {};
    if (typeof limit === "number") {
      payload.limit = limit;
    }
    if (forceReclassify) {
      payload.force = true;
    }
    const response = await fetch(`${API_BASE_URL}/classify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || t("classifyFailed"));
    }
    return response.json();
  };

  const applyClassifyMessage = (data: {
    classified: number;
    total: number;
    failed: number;
    remaining_unclassified?: number;
  }) => {
    const remaining =
      typeof data.remaining_unclassified === "number"
        ? data.remaining_unclassified
        : null;
    setActionMessage(
      remaining === null
        ? t("classifiedWithValue", {
            classified: data.classified,
            total: data.total,
            failed: data.failed,
          })
        : t("classifiedWithRemainingValue", {
            classified: data.classified,
            total: data.total,
            failed: data.failed,
            remaining,
          })
    );
    setActionStatus("success");
    return remaining;
  };

  const handleClassifyOnce = async (limit?: number) => {
    setClassifying(true);
    setActionMessage(null);
    setActionStatus(null);
    try {
      const data = await requestClassify(limit);
      applyClassifyMessage(data);
      await loadRepos();
    } catch (err) {
      const message = err instanceof Error ? err.message : t("classifyFailed");
      setActionMessage(message);
      setActionStatus("error");
    } finally {
      setClassifying(false);
    }
  };

  const handleClassifyBatch = () => handleClassifyOnce(parseClassifyLimit());
  const handleClassifyAll = () => handleClassifyOnce(0);
  const handleClassifyUntilDone = async () => {
    if (classifying) return;
    if (forceReclassify) {
      await handleClassifyOnce(0);
      return;
    }
    setClassifyLooping(true);
    setClassifying(true);
    setActionMessage(null);
    setActionStatus(null);
    try {
      const limit = parseClassifyLimit();
      let previousRemaining: number | null = null;
      for (let round = 0; round < 200; round += 1) {
        const data = await requestClassify(limit);
        const remaining = applyClassifyMessage(data);
        const total = typeof data.total === "number" ? data.total : 0;
        if (total === 0) break;
        if (remaining === null || remaining <= 0) break;
        if (previousRemaining !== null && remaining >= previousRemaining) {
          break;
        }
        previousRemaining = remaining;
      }
      await loadRepos();
    } catch (err) {
      const message = err instanceof Error ? err.message : t("classifyFailed");
      setActionMessage(message);
      setActionStatus("error");
    } finally {
      setClassifying(false);
      setClassifyLooping(false);
    }
  };

  const languageCounts = useMemo(() => {
    const map = new Map<string, number>();
    repos.forEach((repo) => {
      const key = repo.language || "unknown";
      map.set(key, (map.get(key) || 0) + 1);
    });
    return Array.from(map.entries())
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count);
  }, [repos]);

  const userCounts = useMemo(() => {
    const map = new Map<string, number>();
    repos.forEach((repo) => {
      const users = repo.star_users || [];
      users.forEach((user) => {
        map.set(user, (map.get(user) || 0) + 1);
      });
    });
    return Array.from(map.entries())
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count);
  }, [repos]);

  const filteredRepos = useMemo(() => repos, [repos]);
  const unclassifiedCount = useMemo(
    () => repos.filter((repo) => !repo.category).length,
    [repos]
  );

  const lastSyncLabel = status?.last_sync_at
    ? new Date(status.last_sync_at).toLocaleString()
    : t("never");
  const classifyLabel = classifying
    ? t("classifying")
    : unclassifiedCount > 0
      ? t("classifyNext")
      : t("classify");
  const classifyAllLabel = classifying ? t("classifying") : t("classifyAll");
  const classifyUntilDoneLabel = classifyLooping
    ? t("classifying")
    : t("classifyUntilDone");

  return (
    <main className="min-h-screen px-6 py-10 lg:px-12">
      <section className="mx-auto max-w-[1400px]">
        {actionMessage && (
          <div
            className={`mb-6 flex flex-col gap-3 rounded-2xl border px-4 py-3 text-sm shadow-soft sm:flex-row sm:items-center sm:justify-between ${
              actionStatus === "error"
              ? "border-copper/30 bg-surface text-copper"
              : "border-moss/20 bg-surface text-moss"
            }`}
            role={actionStatus === "error" ? "alert" : "status"}
            aria-live="polite"
          >
            <div className="space-y-1">
              <p className="text-xs uppercase tracking-[0.2em] text-ink/50">
                {actionStatus === "error"
                  ? t("actionFailed")
                  : t("actionComplete")}
              </p>
              <p className="text-ink/80">{actionMessage}</p>
            </div>
            <button
              type="button"
              className="self-start rounded-full border border-ink/10 px-3 py-1 text-xs text-ink/60 transition hover:text-ink sm:self-auto"
              onClick={() => {
                setActionMessage(null);
                setActionStatus(null);
              }}
            >
              {t("dismiss")}
            </button>
          </div>
        )}
        <header className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-3 animate-fade-up">
            <p className="text-sm uppercase tracking-[0.2em] text-copper">
              StarSorty
            </p>
            <h1 className="font-display text-4xl font-semibold leading-tight text-ink md:text-5xl">
              {t("title")}
            </h1>
            <p className="max-w-xl text-base text-ink/80">
              {t("subtitle")}
            </p>
          </div>
          <div className="animate-fade-in">
            <div className="space-y-3 text-right">
              <div className="rounded-full border border-ink/10 bg-surface/70 px-4 py-2 shadow-soft">
                <span className="text-sm text-ink/80">
                  {t("lastSyncWithValue", { value: lastSyncLabel })}
                </span>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2">
                <div className="flex items-center rounded-full border border-ink/10 bg-surface px-1 py-1 text-xs">
                  <button
                    type="button"
                    onClick={() => setLocale("en")}
                    className={`rounded-full px-3 py-1 font-semibold transition ${
                      locale === "en"
                        ? "bg-clay text-ink"
                        : "text-ink/60 hover:text-ink"
                    }`}
                    aria-pressed={locale === "en"}
                  >
                    EN
                  </button>
                  <button
                    type="button"
                    onClick={() => setLocale("zh")}
                    className={`rounded-full px-3 py-1 font-semibold transition ${
                      locale === "zh"
                        ? "bg-clay text-ink"
                        : "text-ink/60 hover:text-ink"
                    }`}
                    aria-pressed={locale === "zh"}
                  >
                    中文
                  </button>
                </div>
                <button
                  type="button"
                  onClick={toggleTheme}
                  className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-moss hover:text-moss"
                  aria-label={t("theme")}
                >
                  {theme === "dark" ? t("dark") : t("light")}
                </button>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={handleSync}
                  disabled={syncing}
                  className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-moss hover:text-moss disabled:opacity-60"
                >
                  {syncing ? t("syncing") : t("syncNow")}
                </button>
                <div className="flex items-center gap-2 rounded-full border border-ink/10 bg-surface px-3 py-2 text-xs text-ink/70">
                  <span>{t("batchSize")}</span>
                  <input
                    type="number"
                    min={1}
                    max={500}
                    step={1}
                    value={classifyLimit}
                    onChange={(event) => {
                      const value = event.target.value;
                      if (/^\d*$/.test(value)) {
                        setClassifyLimit(value);
                      }
                    }}
                    className="w-14 bg-transparent text-right text-ink outline-none"
                    aria-label={t("batchSize")}
                  />
                </div>
                <label className="flex items-center gap-2 rounded-full border border-ink/10 bg-surface px-3 py-2 text-xs text-ink/70">
                  <input
                    type="checkbox"
                    checked={forceReclassify}
                    onChange={(event) => setForceReclassify(event.target.checked)}
                    className="accent-moss"
                  />
                  <span>{t("forceReclassify")}</span>
                </label>
                <button
                  type="button"
                  onClick={handleClassifyBatch}
                  disabled={classifying}
                  className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-moss hover:text-moss disabled:opacity-60"
                >
                  {classifyLabel}
                </button>
                <button
                  type="button"
                  onClick={handleClassifyAll}
                  disabled={classifying}
                  className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-moss hover:text-moss disabled:opacity-60"
                >
                  {classifyAllLabel}
                </button>
                <button
                  type="button"
                  onClick={handleClassifyUntilDone}
                  disabled={classifying}
                  className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-moss hover:text-moss disabled:opacity-60"
                >
                  {classifyUntilDoneLabel}
                </button>
                <a
                  href="/settings"
                  className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-moss hover:text-moss"
                >
                  {t("settings")}
                </a>
              </div>
            </div>
          </div>
        </header>

        <div className="mt-10 flex flex-col gap-6 xl:flex-row xl:items-start">
          <aside className="rounded-3xl border border-ink/10 bg-surface/70 p-6 shadow-soft animate-fade-up stagger-1 xl:sticky xl:top-6 xl:w-64 xl:shrink-0">
            <h2 className="font-display text-lg font-semibold">
              {t("languages")}
            </h2>
            <div className="mt-6 space-y-3 text-sm">
              <button
                className={`flex w-full items-center justify-between rounded-2xl px-3 py-2 text-left ${
                  language === null
                    ? "bg-clay text-ink"
                    : "bg-surface/70 text-ink/70"
                }`}
                onClick={() => setLanguage(null)}
              >
                <span>{t("all")}</span>
                <span>{totalCount || repos.length}</span>
              </button>
              {languageCounts.slice(0, 8).map((lang) => (
                <button
                  key={lang.name}
                  className={`flex w-full items-center justify-between rounded-2xl px-3 py-2 text-left ${
                    language === lang.name
                      ? "bg-clay text-ink"
                      : "bg-surface/70 text-ink/70"
                }`}
                onClick={() => setLanguage(lang.name)}
              >
                <span>{lang.name === "unknown" ? t("unknown") : lang.name}</span>
                <span>{lang.count}</span>
              </button>
              ))}
            </div>
            {groupMode && (
              <div className="mt-8">
                <h3 className="text-xs uppercase tracking-[0.2em] text-ink/60">
                  {t("users")}
                </h3>
                <div className="mt-4 space-y-2 text-sm">
                  <button
                    className={`flex w-full items-center justify-between rounded-2xl px-3 py-2 text-left ${
                      sourceUser === null
                        ? "bg-clay text-ink"
                        : "bg-surface/70 text-ink/70"
                    }`}
                    onClick={() => setSourceUser(null)}
                  >
                    <span>{t("all")}</span>
                    <span>{totalCount || repos.length}</span>
                  </button>
                  {userCounts.map((user) => (
                    <button
                      key={user.name}
                      className={`flex w-full items-center justify-between rounded-2xl px-3 py-2 text-left ${
                        sourceUser === user.name
                          ? "bg-clay text-ink"
                          : "bg-surface/70 text-ink/70"
                      }`}
                      onClick={() => setSourceUser(user.name)}
                    >
                      <span>{user.name}</span>
                      <span>{user.count}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-8 border-t border-ink/10 pt-6">
              <h2 className="font-display text-lg font-semibold">
                {t("filters")}
              </h2>
              <div className="mt-5 space-y-4 text-sm">
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-ink/60">
                    {t("stars")}
                  </p>
                  <div className="mt-2 space-y-2">
                    <button
                      className={`w-full rounded-2xl border border-ink/10 px-3 py-2 text-left ${
                        minStars === null ? "bg-clay" : "bg-surface"
                      }`}
                      onClick={() => setMinStars(null)}
                    >
                      {t("any")}
                    </button>
                    {STAR_FILTERS.map((tier) => (
                      <button
                        key={tier}
                        className={`w-full rounded-2xl border border-ink/10 px-3 py-2 text-left ${
                          minStars === tier ? "bg-clay" : "bg-surface"
                        }`}
                        onClick={() => setMinStars(tier)}
                      >
                        {tier.toLocaleString()}+
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-ink/60">
                    {t("status")}
                  </p>
                  <div className="mt-2 space-y-2 text-ink/70">
                    <div>{t("totalWithValue", { count: totalCount || repos.length })}</div>
                    <div>{t("showingWithValue", { count: repos.length })}</div>
                    <div>{t("unclassifiedWithValue", { count: unclassifiedCount })}</div>
                    <div>{t("apiBaseWithValue", { value: API_BASE_URL })}</div>
                  </div>
                </div>
              </div>
            </div>
          </aside>

          <section className="min-w-0 flex-1 space-y-6">
            <div className="rounded-3xl border border-ink/10 bg-surface/80 p-5 shadow-soft animate-fade-up stagger-2">
              <div className="flex flex-col gap-3 md:flex-row md:items-center">
                <input
                  className="w-full rounded-full border border-ink/10 bg-surface px-4 py-3 text-sm outline-none focus:border-moss"
                  placeholder={t("searchPlaceholder")}
                  value={queryInput}
                  onChange={(event) => setQueryInput(event.target.value)}
                />
                <button
                  type="button"
                  className="rounded-full bg-moss px-5 py-3 text-sm font-semibold text-white"
                  onClick={() => setQuery(queryInput.trim())}
                >
                  {t("search")}
                </button>
              </div>
              {error && (
                <p className="mt-3 text-xs text-copper">
                  {t("apiErrorWithValue", { message: error })}
                </p>
              )}
              {loading && (
                <p className="mt-3 text-xs text-ink/60">
                  {t("loadingRepos")}
                </p>
              )}
            </div>

            <div className="grid gap-4">
              {!loading && filteredRepos.length === 0 && (
                <div className="rounded-3xl border border-ink/10 bg-surface/80 p-6 text-sm text-ink/70 shadow-soft">
                  <p className="text-sm text-ink/70">{t("noRepos")}</p>
                </div>
              )}
              {filteredRepos.map((repo, index) => (
                <article
                  key={repo.full_name}
                  className={`rounded-3xl border border-ink/10 bg-surface/90 p-6 shadow-soft animate-fade-up stagger-${
                    (index % 4) + 1
                  }`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="min-w-0">
                      <h3 className="font-display text-xl font-semibold break-words">
                        <a
                          href={repo.html_url}
                          target="_blank"
                          rel="noreferrer"
                          className="transition hover:text-moss"
                        >
                          {repo.name}
                        </a>
                      </h3>
                      {repo.description ? (
                        <p className="mt-2 text-sm text-ink/80 break-words">
                          {repo.description}
                        </p>
                      ) : (
                        <p className="mt-2 text-sm text-ink/80 break-words">
                          {t("noDescription")}
                        </p>
                      )}
                    </div>
                    <div className="flex shrink-0 flex-col items-start gap-2 text-xs sm:items-end">
                      <a
                        href={repo.html_url}
                        target="_blank"
                        rel="noreferrer"
                        className="rounded-full border border-ink/10 bg-surface px-3 py-1 text-ink/70 transition hover:border-moss hover:text-moss"
                      >
                        {t("viewOnGithub")}
                      </a>
                      <span className="rounded-full border border-ink/10 bg-sand px-3 py-1 text-xs">
                        {repo.language ? repo.language : t("unknown")}
                      </span>
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-ink/70">
                    <span>
                      {t("starsWithValue", {
                        count: formatStars(repo.stargazers_count),
                      })}
                    </span>
                    <span>
                      {t("updatedWithValue", { date: formatDate(repo.updated_at) })}
                    </span>
                    {repo.category && (
                      <span className="rounded-full bg-moss/10 px-2 py-1 text-moss">
                        {repo.category}
                        {repo.subcategory ? ` / ${repo.subcategory}` : ""}
                      </span>
                    )}
                    {repo.star_users && repo.star_users.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {repo.star_users.slice(0, 3).map((user) => (
                          <span
                            key={user}
                            className="rounded-full border border-ink/10 bg-surface px-2 py-1"
                          >
                            @{user}
                          </span>
                        ))}
                      </div>
                    )}
                    {repo.topics.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {repo.topics.slice(0, 4).map((tag) => (
                          <span
                            key={tag}
                            className="rounded-full bg-clay px-2 py-1"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                    {repo.tags && repo.tags.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {repo.tags.slice(0, 4).map((tag) => (
                          <span
                            key={tag}
                            className="rounded-full border border-ink/10 bg-surface px-2 py-1"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </section>

        </div>
      </section>
    </main>
  );
}
