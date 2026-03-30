"use client";

const LEGACY_STORAGE_KEY = "starsorty.admin_token";
const LEGACY_SESSION_KEY = "starsorty.admin_session";
const CSRF_COOKIE_KEY = "starsorty_admin_csrf";

const clearLegacyAdminState = () => {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
    window.sessionStorage.removeItem(LEGACY_SESSION_KEY);
  } catch {}
};

const getCookieValue = (cookieName: string) => {
  if (typeof document === "undefined") return "";
  try {
    const prefix = `${cookieName}=`;
    const match = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith(prefix));
    return match ? decodeURIComponent(match.slice(prefix.length)) : "";
  } catch {
    return "";
  }
};

const expireCookie = (cookieName: string) => {
  if (typeof document === "undefined") return;
  try {
    document.cookie = `${cookieName}=; Max-Age=0; Path=/; SameSite=Lax`;
  } catch {}
};

export const getAdminCsrfToken = () => {
  clearLegacyAdminState();
  return getCookieValue(CSRF_COOKIE_KEY);
};

export const buildAdminHeaders = (base: Record<string, string> = {}) => {
  const csrfToken = getAdminCsrfToken();
  if (!csrfToken) return base;
  return { ...base, "X-CSRF-Token": csrfToken };
};

export const clearAdminClientState = () => {
  clearLegacyAdminState();
  expireCookie(CSRF_COOKIE_KEY);
};

type AdminFetchInit = Omit<RequestInit, "headers"> & {
  headers?: Record<string, string>;
};

export const adminFetch = (input: RequestInfo | URL, init: AdminFetchInit = {}) => {
  const { headers = {}, ...rest } = init;
  return fetch(input, {
    ...rest,
    credentials: "include",
    headers: buildAdminHeaders(headers),
  });
};
