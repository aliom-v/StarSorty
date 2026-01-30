"use client";

import { useCallback, useEffect, useState } from "react";
import { buildAdminHeaders } from "../../lib/admin";
import { API_BASE_URL } from "../../lib/apiBase";
import { getErrorMessage, readApiError } from "../../lib/apiError";

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

type Props = {
  t: (key: string, params?: Record<string, unknown>) => string;
  message: string | null;
  setMessage: (msg: string | null) => void;
};

export default function ClassifySection({ t, message, setMessage }: Props) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [statsError, setStatsError] = useState(false);
  const [statusError, setStatusError] = useState(false);
  const [classifying, setClassifying] = useState(false);
  const [classifyLimit, setClassifyLimit] = useState("20");
  const [concurrency, setConcurrency] = useState("3");
  const [forceReclassify, setForceReclassify] = useState(false);
  const [backgroundStatus, setBackgroundStatus] = useState<BackgroundStatus | null>(null);

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
    const parsed = parseInt(classifyLimit, 10);
    if (Number.isNaN(parsed)) return 20;
    return Math.max(1, Math.min(500, parsed));
  };

  const parseConcurrency = () => {
    const parsed = parseInt(concurrency, 10);
    if (Number.isNaN(parsed)) return 3;
    return Math.max(1, Math.min(10, parsed));
  };

  const handleClassify = async (limit?: number) => {
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
      const data = await res.json();
      const classified = data.classified ?? 0;
      const total = data.total ?? 0;
      const failed = data.failed ?? 0;
      setMessage(t("classifiedWithValue", { classified, total, failed }));
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

  return (
    <div className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
      <h2 className="font-display text-lg font-semibold">{t("classifyOperations")}</h2>
      {statsError ? (
        <p className="mt-2 text-sm text-copper">{t("loadStatsError")}</p>
      ) : stats && (
        <p className="mt-2 text-sm text-ink/70">
          {t("unclassifiedWithValue", { count: stats.unclassified })} / {t("totalWithValue", { count: stats.total })}
        </p>
      )}

      {statusError ? (
        <div className="mt-4 rounded-2xl border border-copper/30 bg-copper/5 px-4 py-3">
          <p className="text-xs text-copper">{t("loadStatusError")}</p>
        </div>
      ) : backgroundStatus && (
        <div className="mt-4 rounded-2xl border border-ink/10 bg-surface/70 px-4 py-3">
          <p className="text-xs uppercase tracking-[0.2em] text-ink/60">{t("backgroundStatus")}</p>
          <div className="mt-2 flex flex-wrap gap-3 text-xs text-ink/70">
            <span>{backgroundRunning ? t("backgroundRunning") : t("backgroundIdle")}</span>
            <span>{t("processedWithValue", { count: backgroundStatus.processed })}</span>
            <span>{t("failedWithValue", { count: backgroundStatus.failed })}</span>
            <span>{t("remainingWithValue", { count: backgroundStatus.remaining })}</span>
            <span>{t("batchSize")}: {backgroundStatus.batch_size}</span>
            <span>{t("concurrency")}: {backgroundStatus.concurrency}</span>
          </div>
          {backgroundStatus.last_error && backgroundStatus.last_error !== "Stopped by user" && (
            <p className="mt-2 text-xs text-copper">{backgroundStatus.last_error}</p>
          )}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2 rounded-full border border-ink/10 bg-surface px-3 py-2 text-xs text-ink/70">
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
        <div className="flex items-center gap-2 rounded-full border border-ink/10 bg-surface px-3 py-2 text-xs text-ink/70">
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
        <label className="flex items-center gap-2 rounded-full border border-ink/10 bg-surface px-3 py-2 text-xs text-ink/70">
          <input
            type="checkbox"
            checked={forceReclassify}
            onChange={(e) => setForceReclassify(e.target.checked)}
            className="accent-moss"
          />
          <span>{t("forceReclassify")}</span>
        </label>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleClassifyBatch}
          disabled={classifying}
          className="rounded-full bg-moss px-5 py-2 text-sm font-semibold text-white disabled:opacity-60"
        >
          {classifying ? t("classifying") : t("backgroundClassify")}
        </button>
        <button
          type="button"
          onClick={handleClassifyAll}
          disabled={classifying}
          className="rounded-full border border-ink/10 bg-surface px-5 py-2 text-sm font-semibold text-ink disabled:opacity-60"
        >
          {t("classifyAll")}
        </button>
        <button
          type="button"
          onClick={handleBackgroundStart}
          disabled={backgroundRunning}
          className="rounded-full border border-ink/10 bg-surface px-5 py-2 text-sm font-semibold text-ink disabled:opacity-60"
        >
          {t("startBackground")}
        </button>
        <button
          type="button"
          onClick={handleBackgroundStop}
          disabled={!backgroundRunning}
          className="rounded-full border border-ink/10 bg-surface px-5 py-2 text-sm font-semibold text-ink disabled:opacity-60"
        >
          {t("stop")}
        </button>
      </div>
      {message && <p className="mt-3 text-xs text-ink/70">{message}</p>}
    </div>
  );
}
