"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

const STORAGE_KEY = "starsorty.lang";

const translations = {
  en: {
    title: "Your stars, organized like a product.",
    subtitle:
      "Search, filter, and refine your GitHub stars with AI-assisted categories and durable manual overrides.",
    searchPlaceholder: "Search repos, tags, descriptions",
    filters: "Filters",
    languages: "Languages",
    users: "Users",
    stars: "Stars",
    status: "Status",
    all: "All",
    any: "Any",
    search: "Search",
    lastSync: "Last sync",
    lastSyncWithValue: "Last sync: {value}",
    syncNow: "Sync now",
    syncing: "Syncing...",
    classify: "Classify",
    classifyNext: "Classify next batch",
    classifyAll: "Classify all remaining",
    classifyUntilDone: "Classify until done",
    forceReclassify: "Force reclassify",
    classifying: "Classifying...",
    settings: "Settings",
    total: "Total",
    totalWithValue: "Total: {count}",
    batchSize: "Batch size",
    unclassifiedWithValue: "Unclassified: {count}",
    showing: "Showing",
    showingWithValue: "Showing: {count}",
    theme: "Theme",
    language: "Language",
    light: "Light",
    dark: "Dark",
    actionComplete: "Action complete",
    actionFailed: "Action failed",
    never: "never",
    dismiss: "Dismiss",
    loadingRepos: "Loading repos...",
    noRepos: "No repos yet. Run the sync API to pull your GitHub stars.",
    noDescription: "No description yet.",
    viewOnGithub: "View on GitHub",
    starsWithValue: "Stars: {count}",
    updatedWithValue: "Updated: {date}",
    apiErrorWithValue: "API error: {message}",
    apiBaseWithValue: "API: {value}",
    unknown: "unknown",
    syncedWithValue: "Synced {count} repos",
    classifiedWithValue: "Classified {classified}/{total} (failed {failed})",
    classifiedWithRemainingValue:
      "Classified {classified}/{total} (failed {failed}), {remaining} unclassified left",
    syncFailed: "Sync failed",
    classifyFailed: "Classify failed",
    unknownError: "Unknown error",
  },
  zh: {
    title: "把你的星标像产品一样整理。",
    subtitle:
      "用 AI 分类与手动覆盖，搜索、筛选并精炼你的 GitHub Star 列表。",
    searchPlaceholder: "搜索仓库、标签、描述",
    filters: "筛选",
    languages: "语言",
    users: "用户",
    stars: "星标",
    status: "状态",
    all: "全部",
    any: "不限",
    search: "搜索",
    lastSync: "上次同步",
    lastSyncWithValue: "上次同步：{value}",
    syncNow: "立即同步",
    syncing: "同步中...",
    classify: "分类",
    classifyNext: "继续分类",
    classifyAll: "分类全部",
    classifyUntilDone: "自动分类完成",
    forceReclassify: "强制重分类",
    classifying: "分类中...",
    settings: "设置",
    total: "总数",
    totalWithValue: "总数：{count}",
    batchSize: "批量大小",
    unclassifiedWithValue: "未分类：{count}",
    showing: "显示",
    showingWithValue: "显示：{count}",
    theme: "主题",
    language: "语言",
    light: "浅色",
    dark: "深色",
    actionComplete: "操作完成",
    actionFailed: "操作失败",
    never: "从未",
    dismiss: "关闭",
    loadingRepos: "加载仓库中...",
    noRepos: "还没有仓库。请运行同步接口拉取你的 GitHub Star。",
    noDescription: "暂无描述。",
    viewOnGithub: "在 GitHub 查看",
    starsWithValue: "星标：{count}",
    updatedWithValue: "更新：{date}",
    apiErrorWithValue: "API 错误：{message}",
    apiBaseWithValue: "API：{value}",
    unknown: "未知",
    syncedWithValue: "已同步 {count} 个仓库",
    classifiedWithValue: "已分类 {classified}/{total}（失败 {failed}）",
    classifiedWithRemainingValue:
      "已分类 {classified}/{total}（失败 {failed}），剩余未分类 {remaining}",
    syncFailed: "同步失败",
    classifyFailed: "分类失败",
    unknownError: "未知错误",
  },
} as const;

export type Locale = "en" | "zh";
export type Messages = (typeof translations)["en"];
export type MessageValues = Record<string, string | number>;

export const formatMessage = (template: string, values?: MessageValues) => {
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (match, key) => {
    const value = values[key];
    return value === undefined || value === null ? match : String(value);
  });
};

type I18nContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: keyof Messages, values?: MessageValues) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);

const detectLocale = (): Locale => {
  if (typeof navigator === "undefined") return "en";
  const language = navigator.languages?.[0] || navigator.language;
  if (!language) return "en";
  return language.toLowerCase().startsWith("zh") ? "zh" : "en";
};

const readStoredLocale = (): Locale | null => {
  if (typeof window === "undefined") return null;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "zh") return stored;
  } catch {}
  return null;
};

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");

  useEffect(() => {
    const stored = readStoredLocale();
    const initialLocale = stored ?? detectLocale();
    setLocaleState(initialLocale);
    if (typeof document !== "undefined") {
      document.documentElement.lang = initialLocale;
    }
  }, []);

  const setLocale = useCallback((nextLocale: Locale) => {
    setLocaleState(nextLocale);
    if (typeof document !== "undefined") {
      document.documentElement.lang = nextLocale;
    }
    try {
      window.localStorage.setItem(STORAGE_KEY, nextLocale);
    } catch {}
  }, []);

  const messages = useMemo(
    () => translations[locale] ?? translations.en,
    [locale]
  );

  const t = useCallback(
    (key: keyof Messages, values?: MessageValues) =>
      formatMessage(messages[key] ?? translations.en[key], values),
    [messages]
  );

  const value = useMemo(
    () => ({ locale, setLocale, t }),
    [locale, setLocale, t]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n must be used within I18nProvider");
  }
  return context;
}
