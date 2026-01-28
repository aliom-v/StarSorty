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

type ForegroundProgress = {
  running: boolean;
  processed: number;
  failed: number;
  remaining: number | null;
  startRemaining: number | null;
  lastBatch: number;
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
  const [classifying, setClassifying] = useState(false);
  const [classifyLimit, setClassifyLimit] = useState("20");
  const [classifyConcurrency, setClassifyConcurrency] = useState("3");
  const [includeReadme, setIncludeReadme] = useState(true);
  const [classifyLooping, setClassifyLooping] = useState(false);
  const [forceReclassify, setForceReclassify] = useState(false);
  const [backgroundStatus, setBackgroundStatus] = useState<BackgroundStatus | null>(null);
  const [wasBackgroundRunning, setWasBackgroundRunning] = useState(false);
  const [taskInfoId, setTaskInfoId] = useState<string | null>(null);
  const [taskInfo, setTaskInfo] = useState<TaskStatus | null>(null);
  const [followActiveTask, setFollowActiveTask] = useState(true);
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null);
  const [retryingTask, setRetryingTask] = useState(false);
  const [pollingPaused, setPollingPaused] = useState(false);
  const [foregroundProgress, setForegroundProgress] = useState<ForegroundProgress>({
    running: false,
    processed: 0,
    failed: 0,
    remaining: null,
    startRemaining: null,
    lastBatch: 0,
  });
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [subcategory, setSubcategory] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [minStars, setMinStars] = useState<number | null>(null);
  const [sourceUser, setSourceUser] = useState<string | null>(null);
  const [groupMode, setGroupMode] = useState(false);
  const activeError = configError || error;
  const unknownErrorMessage = t("unknownError");

  const handleTagToggle = useCallback((tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
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

  const loadStats = useCallback(async () => {
    setError(null);
    try {
      const statsRes = await fetch(`${API_BASE_URL}/stats`);
      if (!statsRes.ok) {
        const detail = await readApiError(statsRes, unknownErrorMessage);
        setError(detail);
        return;
      }
      const statsData = await statsRes.json();
      setStats(statsData);
    } catch {
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
      if (!res.ok) {
        const detail = await readApiError(res, `Repos fetch failed (${res.status})`);
        throw new Error(detail);
      }
      const data = await res.json();
      const total = Number(data.total || 0);
      const items: Repo[] = data.items || [];

      setTotalCount(total || items.length);
      setRepos((prev) => (append ? [...prev, ...items] : items));
      setHasMore(offset + items.length < total);
    } catch (err) {
      const message = getErrorMessage(err, unknownErrorMessage);
      setError(message);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [category, minStars, query, selectedTags, sourceUser, subcategory, unknownErrorMessage]);

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
      pollTargetIdRef.current = null;
      pollFailureCountRef.current = 0;
      pollingPausedRef.current = false;
      setPollingPaused(false);
      setTaskInfo(null);
      setTaskInfoId(null);
      setPendingTaskId(null);
      setActionMessage(t("taskNotFound"));
      setActionStatus("error");
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
        await loadStats();
        setSourceUser(null);
        await loadRepos(false);
      } else if (data.status === "failed") {
        setActionMessage(data.message || t("syncFailed"));
        setActionStatus("error");
        setSyncing(false);
        setSyncTaskId(null);
      }
    }
  }, [loadRepos, loadStats, loadStatus, pausePolling, pollBackgroundStatusNow, t]);

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
    if (wasBackgroundRunning && !running) {
      loadRepos(false);
      loadStats();
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
    setWasBackgroundRunning(running);
  }, [
    backgroundStatus?.running,
    backgroundStatus?.last_error,
    loadRepos,
    loadStats,
    t,
    wasBackgroundRunning,
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
        await loadStats();
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

  const parseClassifyLimit = () => {
    const parsed = parseInt(classifyLimit, 10);
    if (Number.isNaN(parsed)) return 20;
    return Math.max(1, Math.min(500, parsed));
  };

  const parseClassifyConcurrency = () => {
    const parsed = parseInt(classifyConcurrency, 10);
    if (Number.isNaN(parsed)) return 3;
    return Math.max(1, Math.min(10, parsed));
  };

  const startForegroundProgress = () => {
    const initialRemaining = forceReclassify ? null : (stats?.unclassified ?? null);
    setForegroundProgress({
      running: true,
      processed: 0,
      failed: 0,
      remaining: initialRemaining,
      startRemaining: initialRemaining,
      lastBatch: 0,
    });
  };

  const updateForegroundProgress = (data: {
    classified: number;
    failed: number;
    remaining_unclassified?: number;
  }) => {
    setForegroundProgress((prev) => {
      const batchProcessed = data.classified + data.failed;
      const remaining =
        typeof data.remaining_unclassified === "number"
          ? data.remaining_unclassified
          : prev.remaining;
      const startRemaining =
        prev.startRemaining ??
        (typeof remaining === "number" ? remaining + batchProcessed : null);
      return {
        ...prev,
        processed: prev.processed + batchProcessed,
        failed: prev.failed + data.failed,
        remaining,
        startRemaining,
        lastBatch: batchProcessed,
      };
    });
  };

  const stopForegroundProgress = () => {
    setForegroundProgress((prev) => ({ ...prev, running: false }));
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

  const requestClassify = async (limit?: number) => {
    const payload: { limit?: number; force?: boolean; include_readme?: boolean } = {};
    if (typeof limit === "number") {
      payload.limit = limit;
    }
    if (forceReclassify) {
      payload.force = true;
    }
    if (!includeReadme) {
      payload.include_readme = false;
    }
    const response = await fetch(`${API_BASE_URL}/classify`, {
      method: "POST",
      headers: buildAdminHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const detail = await readApiError(response, t("classifyFailed"));
      throw new Error(detail);
    }
    return response.json();
  };

  const queueForceClassify = async (limit?: number) => {
    const payload: { limit?: number; force: boolean; include_readme?: boolean } = {
      force: true,
    };
    if (typeof limit === "number") {
      payload.limit = limit;
    }
    if (!includeReadme) {
      payload.include_readme = false;
    }
    const response = await fetch(`${API_BASE_URL}/classify`, {
      method: "POST",
      headers: buildAdminHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const detail = await readApiError(response, t("classifyFailed"));
      throw new Error(detail);
    }
    await response.json();
    await loadBackgroundStatus();
    setActionMessage(t("classifyQueued"));
    setActionStatus("success");
  };

  const applyClassifyMessage = (data: {
    classified: number;
    total: number;
    failed: number;
    remaining_unclassified?: number;
  }) => {
    updateForegroundProgress(data);
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
    if (forceReclassify) {
      setActionMessage(null);
      setActionStatus(null);
      try {
        await queueForceClassify(limit);
      } catch (err) {
        const message = getErrorMessage(err, t("classifyFailed"));
        setActionMessage(message);
        setActionStatus("error");
      }
      return;
    }
    setClassifying(true);
    setActionMessage(null);
    setActionStatus(null);
    startForegroundProgress();
    try {
      const data = await requestClassify(limit);
      applyClassifyMessage(data);
      await loadRepos(false);
      await loadStats();
    } catch (err) {
      const message = getErrorMessage(err, t("classifyFailed"));
      setActionMessage(message);
      setActionStatus("error");
    } finally {
      setClassifying(false);
      stopForegroundProgress();
    }
  };

  const handleClassifyBatch = () => handleClassifyOnce(parseClassifyLimit());
  const handleClassifyAll = () => handleClassifyOnce(0);
  const handleClassifyUntilDone = async () => {
    if (classifying) return;
    if (forceReclassify) {
      try {
        await queueForceClassify(0);
      } catch (err) {
        const message = getErrorMessage(err, t("classifyFailed"));
        setActionMessage(message);
        setActionStatus("error");
      }
      return;
    }
    setClassifyLooping(true);
    setClassifying(true);
    setActionMessage(null);
    setActionStatus(null);
    startForegroundProgress();
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
      await loadRepos(false);
      await loadStats();
    } catch (err) {
      const message = getErrorMessage(err, t("classifyFailed"));
      setActionMessage(message);
      setActionStatus("error");
    } finally {
      setClassifying(false);
      setClassifyLooping(false);
      stopForegroundProgress();
    }
  };

  const handleBackgroundStart = async () => {
    setActionMessage(null);
    setActionStatus(null);
    try {
      const payload: {
        limit?: number;
        force?: boolean;
        include_readme?: boolean;
        concurrency?: number;
      } = {
        limit: parseClassifyLimit(),
        concurrency: parseClassifyConcurrency(),
      };
      if (forceReclassify) {
        payload.force = true;
      }
      if (!includeReadme) {
        payload.include_readme = false;
      }
      const res = await fetch(`${API_BASE_URL}/classify/background`, {
        method: "POST",
        headers: buildAdminHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
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
  const backgroundRunning = backgroundStatus?.running ?? false;
  const backgroundProcessed = backgroundStatus?.processed ?? 0;
  const backgroundFailed = backgroundStatus?.failed ?? 0;
  const backgroundSucceeded = Math.max(0, backgroundProcessed - backgroundFailed);
  const backgroundRemaining = backgroundStatus?.remaining ?? 0;
  const backgroundBatchSize =
    backgroundStatus?.batch_size && backgroundStatus.batch_size > 0
      ? backgroundStatus.batch_size
      : parseClassifyLimit();
  const backgroundConcurrency =
    backgroundStatus?.concurrency && backgroundStatus.concurrency > 0
      ? backgroundStatus.concurrency
      : parseClassifyConcurrency();
  const backgroundLastError = backgroundStatus?.last_error ?? null;
  const showBackgroundError =
    !!backgroundLastError && backgroundLastError !== "Stopped by user";
  const showForegroundProgress =
    foregroundProgress.running || foregroundProgress.processed > 0;
  const taskRetryable =
    taskInfo?.status === "failed" && taskInfo?.task_type === "classify";
  const foregroundPercent =
    foregroundProgress.startRemaining !== null &&
    foregroundProgress.startRemaining > 0 &&
    foregroundProgress.remaining !== null
      ? Math.min(
          100,
          Math.max(
            0,
            Math.round(
              ((foregroundProgress.startRemaining - foregroundProgress.remaining) /
                foregroundProgress.startRemaining) *
                100
            )
          )
        )
      : null;

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
                  disabled={classifying || backgroundRunning}
                  className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-moss hover:text-moss disabled:opacity-60"
                >
                  {classifyLabel}
                </button>
                <button
                  type="button"
                  onClick={handleClassifyAll}
                  disabled={classifying || backgroundRunning}
                  className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-moss hover:text-moss disabled:opacity-60"
                >
                  {classifyAllLabel}
                </button>
                <button
                  type="button"
                  onClick={handleClassifyUntilDone}
                  disabled={classifying || backgroundRunning}
                  className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-moss hover:text-moss disabled:opacity-60"
                >
                  {classifyUntilDoneLabel}
                </button>
                <a
                  href="/settings/"
                  className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink transition hover:border-moss hover:text-moss"
                >
                  {t("settings")}
                </a>
              </div>
              <div className="rounded-3xl border border-ink/10 bg-surface/80 p-4 text-left shadow-soft">
                <div className="space-y-3">
                  <div className="space-y-1">
                    <p className="text-xs uppercase tracking-[0.2em] text-ink/60">
                      {t("backgroundStatus")}
                    </p>
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
                    {showBackgroundError && (
                      <p className="text-xs text-copper">{backgroundLastError}</p>
                    )}
                    {taskInfoId && (
                      <div className="mt-2 flex flex-col gap-2 text-xs text-ink/70">
                        <div className="flex flex-wrap items-center gap-2">
                          <span>{t("taskIdWithValue", { value: taskInfoId })}</span>
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
                    <div className="flex items-center gap-2 rounded-full border border-ink/10 bg-surface px-3 py-2 text-xs text-ink/70">
                      <span>{t("concurrency")}</span>
                      <input
                        type="number"
                        min={1}
                        max={10}
                        step={1}
                        value={classifyConcurrency}
                        onChange={(event) => {
                          const value = event.target.value;
                          if (/^\d*$/.test(value)) {
                            setClassifyConcurrency(value);
                          }
                        }}
                        className="w-12 bg-transparent text-right text-ink outline-none"
                        aria-label={t("concurrency")}
                      />
                    </div>
                    <label className="flex items-center gap-2 rounded-full border border-ink/10 bg-surface px-3 py-2 text-xs text-ink/70">
                      <input
                        type="checkbox"
                        checked={includeReadme}
                        onChange={(event) => setIncludeReadme(event.target.checked)}
                        className="accent-moss"
                      />
                      <span>{t("includeReadme")}</span>
                    </label>
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
                  {showForegroundProgress && (
                    <div className="rounded-2xl border border-ink/10 bg-surface/70 px-4 py-3 text-xs text-ink/70">
                      <p className="text-xs uppercase tracking-[0.2em] text-ink/60">
                        {t("foregroundStatus")}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-3">
                        <span>
                          {foregroundProgress.running
                            ? t("backgroundRunning")
                            : t("backgroundIdle")}
                        </span>
                        <span>
                          {t("processedWithValue", {
                            count: foregroundProgress.processed,
                          })}
                        </span>
                        <span>
                          {t("failedWithValue", {
                            count: foregroundProgress.failed,
                          })}
                        </span>
                        <span>
                          {t("remainingWithValue", {
                            count: foregroundProgress.remaining ?? "n/a",
                          })}
                        </span>
                        {foregroundProgress.startRemaining !== null && (
                          <span>
                            {t("totalWithValue", {
                              count: foregroundProgress.startRemaining,
                            })}
                          </span>
                        )}
                      </div>
                      {foregroundPercent !== null && (
                        <div className="mt-2 h-1.5 w-full rounded-full bg-clay">
                          <div
                            className="h-1.5 rounded-full bg-moss"
                            style={{ width: `${foregroundPercent}%` }}
                          />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </header>

        <div className="mt-10 flex flex-col gap-6 xl:flex-row xl:items-start">
          <aside className="rounded-3xl border border-ink/10 bg-surface/70 p-6 shadow-soft animate-fade-up stagger-1 xl:sticky xl:top-6 xl:w-72 xl:shrink-0 xl:max-h-[calc(100vh-3rem)] xl:overflow-y-auto">
            <h2 className="font-display text-lg font-semibold">
              {t("tagCloud")}
            </h2>

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
              {TAG_GROUPS.map((group) => {
                const groupTagCounts = stats?.tags?.filter((t) =>
                  group.tags.includes(t.name)
                ) ?? [];
                if (groupTagCounts.length === 0) return null;
                return (
                  <div key={group.id}>
                    <h3 className="text-xs uppercase tracking-[0.2em] text-ink/60">
                      {group.name}
                    </h3>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {groupTagCounts.map((tagItem) => (
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
                );
              })}
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
                  <p className="text-sm text-ink/70">{t("noRepos")}</p>
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
