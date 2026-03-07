"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { buildAdminHeaders } from "./lib/admin";
import { API_BASE_URL } from "./lib/apiBase";
import { getErrorMessage, readApiError } from "./lib/apiError";
import { useI18n } from "./lib/i18n";
import { useTheme } from "./lib/theme";
import { TAG_GROUPS } from "./lib/tagGroups";

// Components
import RepoCard from "./components/RepoCard";
import Sidebar from "./components/Sidebar";
import Header from "./components/Header";
import SearchSection from "./components/SearchSection";
import StatusBanner from "./components/StatusBanner";

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
  tag_ids?: string[];
  summary_zh?: string | null;
  keywords?: string[];
  search_score?: number | null;
  match_reasons?: string[];
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

type TagGroupWithCounts = {
  id: string;
  name: string;
  tags: string[];
  tagCounts: StatsItem[];
};

const PAGE_SIZE = 60;

export default function Home() {
  const { t } = useI18n();
  const { theme, toggleTheme } = useTheme();
  
  // State
  const [repos, setRepos] = useState<Repo[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<"success" | "error" | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncTaskId, setSyncTaskId] = useState<string | null>(null);
  const [backgroundStatus, setBackgroundStatus] = useState<BackgroundStatus | null>(null);
  const [taskInfoId, setTaskInfoId] = useState<string | null>(null);
  const [taskInfo, setTaskInfo] = useState<TaskStatus | null>(null);
  const [followActiveTask, setFollowActiveTask] = useState(true);
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null);
  const [pollingPaused, setPollingPaused] = useState(false);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [subcategory, setSubcategory] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagMode, setTagMode] = useState<"or" | "and">("or");
  const [sortMode, setSortMode] = useState<"relevance" | "stars" | "updated">("stars");
  const [minStars, setMinStars] = useState<number | null>(null);
  const [sourceUser, setSourceUser] = useState<string | null>(null);
  const [groupMode, setGroupMode] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Refs
  const wasBackgroundRunningRef = useRef(false);
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

  const activeError = configError || error;
  const unknownErrorMessage = t("unknownError");
  const activePreferenceUser = sourceUser || "global";

  // Callbacks
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
    setTagMode("or");
    setSortMode("stars");
    setMinStars(null);
    setSourceUser(null);
  }, []);

  const handleRepoClick = useCallback(
    (repo: Repo) => {
      const payload = {
        user_id: activePreferenceUser,
        full_name: repo.full_name,
        query: query || null,
      };
      void fetch(`${API_BASE_URL}/feedback/click`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).catch(() => {});
    },
    [activePreferenceUser, query]
  );

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
      params.set("tag_mode", tagMode);
      params.set("sort", sortMode);
      params.set("user_id", activePreferenceUser);
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

      setRepos((prev) => {
        if (!append) return items;
        const existingNames = new Set(prev.map((r) => r.full_name));
        const newItems = items.filter((item) => !existingNames.has(item.full_name));
        return [...prev, ...newItems];
      });
      setHasMore(offset + items.length < total);

      if (!append && query) {
        void fetch(`${API_BASE_URL}/feedback/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: activePreferenceUser,
            query,
            results_count: total,
            selected_tags: selectedTags,
            category,
            subcategory,
          }),
        }).catch(() => {});
      }
    } catch (err) {
      if (reposRequestIdRef.current !== requestId) return;
      const message = getErrorMessage(err, unknownErrorMessage);
      setError(message);
    } finally {
      if (reposRequestIdRef.current !== requestId) return;
      setLoading(false);
      setLoadingMore(false);
    }
  }, [activePreferenceUser, category, minStars, query, selectedTags, sourceUser, subcategory, tagMode, sortMode, unknownErrorMessage]);

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
    } catch {
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
    } catch {
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
  }, [category, loadRepos, minStars, query, selectedTags, sourceUser, subcategory, tagMode, sortMode]);

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
    if (backgroundStatus?.running) return;
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

  const handleBackgroundStart = async () => {
    if (syncing || backgroundStatus?.running) return;
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
    if (!backgroundStatus?.running) return;
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

  // Memos
  const userCounts = useMemo(() => {
    if (stats?.users?.length) return stats.users;
    return [];
  }, [stats]);

  const tagGroupsWithCounts = useMemo<TagGroupWithCounts[]>(() => {
    if (!stats?.tags) return [];
    return TAG_GROUPS.map((group) => {
      const groupTagCounts = stats.tags.filter((tag) => group.tags.includes(tag.name));
      if (groupTagCounts.length === 0) return null;
      return { ...group, tagCounts: groupTagCounts };
    }).filter((group): group is TagGroupWithCounts => group !== null);
  }, [stats?.tags]);

  const lastSyncLabel = status?.last_sync_at
    ? new Date(status.last_sync_at).toLocaleString()
    : t("never");
  
  const backgroundRunning = backgroundStatus?.running ?? false;
  const backgroundProcessed = backgroundStatus?.processed ?? 0;
  const backgroundRemaining = backgroundStatus?.remaining ?? 0;
  const unclassifiedCount = stats?.unclassified ?? 0;
  const overallTotal = stats?.total ?? 0;

  const taskStatus = taskInfo?.status || "";
  const taskType = taskInfo?.task_type || "";
  const syncRunning = syncing || (taskType === "sync" && (taskStatus === "running" || taskStatus === "queued"));
  
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

  const activeFilterCount = [
    !!query,
    !!category,
    !!subcategory,
    selectedTags.length > 0,
    minStars !== null,
    sourceUser !== null,
  ].filter(Boolean).length;

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        document.getElementById("search-input")?.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const SkeletonCard = () => (
    <div className="rounded-[2.5rem] bg-surface/20 border border-ink/5 p-8 space-y-8 animate-pulse-subtle">
      <div className="flex justify-between items-start gap-6">
        <div className="space-y-4 flex-1">
          <div className="h-8 bg-ink/5 rounded-2xl w-1/3" />
          <div className="space-y-2">
            <div className="h-4 bg-ink/5 rounded-lg w-full" />
            <div className="h-4 bg-ink/5 rounded-lg w-2/3" />
          </div>
        </div>
        <div className="h-12 w-24 bg-ink/5 rounded-full shrink-0" />
      </div>
      <div className="flex gap-2">
        <div className="h-8 w-20 bg-ink/5 rounded-full" />
        <div className="h-8 w-24 bg-ink/5 rounded-full" />
      </div>
    </div>
  );

  return (
    <main className="relative flex h-screen w-full overflow-hidden bg-transparent perspective-lg">
      {/* 1. 全局侧边栏 - 模拟 iOS 侧边栏材质 */}
      <aside className="hidden md:flex flex-col w-80 lg:w-96 h-full flex-shrink-0 border-r border-ink/5 glass-dark z-20">
        <Sidebar 
          t={t}
          sidebarOpen={sidebarOpen}
          setSidebarOpen={setSidebarOpen}
          selectedTags={selectedTags}
          handleTagToggle={handleTagToggle}
          setSelectedTags={setSelectedTags}
          tagMode={tagMode}
          setTagMode={setTagMode}
          tagGroups={tagGroupsWithCounts}
          groupMode={groupMode}
          sourceUser={sourceUser}
          setSourceUser={setSourceUser}
          userCounts={userCounts}
          overallTotal={overallTotal}
          unclassifiedCount={unclassifiedCount}
        />
      </aside>

      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-ink/40 backdrop-blur-sm md:hidden"
          onClick={() => setSidebarOpen(false)}
        >
          <aside
            className="h-full w-[min(88vw,24rem)] border-r border-ink/5 bg-surface/90 shadow-premium"
            onClick={(event) => event.stopPropagation()}
          >
            <Sidebar
              t={t}
              sidebarOpen={sidebarOpen}
              setSidebarOpen={setSidebarOpen}
              selectedTags={selectedTags}
              handleTagToggle={handleTagToggle}
              setSelectedTags={setSelectedTags}
              tagMode={tagMode}
              setTagMode={setTagMode}
              tagGroups={tagGroupsWithCounts}
              groupMode={groupMode}
              sourceUser={sourceUser}
              setSourceUser={setSourceUser}
              userCounts={userCounts}
              overallTotal={overallTotal}
              unclassifiedCount={unclassifiedCount}
            />
          </aside>
        </div>
      )}

      {/* 2. 主内容区 - 独立滚动 */}
      <section className="flex-1 h-full overflow-y-auto relative custom-scrollbar bg-surface/20">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.55),transparent_65%)] opacity-80 dark:bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.08),transparent_62%)]" />
        <div className="pointer-events-none absolute right-[8%] top-28 h-48 w-48 rounded-full bg-moss/10 blur-3xl dark:bg-moss/15" />
        <div className="pointer-events-none absolute left-[12%] top-44 h-36 w-36 rounded-full bg-copper/10 blur-3xl dark:bg-copper/10" />
        <div className="relative max-w-6xl mx-auto w-full p-6 md:p-12 lg:p-16 space-y-16">
          
          <Header 
            t={t}
            theme={theme}
            totalRepos={overallTotal}
            shownCount={repos.length}
            activeFilterCount={activeFilterCount}
            toggleTheme={toggleTheme}
            lastSyncLabel={lastSyncLabel}
            syncing={syncRunning}
            backgroundRunning={backgroundRunning}
            disableSyncAction={syncing || backgroundRunning}
            disableClassifyAction={syncing}
            handleSync={handleSync}
            handleBackgroundStart={handleBackgroundStart}
            handleBackgroundStop={handleBackgroundStop}
          />

          <div className="space-y-12">
            <SearchSection 
              t={t}
              queryInput={queryInput}
              setQueryInput={setQueryInput}
              setQuery={setQuery}
              shownCount={repos.length}
              activeFilterCount={activeFilterCount}
              sortMode={sortMode}
              setSortMode={setSortMode}
              activeError={activeError}
              loading={loading}
              hasActiveFilters={hasActiveFilters}
              clearAllFilters={clearAllFilters}
              onOpenFilters={() => setSidebarOpen(true)}
            />

            <div className="space-y-6 pb-24">
              {loading && repos.length === 0 && (
                <div className="grid grid-cols-1 gap-6">
                  {[...Array(5)].map((_, i) => (
                    <SkeletonCard key={i} />
                  ))}
                </div>
              )}

              {repos.length === 0 && !loading && (
                <div className="flex flex-col items-center justify-center py-24 px-6 text-center animate-fade-in panel-muted rounded-[2.5rem]">
                  <div className="h-24 w-24 rounded-full glass flex items-center justify-center text-ink/10 mb-8 shadow-soft">
                    <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                  </div>
                  <h3 className="text-2xl font-black text-ink mb-3 tracking-tight">
                    {hasActiveFilters ? t("noReposForFilters") : t("noRepos")}
                  </h3>
                  <p className="mx-auto mb-8 max-w-sm font-medium text-subtle">
                    {hasActiveFilters 
                      ? "Try adjusting your search or filters to find what you're looking for." 
                      : "Start by syncing your GitHub stars to see them here."}
                  </p>
                  {hasActiveFilters && (
                    <button
                      type="button"
                      className="rounded-full btn-ios-primary px-8 py-3.5 text-xs font-black uppercase tracking-[0.18em]"
                      onClick={clearAllFilters}
                    >
                      {t("clearFilters")}
                    </button>
                  )}
                </div>
              )}

              <div className="grid grid-cols-1 gap-6">
                {repos.map((repo, index) => (
                  <RepoCard
                    key={repo.full_name}
                    repo={repo}
                    index={index}
                    queryActive={!!query}
                    onRepoClick={handleRepoClick}
                    t={t}
                  />
                ))}
              </div>

              {hasMore && (
                <div className="flex justify-center pt-8">
                  <button
                    type="button"
                    onClick={() => loadRepos(true, repos.length)}
                    disabled={loadingMore}
                    className="group flex items-center gap-4 rounded-full glass px-12 py-5 text-xs font-black uppercase tracking-widest text-ink transition-all hover:shadow-premium active:scale-95"
                  >
                    {loadingMore ? (
                      <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    ) : null}
                    {loadingMore ? t("loadingMore") : t("loadMore")}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* 3. 状态横幅 - 悬浮在内容之上 */}
      <StatusBanner 
        t={t}
        actionMessage={actionMessage}
        actionStatus={actionStatus}
        pollingPaused={pollingPaused}
        handleResumePolling={handleResumePolling}
        setActionMessage={setActionMessage}
        setActionStatus={setActionStatus}
        simpleOperationStatus={simpleOperationStatus}
        backgroundRunning={backgroundRunning}
        backgroundProcessed={backgroundProcessed}
        backgroundRemaining={backgroundRemaining}
      />
    </main>
  );
}
