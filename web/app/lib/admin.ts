"use client";

const STORAGE_KEY = "starsorty.admin_token";
const SESSION_KEY = "starsorty.admin_session";

export const getAdminToken = () => {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(STORAGE_KEY) || "";
  } catch {
    return "";
  }
};

export const setAdminToken = (token: string) => {
  if (typeof window === "undefined") return;
  try {
    if (token) {
      window.localStorage.setItem(STORAGE_KEY, token);
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  } catch {}
};

export const getSessionToken = () => {
  if (typeof window === "undefined") return "";
  try {
    return window.sessionStorage.getItem(SESSION_KEY) || "";
  } catch {
    return "";
  }
};

export const setSessionToken = (token: string) => {
  if (typeof window === "undefined") return;
  try {
    if (token) {
      window.sessionStorage.setItem(SESSION_KEY, token);
    } else {
      window.sessionStorage.removeItem(SESSION_KEY);
    }
  } catch {}
};

export const clearSessionToken = () => {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(SESSION_KEY);
  } catch {}
};

export const isSessionAuthenticated = () => {
  return getSessionToken().length > 0;
};

export const buildAdminHeaders = (base: Record<string, string> = {}) => {
  const token = getSessionToken() || getAdminToken();
  if (!token) return base;
  return { ...base, "X-Admin-Token": token };
};
