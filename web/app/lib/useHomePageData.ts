"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { buildAdminHeaders } from "./admin";
import { API_BASE_URL } from "./apiBase";
import { getErrorMessage, readApiError } from "./apiError";
import type { MessageValues, Messages } from "./i18n";
import {
  PAGE_SIZE,
  type ActionStatus,
  type BackgroundStatus,
  type ClientSettings,
  type Repo,
  type RepoListResponse,
  type SortMode,
  type Stats,
  type Status,
  type TagMode,
  type TaskQueued,
  type TaskStatus,
} from "./homePageTypes";
import { mergeRepoItems, normalizeRepoPage } from "./repoListState";
import { createRequestTracker } from "./requestTracker";
import {
  evaluateTrackedPollFailure,
  evaluateTrackedPollResponse,
  getPollingDelayMs,
  shouldPollBackgroundStatus,
} from "./taskPolling";

type Translate = (key: keyof Messages, params?: MessageValues) => string;

type UseHomePageDataArgs = {
  t: Translate;
  query: string;
  category: string | null;
  subcategory: string | null;
  selectedTags: string[];
  tagMode: TagMode;
  sortMode: SortMode;
  minStars: number | null;
  sourceUser: string | null;
  setSourceUser: (user: string | null) => void;
};

type BuildRepoParamsArgs = Omit<UseHomePageDataArgs, "t" | "setSourceUser"> & {
  activePreferenceUser: string;
  offset: number;
};

function buildRepoParams({
  query,
  category,
  subcategory,
  selectedTags,
  tagMode,
  sortMode,
  minStars,
  sourceUser,
  activePreferenceUser,
  offset,
}: BuildRepoParamsArgs) {
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
  return params;
}

export function useHomePageData({
  t,
  query,
  category,
  subcategory,
  selectedTags,
  tagMode,
  sortMode,
  minStars,
  sourceUser,
  setSourceUser,
}: UseHomePageDataArgs) {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<ActionStatus>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncTaskId, setSyncTaskId] = useState<string | null>(null);
  const [backgroundStatus, setBackgroundStatus] =
    useState<BackgroundStatus | null>(null);
  const [taskInfoId, setTaskInfoId] = useState<string | null>(null);
  const [taskInfo, setTaskInfo] = useState<TaskStatus | null>(null);
  const [followActiveTask, setFollowActiveTask] = useState(true);
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null);
  const [pollingPaused, setPollingPaused] = useState(false);
  const [groupMode, setGroupMode] = useState(false);

  const wasBackgroundRunningRef = useRef(false);
  const pollTargetIdRef = useRef<string | null>(null);
  const pollFnRef = useRef<() => void>(() => {});
  const syncTaskIdRef = useRef<string | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollFailureCountRef = useRef(0);
  const pollingPausedRef = useRef(false);
  const pollTickRef = useRef(0);
  const pollRequestTrackerRef = useRef(createRequestTracker());
  const reposRequestTrackerRef = useRef(createRequestTracker());
  const statsRequestIdRef = useRef(0);

  const unknownErrorMessage = t("unknownError");
  const activePreferenceUser = sourceUser || "global";
  const activeTaskId = backgroundStatus?.task_id || syncTaskId;
  const pollTargetId = followActiveTask ? activeTaskId : taskInfoId;

  const handleRepoClick = useCallback(
    (repo: Repo) => {
      void fetch(`${API_BASE_URL}/feedback/click`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: activePreferenceUser,
          full_name: repo.full_name,
          query: query || null,
        }),
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
      setError(getErrorMessage(err, unknownErrorMessage));
    }
  }, [unknownErrorMessage]);

  const loadStats = useCallback(
    async (refresh = false) => {
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
    },
    [unknownErrorMessage]
  );

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
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (delayMs?: number) => {
      stopPolling();
      if (pollingPausedRef.current) return;
      if (document.visibilityState === "hidden") return;
      const nextDelay =
        typeof delayMs === "number"
          ? Math.max(0, delayMs)
          : getPollingDelayMs(
              pollFailureCountRef.current,
              Boolean(pollTargetIdRef.current)
            );
      pollTimerRef.current = setTimeout(() => {
        pollTimerRef.current = null;
        void pollFnRef.current();
      }, nextDelay);
    },
    [stopPolling]
  );

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
    startPolling(0);
  }, [startPolling]);

  const pollBackgroundStatusNow = useCallback(async (requestId: number) => {
    try {
      const res = await fetch(`${API_BASE_URL}/classify/status`);
      if (!res.ok) {
        return;
      }
      const data = await res.json();
      if (!pollRequestTrackerRef.current.isCurrent(requestId)) return;
      setBackgroundStatus(data);
    } catch {
      return;
    }
  }, []);

  const loadRepos = useCallback(
    async (append = false, offsetOverride?: number) => {
      const requestId = reposRequestTrackerRef.current.begin();

      if (append) {
        setLoadingMore(true);
      } else {
        setLoading(true);
        setError(null);
        setRepos([]);
        setHasMore(false);
        setNextOffset(null);
      }
      try {
        const offset =
          append && typeof offsetOverride === "number" ? offsetOverride : 0;
        const params = buildRepoParams({
          query,
          category,
          subcategory,
          selectedTags,
          tagMode,
          sortMode,
          minStars,
          sourceUser,
          activePreferenceUser,
          offset,
        });

        const res = await fetch(`${API_BASE_URL}/repos?${params}`);
        if (!reposRequestTrackerRef.current.isCurrent(requestId)) return;
        if (!res.ok) {
          const detail = await readApiError(
            res,
            `Repos fetch failed (${res.status})`
          );
          throw new Error(detail);
        }
        const data = (await res.json()) as RepoListResponse;
        if (!reposRequestTrackerRef.current.isCurrent(requestId)) return;
        const page = normalizeRepoPage(data, offset);

        setRepos((prev) => mergeRepoItems(prev, page.items, append));
        setHasMore(page.hasMore);
        setNextOffset(page.nextOffset);

        if (!append && query) {
          void fetch(`${API_BASE_URL}/feedback/search`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              user_id: activePreferenceUser,
              query,
              results_count: page.total,
              selected_tags: selectedTags,
              category,
              subcategory,
            }),
          }).catch(() => {});
        }
      } catch (err) {
        if (!reposRequestTrackerRef.current.isCurrent(requestId)) return;
        setError(getErrorMessage(err, unknownErrorMessage));
      } finally {
        if (!reposRequestTrackerRef.current.isCurrent(requestId)) return;
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [
      activePreferenceUser,
      category,
      minStars,
      query,
      selectedTags,
      sortMode,
      sourceUser,
      subcategory,
      tagMode,
      unknownErrorMessage,
    ]
  );

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
    const shouldPollBackground = shouldPollBackgroundStatus(pollTickRef.current);
    if (!taskId) {
      if (shouldPollBackground) {
        const requestId = pollRequestTrackerRef.current.begin();
        await pollBackgroundStatusNow(requestId);
      }
      startPolling();
      return;
    }

    const requestId = pollRequestTrackerRef.current.begin();
    let res: Response;
    try {
      res = await fetch(`${API_BASE_URL}/tasks/${taskId}`);
    } catch {
      const failure = evaluateTrackedPollFailure({
        currentTaskId: pollTargetIdRef.current,
        expectedTaskId: taskId,
        activeRequestId: pollRequestTrackerRef.current.current(),
        requestId,
        failureCount: pollFailureCountRef.current,
      });
      if (failure.ignore) return;
      pollFailureCountRef.current = failure.nextFailureCount;
      if (failure.pause) {
        pausePolling(t("pollingPaused"));
        return;
      }
      startPolling();
      return;
    }

    if (res.status === 404 || !res.ok) {
      const responseState = evaluateTrackedPollResponse({
        currentTaskId: pollTargetIdRef.current,
        expectedTaskId: taskId,
        activeRequestId: pollRequestTrackerRef.current.current(),
        requestId,
        status: res.status,
        failureCount: pollFailureCountRef.current,
      });
      if (responseState.ignore) return;
      pollFailureCountRef.current = responseState.nextFailureCount;
      if (responseState.recoverMissingTask) {
        await handleMissingTaskRecovery();
        return;
      }
      if (responseState.pause) {
        pausePolling(t("pollingPaused"));
        return;
      }
      startPolling();
      return;
    }

    let data: TaskStatus;
    try {
      data = await res.json();
    } catch {
      const failure = evaluateTrackedPollFailure({
        currentTaskId: pollTargetIdRef.current,
        expectedTaskId: taskId,
        activeRequestId: pollRequestTrackerRef.current.current(),
        requestId,
        failureCount: pollFailureCountRef.current,
      });
      if (failure.ignore) return;
      pollFailureCountRef.current = failure.nextFailureCount;
      if (failure.pause) {
        pausePolling(t("pollingPaused"));
        return;
      }
      startPolling();
      return;
    }

    const responseState = evaluateTrackedPollResponse({
      currentTaskId: pollTargetIdRef.current,
      expectedTaskId: taskId,
      activeRequestId: pollRequestTrackerRef.current.current(),
      requestId,
      status: res.status,
      failureCount: pollFailureCountRef.current,
    });
    if (responseState.ignore || !responseState.acceptResult) return;
    pollFailureCountRef.current = responseState.nextFailureCount;
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

    startPolling();
  }, [
    handleMissingTaskRecovery,
    loadRepos,
    loadStats,
    loadStatus,
    pausePolling,
    pollBackgroundStatusNow,
    setSourceUser,
    startPolling,
    t,
  ]);

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
    startPolling(0);
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
      setConfigError(getErrorMessage(err, "Failed to load server config."));
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
    void load();
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
      startPolling(0);
    };

    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [startPolling, stopPolling]);

  useEffect(() => () => stopPolling(), [stopPolling]);

  useEffect(() => {
    const running = backgroundStatus?.running ?? false;
    const wasRunning = wasBackgroundRunningRef.current;
    if (wasRunning && !running) {
      void loadRepos(false);
      void loadStats(true);
      const lastError = backgroundStatus?.last_error;
      if (lastError) {
        const stoppedByUser = lastError === "Stopped by user";
        setActionMessage(stoppedByUser ? t("backgroundStopped") : lastError);
        setActionStatus(stoppedByUser ? "success" : "error");
      } else {
        setActionMessage(t("backgroundComplete"));
        setActionStatus("success");
      }
    }
    wasBackgroundRunningRef.current = running;
  }, [
    backgroundStatus?.last_error,
    backgroundStatus?.running,
    loadRepos,
    loadStats,
    t,
  ]);

  useEffect(() => {
    void loadRepos(false);
  }, [
    category,
    loadRepos,
    minStars,
    query,
    selectedTags,
    sourceUser,
    subcategory,
    tagMode,
    sortMode,
  ]);

  useEffect(() => {
    if (!actionMessage || pollingPaused) return;
    const timer = setTimeout(() => {
      setActionMessage(null);
      setActionStatus(null);
    }, 5000);
    return () => clearTimeout(timer);
  }, [actionMessage, pollingPaused]);

  const handleSync = useCallback(async () => {
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
      setActionMessage(getErrorMessage(err, t("syncFailed")));
      setActionStatus("error");
      setSyncing(false);
    } finally {
      if (!queued) {
        setSyncing(false);
      }
    }
  }, [backgroundStatus?.running, loadRepos, loadStats, loadStatus, setSourceUser, t]);

  const handleBackgroundStart = useCallback(async () => {
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
      setActionMessage(getErrorMessage(err, t("classifyFailed")));
      setActionStatus("error");
    }
  }, [backgroundStatus?.running, loadBackgroundStatus, syncing, t]);

  const handleBackgroundStop = useCallback(async () => {
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
      setActionMessage(getErrorMessage(err, t("classifyFailed")));
      setActionStatus("error");
    }
  }, [backgroundStatus?.running, loadBackgroundStatus, t]);

  return {
    repos,
    stats,
    status,
    loading,
    loadingMore,
    hasMore,
    nextOffset,
    error,
    configError,
    actionMessage,
    actionStatus,
    syncing,
    backgroundStatus,
    taskInfo,
    pollingPaused,
    groupMode,
    loadRepos,
    handleRepoClick,
    handleSync,
    handleBackgroundStart,
    handleBackgroundStop,
    handleResumePolling,
    setActionMessage,
    setActionStatus,
  };
}
