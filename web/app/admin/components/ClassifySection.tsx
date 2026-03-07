"use client";

import { useCallback, useEffect, useState } from "react";
import { buildAdminHeaders } from "../../lib/admin";
import { API_BASE_URL } from "../../lib/apiBase";
import { getErrorMessage, readApiError } from "../../lib/apiError";
import type { TFunction } from "../../lib/i18n";

type Stats = {
  total: number;
  unclassified: number;
};

type BackgroundStatus = {
  running: boolean;
  processed: number;
  failed: number;
  remaining: number;
  batch_size: number;
  concurrency: number;
  task_id?: string | null;
  last_error?: string | null;
};

type TaskQueued = {
  task_id?: string;
  status?: string;
  message?: string | null;
};

type ClassifyResult = {
  classified?: number;
  total?: number;
  failed?: number;
};

type Props = {
  t: TFunction;
  setMessage: (msg: string | null) => void;
};

export default function ClassifySection({ t, setMessage }: Props) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [statsError, setStatsError] = useState(false);
  const [statusError, setStatusError] = useState(false);
  const [classifying, setClassifying] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [classifyLimit, setClassifyLimit] = useState("20");
  const [concurrency, setConcurrency] = useState("3");
  const [forceReclassify, setForceReclassify] = useState(false);
  const [backgroundStatus, setBackgroundStatus] = useState<BackgroundStatus | null>(
    null,
  );

  const loadStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/stats`);
      if (res.ok) {
        const data = await res.json();
        setStats({ total: data.total ?? 0, unclassified: data.unclassified ?? 0 });
        setStatsError(false);
      } else {
        setStatsError(true);
      }
    } catch {
      setStatsError(true);
    }
  }, []);

  const loadBackgroundStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/classify/status`);
      if (res.ok) {
        const data = await res.json();
        setBackgroundStatus(data);
        setStatusError(false);
      } else {
        setStatusError(true);
      }
    } catch {
      setStatusError(true);
    }
  }, []);

  useEffect(() => {
    loadStats();
    loadBackgroundStatus();
  }, [loadStats, loadBackgroundStatus]);

  useEffect(() => {
    const interval = setInterval(() => {
      loadBackgroundStatus();
      loadStats();
    }, 5000);
    return () => clearInterval(interval);
  }, [loadBackgroundStatus, loadStats]);

  const parseClassifyLimit = () => {
    const parsed = Number.parseInt(classifyLimit, 10);
    if (Number.isNaN(parsed)) return 20;
    return Math.max(1, Math.min(500, parsed));
  };

  const parseConcurrency = () => {
    const parsed = Number.parseInt(concurrency, 10);
    if (Number.isNaN(parsed)) return 3;
    return Math.max(1, Math.min(10, parsed));
  };

  const handleClassify = async (limit?: number) => {
    if (backgroundRunning) return;
    setClassifying(true);
    setMessage(null);
    try {
      const payload: { limit?: number; force?: boolean } = {};
      if (typeof limit === "number") {
        payload.limit = limit;
      }
      if (forceReclassify) {
        payload.force = true;
      }
      const res = await fetch(`${API_BASE_URL}/classify`, {
        method: "POST",
        headers: buildAdminHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const detail = await readApiError(res, t("classifyFailed"));
        throw new Error(detail);
      }
      const data = (await res.json()) as TaskQueued | ClassifyResult;
      if (data && typeof data === "object" && "task_id" in data && data.task_id) {
        setMessage(t("classifyQueued"));
      } else {
        const result = data as ClassifyResult;
        const classified =
          typeof result.classified === "number" ? result.classified : 0;
        const total = typeof result.total === "number" ? result.total : 0;
        const failed = typeof result.failed === "number" ? result.failed : 0;
        setMessage(t("classifiedWithValue", { classified, total, failed }));
      }
      await loadStats();
    } catch (err) {
      setMessage(getErrorMessage(err, t("classifyFailed")));
    } finally {
      setClassifying(false);
    }
  };

  const handleClassifyBatch = () => handleClassify(parseClassifyLimit());
  const handleClassifyAll = () => handleClassify(0);

  const handleBackgroundStart = async () => {
    if (classifying || backgroundRunning) return;
    setMessage(null);
    try {
      const payload: { limit?: number; force?: boolean; concurrency?: number } = {
        limit: parseClassifyLimit(),
        concurrency: parseConcurrency(),
      };
      if (forceReclassify) {
        payload.force = true;
      }
      const res = await fetch(`${API_BASE_URL}/classify/background`, {
        method: "POST",
        headers: buildAdminHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const detail = await readApiError(res, t("classifyFailed"));
        throw new Error(detail);
      }
      await loadBackgroundStatus();
      setMessage(t("backgroundClassify"));
    } catch (err) {
      setMessage(getErrorMessage(err, t("classifyFailed")));
    }
  };

  const handleBackgroundStop = async () => {
    if (!backgroundRunning) return;
    setMessage(null);
    try {
      const res = await fetch(`${API_BASE_URL}/classify/stop`, {
        method: "POST",
        headers: buildAdminHeaders(),
      });
      if (!res.ok) {
        const detail = await readApiError(res, t("classifyFailed"));
        throw new Error(detail);
      }
      await loadBackgroundStatus();
      setMessage(t("stopped"));
    } catch (err) {
      setMessage(getErrorMessage(err, t("classifyFailed")));
    }
  };

  const backgroundRunning = backgroundStatus?.running ?? false;
  const simpleStatus = backgroundRunning ? t("classifying") : t("backgroundIdle");
  const disableBackgroundToggle = classifying;
  const disableForegroundClassify = classifying || backgroundRunning;

  return (
    <div className="admin-section">
      <div className="panel-header flex-wrap items-start">
        <div className="space-y-3">
          <h2 className="panel-title">{t("classifyOperations")}</h2>
          {statsError ? (
            <div className="feedback-banner feedback-banner-error max-w-md">
              <span className="feedback-icon" aria-hidden="true" />
              <p className="text-sm leading-6 text-copper">{t("loadStatsError")}</p>
            </div>
          ) : stats ? (
            <div className="flex flex-wrap gap-2">
              <span className="pill-accent px-3 py-1 text-[11px]">
                {t("unclassifiedWithValue", { count: stats.unclassified })}
              </span>
              <span className="pill-muted px-3 py-1 text-[11px]">
                {t("totalWithValue", { count: stats.total })}
              </span>
            </div>
          ) : null}
        </div>
        <button
          type="button"
          className="rounded-full btn-ios-secondary px-3 py-1.5 text-xs font-semibold tracking-[0.08em]"
          onClick={() => setShowAdvanced((prev) => !prev)}
        >
          {showAdvanced ? t("hide") : t("advancedDetails")}
        </button>
      </div>

      <div className="subtle-panel mt-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="info-label">{t("operationStatusWithValue", { value: simpleStatus })}</span>
          <span
            className={`${backgroundRunning ? "pill-accent text-moss" : "pill-muted text-ink/65"} px-3 py-1 text-[11px]`}
          >
            {simpleStatus}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="pill-muted px-3 py-1 text-[11px]">
            {t("batchSize")}: {parseClassifyLimit()}
          </span>
          <span className="pill-muted px-3 py-1 text-[11px]">
            {t("concurrency")}: {parseConcurrency()}
          </span>
        </div>
      </div>

      {showAdvanced && statusError ? (
        <div className="feedback-banner feedback-banner-error mt-4">
          <span className="feedback-icon" aria-hidden="true" />
          <p className="text-xs leading-6 text-copper">{t("loadStatusError")}</p>
        </div>
      ) : showAdvanced && backgroundStatus ? (
        <div className="subtle-panel mt-4">
          <p className="info-label">{t("backgroundStatus")}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="pill-muted px-3 py-1 text-[11px]">
              {backgroundRunning ? t("backgroundRunning") : t("backgroundIdle")}
            </span>
            <span className="pill-muted px-3 py-1 text-[11px]">
              {t("processedWithValue", { count: backgroundStatus.processed })}
            </span>
            <span className="pill-copper px-3 py-1 text-[11px]">
              {t("failedWithValue", { count: backgroundStatus.failed })}
            </span>
            <span className="pill-muted px-3 py-1 text-[11px]">
              {t("remainingWithValue", { count: backgroundStatus.remaining })}
            </span>
            <span className="pill-muted px-3 py-1 text-[11px]">
              {t("batchSize")}: {backgroundStatus.batch_size}
            </span>
            <span className="pill-muted px-3 py-1 text-[11px]">
              {t("concurrency")}: {backgroundStatus.concurrency}
            </span>
          </div>
          {backgroundStatus.last_error &&
            backgroundStatus.last_error !== "Stopped by user" && (
              <div className="feedback-banner feedback-banner-error mt-3">
                <span className="feedback-icon" aria-hidden="true" />
                <p className="text-xs leading-6 text-copper">
                  {backgroundStatus.last_error}
                </p>
              </div>
            )}
        </div>
      ) : null}

      {showAdvanced && (
        <div className="mt-4 flex flex-wrap items-center gap-4">
          <div className="pill-muted gap-2 px-3 py-2 text-xs">
            <span>{t("batchSize")}</span>
            <input
              type="number"
              min={1}
              max={500}
              value={classifyLimit}
              onChange={(e) => {
                const value = e.target.value;
                if (/^\d*$/.test(value)) {
                  setClassifyLimit(value);
                }
              }}
              className="w-14 bg-transparent text-right text-ink outline-none"
            />
          </div>
          <div className="pill-muted gap-2 px-3 py-2 text-xs">
            <span>{t("concurrency")}</span>
            <input
              type="number"
              min={1}
              max={10}
              value={concurrency}
              onChange={(e) => {
                const value = e.target.value;
                if (/^\d*$/.test(value)) {
                  setConcurrency(value);
                }
              }}
              className="w-12 bg-transparent text-right text-ink outline-none"
            />
          </div>
          <label className="pill-muted gap-2 px-3 py-2 text-xs">
            <input
              type="checkbox"
              checked={forceReclassify}
              onChange={(e) => setForceReclassify(e.target.checked)}
              className="accent-moss"
            />
            <span>{t("forceReclassify")}</span>
          </label>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={backgroundRunning ? handleBackgroundStop : handleBackgroundStart}
          disabled={disableBackgroundToggle}
          className={`rounded-full px-5 py-2.5 text-sm font-semibold disabled:opacity-60 ${
            backgroundRunning
              ? "btn-ios-secondary text-copper"
              : "btn-ios-moss text-white"
          }`}
        >
          {backgroundRunning ? t("stop") : t("classify")}
        </button>
        <button
          type="button"
          onClick={handleClassifyAll}
          disabled={disableForegroundClassify}
          className="rounded-full btn-ios-secondary px-5 py-2.5 text-sm font-semibold disabled:opacity-60"
        >
          {t("classifyAll")}
        </button>
        {showAdvanced && (
          <button
            type="button"
            onClick={handleClassifyBatch}
            disabled={disableForegroundClassify}
            className="rounded-full btn-ios-secondary px-5 py-2.5 text-sm font-semibold disabled:opacity-60"
          >
            {classifying ? t("classifying") : t("classifyNext")}
          </button>
        )}
      </div>
    </div>
  );
}
