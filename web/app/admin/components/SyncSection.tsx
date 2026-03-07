"use client";

import { useState } from "react";
import { buildAdminHeaders } from "../../lib/admin";
import { API_BASE_URL } from "../../lib/apiBase";
import { getErrorMessage, readApiError } from "../../lib/apiError";
import type { TFunction } from "../../lib/i18n";

type Props = {
  t: TFunction;
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
    <div className="admin-section">
      <h2 className="panel-title">{t("syncOperations")}</h2>
      <div className="mt-4">
        <button
          type="button"
          onClick={handleSync}
          disabled={syncing}
          className="rounded-full btn-ios-moss px-5 py-2.5 text-sm font-semibold disabled:opacity-60"
        >
          {syncing ? t("syncing") : t("syncNow")}
        </button>
      </div>
    </div>
  );
}
