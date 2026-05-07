"use client";

import type { Messages, MessageValues } from "../lib/i18n";

type HeaderProps = {
  t: (key: keyof Messages, params?: MessageValues) => string;
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
  const busy = backgroundRunning || syncing;
  const metrics = [
    { label: t("total"), value: totalRepos },
    { label: t("showing"), value: shownCount },
    { label: t("filters"), value: activeFilterCount },
  ];

  return (
    <header className="animate-fade-in rounded-lg border border-ink/10 bg-surface shadow-soft">
      <div className="flex flex-col gap-4 px-4 py-4 lg:flex-row lg:items-center lg:justify-between lg:px-5">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md bg-ink px-2 py-1 font-display text-sm font-semibold leading-none text-surface">
              StarSorty
            </span>
            <span className="inline-flex items-center gap-2 rounded-md border border-ink/10 bg-surface-muted px-2.5 py-1 text-[11px] font-medium text-subtle">
              <span
                className={`h-2 w-2 rounded-sm ${
                  busy ? "bg-moss" : "bg-ink/20"
                }`}
              />
              {t("lastSyncWithValue", { value: lastSyncLabel })}
            </span>
          </div>
          <h1 className="mt-3 max-w-3xl font-display text-2xl font-semibold leading-tight text-ink sm:text-3xl">
            {t("title")}
          </h1>
          <p className="mt-1 max-w-3xl text-sm font-medium leading-6 text-soft">
            {t("subtitle")}
          </p>
        </div>

        <div className="flex flex-col gap-3 lg:items-end">
          <div className="grid grid-cols-3 gap-2 rounded-lg bg-ink/[0.025] p-1.5 dark:bg-white/[0.04]">
            {metrics.map((metric, index) => (
              <div
                key={metric.label}
                className={`min-w-[5.2rem] rounded-md px-2.5 py-2 transition-colors ${
                  index === 0
                    ? "bg-moss/10 text-moss"
                    : "text-ink/70"
                }`}
              >
                <p className={`text-[10px] font-semibold uppercase tracking-[0.12em] ${
                  index === 0 ? "text-moss/70" : "text-ink/40"
                }`}>
                  {metric.label}
                </p>
                <p className="mt-0.5 font-display text-xl font-semibold leading-none">
                  {metric.value}
                </p>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-1.5 rounded-lg bg-ink/[0.025] p-1.5 dark:bg-white/[0.04] lg:justify-end">
            <button
              type="button"
              onClick={handleSync}
              disabled={disableSyncAction}
              className="h-9 rounded-md px-3.5 text-xs font-semibold text-ink/55 transition hover:bg-surface hover:text-ink active:translate-y-px disabled:cursor-not-allowed disabled:opacity-35 dark:hover:bg-white/[0.07]"
            >
              {syncing && (
                <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
              {syncing ? t("syncing") : t("syncNow")}
            </button>
            <button
              type="button"
              onClick={backgroundRunning ? handleBackgroundStop : handleBackgroundStart}
              disabled={disableClassifyAction}
              className="h-9 rounded-md bg-moss/12 px-3.5 text-xs font-semibold text-moss transition hover:bg-moss/18 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-35"
            >
              {backgroundRunning ? t("stop") : t("classify")}
            </button>
            <button
              type="button"
              onClick={toggleTheme}
              className="flex h-9 w-9 items-center justify-center rounded-md text-ink/58 transition hover:bg-surface hover:text-moss active:translate-y-px dark:hover:bg-white/[0.07]"
              aria-label={t("theme")}
              title={t("theme")}
            >
              <svg className="h-[1.125rem] w-[1.125rem]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M12 3a9 9 0 100 18 9 9 0 000-18z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M12 3v18" />
              </svg>
            </button>
            <a
              href="/settings/"
              className="flex h-9 w-9 items-center justify-center rounded-md text-ink/58 transition hover:bg-surface hover:text-moss active:translate-y-px dark:hover:bg-white/[0.07]"
              title={t("settings")}
            >
              <svg className="h-[1.125rem] w-[1.125rem]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </a>
            <a
              href="/admin/"
              target="_blank"
              rel="noopener noreferrer"
              className="flex h-9 w-9 items-center justify-center rounded-md text-ink/58 transition hover:bg-surface hover:text-copper active:translate-y-px dark:hover:bg-white/[0.07]"
              title={t("admin")}
            >
              <svg className="h-[1.125rem] w-[1.125rem]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </a>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
