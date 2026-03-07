"use client";

import type { Messages, MessageValues } from "../lib/i18n";

type HeaderProps = {
  t: (key: keyof Messages, params?: MessageValues) => string;
  theme: string;
  totalRepos: number;
  shownCount: number;
  activeFilterCount: number;
  toggleTheme: () => void;
  lastSyncLabel: string;
  syncing: boolean;
  backgroundRunning: boolean;
  disableSyncAction: boolean;
  disableClassifyAction: boolean;
  handleSync: () => void;
  handleBackgroundStart: () => void;
  handleBackgroundStop: () => void;
};

const Header = ({
  t,
  theme,
  totalRepos,
  shownCount,
  activeFilterCount,
  toggleTheme,
  lastSyncLabel,
  syncing,
  backgroundRunning,
  disableSyncAction,
  disableClassifyAction,
  handleSync,
  handleBackgroundStart,
  handleBackgroundStop,
}: HeaderProps) => {
  const heroStats = [
    t("totalWithValue", { count: totalRepos }),
    t("showingWithValue", { count: shownCount }),
    t("filtersWithValue", { count: activeFilterCount }),
  ];

  return (
    <header className="animate-fade-in flex flex-col gap-5 py-1 md:flex-row md:items-end md:justify-between md:gap-7">
      <div className="hero-surface soft-elevated relative max-w-3xl overflow-hidden rounded-[2.5rem] p-6 md:p-9">
        <div className="hero-orb hero-orb-moss" />
        <div className="hero-orb hero-orb-copper" />
        <div className="relative space-y-5">
          <div className="flex items-center gap-3">
            <div className="flex -space-x-1">
              <span className="h-3 w-3 rounded-full bg-copper shadow-[0_0_10px_rgba(184,102,43,0.5)]" />
              <span className="h-3 w-3 rounded-full bg-moss shadow-[0_0_10px_rgba(47,93,80,0.5)]" />
            </div>
            <p className="section-kicker text-copper/80">StarSorty</p>
          </div>

          <div className="space-y-3">
            <h1 className="section-title text-[2.6rem] font-black leading-[0.94] tracking-tighter sm:text-5xl lg:text-[3.7rem]">
              {t("title")}
              <span className="text-moss">.</span>
            </h1>
            <p className="max-w-2xl text-[15px] font-semibold leading-7 text-soft text-balance md:text-lg md:leading-8">
              {t("subtitle")}
            </p>
          </div>

          <div className="flex flex-wrap gap-2.5 pt-2 md:gap-3 md:pt-3">
            {heroStats.map((stat) => (
              <span key={stat} className="hero-metric">
                {stat}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="flex w-full max-w-xl flex-col gap-3 md:gap-3.5 md:items-end">
        <div className="flex w-full flex-wrap items-center gap-3 md:justify-end">
          <div className="flex w-full items-center justify-center gap-3 rounded-full border border-ink/5 bg-surface/70 px-4 py-2.5 text-[11px] font-semibold text-subtle shadow-soft sm:w-auto sm:justify-start">
            <span className="relative flex h-2 w-2">
              {(backgroundRunning || syncing) && (
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-moss opacity-75" />
              )}
              <span
                className={`relative inline-flex h-2 w-2 rounded-full ${
                  backgroundRunning || syncing ? "bg-moss" : "bg-ink/10"
                }`}
              />
            </span>
            <span className="truncate">
              {t("lastSyncWithValue", { value: lastSyncLabel })}
            </span>
          </div>
          <button
            type="button"
            onClick={toggleTheme}
            className="icon-button shrink-0"
            aria-label={t("theme")}
          >
            {theme === "dark" ? (
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707m12.728 0l-.707-.707M6.343 6.343l-.707-.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
            ) : (
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
              </svg>
            )}
          </button>
        </div>

        <div className="flex w-full flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center md:justify-end">
          <button
            type="button"
            onClick={handleSync}
            disabled={disableSyncAction}
            className="rounded-full btn-ios-primary px-5 py-3 text-xs font-semibold tracking-[0.08em] disabled:opacity-30 sm:flex-1 sm:px-6 sm:py-3.5 md:flex-none"
          >
            {syncing ? (
              <span className="flex items-center justify-center gap-3">
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                {t("syncing")}
              </span>
            ) : (
              t("syncNow")
            )}
          </button>
          <button
            type="button"
            onClick={backgroundRunning ? handleBackgroundStop : handleBackgroundStart}
            disabled={disableClassifyAction}
            className="rounded-full btn-ios-secondary px-5 py-3 text-xs font-semibold tracking-[0.08em] disabled:opacity-30 sm:flex-1 sm:px-6 sm:py-3.5 md:flex-none"
          >
            {backgroundRunning ? t("stop") : t("classify")}
          </button>
          <div className="hidden h-9 w-px bg-ink/5 sm:block" />
          <div className="flex items-center gap-2 self-end sm:self-auto">
            <a href="/settings/" className="icon-button" title={t("settings")}>
              <svg className="h-5.5 w-5.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </a>
            <a
              href="/admin/"
              target="_blank"
              rel="noopener noreferrer"
              className="icon-button hover:text-copper"
              title={t("admin")}
            >
              <svg className="h-5.5 w-5.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </a>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
