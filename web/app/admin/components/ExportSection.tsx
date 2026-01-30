"use client";

import { useState } from "react";
import { API_BASE_URL } from "../../lib/apiBase";
import { getErrorMessage, readApiError } from "../../lib/apiError";

type Props = {
  t: (key: string) => string;
  setMessage: (msg: string | null) => void;
};

export default function ExportSection({ t, setMessage }: Props) {
  const [exporting, setExporting] = useState(false);

  const handleExportObsidian = async () => {
    setExporting(true);
    setMessage(null);
    try {
      const res = await fetch(`${API_BASE_URL}/export/obsidian`);
      if (!res.ok) {
        const detail = await readApiError(res, t("exportFailed"));
        throw new Error(detail);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "starsorty-export.zip";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setMessage(t("exportComplete"));
    } catch (err) {
      setMessage(getErrorMessage(err, t("exportFailed")));
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
      <h2 className="font-display text-lg font-semibold">{t("exportData")}</h2>
      <p className="mt-2 text-sm text-ink/70">{t("exportDataDesc")}</p>
      <div className="mt-4">
        <button
          type="button"
          onClick={handleExportObsidian}
          disabled={exporting}
          className="rounded-full bg-moss px-5 py-2 text-sm font-semibold text-white disabled:opacity-60"
        >
          {exporting ? t("exporting") : t("exportToObsidian")}
        </button>
      </div>
    </div>
  );
}
