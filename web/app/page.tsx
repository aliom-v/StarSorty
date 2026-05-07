"use client";

import { useEffect, useState, type ComponentProps } from "react";
import Header from "./components/Header";
import RepoResults from "./components/RepoResults";
import SearchSection from "./components/SearchSection";
import Sidebar from "./components/Sidebar";
import StatusBanner from "./components/StatusBanner";
import { useI18n } from "./lib/i18n";
import { useHomePageData } from "./lib/useHomePageData";
import { useTheme } from "./lib/theme";
import type { HomeDensityMode, HomeGroupMode, HomeRepo } from "./lib/homePageTypes";

export default function Home() {
  const { t } = useI18n();
  const { toggleTheme } = useTheme();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [densityMode, setDensityMode] = useState<HomeDensityMode>("comfortable");
  const [resultGroupMode, setResultGroupMode] = useState<HomeGroupMode>("none");
  const [selectedRepoNames, setSelectedRepoNames] = useState<Set<string>>(() => new Set());
  const { filters, operations, repoList, sidebar, statusBanner, summary } =
    useHomePageData(t);
  const sidebarProps = {
    t,
    sidebarOpen,
    setSidebarOpen,
    language: filters.language,
    setLanguage: filters.setLanguage,
    minStars: filters.minStars,
    setMinStars: filters.setMinStars,
    category: filters.category,
    setCategory: filters.setCategory,
    subcategory: filters.subcategory,
    setSubcategory: filters.setSubcategory,
    selectedTags: filters.selectedTags,
    handleTagToggle: filters.handleTagToggle,
    setSelectedTags: filters.setSelectedTags,
    tagMode: filters.tagMode,
    setTagMode: filters.setTagMode,
    categoryCounts: sidebar.categoryCounts,
    subcategoryCounts: sidebar.subcategoryCounts,
    tagGroups: sidebar.tagGroupsWithCounts,
    groupMode: sidebar.groupMode,
    sourceUser: filters.sourceUser,
    setSourceUser: filters.setSourceUser,
    userCounts: sidebar.userCounts,
    overallTotal: sidebar.overallTotal,
    unclassifiedCount: sidebar.unclassifiedCount,
  } satisfies ComponentProps<typeof Sidebar>;

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

  const toggleRepoSelection = (repo: HomeRepo) => {
    setSelectedRepoNames((current) => {
      const next = new Set(current);
      if (next.has(repo.full_name)) {
        next.delete(repo.full_name);
      } else {
        next.add(repo.full_name);
      }
      return next;
    });
  };

  const selectGroup = (repos: HomeRepo[]) => {
    setSelectedRepoNames((current) => {
      const next = new Set(current);
      repos.forEach((repo) => next.add(repo.full_name));
      return next;
    });
  };

  return (
    <main className="relative flex h-screen w-full overflow-hidden bg-sand text-ink">
      <aside className="z-20 hidden h-full w-72 flex-shrink-0 flex-col border-r border-ink/10 bg-surface md:flex xl:w-80">
        <Sidebar {...sidebarProps} />
      </aside>

      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-ink/35 md:hidden"
          onClick={() => setSidebarOpen(false)}
        >
          <aside
            className="h-full w-[min(90vw,22rem)] border-r border-ink/10 bg-surface shadow-premium"
            onClick={(event) => event.stopPropagation()}
          >
            <Sidebar {...sidebarProps} />
          </aside>
        </div>
      )}

      <section className="custom-scrollbar relative h-full flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[118rem] space-y-4 px-4 py-4 sm:px-5 md:space-y-5 md:px-6 lg:px-8">
          <Header
            t={t}
            totalRepos={summary.overallTotal}
            shownCount={summary.shownCount}
            activeFilterCount={filters.activeFilterCount}
            toggleTheme={toggleTheme}
            lastSyncLabel={summary.lastSyncLabel}
            syncing={operations.syncRunning}
            backgroundRunning={operations.backgroundRunning}
            disableSyncAction={operations.disableSyncAction}
            disableClassifyAction={operations.disableClassifyAction}
            handleSync={operations.handleSync}
            handleBackgroundStart={operations.handleBackgroundStart}
            handleBackgroundStop={operations.handleBackgroundStop}
          />

          <div className="space-y-4">
            <SearchSection
              t={t}
              query={filters.query}
              queryInput={filters.queryInput}
              setQueryInput={filters.setQueryInput}
              submitSearch={filters.submitSearch}
              clearSearch={filters.clearSearch}
              searchDirty={filters.searchDirty}
              shownCount={summary.shownCount}
              activeFilterCount={filters.activeFilterCount}
              sortMode={filters.sortMode}
              setSortMode={filters.setSortMode}
              densityMode={densityMode}
              setDensityMode={setDensityMode}
              groupMode={resultGroupMode}
              setGroupMode={setResultGroupMode}
              selectedCount={selectedRepoNames.size}
              clearSelection={() => setSelectedRepoNames(new Set())}
              activeError={repoList.activeError}
              loading={repoList.loading}
              hasActiveFilters={filters.hasActiveFilters}
              clearAllFilters={filters.clearAllFilters}
              onOpenFilters={() => setSidebarOpen(true)}
            />

            <RepoResults
              t={t}
              repos={repoList.repos}
              query={filters.query}
              loading={repoList.loading}
              hasMore={repoList.hasMore}
              loadingMore={repoList.loadingMore}
              hasActiveFilters={filters.hasActiveFilters}
              densityMode={densityMode}
              groupMode={resultGroupMode}
              selectedRepoNames={selectedRepoNames}
              onToggleSelect={toggleRepoSelection}
              onSelectGroup={selectGroup}
              clearAllFilters={filters.clearAllFilters}
              onLoadMore={repoList.loadNextPage}
              onRepoClick={repoList.handleRepoClick}
            />
          </div>
        </div>
      </section>

      <StatusBanner
        t={t}
        actionMessage={statusBanner.actionMessage}
        actionStatus={statusBanner.actionStatus}
        pollingPaused={statusBanner.pollingPaused}
        handleResumePolling={statusBanner.handleResumePolling}
        dismissAction={statusBanner.dismissAction}
        simpleOperationStatus={statusBanner.simpleOperationStatus}
        backgroundRunning={statusBanner.backgroundRunning}
        backgroundProcessed={statusBanner.backgroundProcessed}
        backgroundRemaining={statusBanner.backgroundRemaining}
      />
    </main>
  );
}
