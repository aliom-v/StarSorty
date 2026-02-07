"use client";

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { buildAdminHeaders } from "./lib/admin";
import { API_BASE_URL } from "./lib/apiBase";
import { getErrorMessage, readApiError } from "./lib/apiError";
import { useI18n, type Messages, type MessageValues } from "./lib/i18n";
import { useTheme } from "./lib/theme";
import { TAG_GROUPS } from "./lib/tagGroups";

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
  summary_zh?: string | null;
  keywords?: string[];
  pushed_at?: string | null;
  updated_at?: string | null;
  starred_at?: string | null;
};

type Status = {
  last_sync_at?: string | null;
  last_result?: string | null;
  last_message?: string | null;
};

type StatsItem = {
  name: string;
  count: number;
};

type SubcategoryStatsItem = StatsItem & {
  category: string;
};

type Stats = {
  total: number;
  unclassified: number;
  categories: StatsItem[];
  subcategories?: SubcategoryStatsItem[];
  tags: StatsItem[];
  users: StatsItem[];
};

type BackgroundStatus = {
  running: boolean;
  started_at?: string | null;
  finished_at?: string | null;
  processed: number;
  failed: number;
  remaining: number;
  last_error?: string | null;
  batch_size: number;
  concurrency: number;
  task_id?: string | null;
};

type TaskQueued = {
  task_id: string;
  status: string;
  message?: string | null;
};

type TaskStatus = {
  task_id: string;
  status: string;
  task_type: string;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  message?: string | null;
  result?: Record<string, unknown> | null;
  retry_from_task_id?: string | null;
};

type ClientSettings = {
  github_mode: string;
  classify_mode: string;
  auto_classify_after_sync: boolean;
};

const PAGE_SIZE = 60;
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

// Memoized RepoCard component to prevent unnecessary re-renders
type RepoCardProps = {
  repo: Repo;
  index: number;
  t: (key: keyof Messages, params?: MessageValues) => string;
};

const RepoCard = memo(function RepoCard({ repo, index, t }: RepoCardProps) {
  const displayDescription = repo.summary_zh || repo.description;
  return (
    <article
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
          {displayDescription ? (
            <p className="mt-2 text-sm text-ink/80 break-words">
              {displayDescription}
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
          <a
            href={`/repo/?full_name=${encodeURIComponent(repo.full_name)}`}
            className="rounded-full border border-ink/10 bg-surface px-3 py-1 text-ink/70 transition hover:border-moss hover:text-moss"
          >
            {t("details")}
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
        {repo.tags && repo.tags.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {repo.tags.slice(0, 6).map((repoTag) => (
              <span
                key={repoTag}
                className="rounded-full bg-moss/10 px-2 py-1 text-moss"
              >
                {repoTag}
              </span>
            ))}
          </div>
        )}
        {repo.keywords && repo.keywords.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {repo.keywords.slice(0, 4).map((keyword) => (
              <span
                key={keyword}
                className="rounded-full border border-ink/10 bg-surface px-2 py-1"
              >
                {keyword}
              </span>
            ))}
          </div>
        )}
      </div>
    </article>
  );
});

export default function Home() {
  const { t, locale, setLocale } = useI18n();
  const { theme, toggleTheme } = useTheme();
  const [repos, setRepos] = useState<Repo[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [stats, setStats] = useState<Stats | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<"success" | "error" | null>(
    null
  );
  const [syncing, setSyncing] = useState(false);
  const [syncTaskId, setSyncTaskId] = useState<string | null>(null);
  const [backgroundStatus, setBackgroundStatus] = useState<BackgroundStatus | null>(null);
  const [taskInfoId, setTaskInfoId] = useState<string | null>(null);
  const [taskInfo, setTaskInfo] = useState<TaskStatus | null>(null);
  const [followActiveTask, setFollowActiveTask] = useState(true);
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null);
  const [retryingTask, setRetryingTask] = useState(false);
  const [pollingPaused, setPollingPaused] = useState(false);
  const [showAdvancedStatus, setShowAdvancedStatus] = useState(false);
  const [showTaskId, setShowTaskId] = useState(false);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [subcategory, setSubcategory] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [minStars, setMinStars] = useState<number | null>(null);
  const [sourceUser, setSourceUser] = useState<string | null>(null);
  const [groupMode, setGroupMode] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const wasBackgroundRunningRef = useRef(false);
  const activeError = configError || error;
  const unknownErrorMessage = t("unknownError");

  const handleTagToggle = useCallback((tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  }, []);

  const clearAllFilters = useCallback(() => {
    setQueryInput("");
    setQuery("");
    setCategory(null);
    setSubcategory(null);
    setSelectedTags([]);
    setMinStars(null);
    setSourceUser(null);
  }, []);

  const loadStatus = useCallback(async () => {
    setError(null);
    try {
      const statusRes = await fetch(`${API_BASE_URL}/status`);
      if (!statusRes.ok) {
        const detail = await readApiError(statusRes, unknownErrorMessage);
        setError(detail);
        setStatus(null);
        return;
      }
      const statusData = await statusRes.json();
      setStatus(statusData);
    } catch (err) {
      const message = getErrorMessage(err, unknownErrorMessage);
      setError(message);
    }
  }, [unknownErrorMessage]);

  const activeTaskId = backgroundStatus?.task_id || syncTaskId;
  const pollTargetId = followActiveTask ? activeTaskId : taskInfoId;
  const pollTargetIdRef = useRef<string | null>(null);
  const pollRequestIdRef = useRef(0);
  const pollFnRef = useRef<() => void>(() => {});
  const syncTaskIdRef = useRef<string | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollFailureCountRef = useRef(0);
  const pollingPausedRef = useRef(false);
  const pollTickRef = useRef(0);
  const reposRequestIdRef = useRef(0);
  const statsRequestIdRef = useRef(0);

  const loadStats = useCallback(async (refresh = false) => {
    const requestId = statsRequestIdRef.current + 1;
    statsRequestIdRef.current = requestId;
    setError(null);
    try {
      const params = new URLSearchParams();
      if (refresh) {
        params.set("refresh", "1");
      }
      const suffix = params.toString();
      const statsRes = await fetch(
        `${API_BASE_URL}/stats${suffix ? `?${suffix}` : ""}`,
        { cache: "no-store" }
      );
      if (statsRequestIdRef.current !== requestId) return;
      if (!statsRes.ok) {
        const detail = await readApiError(statsRes, unknownErrorMessage);
        if (statsRequestIdRef.current !== requestId) return;
        setError(detail);
        return;
      }
      const statsData = await statsRes.json();
      if (statsRequestIdRef.current !== requestId) return;
      setStats(statsData);
    } catch {
      if (statsRequestIdRef.current !== requestId) return;
      setStats(null);
    }
  }, [unknownErrorMessage]);

  const loadBackgroundStatus = useCallback(async () => {
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/classify/status`);
      if (!res.ok) {
        const detail = await readApiError(res, unknownErrorMessage);
        setError(detail);
        return;
      }
      const data = await res.json();
      setBackgroundStatus(data);
    } catch {
      setBackgroundStatus(null);
    }
  }, [unknownErrorMessage]);

  useEffect(() => {
    syncTaskIdRef.current = syncTaskId;
  }, [syncTaskId]);

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    if (pollIntervalRef.current) return;
    pollIntervalRef.current = setInterval(() => {
      pollFnRef.current();
    }, 8000);
  }, []);

  const pausePolling = useCallback(
    (message: string) => {
      pollingPausedRef.current = true;
      setPollingPaused(true);
      stopPolling();
      setActionMessage(message);
      setActionStatus("error");
    },
    [stopPolling]
  );

  const handleResumePolling = useCallback(() => {
    pollingPausedRef.current = false;
    pollFailureCountRef.current = 0;
    setPollingPaused(false);
    setActionMessage(null);
    setActionStatus(null);
    if (document.visibilityState === "hidden") return;
    startPolling();
    pollFnRef.current();
  }, [startPolling]);

  const pollBackgroundStatusNow = useCallback(async (requestId: number) => {
    try {
      const res = await fetch(`${API_BASE_URL}/classify/status`);
      if (!res.ok) {
        return;
      }
      const data = await res.json();
      if (pollRequestIdRef.current !== requestId) return;
      setBackgroundStatus(data);
    } catch {
      return;
    }
  }, []);

  const loadRepos = useCallback(async (append = false, offsetOverride?: number) => {
    const requestId = reposRequestIdRef.current + 1;
    reposRequestIdRef.current = requestId;

    if (append) {
      setLoadingMore(true);
    } else {
      setLoading(true);
      setError(null);
      setRepos([]);
      setHasMore(false);
    }
    try {
      const offset = append && typeof offsetOverride === "number" ? offsetOverride : 0;
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(offset),
      });
      if (query) params.set("q", query);
      if (category) params.set("category", category);
      if (subcategory) params.set("subcategory", subcategory);
      if (selectedTags.length > 0) params.set("tags", selectedTags.join(","));
      if (minStars) params.set("min_stars", String(minStars));
      if (sourceUser) params.set("star_user", sourceUser);

      const res = await fetch(`${API_BASE_URL}/repos?${params}`);
      if (reposRequestIdRef.current !== requestId) return;
      if (!res.ok) {
        const detail = await readApiError(res, `Repos fetch failed (${res.status})`);
        throw new Error(detail);
      }
      const data = await res.json();
      if (reposRequestIdRef.current !== requestId) return;
      const total = Number(data.total || 0);
      const items: Repo[] = data.items || [];

      setTotalCount(total || items.length);
      setRepos((prev) => {
        if (!append) return items;
        // Deduplicate by full_name when appending
        const existingNames = new Set(prev.map((r) => r.full_name));
        const newItems = items.filter((item) => !existingNames.has(item.full_name));
        return [...prev, ...newItems];
      });
      setHasMore(offset + items.length < total);
    } catch (err) {
      if (reposRequestIdRef.current !== requestId) return;
      const message = getErrorMessage(err, unknownErrorMessage);
      setError(message);
    } finally {
      if (reposRequestIdRef.current !== requestId) return;
      setLoading(false);
      setLoadingMore(false);
    }
  }, [category, minStars, query, selectedTags, sourceUser, subcategory, unknownErrorMessage]);

  const handleMissingTaskRecovery = useCallback(async () => {
    pollTargetIdRef.current = null;
    pollFailureCountRef.current = 0;
    pollingPausedRef.current = false;
    setPollingPaused(false);
    setTaskInfo(null);
    setTaskInfoId(null);
    setPendingTaskId(null);
    setSyncTaskId(null);
    setSyncing(false);
    setFollowActiveTask(true);

    await loadBackgroundStatus();
    await loadStatus();
    await loadStats(true);
    await loadRepos(false);

    setActionMessage(null);
    setActionStatus(null);
  }, [loadBackgroundStatus, loadRepos, loadStats, loadStatus]);

  const pollTaskNow = useCallback(async () => {
    const taskId = pollTargetIdRef.current;
    pollTickRef.current += 1;
    const shouldPollBackground = pollTickRef.current % 5 === 0;
    if (!taskId) {
      if (!shouldPollBackground) return;
      const requestId = pollRequestIdRef.current + 1;
      pollRequestIdRef.current = requestId;
      await pollBackgroundStatusNow(requestId);
      return;
    }
    const requestId = pollRequestIdRef.current + 1;
    pollRequestIdRef.current = requestId;
    let res: Response;
    try {
      res = await fetch(`${API_BASE_URL}/tasks/${taskId}`);
    } catch (err) {
      if (pollTargetIdRef.current !== taskId) return;
      if (pollRequestIdRef.current !== requestId) return;
      pollFailureCountRef.current += 1;
      if (pollFailureCountRef.current >= 3) {
        pausePolling(t("pollingPaused"));
      }
      return;
    }
    if (pollTargetIdRef.current !== taskId) return;
    if (pollRequestIdRef.current !== requestId) return;
    if (res.status === 404) {
      await handleMissingTaskRecovery();
      return;
    }
    if (!res.ok) {
      if (res.status >= 500 || res.status === 429) {
        pollFailureCountRef.current += 1;
        if (pollFailureCountRef.current >= 3) {
          pausePolling(t("pollingPaused"));
        }
      }
      return;
    }
    let data: TaskStatus;
    try {
      data = await res.json();
    } catch (err) {
      if (pollTargetIdRef.current !== taskId) return;
      if (pollRequestIdRef.current !== requestId) return;
      pollFailureCountRef.current += 1;
      if (pollFailureCountRef.current >= 3) {
        pausePolling(t("pollingPaused"));
      }
      return;
    }
    if (pollTargetIdRef.current !== taskId) return;
    if (pollRequestIdRef.current !== requestId) return;
    pollFailureCountRef.current = 0;
    setTaskInfo(data);

    if (shouldPollBackground) {
      await pollBackgroundStatusNow(requestId);
    }

    if (taskId === syncTaskIdRef.current) {
      if (data.status === "finished") {
        const result = data.result ?? {};
        const count =
          typeof result === "object" && result && "count" in result
            ? Number((result as { count?: number }).count ?? 0)
            : null;
        setActionMessage(
          typeof count === "number" && !Number.isNaN(count)
            ? t("syncedWithValue", { count })
            : t("syncComplete")
        );
        setActionStatus("success");
        setSyncing(false);
        setSyncTaskId(null);
        await loadStatus();
        await loadStats(true);
        setSourceUser(null);
        await loadRepos(false);
      } else if (data.status === "failed") {
        setActionMessage(data.message || t("syncFailed"));
        setActionStatus("error");
        setSyncing(false);
        setSyncTaskId(null);
      }
    }
  }, [handleMissingTaskRecovery, loadRepos, loadStats, loadStatus, pausePolling, pollBackgroundStatusNow, t]);

  useEffect(() => {
    pollFnRef.current = pollTaskNow;
  }, [pollTaskNow]);

  useEffect(() => {
    pollTargetIdRef.current = pollTargetId;
    pollTickRef.current = 0;
    pollFailureCountRef.current = 0;
    if (!pollTargetId) {
      setTaskInfo(null);
      if (pollingPausedRef.current) return;
      if (document.visibilityState === "hidden") {
        stopPolling();
        return;
      }
      startPolling();
      return;
    }
    if (pollingPausedRef.current) return;
    if (document.visibilityState === "hidden") {
      stopPolling();
      return;
    }
    startPolling();
    pollFnRef.current();
  }, [pollTargetId, startPolling, stopPolling]);

  const loadClientSettings = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/config/client-settings`);
      if (!res.ok) {
        const detail = await readApiError(res, "Failed to load server config.");
        setConfigError(detail);
        setGroupMode(false);
        return;
      }
      const data = (await res.json()) as ClientSettings;
      setGroupMode(String(data.github_mode || "merge") === "group");
      setConfigError(null);
    } catch (err) {
      const message = getErrorMessage(err, "Failed to load server config.");
      setConfigError(message);
      setGroupMode(false);
    }
  }, []);

  useEffect(() => {
    const load = async () => {
      await loadStatus();
      await loadStats();
      await loadBackgroundStatus();
      await loadClientSettings();
    };
    load();
  }, [loadBackgroundStatus, loadClientSettings, loadStats, loadStatus]);

  useEffect(() => {
    if (!followActiveTask) return;
    if (!activeTaskId) {
      setTaskInfoId(null);
      setTaskInfo(null);
      setPendingTaskId(null);
      return;
    }
    if (pendingTaskId && activeTaskId !== pendingTaskId) {
      return;
    }
    if (pendingTaskId && activeTaskId === pendingTaskId) {
      setPendingTaskId(null);
    }
    if (taskInfoId !== activeTaskId) {
      setTaskInfoId(activeTaskId);
    }
  }, [activeTaskId, followActiveTask, pendingTaskId, taskInfoId]);

  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === "hidden") {
        stopPolling();
        return;
      }
      if (pollingPausedRef.current) return;
      startPolling();
      pollFnRef.current();
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [startPolling, stopPolling]);

  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  useEffect(() => {
    const running = backgroundStatus?.running ?? false;
    const wasRunning = wasBackgroundRunningRef.current;
    if (wasRunning && !running) {
      loadRepos(false);
      loadStats(true);
      const lastError = backgroundStatus?.last_error;
      if (lastError) {
        const stoppedByUser = lastError === "Stopped by user";
        setActionMessage(
          stoppedByUser ? t("backgroundStopped") : lastError
        );
        setActionStatus(stoppedByUser ? "success" : "error");
      } else {
        setActionMessage(t("backgroundComplete"));
        setActionStatus("success");
      }
    }
    wasBackgroundRunningRef.current = running;
  }, [
    backgroundStatus?.running,
    backgroundStatus?.last_error,
    loadRepos,
    loadStats,
    t,
  ]);

  useEffect(() => {
    loadRepos(false);
  }, [category, loadRepos, minStars, query, selectedTags, sourceUser, subcategory]);

  useEffect(() => {
    if (!actionMessage) return;
    if (pollingPaused) return;
    const timer = setTimeout(() => {
      setActionMessage(null);
      setActionStatus(null);
    }, 5000);
    return () => clearTimeout(timer);
  }, [actionMessage, pollingPaused]);

  const handleSync = async () => {
    setSyncing(true);
    setActionMessage(null);
    setActionStatus(null);
    let queued = false;
    try {
      const response = await fetch(`${API_BASE_URL}/sync`, {
        method: "POST",
        headers: buildAdminHeaders(),
      });
      if (!response.ok) {
        const detail = await readApiError(response, t("syncFailed"));
        throw new Error(detail);
      }
      const data = (await response.json()) as Partial<TaskQueued & { count?: number }>;
      if (data.task_id) {
        setSyncTaskId(data.task_id);
        queued = true;
        setActionMessage(t("syncQueued"));
        setActionStatus("success");
      } else {
        const count = typeof data.count === "number" ? data.count : 0;
        setActionMessage(t("syncedWithValue", { count }));
        setActionStatus("success");
        await loadStatus();
        await loadStats(true);
        setSourceUser(null);
        await loadRepos(false);
        setSyncing(false);
      }
    } catch (err) {
      const message = getErrorMessage(err, t("syncFailed"));
      setActionMessage(message);
      setActionStatus("error");
      setSyncing(false);
    } finally {
      if (!queued) {
        setSyncing(false);
      }
    }
  };

  const handleRetryTask = async (taskId: string) => {
    if (retryingTask) return;
    setRetryingTask(true);
    setActionMessage(null);
    setActionStatus(null);
    try {
      const res = await fetch(`${API_BASE_URL}/tasks/${taskId}/retry`, {
        method: "POST",
        headers: buildAdminHeaders(),
      });
      if (!res.ok) {
        const detail = await readApiError(res, t("classifyFailed"));
        throw new Error(detail);
      }
      const data = (await res.json()) as TaskQueued;
      if (data?.task_id) {
        setFollowActiveTask(true);
        setTaskInfoId(data.task_id);
        setTaskInfo(null);
        setPendingTaskId(data.task_id);
        await loadBackgroundStatus();
        setActionMessage(t("retryQueued"));
        setActionStatus("success");
      }
    } catch (err) {
      const message = getErrorMessage(err, t("classifyFailed"));
      setActionMessage(message);
      setActionStatus("error");
    } finally {
      setRetryingTask(false);
    }
  };

  const handleBackgroundStart = async () => {
    setActionMessage(null);
    setActionStatus(null);
    try {
      const res = await fetch(`${API_BASE_URL}/classify/background`, {
        method: "POST",
        headers: buildAdminHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ limit: 20, concurrency: 3 }),
      });
      if (!res.ok) {
        const detail = await readApiError(res, t("classifyFailed"));
        throw new Error(detail);
      }
      await loadBackgroundStatus();
      setActionMessage(t("backgroundClassify"));
      setActionStatus("success");
    } catch (err) {
      const message = getErrorMessage(err, t("classifyFailed"));
      setActionMessage(message);
      setActionStatus("error");
    }
  };

  const handleBackgroundStop = async () => {
    setActionMessage(null);
    setActionStatus(null);
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
      setActionMessage(t("stop"));
      setActionStatus("success");
    } catch (err) {
      const message = getErrorMessage(err, t("classifyFailed"));
      setActionMessage(message);
      setActionStatus("error");
    }
  };

  const categoryCounts = useMemo(() => {
    if (stats?.categories?.length) return stats.categories;
    const map = new Map<string, number>();
    repos.forEach((repo) => {
      const key = repo.category || "uncategorized";
      map.set(key, (map.get(key) || 0) + 1);
    });
    return Array.from(map.entries())
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count);
  }, [repos, stats]);

  const subcategoryCounts = useMemo(() => {
    if (!category) return [];
    const items = stats?.subcategories?.filter((item) => item.category === category);
    if (items && items.length > 0) {
      return [...items].sort((a, b) => b.count - a.count);
    }
    const map = new Map<string, number>();
    repos.forEach((repo) => {
      const repoCategory = repo.category || "uncategorized";
      if (repoCategory !== category) return;
      const key = repo.subcategory || "other";
      map.set(key, (map.get(key) || 0) + 1);
    });
    return Array.from(map.entries())
      .map(([name, count]) => ({ name, count, category }))
      .sort((a, b) => b.count - a.count);
  }, [category, repos, stats]);

  const userCounts = useMemo(() => {
    if (stats?.users?.length) return stats.users;
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
  }, [repos, stats]);

  const unclassifiedCount = useMemo(
    () =>
      stats?.unclassified ?? repos.filter((repo) => !repo.category).length,
    [repos, stats]
  );
  const overallTotal = stats?.total ?? (totalCount || repos.length);
  const selectedCategoryCount = useMemo(() => {
    if (!category) return overallTotal;
    const selected = categoryCounts.find((item) => item.name === category);
    return selected?.count ?? 0;
  }, [category, categoryCounts, overallTotal]);

  // Pre-compute non-empty tag groups to avoid filtering on every render
  const tagGroupsWithCounts = useMemo(() => {
    if (!stats?.tags) return [];
    return TAG_GROUPS.map((group) => {
      const groupTagCounts = stats.tags.filter((t) => group.tags.includes(t.name));
      if (groupTagCounts.length === 0) return null;
      return { ...group, tagCounts: groupTagCounts };
    }).filter(Boolean) as Array<{ id: string; name: string; tags: string[]; tagCounts: StatsItem[] }>;
  }, [stats?.tags]);

  const lastSyncLabel = status?.last_sync_at
    ? new Date(status.last_sync_at).toLocaleString()
    : t("never");
  const backgroundRunning = backgroundStatus?.running ?? false;
  const backgroundProcessed = backgroundStatus?.processed ?? 0;
  const backgroundFailed = backgroundStatus?.failed ?? 0;
  const backgroundSucceeded = Math.max(0, backgroundProcessed - backgroundFailed);
  const backgroundRemaining = backgroundStatus?.remaining ?? 0;
  const backgroundBatchSize = backgroundStatus?.batch_size ?? 20;
  const backgroundConcurrency = backgroundStatus?.concurrency ?? 3;
  const backgroundLastError = backgroundStatus?.last_error ?? null;
  const showBackgroundError =
    !!backgroundLastError && backgroundLastError !== "Stopped by user";
  const taskRetryable =
    taskInfo?.status === "failed" && taskInfo?.task_type === "classify";
  const taskStatus = taskInfo?.status || "";
  const taskType = taskInfo?.task_type || "";
  const taskTypeLabel = taskType === "sync"
    ? t("taskTypeSync")
    : taskType === "classify"
      ? t("taskTypeClassify")
      : taskType === "expired"
        ? t("taskTypeExpired")
        : taskType === "missing"
          ? t("taskTypeMissing")
      : taskType
        ? taskType
        : t("taskTypeUnknown");
  const syncRunning =
    syncing || (taskType === "sync" && (taskStatus === "running" || taskStatus === "queued"));
  const simpleOperationStatus = backgroundRunning
    ? t("classifying")
    : syncRunning
      ? t("syncing")
      : t("backgroundIdle");
  const hasActiveFilters =
    !!query ||
    !!category ||
    !!subcategory ||
    selectedTags.length > 0 ||
    minStars !== null ||
    sourceUser !== null;

  return (
    <main className="h-screen flex flex-col overflow-hidden px-6 py-6 lg:px-12">
      <section className="mx-auto max-w-[1400px] w-full flex flex-col flex-1 min-h-0">
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
            <div className="flex flex-wrap items-center gap-2 self-start sm:self-auto">
              {pollingPaused && (
                <button
                  type="button"
                  className="rounded-full border border-ink/10 px-3 py-1 text-xs text-ink/70 transition hover:border-moss hover:text-moss"
                  onClick={handleResumePolling}
                >
                  {t("reconnect")}
                </button>
              )}
              <button
                type="button"
                className="rounded-full border border-ink/10 px-3 py-1 text-xs text-ink/60 transition hover:text-ink"
                onClick={() => {
                  setActionMessage(null);
                  setActionStatus(null);
                }}
              >
                {t("dismiss")}
              </button>
            </div>
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
                <button
                  type="button"
                  onClick={handleBackgroundStart}
                  disabled={backgroundRunning}
                  className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-moss hover:text-moss disabled:opacity-60"
                >
                  {backgroundRunning ? t("classifying") : t("classify")}
                </button>
                <a
                  href="/settings/"
                  className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-moss hover:text-moss"
                >
                  {t("settings")}
                </a>
                <a
                  href="/admin/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-copper hover:text-copper"
                >
                  {t("admin")}
                </a>
              </div>
              <div className="rounded-3xl border border-ink/10 bg-surface/80 p-4 text-left shadow-soft">
                <div className="space-y-3">
                  <div className="space-y-2">
                    <p className="text-xs uppercase tracking-[0.2em] text-ink/60">
                      {t("simpleStatus")}
                    </p>
                    <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-ink/70">
                      <span>{t("operationStatusWithValue", { value: simpleOperationStatus })}</span>
                      <button
                        type="button"
                        className="rounded-full border border-ink/10 px-3 py-1 text-xs text-ink/70 transition hover:border-moss hover:text-moss"
                        onClick={() => setShowAdvancedStatus((prev) => !prev)}
                      >
                        {showAdvancedStatus ? t("hide") : t("advancedDetails")}
                      </button>
                    </div>
                    {showAdvancedStatus && (
                      <div className="flex flex-wrap gap-3 text-xs text-ink/70">
                        <span>
                          {backgroundRunning ? t("backgroundRunning") : t("backgroundIdle")}
                        </span>
                        <span>{t("processedWithValue", { count: backgroundProcessed })}</span>
                        <span>{t("succeededWithValue", { count: backgroundSucceeded })}</span>
                        <span>{t("failedWithValue", { count: backgroundFailed })}</span>
                        <span>{t("remainingWithValue", { count: backgroundRemaining })}</span>
                        <span>
                          {t("batchSize")}: {backgroundBatchSize}
                        </span>
                        <span>
                          {t("concurrency")}: {backgroundConcurrency}
                        </span>
                      </div>
                    )}
                    {showBackgroundError && (
                      <p className="text-xs text-copper">{backgroundLastError}</p>
                    )}
                    {showAdvancedStatus && taskInfoId && (
                      <div className="mt-2 flex flex-col gap-2 text-xs text-ink/70">
                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            className="rounded-full border border-ink/10 px-3 py-1 text-xs text-ink/70 transition hover:border-moss hover:text-moss"
                            onClick={() => setShowTaskId((prev) => !prev)}
                          >
                            {showTaskId ? t("hideTaskId") : t("showTaskId")}
                          </button>
                          {showTaskId && (
                            <span>{t("taskIdWithValue", { value: taskInfoId })}</span>
                          )}
                          <span>
                            {t("taskTypeWithValue", {
                              value: taskTypeLabel,
                            })}
                          </span>
                          <span>
                            {t("taskStatusWithValue", {
                              value: taskInfo?.status || t("fetching"),
                            })}
                          </span>
                          {taskRetryable && (
                            <button
                              type="button"
                              className="rounded-full border border-ink/10 px-3 py-1 text-xs text-ink/70 transition hover:border-moss hover:text-moss disabled:opacity-60"
                              onClick={() => handleRetryTask(taskInfoId)}
                              disabled={retryingTask}
                            >
                              {retryingTask ? t("retrying") : t("retry")}
                            </button>
                          )}
                        </div>
                        {!!taskInfo?.message && (
                          <span className="text-xs text-ink/50">{taskInfo.message}</span>
                        )}
                        {!!taskInfo?.retry_from_task_id && (
                          <div className="flex flex-wrap items-center gap-2 text-xs text-ink/60">
                            <span>
                              {t("retryFromWithValue", {
                                value: taskInfo.retry_from_task_id,
                              })}
                            </span>
                            <button
                              type="button"
                              className="text-xs text-ink/70 underline transition hover:text-moss"
                              onClick={() => {
                                setFollowActiveTask(false);
                                setPendingTaskId(null);
                                setTaskInfoId(taskInfo.retry_from_task_id || null);
                              }}
                            >
                              {t("viewTask")}
                            </button>
                            {followActiveTask === false && activeTaskId && (
                              <button
                                type="button"
                                className="text-xs text-ink/60 underline transition hover:text-moss"
                                onClick={() => {
                                  setFollowActiveTask(true);
                                  setPendingTaskId(null);
                                  setTaskInfoId(activeTaskId || null);
                                }}
                              >
                                {t("viewCurrentTask")}
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={handleBackgroundStart}
                      disabled={backgroundRunning}
                      className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-moss hover:text-moss disabled:opacity-60"
                    >
                      {t("backgroundClassify")}
                    </button>
                    <button
                      type="button"
                      onClick={handleBackgroundStop}
                      disabled={!backgroundRunning}
                      className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-copper hover:text-copper disabled:opacity-60"
                    >
                      {t("stop")}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </header>

        <div className="mt-6 flex flex-col gap-6 xl:flex-row flex-1 min-h-0 overflow-hidden">
          <aside className="rounded-3xl border border-ink/10 bg-surface/70 p-6 shadow-soft animate-fade-up stagger-1 xl:w-72 xl:shrink-0 xl:overflow-y-auto">
            <button
              type="button"
              className="flex w-full items-center justify-between xl:cursor-default"
              onClick={() => setSidebarOpen(!sidebarOpen)}
            >
              <h2 className="font-display text-lg font-semibold">
                {t("tagCloud")}
              </h2>
              <span className="text-ink/40 xl:hidden">
                {sidebarOpen ? "▲" : "▼"}
              </span>
            </button>

            <div className={`${sidebarOpen ? "block" : "hidden"} xl:block`}>
              {selectedTags.length > 0 && (
                <div className="mt-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-ink/60">
                    {t("selectedTags")}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {selectedTags.map((tag) => (
                      <button
                        key={tag}
                        type="button"
                        className="rounded-full bg-moss px-3 py-1 text-xs text-white transition hover:bg-moss/80"
                        onClick={() => handleTagToggle(tag)}
                      >
                        {tag} ×
                      </button>
                    ))}
                    <button
                      type="button"
                      className="rounded-full border border-ink/10 bg-surface px-3 py-1 text-xs text-ink/70 transition hover:border-copper hover:text-copper"
                      onClick={() => setSelectedTags([])}
                    >
                      {t("clearTags")}
                    </button>
                  </div>
                </div>
              )}

              <div className="mt-6 space-y-4">
                {tagGroupsWithCounts.map((group) => (
                  <div key={group.id}>
                    <h3 className="text-xs uppercase tracking-[0.2em] text-ink/60">
                      {group.name}
                    </h3>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {group.tagCounts.map((tagItem) => (
                        <button
                          key={tagItem.name}
                          type="button"
                          className={`rounded-full px-3 py-1 text-xs transition ${
                            selectedTags.includes(tagItem.name)
                              ? "bg-moss text-white"
                              : "bg-surface border border-ink/10 text-ink/70 hover:border-moss hover:text-moss"
                          }`}
                          onClick={() => handleTagToggle(tagItem.name)}
                        >
                          {tagItem.name} ({tagItem.count})
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              {groupMode && (
                <div className="mt-8 border-t border-ink/10 pt-6">
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
                      <span>{overallTotal}</span>
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
                  {t("status")}
                </h2>
                <div className="mt-4 space-y-2 text-sm text-ink/70">
                  <div>{t("totalWithValue", { count: overallTotal })}</div>
                  <div>{t("showingWithValue", { count: repos.length })}</div>
                  <div>{t("unclassifiedWithValue", { count: unclassifiedCount })}</div>
                </div>
              </div>
            </div>
          </aside>

          <section className="min-w-0 flex-1 space-y-6 overflow-y-auto">
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
              {activeError && (
                <p className="mt-3 text-xs text-copper">
                  {t("apiErrorWithValue", { message: activeError })}
                </p>
              )}
              {loading && (
                <p className="mt-3 text-xs text-ink/60">
                  {t("loadingRepos")}
                </p>
              )}
            </div>
            <div className="grid gap-4">
              {!loading && repos.length === 0 && (
                <div className="rounded-3xl border border-ink/10 bg-surface/80 p-6 text-sm text-ink/70 shadow-soft">
                  <p className="text-sm text-ink/70">
                    {hasActiveFilters ? t("noReposForFilters") : t("noRepos")}
                  </p>
                  {hasActiveFilters && (
                    <button
                      type="button"
                      className="mt-3 rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-moss hover:text-moss"
                      onClick={clearAllFilters}
                    >
                      {t("clearFilters")}
                    </button>
                  )}
                </div>
              )}
              {repos.map((repo, index) => (
                <RepoCard key={repo.full_name} repo={repo} index={index} t={t} />
              ))}
            </div>
            {hasMore && (
              <div className="flex justify-center">
                <button
                  type="button"
                  onClick={() => loadRepos(true, repos.length)}
                  disabled={loadingMore}
                  className="rounded-full border border-ink/10 bg-surface px-5 py-2 text-sm font-semibold text-ink transition hover:border-moss hover:text-moss disabled:opacity-60"
                >
                  {loadingMore ? t("loadingMore") : t("loadMore")}
                </button>
              </div>
            )}
          </section>

        </div>
      </section>
    </main>
  );
}
