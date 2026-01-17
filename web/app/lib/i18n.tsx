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
    categories: "Categories",
    tools: "Tools",
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
    processedWithValue: "Processed: {count}",
    succeededWithValue: "Succeeded: {count}",
    failedWithValue: "Failed: {count}",
    remainingWithValue: "Remaining: {count}",
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
    syncQueued: "Sync queued",
    syncComplete: "Sync finished",
    classifiedWithValue: "Classified {classified}/{total} (failed {failed})",
    classifiedWithRemainingValue:
      "Classified {classified}/{total} (failed {failed}), {remaining} unclassified left",
    syncFailed: "Sync failed",
    classifyFailed: "Classify failed",
    classifyQueued: "Classification queued",
    retry: "Retry",
    retrying: "Retrying...",
    retryQueued: "Retry queued",
    pollingPaused: "Polling paused after repeated errors. Check connection.",
    reconnect: "Reconnect",
    taskNotFound: "Task not found.",
    taskIdWithValue: "Task: {value}",
    taskStatusWithValue: "Status: {value}",
    retryFromWithValue: "Retry from: {value}",
    viewTask: "View task",
    viewCurrentTask: "View current",
    backgroundClassify: "Classify in background",
    backgroundStatus: "Background status",
    foregroundStatus: "Foreground status",
    backgroundRunning: "Running",
    backgroundIdle: "Idle",
    backgroundComplete: "Background classification finished",
    backgroundStopped: "Background classification stopped",
    stop: "Stop",
    includeReadme: "Include README",
    concurrency: "Concurrency",
    details: "Details",
    loadMore: "Load more",
    loadingMore: "Loading more...",
    fetching: "Fetching...",
    back: "Back",
    adminToken: "Admin token",
    adminTokenHint: "Stored locally for demo writes.",
    readmeSummary: "README summary",
    noReadmeSummary: "No README summary yet.",
    fetchReadme: "Fetch README",
    readmeUpdated: "README updated.",
    readmeUpdateFailed: "README update failed.",
    aiClassification: "AI classification",
    manualOverrides: "Manual overrides",
    overrideHistory: "Override history",
    noOverrideHistory: "No override history yet.",
    overrideNote: "Note",
    category: "Category",
    subcategory: "Subcategory",
    tags: "Tags",
    topics: "Topics",
    forksWithValue: "Forks: {count}",
    pushedWithValue: "Pushed: {date}",
    starredWithValue: "Starred: {date}",
    confidenceWithValue: "Confidence: {value}",
    providerWithValue: "Provider: {value}",
    modelWithValue: "Model: {value}",
    unknownError: "Unknown error",
  },
  zh: {
    title: "把你的星标像产品一样整理。",
    subtitle:
      "用 AI 分类与手动覆盖，搜索、筛选并精炼你的 GitHub Star 列表。",
    searchPlaceholder: "搜索仓库、标签、描述",
    filters: "筛选",
    languages: "语言",
    categories: "分类",
    tools: "工具",
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
    processedWithValue: "已处理：{count}",
    succeededWithValue: "成功：{count}",
    failedWithValue: "失败：{count}",
    remainingWithValue: "剩余：{count}",
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
    syncQueued: "同步已加入队列",
    syncComplete: "同步已完成",
    classifiedWithValue: "已分类 {classified}/{total}（失败 {failed}）",
    classifiedWithRemainingValue:
      "已分类 {classified}/{total}（失败 {failed}），剩余未分类 {remaining}",
    syncFailed: "同步失败",
    classifyFailed: "分类失败",
    classifyQueued: "分类已加入队列",
    retry: "重试",
    retrying: "重试中...",
    retryQueued: "重试已加入队列",
    pollingPaused: "轮询已暂停，请检查连接。",
    reconnect: "恢复连接",
    taskNotFound: "任务不存在。",
    taskIdWithValue: "任务：{value}",
    taskStatusWithValue: "状态：{value}",
    retryFromWithValue: "重试来源：{value}",
    viewTask: "查看任务",
    viewCurrentTask: "查看当前任务",
    backgroundClassify: "后台分类",
    backgroundStatus: "后台状态",
    foregroundStatus: "前台状态",
    backgroundRunning: "运行中",
    backgroundIdle: "空闲",
    backgroundComplete: "后台分类完成",
    backgroundStopped: "后台分类已停止",
    stop: "停止",
    includeReadme: "包含 README",
    concurrency: "并发数",
    details: "详情",
    loadMore: "加载更多",
    loadingMore: "加载更多中...",
    fetching: "拉取中...",
    back: "返回",
    adminToken: "管理员令牌",
    adminTokenHint: "仅本地保存，用于演示写入。",
    readmeSummary: "README 摘要",
    noReadmeSummary: "暂无 README 摘要",
    fetchReadme: "拉取 README",
    readmeUpdated: "README 已更新。",
    readmeUpdateFailed: "README 更新失败。",
    aiClassification: "AI 分类",
    manualOverrides: "手动覆盖",
    overrideHistory: "覆盖历史",
    noOverrideHistory: "暂无覆盖历史",
    overrideNote: "备注",
    category: "分类",
    subcategory: "子类",
    tags: "标签",
    topics: "主题",
    forksWithValue: "分叉：{count}",
    pushedWithValue: "推送：{date}",
    starredWithValue: "星标：{date}",
    confidenceWithValue: "置信度：{value}",
    providerWithValue: "提供方：{value}",
    modelWithValue: "模型：{value}",
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
