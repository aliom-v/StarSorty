const tryParseDetail = (text: string) => {
  const trimmed = text.trim();
  if (!trimmed) return null;
  try {
    const parsed = JSON.parse(trimmed) as { detail?: unknown };
    const detail = parsed?.detail;
    if (typeof detail === "string") return detail;
    if (detail !== undefined) return JSON.stringify(detail);
  } catch {
    return null;
  }
  return null;
};

export const readApiError = async (res: Response, fallback: string) => {
  try {
    const text = await res.text();
    const detail = tryParseDetail(text);
    if (detail) return detail;
    const trimmed = text.trim();
    return trimmed || fallback;
  } catch {
    return fallback;
  }
};

export const getErrorMessage = (err: unknown, fallback: string) => {
  if (err instanceof Error && err.message) return err.message;
  if (typeof err === "string") return err;
  return fallback;
};
