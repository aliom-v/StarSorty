"use client";

import type { Messages, MessageValues } from "../lib/i18n";
import type { HomeSortMode } from "../lib/homePageTypes";

type SearchSectionProps = {
  t: (key: keyof Messages, params?: MessageValues) => string;
  query: string;
  queryInput: string;
  setQueryInput: (value: string) => void;
  submitSearch: () => void;
  clearSearch: () => void;
  searchDirty: boolean;
  shownCount: number;
  activeFilterCount: number;
  sortMode: HomeSortMode;
  setSortMode: (mode: HomeSortMode) => void;
  activeError: string | null;
  loading: boolean;
  hasActiveFilters: boolean;
  clearAllFilters: () => void;
  onOpenFilters: () => void;
};

const sortLabelKeys: Record<SearchSectionProps["sortMode"], keyof Messages> = {
  stars: "sortStars",
  updated: "sortUpdated",
  relevance: "sortRelevance",
};

const getConfigHintKey = (message: string): keyof Messages => {
  if (message.includes("AI_PROVIDER")) return "configHintAiProvider";
  if (message.includes("GitHub") || message.includes("github")) {
    return "configHintGithub";
  }
  return "configHintGeneric";
};

const SearchSection = ({
  t,
  query,
  queryInput,
  setQueryInput,
  submitSearch,
  clearSearch,
  searchDirty,
  shownCount,
  activeFilterCount,
  sortMode,
  setSortMode,
  activeError,
  loading,
  hasActiveFilters,
  clearAllFilters,
  onOpenFilters,
}: SearchSectionProps) => {
  const disableSearchAction = loading || !searchDirty;
  const disableRelevanceSort = !query;

  return (
    <div className="animate-fade-up sticky top-0 z-30 -mx-4 border-y border-ink/10 bg-sand/95 px-4 py-3 backdrop-blur md:-mx-6 md:px-6 lg:-mx-8 lg:px-8">
      <div className="mx-auto flex w-full max-w-[118rem] flex-col gap-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <form
            className="relative min-w-0 flex-1"
            onSubmit={(event) => {
              event.preventDefault();
              submitSearch();
            }}
          >
            <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-ink/35">
              <svg className="h-[1.125rem] w-[1.125rem]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <input
              id="search-input"
              className="h-11 w-full rounded-lg border border-ink/10 bg-surface pl-10 pr-32 text-sm font-medium text-ink shadow-sm outline-none transition focus:border-moss/45 focus:ring-2 focus:ring-moss/10 sm:pr-48"
              placeholder={t("searchPlaceholder")}
              value={queryInput}
              onChange={(event) => setQueryInput(event.target.value)}
            />
            <div className="absolute inset-y-1 right-1 flex items-center gap-1.5">
              {!queryInput && (
                <div className="hidden select-none items-center gap-1 rounded-md border border-ink/10 bg-surface-muted px-2 py-1 text-[10px] font-semibold text-ink/40 sm:flex">
                  <span>⌘</span>
                  <span>K</span>
                </div>
              )}
              {queryInput && (
                <button
                  type="button"
                  className="hidden h-8 rounded-md px-2 text-[11px] font-semibold text-ink/52 transition hover:bg-ink/5 hover:text-ink sm:block"
                  onClick={clearSearch}
                >
                  {t("clear")}
                </button>
              )}
              <button
                type="submit"
                disabled={disableSearchAction}
                className="btn-ios-moss h-9 px-3 text-xs font-semibold"
              >
                {t("search")}
              </button>
            </div>
          </form>

          <div className="flex flex-wrap items-center gap-2 xl:justify-end">
            <span className="pill-muted h-8">{t("showingWithValue", { count: shownCount })}</span>
            {hasActiveFilters && (
              <span className="pill-accent h-8">
                {t("filtersWithValue", { count: activeFilterCount })}
              </span>
            )}
            <button
              type="button"
              className="btn-ios-secondary h-8 gap-2 px-3 text-xs font-semibold md:hidden"
              onClick={onOpenFilters}
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4h18M6 12h12m-9 8h6" />
              </svg>
              {t("filters")}
            </button>
            <div className="flex items-center gap-2">
              <span className="hidden text-[10px] font-semibold uppercase tracking-[0.12em] text-ink/40 sm:inline">
                {t("sortBy")}
              </span>
              <div className="flex rounded-lg border border-ink/10 bg-surface-muted p-1">
                {(["stars", "updated", "relevance"] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    disabled={mode === "relevance" && disableRelevanceSort}
                    className={`rounded-md px-2.5 py-1.5 text-[11px] font-semibold transition ${
                      sortMode === mode
                        ? "bg-surface text-ink shadow-sm"
                        : "text-ink/50 hover:bg-surface/70 hover:text-ink"
                    } ${
                      mode === "relevance" && disableRelevanceSort
                        ? "cursor-not-allowed opacity-40 hover:bg-transparent hover:text-ink/50"
                        : ""
                    }`}
                    onClick={() => setSortMode(mode)}
                  >
                    {t(sortLabelKeys[mode])}
                  </button>
                ))}
              </div>
            </div>
            {hasActiveFilters && (
              <button
                type="button"
                className="h-8 rounded-md px-2 text-[11px] font-semibold text-copper transition hover:bg-copper/10 hover:text-copper"
                onClick={clearAllFilters}
              >
                {t("clearFilters")}
              </button>
            )}
          </div>
        </div>

        {activeError && (
          <div className="animate-fade-in rounded-lg border border-copper/20 bg-copper/10 p-4 text-copper">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="flex min-w-0 gap-3">
                <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-sm bg-copper" />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-copper">
                    {t("configNeedsAttention")}
                  </p>
                  <p className="mt-1 text-sm font-medium leading-6 text-copper/85">
                    {t(getConfigHintKey(activeError))}
                  </p>
                  <code className="mt-3 block overflow-x-auto rounded-md bg-copper/10 px-3 py-2 text-xs font-semibold leading-5 text-copper">
                    {activeError}
                  </code>
                </div>
              </div>

              <div className="flex shrink-0 flex-wrap gap-2 lg:justify-end">
                <a
                  href="/settings/"
                  className="inline-flex h-8 items-center rounded-md bg-surface px-3 text-xs font-semibold text-copper shadow-sm transition hover:bg-copper/10"
                >
                  {t("viewSettings")}
                </a>
                <a
                  href="/admin/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex h-8 items-center rounded-md bg-copper px-3 text-xs font-semibold text-white shadow-sm transition hover:bg-copper/90"
                >
                  {t("goToAdmin")}
                </a>
              </div>
            </div>
          </div>
        )}

        {loading && !activeError && (
          <div className="h-1 w-full overflow-hidden rounded-full bg-ink/[0.06]">
            <div className="animate-loading-bar h-full rounded-full bg-moss/55" />
          </div>
        )}
      </div>
    </div>
  );
};

export default SearchSection;
