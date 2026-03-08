"use client";

import RepoCard from "./RepoCard";
import type { Messages, MessageValues } from "../lib/i18n";
import type { HomeRepo } from "../lib/homePageTypes";

type RepoResultsProps = {
  t: (key: keyof Messages, params?: MessageValues) => string;
  repos: HomeRepo[];
  query: string;
  loading: boolean;
  hasMore: boolean;
  loadingMore: boolean;
  hasActiveFilters: boolean;
  clearAllFilters: () => void;
  onLoadMore: () => void;
  onRepoClick: (repo: HomeRepo) => void;
};

const SkeletonCard = () => (
  <div className="rounded-[2.5rem] border border-ink/5 bg-surface/20 p-8 animate-pulse-subtle space-y-8">
    <div className="flex items-start justify-between gap-6">
      <div className="flex-1 space-y-4">
        <div className="h-8 w-1/3 rounded-2xl bg-ink/5" />
        <div className="space-y-2">
          <div className="h-4 w-full rounded-lg bg-ink/5" />
          <div className="h-4 w-2/3 rounded-lg bg-ink/5" />
        </div>
      </div>
      <div className="h-12 w-24 shrink-0 rounded-full bg-ink/5" />
    </div>
    <div className="flex gap-2">
      <div className="h-8 w-20 rounded-full bg-ink/5" />
      <div className="h-8 w-24 rounded-full bg-ink/5" />
    </div>
  </div>
);

const RepoResults = ({
  t,
  repos,
  query,
  loading,
  hasMore,
  loadingMore,
  hasActiveFilters,
  clearAllFilters,
  onLoadMore,
  onRepoClick,
}: RepoResultsProps) => {
  return (
    <div className="space-y-6 pb-24">
      {loading && repos.length === 0 && (
        <div className="grid grid-cols-1 gap-6">
          {[...Array(5)].map((_, index) => (
            <SkeletonCard key={index} />
          ))}
        </div>
      )}

      {repos.length === 0 && !loading && (
        <div className="panel-muted animate-fade-in flex flex-col items-center justify-center rounded-[2.5rem] px-6 py-24 text-center">
          <div className="glass mb-8 flex h-24 w-24 items-center justify-center rounded-full text-ink/10 shadow-soft">
            <svg className="h-12 w-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
          </div>
          <h3 className="mb-3 text-2xl font-black tracking-tight text-ink">
            {hasActiveFilters ? t("noReposForFilters") : t("noRepos")}
          </h3>
          <p className="mx-auto mb-8 max-w-sm font-medium text-subtle">
            {hasActiveFilters
              ? t("noReposForFiltersHint")
              : t("noReposHint")}
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
            onRepoClick={onRepoClick}
            t={t}
          />
        ))}
      </div>

      {hasMore && (
        <div className="flex justify-center pt-8">
          <button
            type="button"
            onClick={onLoadMore}
            disabled={loadingMore}
            className="group flex items-center gap-4 rounded-full glass px-12 py-5 text-xs font-black uppercase tracking-widest text-ink transition-all hover:shadow-premium active:scale-95"
          >
            {loadingMore ? (
              <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor">
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
  );
};

export default RepoResults;
