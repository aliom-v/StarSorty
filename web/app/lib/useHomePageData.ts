import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { adminFetch } from "./admin";
import { API_BASE_URL } from "./apiBase";
import { getErrorMessage, readApiError } from "./apiError";
import type { Messages, MessageValues } from "./i18n";
import {
  type HomeActionStatus,
  type HomeBackgroundStatus,
  type HomeClientSettings,
  type HomeRepo,
  type HomeRepoListResponse,
  type HomeStats,
  type HomeStatsItem,
  type HomeStatus,
  type HomeTagGroupWithCounts,
  type HomeTaskQueued,
  type HomeTaskStatus,
} from "./homePageTypes";
import { mergeRepoItems, normalizeRepoPage } from "./repoListState";
import {
  createAbortableRequestTracker,
  createRequestTracker,
  isAbortError,
} from "./requestTracker";
import {
  evaluateTrackedPollFailure,
  evaluateTrackedPollResponse,
  getPollingDelayMs,
  shouldPollBackgroundStatus,
} from "./taskPolling";
import { TAG_GROUPS } from "./tagGroups";
import { buildRepoSearchParams } from "./homePageFilters";
import { useHomePageFilters } from "./useHomePageFilters";

const PAGE_SIZE = 60;

type Translate = (key: keyof Messages, params?: MessageValues) => string;

export function useHomePageData(t: Translate) {
  const [repos, setRepos] = useState<HomeRepo[]>([]);
  const [stats, setStats] = useState<HomeStats | null>(null);
  const [status, setStatus] = useState<HomeStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<HomeActionStatus>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncTaskId, setSyncTaskId] = useState<string | null>(null);
  const [backgroundStatus, setBackgroundStatus] =
    useState<HomeBackgroundStatus | null>(null);
  const [taskInfoId, setTaskInfoId] = useState<string | null>(null);
  const [taskInfo, setTaskInfo] = useState<HomeTaskStatus | null>(null);
  const [followActiveTask, setFollowActiveTask] = useState(true);
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null);
  const [pollingPaused, setPollingPaused] = useState(false);
  const [groupMode, setGroupMode] = useState(false);
  const filterState = useHomePageFilters();
  const {
    query,
    language,
    category,
    subcategory,
    selectedTags,
    tagMode,
    sortMode,
    minStars,
    sourceUser,
    activePreferenceUser,
    setSubcategory,
    setSortMode,
    setSourceUser,
  } = filterState;

  const wasBackgroundRunningRef = useRef(false);
  const pollTargetIdRef = useRef<string | null>(null);
  const pollFnRef = useRef<() => void>(() => {});
  const syncTaskIdRef = useRef<string | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollFailureCountRef = useRef(0);
  const pollingPausedRef = useRef(false);
  const pollTickRef = useRef(0);
  const statusRequestTrackerRef = useRef(createAbortableRequestTracker());
  const backgroundStatusRequestTrackerRef = useRef(
    createAbortableRequestTracker()
  );
  const statsRequestTrackerRef = useRef(createAbortableRequestTracker());
  const clientSettingsRequestTrackerRef = useRef(
    createAbortableRequestTracker()
  );
  const pollRequestTrackerRef = useRef(createRequestTracker());
  const reposRequestTrackerRef = useRef(createAbortableRequestTracker());

  const activeError = configError || error;
  const unknownErrorMessage = t("unknownError");

  const handleRepoClick = useCallback(
    (repo: HomeRepo) => {
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

  const clearActionFeedback = useCallback(() => {
    setActionMessage(null);
    setActionStatus(null);
  }, []);

  const loadStatus = useCallback(async () => {
    const { requestId, signal } = statusRequestTrackerRef.current.begin();
    setError(null);
    try {
      const statusRes = await fetch(`${API_BASE_URL}/status`, { signal });
      if (!statusRequestTrackerRef.current.isCurrent(requestId)) return;
      if (!statusRes.ok) {
        const detail = await readApiError(statusRes, unknownErrorMessage);
        if (!statusRequestTrackerRef.current.isCurrent(requestId)) return;
        setError(detail);
        setStatus(null);
        return;
      }
      const statusData = (await statusRes.json()) as HomeStatus;
      if (!statusRequestTrackerRef.current.isCurrent(requestId)) return;
      setStatus(statusData);
    } catch (err) {
      if (
        !statusRequestTrackerRef.current.isCurrent(requestId) ||
        isAbortError(err)
      ) {
        return;
      }
      const message = getErrorMessage(err, unknownErrorMessage);
      setStatus(null);
      setError(message);
    }
  }, [unknownErrorMessage]);

  const activeTaskId = backgroundStatus?.task_id || syncTaskId;
  const pollTargetId = followActiveTask ? activeTaskId : taskInfoId;

  const loadStats = useCallback(
    async (refresh = false) => {
      const { requestId, signal } = statsRequestTrackerRef.current.begin();
      setError(null);
      try {
        const params = new URLSearchParams();
        if (refresh) {
          params.set("refresh", "1");
        }
        const suffix = params.toString();
        const statsRes = await fetch(
          `${API_BASE_URL}/stats${suffix ? `?${suffix}` : ""}`,
          { cache: "no-store", signal }
        );
        if (!statsRequestTrackerRef.current.isCurrent(requestId)) return;
        if (!statsRes.ok) {
          const detail = await readApiError(statsRes, unknownErrorMessage);
          if (!statsRequestTrackerRef.current.isCurrent(requestId)) return;
          setStats(null);
          setError(detail);
          return;
        }
        const statsData = (await statsRes.json()) as HomeStats;
        if (!statsRequestTrackerRef.current.isCurrent(requestId)) return;
        setStats(statsData);
      } catch (err) {
        if (
          !statsRequestTrackerRef.current.isCurrent(requestId) ||
          isAbortError(err)
        ) {
          return;
        }
        setStats(null);
        setError(getErrorMessage(err, unknownErrorMessage));
      }
    },
    [unknownErrorMessage]
  );

  const loadBackgroundStatus = useCallback(async () => {
    const { requestId, signal } =
      backgroundStatusRequestTrackerRef.current.begin();
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/classify/status`, { signal });
      if (!backgroundStatusRequestTrackerRef.current.isCurrent(requestId)) {
        return;
      }
      if (!res.ok) {
        const detail = await readApiError(res, unknownErrorMessage);
        if (!backgroundStatusRequestTrackerRef.current.isCurrent(requestId)) {
          return;
        }
        setError(detail);
        setBackgroundStatus(null);
        return;
      }
      const data = (await res.json()) as HomeBackgroundStatus;
      if (!backgroundStatusRequestTrackerRef.current.isCurrent(requestId)) {
        return;
      }
      setBackgroundStatus(data);
    } catch (err) {
      if (
        !backgroundStatusRequestTrackerRef.current.isCurrent(requestId) ||
        isAbortError(err)
      ) {
        return;
      }
      setBackgroundStatus(null);
      setError(getErrorMessage(err, unknownErrorMessage));
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
    clearActionFeedback();
    if (document.visibilityState === "hidden") return;
    startPolling(0);
  }, [clearActionFeedback, startPolling]);

  const pollBackgroundStatusNow = useCallback(async (requestId: number) => {
    try {
      const res = await fetch(`${API_BASE_URL}/classify/status`);
      if (!res.ok) {
        return;
      }
      const data = (await res.json()) as HomeBackgroundStatus;
      if (!pollRequestTrackerRef.current.isCurrent(requestId)) return;
      setBackgroundStatus(data);
    } catch {
      return;
    }
  }, []);

  const loadRepos = useCallback(
    async (append = false, offsetOverride?: number) => {
      const { requestId, signal } = reposRequestTrackerRef.current.begin();

      if (append) {
        setLoadingMore(true);
      } else {
        setLoading(true);
        setError(null);
        setHasMore(false);
        setNextOffset(null);
      }

      try {
        const offset =
          append && typeof offsetOverride === "number" ? offsetOverride : 0;
        const params = buildRepoSearchParams({
          query,
          language,
          minStars,
          category,
          subcategory,
          selectedTags,
          tagMode,
          sortMode,
          activePreferenceUser,
          sourceUser,
          limit: PAGE_SIZE,
          offset,
        });

        const res = await fetch(`${API_BASE_URL}/repos?${params}`, { signal });
        if (!reposRequestTrackerRef.current.isCurrent(requestId)) return;
        if (!res.ok) {
          const detail = await readApiError(
            res,
            `Repos fetch failed (${res.status})`
          );
          throw new Error(detail);
        }
        const data = (await res.json()) as HomeRepoListResponse;
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
        if (
          !reposRequestTrackerRef.current.isCurrent(requestId) ||
          isAbortError(err)
        ) {
          return;
        }
        const message = getErrorMessage(err, unknownErrorMessage);
        setError(message);
      } finally {
        if (!reposRequestTrackerRef.current.isCurrent(requestId)) return;
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [
      activePreferenceUser,
      query,
      language,
      minStars,
      category,
      subcategory,
      selectedTags,
      sourceUser,
      tagMode,
      sortMode,
      unknownErrorMessage,
    ]
  );

  const refreshAfterSync = useCallback(async () => {
    if (sourceUser !== null) {
      await Promise.all([loadStatus(), loadStats(true)]);
      setSourceUser(null);
      return;
    }
    await Promise.all([loadStatus(), loadStats(true), loadRepos(false)]);
  }, [loadRepos, loadStats, loadStatus, setSourceUser, sourceUser]);

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

    await Promise.all([
      loadBackgroundStatus(),
      loadStatus(),
      loadStats(true),
      loadRepos(false),
    ]);

    clearActionFeedback();
  }, [clearActionFeedback, loadBackgroundStatus, loadRepos, loadStats, loadStatus]);

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

    let data: HomeTaskStatus;
    try {
      data = (await res.json()) as HomeTaskStatus;
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
        await refreshAfterSync();
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
    pausePolling,
    pollBackgroundStatusNow,
    refreshAfterSync,
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
    const { requestId, signal } =
      clientSettingsRequestTrackerRef.current.begin();
    try {
      const res = await fetch(`${API_BASE_URL}/api/config/client-settings`, {
        signal,
      });
      if (!clientSettingsRequestTrackerRef.current.isCurrent(requestId)) {
        return;
      }
      if (!res.ok) {
        const detail = await readApiError(res, "Failed to load server config.");
        if (!clientSettingsRequestTrackerRef.current.isCurrent(requestId)) {
          return;
        }
        setConfigError(detail);
        setGroupMode(false);
        return;
      }
      const data = (await res.json()) as HomeClientSettings;
      if (!clientSettingsRequestTrackerRef.current.isCurrent(requestId)) {
        return;
      }
      setGroupMode(String(data.github_mode || "merge") === "group");
      setConfigError(null);
    } catch (err) {
      if (
        !clientSettingsRequestTrackerRef.current.isCurrent(requestId) ||
        isAbortError(err)
      ) {
        return;
      }
      const message = getErrorMessage(err, "Failed to load server config.");
      setConfigError(message);
      setGroupMode(false);
    }
  }, []);

  useEffect(() => {
    if (sortMode !== "relevance" || query) {
      return;
    }
    setSortMode("stars");
  }, [query, setSortMode, sortMode]);

  useEffect(() => {
    const load = async () => {
      await Promise.all([
        loadStatus(),
        loadStats(),
        loadBackgroundStatus(),
        loadClientSettings(),
      ]);
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

  useEffect(() => {
    const statusTracker = statusRequestTrackerRef.current;
    const backgroundStatusTracker = backgroundStatusRequestTrackerRef.current;
    const statsTracker = statsRequestTrackerRef.current;
    const clientSettingsTracker = clientSettingsRequestTrackerRef.current;
    const reposTracker = reposRequestTrackerRef.current;
    const pollTracker = pollRequestTrackerRef.current;

    return () => {
      stopPolling();
      statusTracker.reset();
      backgroundStatusTracker.reset();
      statsTracker.reset();
      clientSettingsTracker.reset();
      reposTracker.reset();
      pollTracker.reset();
    };
  }, [stopPolling]);

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
  }, [loadRepos]);

  useEffect(() => {
    if (!actionMessage) return;
    if (pollingPaused) return;
    const timer = setTimeout(() => {
      clearActionFeedback();
    }, 5000);
    return () => clearTimeout(timer);
  }, [actionMessage, clearActionFeedback, pollingPaused]);

  const handleSync = useCallback(async () => {
    if (backgroundStatus?.running) return;
    setSyncing(true);
    clearActionFeedback();
    let queued = false;

    try {
      const response = await adminFetch(`${API_BASE_URL}/sync`, {
        method: "POST",
      });
      if (!response.ok) {
        const detail = await readApiError(response, t("syncFailed"));
        throw new Error(detail);
      }
      const data = (await response.json()) as Partial<HomeTaskQueued & { count?: number }>;
      if (data.task_id) {
        setSyncTaskId(data.task_id);
        queued = true;
        setActionMessage(t("syncQueued"));
        setActionStatus("success");
      } else {
        const count = typeof data.count === "number" ? data.count : 0;
        setActionMessage(t("syncedWithValue", { count }));
        setActionStatus("success");
        await refreshAfterSync();
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
  }, [backgroundStatus?.running, clearActionFeedback, refreshAfterSync, t]);

  const handleBackgroundStart = useCallback(async () => {
    if (syncing || backgroundStatus?.running) return;
    clearActionFeedback();
    try {
      const res = await adminFetch(`${API_BASE_URL}/classify/background`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
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
  }, [backgroundStatus?.running, clearActionFeedback, loadBackgroundStatus, syncing, t]);

  const handleBackgroundStop = useCallback(async () => {
    if (!backgroundStatus?.running) return;
    clearActionFeedback();
    try {
      const res = await adminFetch(`${API_BASE_URL}/classify/stop`, {
        method: "POST",
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
  }, [backgroundStatus?.running, clearActionFeedback, loadBackgroundStatus, t]);

  const userCounts = useMemo<HomeStatsItem[]>(() => {
    if (stats?.users?.length) return stats.users;
    return [];
  }, [stats]);

  const categoryCounts = useMemo<HomeStatsItem[]>(() => {
    if (stats?.categories?.length) return stats.categories;
    return [];
  }, [stats]);

  const subcategoryCounts = useMemo(() => {
    const items = stats?.subcategories ?? [];
    if (!category) return items;
    return items.filter((item) => item.category === category);
  }, [category, stats?.subcategories]);

  useEffect(() => {
    const allSubcategories = stats?.subcategories;
    if (!subcategory || !allSubcategories?.length) {
      return;
    }
    const currentOptions = category
      ? allSubcategories.filter((item) => item.category === category)
      : allSubcategories;
    if (!currentOptions.some((item) => item.name === subcategory)) {
      setSubcategory(null);
    }
  }, [category, setSubcategory, stats?.subcategories, subcategory]);

  const tagGroupsWithCounts = useMemo<HomeTagGroupWithCounts[]>(() => {
    if (!stats?.tags) return [];
    return TAG_GROUPS.map((group) => {
      const groupTagCounts = stats.tags.filter((tag) =>
        group.tags.includes(tag.name)
      );
      if (groupTagCounts.length === 0) return null;
      return { ...group, tagCounts: groupTagCounts };
    }).filter((group): group is HomeTagGroupWithCounts => group !== null);
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
  const syncRunning =
    syncing ||
    (taskType === "sync" &&
      (taskStatus === "running" || taskStatus === "queued"));

  const simpleOperationStatus = backgroundRunning
    ? t("classifying")
    : syncRunning
      ? t("syncing")
      : t("backgroundIdle");

  const loadNextPage = useCallback(() => {
    void loadRepos(true, nextOffset ?? repos.length);
  }, [loadRepos, nextOffset, repos.length]);

  return {
    filters: filterState,
    repoList: {
      repos,
      loading,
      loadingMore,
      hasMore,
      activeError,
      handleRepoClick,
      loadNextPage,
    },
    operations: {
      backgroundRunning,
      syncRunning,
      disableSyncAction: syncing || backgroundRunning,
      disableClassifyAction: syncing,
      handleSync,
      handleBackgroundStart,
      handleBackgroundStop,
    },
    sidebar: {
      groupMode,
      userCounts,
      categoryCounts,
      subcategoryCounts,
      tagGroupsWithCounts,
      overallTotal,
      unclassifiedCount,
    },
    summary: {
      lastSyncLabel,
      overallTotal,
      shownCount: repos.length,
    },
    statusBanner: {
      actionMessage,
      actionStatus,
      pollingPaused,
      simpleOperationStatus,
      backgroundRunning,
      backgroundProcessed,
      backgroundRemaining,
      handleResumePolling,
      dismissAction: clearActionFeedback,
    },
  };
}
