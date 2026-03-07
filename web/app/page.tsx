"use client";

import { useEffect, useMemo } from "react";

import Header from "./components/Header";
import RepoCard from "./components/RepoCard";
import SearchSection from "./components/SearchSection";
import Sidebar from "./components/Sidebar";
import StatusBanner from "./components/StatusBanner";
import type { TagGroupWithCounts } from "./lib/homePageTypes";
import { useHomePageData } from "./lib/useHomePageData";
import { useHomePageFilters } from "./lib/useHomePageFilters";
import { useI18n } from "./lib/i18n";
import { TAG_GROUPS } from "./lib/tagGroups";
import { useTheme } from "./lib/theme";

export default function Home() {
  const { t } = useI18n();
  const { theme, toggleTheme } = useTheme();
  const {
    queryInput,
    setQueryInput,
    query,
    setQuery,
    category,
    subcategory,
    selectedTags,
    setSelectedTags,
    tagMode,
    setTagMode,
    sortMode,
    setSortMode,
    minStars,
    sourceUser,
    setSourceUser,
    sidebarOpen,
    setSidebarOpen,
    handleTagToggle,
    clearAllFilters,
  } = useHomePageFilters();
  const {
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
  } = useHomePageData({
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
  });

  const activeError = configError || error;
  const userCounts = useMemo(() => {
    if (stats?.users?.length) return stats.users;
    return [];
  }, [stats]);
  const tagGroupsWithCounts = useMemo<TagGroupWithCounts[]>(() => {
    if (!stats?.tags) return [];
    return TAG_GROUPS.map((group) => {
      const groupTagCounts = stats.tags.filter((tag) =>
        group.tags.includes(tag.name)
      );
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
  const syncRunning =
    syncing ||
    (taskType === "sync" && (taskStatus === "running" || taskStatus === "queued"));
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
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
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
                  {[...Array(5)].map((_, index) => (
                    <SkeletonCard key={index} />
                  ))}
                </div>
              )}

              {repos.length === 0 && !loading && (
                <div className="flex flex-col items-center justify-center py-24 px-6 text-center animate-fade-in panel-muted rounded-[2.5rem]">
                  <div className="h-24 w-24 rounded-full glass flex items-center justify-center text-ink/10 mb-8 shadow-soft">
                    <svg
                      className="w-12 h-12"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={1.5}
                        d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                      />
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
                    onClick={() => loadRepos(true, nextOffset ?? repos.length)}
                    disabled={loadingMore}
                    className="group flex items-center gap-4 rounded-full glass px-12 py-5 text-xs font-black uppercase tracking-widest text-ink transition-all hover:shadow-premium active:scale-95"
                  >
                    {loadingMore ? (
                      <svg
                        className="w-4 h-4 animate-spin"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                      >
                        <path
                          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                          strokeWidth="2.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
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
