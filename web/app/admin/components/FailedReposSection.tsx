"use client";

import { useCallback, useEffect, useState } from "react";
import { buildAdminHeaders } from "../../lib/admin";
import { API_BASE_URL } from "../../lib/apiBase";
import { getErrorMessage, readApiError } from "../../lib/apiError";
import type { TFunction } from "../../lib/i18n";

type FailedRepo = {
  full_name: string;
  name: string;
  owner: string;
  description: string | null;
  language: string | null;
  classify_fail_count: number;
};

type Props = {
  t: TFunction;
  setMessage: (msg: string | null) => void;
};

export default function FailedReposSection({ t, setMessage }: Props) {
  const [failedRepos, setFailedRepos] = useState<FailedRepo[]>([]);
  const [failedTotal, setFailedTotal] = useState(0);
  const [showFailedRepos, setShowFailedRepos] = useState(false);
  const [loadingFailedRepos, setLoadingFailedRepos] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const loadFailedRepos = useCallback(async () => {
    setLoadingFailedRepos(true);
    setLocalError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/repos/failed`, {
        headers: buildAdminHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        setFailedRepos(data.items ?? []);
        setFailedTotal(Number(data.total ?? (data.items?.length ?? 0)));
      } else {
        setLocalError(t("loadFailedReposError"));
      }
    } catch {
      setLocalError(t("loadFailedReposError"));
    } finally {
      setLoadingFailedRepos(false);
    }
  }, [t]);

  const handleResetFailed = async () => {
    setMessage(null);
    try {
      const res = await fetch(`${API_BASE_URL}/repos/failed/reset`, {
        method: "POST",
        headers: buildAdminHeaders(),
      });
      if (!res.ok) {
        const detail = await readApiError(res, t("unknownError"));
        throw new Error(detail);
      }
      const data = await res.json();
      setMessage(t("resetFailedWithValue", { count: data.reset_count ?? 0 }));
      await loadFailedRepos();
    } catch (err) {
      setMessage(getErrorMessage(err, t("unknownError")));
    }
  };

  useEffect(() => {
    if (showFailedRepos || failedTotal === 0) {
      loadFailedRepos();
    }
  }, [showFailedRepos, failedTotal, loadFailedRepos]);

  return (
    <div className="admin-section">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <h2 className="panel-title">{t("failedRepos")}</h2>
          <p className="text-sm text-ink/60">
            {t("failedReposWithValue", { count: failedTotal })}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setShowFailedRepos(!showFailedRepos)}
            className="rounded-full btn-ios-secondary px-4 py-2 text-xs font-semibold text-ink"
          >
            {showFailedRepos ? t("hide") : t("show")}
          </button>
          <button
            type="button"
            onClick={handleResetFailed}
            className="rounded-full btn-ios-secondary px-4 py-2 text-xs font-semibold text-copper hover:text-copper"
          >
            {t("resetFailed")}
          </button>
        </div>
      </div>

      {showFailedRepos && (
        <div className="subtle-panel mt-5 space-y-3">
          {loadingFailedRepos ? (
            <p className="text-sm text-ink/65">{t("loadingRepos")}</p>
          ) : localError ? (
            <div className="feedback-banner feedback-banner-error">
              <span className="feedback-icon" aria-hidden="true" />
              <p className="text-sm leading-6 text-copper">{localError}</p>
            </div>
          ) : failedRepos.length === 0 ? (
            <p className="text-sm text-ink/65">{t("noFailedRepos")}</p>
          ) : (
            failedRepos.map((repo) => (
              <div
                key={repo.full_name}
                className="subtle-panel border-ink/5 bg-surface/80"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <a
                      href={`https://github.com/${repo.full_name}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm font-semibold text-ink transition hover:text-moss"
                    >
                      {repo.full_name}
                    </a>
                    {repo.description && (
                      <p className="mt-1 text-xs leading-6 text-ink/60 line-clamp-2">
                        {repo.description}
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    {repo.language && (
                      <span className="pill-muted px-3 py-1 text-[11px]">
                        {repo.language}
                      </span>
                    )}
                    <span className="pill-copper px-3 py-1 text-[11px]">
                      {t("failCountWithValue", {
                        count: repo.classify_fail_count,
                      })}
                    </span>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
