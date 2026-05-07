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
    <div className="pointer-events-none fixed left-1/2 top-3 z-[100] w-full max-w-md -translate-x-1/2 px-4">
      <div
        className={`pointer-events-auto mx-auto rounded-lg border border-ink/10 bg-surface shadow-premium transition-all duration-300 ${
          isVisible
            ? "translate-y-0 scale-100 opacity-100"
            : "-translate-y-16 scale-95 opacity-0"
        }`}
      >
        <div className="flex items-start justify-between gap-4 px-4 py-3">
          <div className="flex min-w-0 items-start gap-3">
            {backgroundRunning ? (
              <div className="relative mt-1.5 flex h-2.5 w-2.5 shrink-0">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-moss opacity-75" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-sm bg-moss" />
              </div>
            ) : (
              <div
                className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-sm ${
                  actionStatus === "error"
                    ? "bg-copper"
                    : "bg-moss"
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
                className="btn-ios-secondary h-7 px-2.5 text-[10px] font-semibold text-copper"
              >
                {t("reconnect")}
              </button>
            )}

            {(actionMessage || !backgroundRunning) && (
              <button
                onClick={dismissAction}
                className="flex h-7 w-7 items-center justify-center rounded-md text-ink/35 transition-colors hover:bg-ink/5 hover:text-ink/60"
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
