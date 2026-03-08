"use client";

import type { Messages, MessageValues } from "../lib/i18n";
import type { HomeSortMode } from "../lib/homePageTypes";

type SearchSectionProps = {
  t: (key: keyof Messages, params?: MessageValues) => string;
  queryInput: string;
  setQueryInput: (value: string) => void;
  setQuery: (value: string) => void;
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

const SearchSection = ({
  t,
  queryInput,
  setQueryInput,
  setQuery,
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
  return (
    <div className="animate-fade-up sticky top-0 z-30 -mx-4 mb-5 space-y-4 border-b border-ink/5 bg-sand/70 px-4 py-4 backdrop-blur-2xl dark:border-white/5 dark:bg-sand/42 md:-mx-12 md:mb-6 md:space-y-5 md:px-12 md:py-5 lg:-mx-16 lg:px-16">
      <div className="group relative mx-auto w-full max-w-6xl">
        <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-5 text-ink/20 transition-all duration-500 group-focus-within:scale-110 group-focus-within:text-moss dark:text-ink/35 sm:pl-6">
          <svg className="h-5 w-5 sm:h-6 sm:w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <input
          id="search-input"
          className="glass h-[3.25rem] w-full rounded-[1.75rem] border-ink/5 pl-14 pr-24 text-[15px] font-medium outline-none transition-all duration-300 focus:bg-surface focus:shadow-premium focus:ring-4 focus:ring-moss/5 dark:border-white/5 dark:bg-surface/52 dark:focus:bg-surface/75 dark:focus:ring-white/5 sm:h-14 sm:pl-16 sm:pr-36 md:h-16 md:rounded-[1.9rem] md:pr-52 md:text-lg"
          placeholder={t("searchPlaceholder")}
          value={queryInput}
          onChange={(event) => setQueryInput(event.target.value)}
          onKeyDown={(e) => e.key === "Enter" && setQuery(queryInput.trim())}
        />
        <div className="absolute inset-y-1.5 right-1.5 flex items-center gap-2 sm:inset-y-2 sm:right-2 sm:gap-3">
          {!queryInput && (
            <div className="hidden select-none items-center gap-1.5 rounded-xl border border-ink/5 bg-ink/[0.03] px-3 py-1.5 text-[10px] font-black text-ink/30 dark:border-transparent dark:bg-white/[0.05] dark:text-ink/45 md:flex">
              <span className="text-[12px]">⌘</span>
              <span>K</span>
            </div>
          )}
          {queryInput && (
            <button
              type="button"
              className="hidden h-10 px-4 text-[11px] font-semibold tracking-[0.06em] text-ink/40 transition-all hover:text-ink/60 active:scale-90 dark:text-ink/50 dark:hover:text-ink/80 sm:block"
              onClick={() => {
                setQueryInput("");
                setQuery("");
              }}
            >
              {t("clear")}
            </button>
          )}
          <button
            type="button"
            className="btn-ios-moss h-10 rounded-[1.1rem] px-4 text-[11px] font-semibold tracking-[0.08em] sm:h-11 sm:rounded-[1.25rem] sm:px-5 md:px-7"
            onClick={() => setQuery(queryInput.trim())}
          >
            {t("search")}
          </button>
        </div>
      </div>

      <div className="mx-auto flex w-full max-w-6xl flex-col gap-3.5 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-wrap items-center gap-2.5 text-[11px] font-semibold text-subtle sm:gap-3">
          <span className="pill-muted">{t("showingWithValue", { count: shownCount })}</span>
          {hasActiveFilters && (
            <span className="pill-accent">
              {t("filtersWithValue", { count: activeFilterCount })}
            </span>
          )}
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-full btn-ios-secondary px-4 py-2 text-[11px] font-semibold tracking-[0.06em] text-ink/70 md:hidden"
            onClick={onOpenFilters}
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4h18M6 12h12m-9 8h6" />
            </svg>
            {t("filters")}
          </button>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center md:justify-end">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
            <span className="section-kicker px-1 sm:px-0">{t("sortBy")}</span>
            <div className="flex rounded-[1.25rem] border border-ink/5 bg-ink/[0.03] p-1.5 shadow-inner dark:border-transparent dark:bg-white/[0.05]">
              {(["stars", "updated", "relevance"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className={`rounded-xl px-3 py-2 text-[11px] font-semibold tracking-[0.06em] transition-all duration-300 sm:px-4 md:px-5 ${
                    sortMode === mode
                      ? "bg-surface text-ink shadow-soft dark:bg-white/[0.1]"
                      : "text-ink/40 hover:bg-ink/[0.02] hover:text-ink/70 dark:text-ink/55 dark:hover:bg-white/[0.04] dark:hover:text-ink/80"
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
              className="self-start px-1 text-[10px] font-semibold tracking-[0.12em] text-copper transition-all hover:text-copper/70 active:scale-95 sm:self-auto"
              onClick={clearAllFilters}
            >
              {t("clearFilters")}
            </button>
          )}
        </div>
      </div>

      {activeError && (
        <div className="mx-auto w-full max-w-6xl">
          <div className="feedback-banner feedback-banner-error animate-fade-in">
            <span className="feedback-icon" aria-hidden="true" />
            <p className="text-sm font-medium leading-6 text-copper">
              {t("apiErrorWithValue", { message: activeError })}
            </p>
          </div>
        </div>
      )}

      {loading && !activeError && (
        <div className="mx-auto h-1.5 w-full max-w-6xl overflow-hidden rounded-full bg-ink/[0.03] shadow-inner">
          <div className="animate-loading-bar h-full rounded-full bg-moss/40 shadow-[0_0_10px_rgba(47,93,80,0.3)]" />
        </div>
      )}
    </div>
  );
};

export default SearchSection;
