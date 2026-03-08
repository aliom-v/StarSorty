"use client";

import { useEffect, useState } from "react";
import Header from "./components/Header";
import RepoResults from "./components/RepoResults";
import SearchSection from "./components/SearchSection";
import Sidebar from "./components/Sidebar";
import StatusBanner from "./components/StatusBanner";
import { useI18n } from "./lib/i18n";
import { useHomePageData } from "./lib/useHomePageData";
import { useTheme } from "./lib/theme";

export default function Home() {
  const { t } = useI18n();
  const { theme, toggleTheme } = useTheme();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { filters, operations, repoList, sidebar, statusBanner, summary } =
    useHomePageData(t);

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

  return (
    <main className="relative flex h-screen w-full overflow-hidden bg-transparent perspective-lg">
      <aside className="glass-dark z-20 hidden h-full w-80 flex-shrink-0 flex-col border-r border-ink/5 md:flex lg:w-96">
        <Sidebar
          t={t}
          sidebarOpen={sidebarOpen}
          setSidebarOpen={setSidebarOpen}
          selectedTags={filters.selectedTags}
          handleTagToggle={filters.handleTagToggle}
          setSelectedTags={filters.setSelectedTags}
          tagMode={filters.tagMode}
          setTagMode={filters.setTagMode}
          tagGroups={sidebar.tagGroupsWithCounts}
          groupMode={sidebar.groupMode}
          sourceUser={filters.sourceUser}
          setSourceUser={filters.setSourceUser}
          userCounts={sidebar.userCounts}
          overallTotal={sidebar.overallTotal}
          unclassifiedCount={sidebar.unclassifiedCount}
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
              selectedTags={filters.selectedTags}
              handleTagToggle={filters.handleTagToggle}
              setSelectedTags={filters.setSelectedTags}
              tagMode={filters.tagMode}
              setTagMode={filters.setTagMode}
              tagGroups={sidebar.tagGroupsWithCounts}
              groupMode={sidebar.groupMode}
              sourceUser={filters.sourceUser}
              setSourceUser={filters.setSourceUser}
              userCounts={sidebar.userCounts}
              overallTotal={sidebar.overallTotal}
              unclassifiedCount={sidebar.unclassifiedCount}
            />
          </aside>
        </div>
      )}

      <section className="custom-scrollbar relative h-full flex-1 overflow-y-auto bg-surface/20">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.55),transparent_65%)] opacity-80 dark:bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.08),transparent_62%)]" />
        <div className="pointer-events-none absolute right-[8%] top-28 h-48 w-48 rounded-full bg-moss/10 blur-3xl dark:bg-moss/15" />
        <div className="pointer-events-none absolute left-[12%] top-44 h-36 w-36 rounded-full bg-copper/10 blur-3xl dark:bg-copper/10" />
        <div className="relative mx-auto w-full max-w-6xl space-y-16 p-6 md:p-12 lg:p-16">
          <Header
            t={t}
            theme={theme}
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

          <div className="space-y-12">
            <SearchSection
              t={t}
              queryInput={filters.queryInput}
              setQueryInput={filters.setQueryInput}
              setQuery={filters.setQuery}
              shownCount={summary.shownCount}
              activeFilterCount={filters.activeFilterCount}
              sortMode={filters.sortMode}
              setSortMode={filters.setSortMode}
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
