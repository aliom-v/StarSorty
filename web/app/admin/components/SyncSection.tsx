"use client";

import { useState } from "react";
import { buildAdminHeaders } from "../../lib/admin";
import { API_BASE_URL } from "../../lib/apiBase";
import { getErrorMessage, readApiError } from "../../lib/apiError";

type Props = {
  t: (key: string) => string;
  setMessage: (msg: string | null) => void;
};

export default function SyncSection({ t, setMessage }: Props) {
  const [syncing, setSyncing] = useState(false);

  const handleSync = async () => {
    setSyncing(true);
    setMessage(null);
    try {
      const res = await fetch(`${API_BASE_URL}/sync`, {
        method: "POST",
        headers: buildAdminHeaders(),
      });
      if (!res.ok) {
        const detail = await readApiError(res, t("syncFailed"));
        throw new Error(detail);
      }
      setMessage(t("syncQueued"));
    } catch (err) {
      setMessage(getErrorMessage(err, t("syncFailed")));
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
      <h2 className="font-display text-lg font-semibold">{t("syncOperations")}</h2>
      <div className="mt-4">
        <button
          type="button"
          onClick={handleSync}
          disabled={syncing}
          className="rounded-full bg-moss px-5 py-2 text-sm font-semibold text-white disabled:opacity-60"
        >
          {syncing ? t("syncing") : t("syncNow")}
        </button>
      </div>
    </div>
  );
}
