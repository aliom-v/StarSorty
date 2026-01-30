"use client";

import { useCallback, useEffect, useState } from "react";
import { buildAdminHeaders } from "../../lib/admin";
import { API_BASE_URL } from "../../lib/apiBase";
import { getErrorMessage, readApiError } from "../../lib/apiError";

type FailedRepo = {
  full_name: string;
  name: string;
  owner: string;
  description: string | null;
  language: string | null;
  classify_fail_count: number;
};

type Props = {
  t: (key: string, params?: Record<string, unknown>) => string;
  setMessage: (msg: string | null) => void;
};

export default function FailedReposSection({ t, setMessage }: Props) {
  const [failedRepos, setFailedRepos] = useState<FailedRepo[]>([]);
  const [showFailedRepos, setShowFailedRepos] = useState(false);

  const loadFailedRepos = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/repos/failed`);
      if (res.ok) {
        const data = await res.json();
        setFailedRepos(data.items ?? []);
      } else {
        setMessage(t("loadFailedReposError"));
      }
    } catch {
      setMessage(t("loadFailedReposError"));
    }
  }, [t, setMessage]);

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
    if (showFailedRepos) {
      loadFailedRepos();
    }
  }, [showFailedRepos, loadFailedRepos]);

  return (
    <div className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-lg font-semibold">{t("failedRepos")}</h2>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setShowFailedRepos(!showFailedRepos)}
            className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink"
          >
            {showFailedRepos ? t("hide") : t("show")}
          </button>
          <button
            type="button"
            onClick={handleResetFailed}
            className="rounded-full border border-ink/10 bg-surface px-4 py-2 text-xs font-semibold text-ink hover:border-copper hover:text-copper"
          >
            {t("resetFailed")}
          </button>
        </div>
      </div>
      {showFailedRepos && (
        <div className="mt-4 space-y-2">
          {failedRepos.length === 0 ? (
            <p className="text-sm text-ink/70">{t("noFailedRepos")}</p>
          ) : (
            failedRepos.map((repo) => (
              <div key={repo.full_name} className="rounded-2xl border border-ink/10 bg-surface px-4 py-3">
                <div className="flex items-center justify-between">
                  <a
                    href={`https://github.com/${repo.full_name}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm font-medium text-ink hover:text-moss"
                  >
                    {repo.full_name}
                  </a>
                  <span className="text-xs text-copper">{t("failCountWithValue", { count: repo.classify_fail_count })}</span>
                </div>
                {repo.description && (
                  <p className="mt-1 text-xs text-ink/60 line-clamp-2">{repo.description}</p>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
