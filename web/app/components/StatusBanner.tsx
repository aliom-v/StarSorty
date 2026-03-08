"use client";

import type { Messages, MessageValues } from "../lib/i18n";
import type { HomeActionStatus } from "../lib/homePageTypes";

type StatusBannerProps = {
  t: (key: keyof Messages, params?: MessageValues) => string;
  actionMessage: string | null;
  actionStatus: HomeActionStatus;
  pollingPaused: boolean;
  handleResumePolling: () => void;
  dismissAction: () => void;
  simpleOperationStatus: string;
  backgroundRunning: boolean;
  backgroundProcessed: number;
  backgroundRemaining: number;
};

const StatusBanner = ({
  t,
  actionMessage,
  actionStatus,
  pollingPaused,
  handleResumePolling,
  dismissAction,
  simpleOperationStatus,
  backgroundRunning,
  backgroundProcessed,
  backgroundRemaining,
}: StatusBannerProps) => {
  const isVisible = !!actionMessage || backgroundRunning || pollingPaused;

  return (
    <div className="pointer-events-none fixed left-1/2 top-4 z-[100] w-full max-w-md -translate-x-1/2 px-4 md:top-8">
      <div
        className={`pointer-events-auto mx-auto rounded-[2rem] glass shadow-premium transition-all duration-700 [transition-timing-function:cubic-bezier(0.16,1,0.3,1)] border-ink/5 ${
          isVisible
            ? "translate-y-0 scale-100 opacity-100"
            : "-translate-y-16 scale-95 opacity-0"
        }`}
      >
        <div className="flex items-start justify-between gap-4 px-4 py-3.5 sm:px-5 sm:py-4">
          <div className="flex min-w-0 items-start gap-3.5">
            {backgroundRunning ? (
              <div className="relative mt-1 flex h-3 w-3 shrink-0">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-moss opacity-75" />
                <span className="relative inline-flex h-3 w-3 rounded-full bg-moss" />
              </div>
            ) : (
              <div
                className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${
                  actionStatus === "error"
                    ? "bg-copper shadow-[0_0_10px_rgba(184,102,43,0.5)]"
                    : "bg-moss shadow-[0_0_10px_rgba(47,93,80,0.5)]"
                }`}
              />
            )}

            <div className="min-w-0">
              <p className="truncate text-[11px] font-black uppercase tracking-[0.15em] text-ink/85">
                {actionMessage || simpleOperationStatus}
              </p>
              {backgroundRunning && (
                <p className="mt-1 text-[10px] font-semibold leading-5 text-ink/45">
                  {t("processedWithValue", { count: backgroundProcessed })}
                  <span className="mx-1.5 text-ink/20">·</span>
                  {t("remainingWithValue", { count: backgroundRemaining })}
                </p>
              )}
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {pollingPaused && (
              <button
                onClick={handleResumePolling}
                className="rounded-full btn-ios-secondary px-3 py-1.5 text-[10px] font-semibold tracking-[0.1em] text-copper"
              >
                {t("reconnect")}
              </button>
            )}

            {(actionMessage || !backgroundRunning) && (
              <button
                onClick={dismissAction}
                className="flex h-8 w-8 items-center justify-center rounded-full text-ink/30 transition-colors hover:bg-ink/5 hover:text-ink/55"
                aria-label={t("dismiss")}
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default StatusBanner;
