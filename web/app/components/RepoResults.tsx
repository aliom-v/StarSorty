"use client";

import RepoCard from "./RepoCard";
import type { Messages, MessageValues } from "../lib/i18n";
import type { HomeDensityMode, HomeGroupMode, HomeRepo } from "../lib/homePageTypes";

type RepoResultsProps = {
  t: (key: keyof Messages, params?: MessageValues) => string;
  repos: HomeRepo[];
  query: string;
  loading: boolean;
  hasMore: boolean;
  loadingMore: boolean;
  hasActiveFilters: boolean;
  densityMode: HomeDensityMode;
  groupMode: HomeGroupMode;
  selectedRepoNames: Set<string>;
  onToggleSelect: (repo: HomeRepo) => void;
  onSelectGroup: (repos: HomeRepo[]) => void;
  clearAllFilters: () => void;
  onLoadMore: () => void;
  onRepoClick: (repo: HomeRepo) => void;
};

const SkeletonCard = () => (
  <div className="animate-pulse-subtle space-y-4 rounded-lg border border-ink/10 bg-surface p-4">
    <div className="flex items-start justify-between gap-6">
      <div className="flex-1 space-y-3">
        <div className="h-4 w-40 rounded bg-ink/10" />
        <div className="h-6 w-1/3 rounded bg-ink/10" />
        <div className="space-y-2">
          <div className="h-3.5 w-full rounded bg-ink/10" />
          <div className="h-3.5 w-2/3 rounded bg-ink/10" />
        </div>
      </div>
      <div className="h-9 w-24 shrink-0 rounded-md bg-ink/10" />
    </div>
    <div className="flex gap-2">
      <div className="h-6 w-20 rounded-md bg-ink/10" />
      <div className="h-6 w-24 rounded-md bg-ink/10" />
    </div>
  </div>
);

const onboardingSteps = [
  {
    key: "github",
    label: "onboardingGithub",
    description: "onboardingGithubDesc",
  },
  {
    key: "sync",
    label: "onboardingSync",
    description: "onboardingSyncDesc",
  },
  {
    key: "classify",
    label: "onboardingClassify",
    description: "onboardingClassifyDesc",
  },
] as const;

const RepoResults = ({
  t,
  repos,
  query,
  loading,
  hasMore,
  loadingMore,
  hasActiveFilters,
  densityMode,
  groupMode,
  selectedRepoNames,
  onToggleSelect,
  onSelectGroup,
  clearAllFilters,
  onLoadMore,
  onRepoClick,
}: RepoResultsProps) => {
  return (
    <div className="space-y-3 pb-20">
      {loading && repos.length === 0 && (
        <div className="grid grid-cols-1 gap-3">
          {[...Array(5)].map((_, index) => (
            <SkeletonCard key={index} />
          ))}
        </div>
      )}

      {repos.length === 0 && !loading && (
        <div className="panel-muted animate-fade-in overflow-hidden">
          {hasActiveFilters ? (
            <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
              <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-lg border border-ink/10 bg-surface text-ink/25">
                <svg className="h-7 w-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                  />
                </svg>
              </div>
              <h3 className="mb-2 font-display text-xl font-semibold tracking-normal text-ink">
                {t("noReposForFilters")}
              </h3>
              <p className="mx-auto mb-5 max-w-sm text-sm font-medium leading-6 text-subtle">
                {t("noReposForFiltersHint")}
              </p>
              <button
                type="button"
                className="btn-ios-primary h-9 px-4 text-xs font-semibold"
                onClick={clearAllFilters}
              >
                {t("clearFilters")}
              </button>
            </div>
          ) : (
            <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_22rem]">
              <div className="px-5 py-6 md:px-6 md:py-7">
                <div className="flex items-start gap-4">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-moss/10 text-moss">
                    <svg className="h-[1.375rem] w-[1.375rem]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7h16M4 12h10M4 17h7" />
                    </svg>
                  </div>
                  <div className="min-w-0">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-moss/70">
                      {t("onboardingKicker")}
                    </p>
                    <h3 className="mt-2 font-display text-2xl font-semibold leading-tight text-ink">
                      {t("onboardingTitle")}
                    </h3>
                    <p className="mt-2 max-w-2xl text-sm font-medium leading-6 text-soft">
                      {t("onboardingDesc")}
                    </p>
                  </div>
                </div>

                <div className="mt-6 grid gap-3">
                  {onboardingSteps.map((step, index) => (
                    <div key={step.key} className="flex gap-3 rounded-lg bg-surface p-3">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-ink text-xs font-semibold text-surface">
                        {index + 1}
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-ink">
                          {t(step.label)}
                        </p>
                        <p className="mt-1 text-sm font-medium leading-6 text-subtle">
                          {t(step.description)}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="border-t border-ink/10 bg-surface px-5 py-5 lg:border-l lg:border-t-0">
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink/45">
                  {t("nextActions")}
                </p>
                <div className="mt-4 grid gap-2">
                  <a
                    href="/settings/"
                    className="flex items-center justify-between rounded-lg bg-surface-muted px-3 py-3 text-sm font-semibold text-ink transition hover:bg-moss/10 hover:text-moss"
                  >
                    <span>{t("viewSettings")}</span>
                    <span className="text-ink/35">→</span>
                  </a>
                  <a
                    href="/admin/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-between rounded-lg bg-moss px-3 py-3 text-sm font-semibold text-white transition hover:bg-moss/90"
                  >
                    <span>{t("goToAdmin")}</span>
                    <span className="text-white/70">→</span>
                  </a>
                </div>
                <p className="mt-4 text-xs font-medium leading-5 text-subtle">
                  {t("onboardingNote")}
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {(() => {
        const groups = repos.reduce<Record<string, HomeRepo[]>>((acc, repo) => {
          const key =
            groupMode === "category"
              ? repo.category || t("unknown")
              : groupMode === "language"
                ? repo.language || t("unknown")
                : "";
          if (!acc[key]) acc[key] = [];
          acc[key].push(repo);
          return acc;
        }, {});
        const entries = groupMode === "none" ? [["", repos] as const] : Object.entries(groups);

        return (
          <div className="space-y-4">
            {entries.map(([groupName, groupRepos]) => (
              <section key={groupName || "all"} className="space-y-2">
                {groupMode !== "none" && (
                  <div className="flex items-center justify-between rounded-lg border border-ink/10 bg-surface-muted px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span className="section-kicker">{groupName}</span>
                      <span className="pill-muted">{groupRepos.length}</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => onSelectGroup(groupRepos)}
                      className="h-7 rounded-md px-2 text-[11px] font-semibold text-moss transition hover:bg-moss/10"
                    >
                      {t("selectGroup")}
                    </button>
                  </div>
                )}
                <div className="grid grid-cols-1 gap-3">
                  {groupRepos.map((repo, index) => (
                    <RepoCard
                      key={repo.full_name}
                      repo={repo}
                      index={index}
                      queryActive={!!query}
                      density={densityMode}
                      selected={selectedRepoNames.has(repo.full_name)}
                      onToggleSelect={onToggleSelect}
                      onRepoClick={onRepoClick}
                      t={t}
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>
        );
      })()}

      {hasMore && (
        <div className="flex justify-center pt-5">
          <button
            type="button"
            onClick={onLoadMore}
            disabled={loading || loadingMore}
            className={`glass flex h-10 items-center gap-3 rounded-md px-5 text-xs font-semibold text-ink transition-all ${
              loading || loadingMore
                ? "cursor-not-allowed opacity-60"
                : "hover:border-moss/25 hover:bg-moss/10 hover:text-moss active:translate-y-px"
            }`}
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
