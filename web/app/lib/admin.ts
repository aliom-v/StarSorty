"use client";

const STORAGE_KEY = "starsorty.admin_token";

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

export const buildAdminHeaders = (base: Record<string, string> = {}) => {
  const token = getAdminToken();
  if (!token) return base;
  return { ...base, "X-Admin-Token": token };
};
