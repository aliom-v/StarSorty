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
    subcategories: "Subcategories",
    users: "Users",
    stars: "Stars",
    status: "Status",
    all: "All",
    any: "Any",
    search: "Search",
    lastSync: "Last sync",
    lastSyncWithValue: "Last sync: {value}",
    syncNow: "Sync",
    syncing: "Syncing...",
    classify: "Classify",
    classifyNext: "Next",
    classifyAll: "All",
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
    loadingSettings: "Loading settings...",
    noRepos: "No repos yet. Run the sync API to pull your GitHub stars.",
    noReposForFilters: "No repos match current filters. Try clearing filters.",
    clearFilters: "Clear filters",
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
    taskStateResynced: "Task state changed. Resynced with server.",
    taskIdWithValue: "Task: {value}",
    taskStatusWithValue: "Status: {value}",
    taskTypeWithValue: "Type: {value}",
    taskTypeSync: "Sync task",
    taskTypeClassify: "Classification task",
    taskTypeUnknown: "Unknown task",
    taskTypeExpired: "Expired task",
    taskTypeMissing: "Cleaned task",
    showTaskId: "Show task ID",
    hideTaskId: "Hide task ID",
    retryFromWithValue: "Retry from: {value}",
    viewTask: "View task",
    viewCurrentTask: "View current",
    backgroundClassify: "Classify",
    backgroundStatus: "Background status",
    simpleStatus: "Status",
    operationStatusWithValue: "Operation: {value}",
    foregroundStatus: "Foreground status",
    backgroundRunning: "Running",
    backgroundIdle: "Idle",
    backgroundComplete: "Background classification finished",
    backgroundStopped: "Background classification stopped",
    stop: "Stop",
    includeReadme: "Include README",
    concurrency: "Concurrency",
    details: "Details",
    advancedDetails: "Advanced details",
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
    tagCloud: "Tag Cloud",
    selectedTags: "Selected Tags",
    clearTags: "Clear",
    summary: "Summary",
    keywords: "Keywords",
    // Admin page
    admin: "Admin",
    adminPageTitle: "Administration",
    adminPageSubtitle: "Manage sync, classification, and settings.",
    enterPassword: "Enter admin password",
    password: "Password",
    login: "Login",
    logout: "Logout",
    passwordRequired: "Password required",
    passwordIncorrect: "Password incorrect",
    verifying: "Verifying...",
    syncOperations: "Sync Operations",
    classifyOperations: "Classify Operations",
    configSettings: "Configuration",
    githubUsername: "GitHub Username",
    githubTargetUsername: "Target Username",
    githubUsernames: "Usernames (comma-separated)",
    githubIncludeSelf: "Include self",
    githubMode: "GitHub Mode",
    classifyMode: "Classify Mode",
    autoClassifyAfterSync: "Auto classify after sync",
    syncCron: "Sync schedule (cron)",
    syncTimeout: "Sync timeout (seconds)",
    rulesJson: "Rules JSON",
    save: "Save",
    saving: "Saving...",
    saved: "Saved",
    saveFailed: "Save failed",
    // Admin page - additional
    startBackground: "Start background",
    stopped: "Stopped",
    failedRepos: "Failed Repos",
    failedReposWithValue: "Failed repos: {count}",
    resetFailed: "Reset failed",
    noFailedRepos: "No failed repos",
    failCountWithValue: "Failed {count} times",
    resetFailedWithValue: "Reset {count} repos",
    hide: "Hide",
    show: "Show",
    // Settings page (read-only)
    settingsPageTitle: "Settings Overview",
    settingsPageSubtitle: "View current configuration. To modify, go to Admin page.",
    currentConfig: "Current Configuration",
    tokenStatus: "Token Status",
    githubTokenSet: "GitHub Token",
    aiApiKeySet: "AI API Key",
    configured: "Configured",
    notConfigured: "Not configured",
    goToAdmin: "Go to Admin",
    // Export
    exportData: "Export Data",
    exportDataDesc: "Export your starred repos to Obsidian-compatible Markdown files.",
    exportToObsidian: "Export to Obsidian",
    exporting: "Exporting...",
    exportComplete: "Export complete",
    exportFailed: "Export failed",
    loadFailedReposError: "Failed to load failed repos",
    loadStatsError: "Failed to load stats",
    loadStatusError: "Failed to load background status",
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
    subcategories: "二级分类",
    users: "用户",
    stars: "星标",
    status: "状态",
    all: "全部",
    any: "不限",
    search: "搜索",
    lastSync: "上次同步",
    lastSyncWithValue: "上次同步：{value}",
    syncNow: "同步",
    syncing: "同步中...",
    classify: "分类",
    classifyNext: "继续",
    classifyAll: "全部",
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
    loadingSettings: "加载设置中...",
    noRepos: "还没有仓库。请运行同步接口拉取你的 GitHub Star。",
    noReposForFilters: "当前筛选条件下没有结果，试试清空筛选。",
    clearFilters: "清空筛选",
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
    taskStateResynced: "任务状态已变化，已与服务端重新同步。",
    taskIdWithValue: "任务：{value}",
    taskStatusWithValue: "状态：{value}",
    taskTypeWithValue: "类型：{value}",
    taskTypeSync: "同步任务",
    taskTypeClassify: "分类任务",
    taskTypeUnknown: "未知任务",
    taskTypeExpired: "过期任务",
    taskTypeMissing: "已清理任务",
    showTaskId: "显示任务ID",
    hideTaskId: "隐藏任务ID",
    retryFromWithValue: "重试来源：{value}",
    viewTask: "查看任务",
    viewCurrentTask: "查看当前任务",
    backgroundClassify: "分类",
    backgroundStatus: "后台状态",
    simpleStatus: "状态",
    operationStatusWithValue: "当前操作：{value}",
    foregroundStatus: "前台状态",
    backgroundRunning: "运行中",
    backgroundIdle: "空闲",
    backgroundComplete: "后台分类完成",
    backgroundStopped: "后台分类已停止",
    stop: "停止",
    includeReadme: "包含 README",
    concurrency: "并发数",
    details: "详情",
    advancedDetails: "高级详情",
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
    tagCloud: "标签云",
    selectedTags: "已选标签",
    clearTags: "清除",
    summary: "摘要",
    keywords: "关键词",
    // Admin page
    admin: "管理",
    adminPageTitle: "管理后台",
    adminPageSubtitle: "管理同步、分类和设置。",
    enterPassword: "输入管理员密码",
    password: "密码",
    login: "登录",
    logout: "退出",
    passwordRequired: "请输入密码",
    passwordIncorrect: "密码错误",
    verifying: "验证中...",
    syncOperations: "同步操作",
    classifyOperations: "分类操作",
    configSettings: "配置设置",
    githubUsername: "GitHub 用户名",
    githubTargetUsername: "目标用户名",
    githubUsernames: "用户名列表（逗号分隔）",
    githubIncludeSelf: "包含自己",
    githubMode: "GitHub 模式",
    classifyMode: "分类模式",
    autoClassifyAfterSync: "同步后自动分类",
    syncCron: "同步计划（cron）",
    syncTimeout: "同步超时（秒）",
    rulesJson: "规则 JSON",
    save: "保存",
    saving: "保存中...",
    saved: "已保存",
    saveFailed: "保存失败",
    // Admin page - additional
    startBackground: "启动后台",
    stopped: "已停止",
    failedRepos: "失败仓库",
    failedReposWithValue: "失败仓库：{count}",
    resetFailed: "重置失败",
    noFailedRepos: "没有失败的仓库",
    failCountWithValue: "失败 {count} 次",
    resetFailedWithValue: "已重置 {count} 个仓库",
    hide: "隐藏",
    show: "显示",
    // Settings page (read-only)
    settingsPageTitle: "设置概览",
    settingsPageSubtitle: "查看当前配置。如需修改，请前往管理页面。",
    currentConfig: "当前配置",
    tokenStatus: "令牌状态",
    githubTokenSet: "GitHub Token",
    aiApiKeySet: "AI API Key",
    configured: "已配置",
    notConfigured: "未配置",
    goToAdmin: "前往管理",
    // Export
    exportData: "数据导出",
    exportDataDesc: "将你的 Star 仓库导出为 Obsidian 兼容的 Markdown 文件。",
    exportToObsidian: "导出到 Obsidian",
    exporting: "导出中...",
    exportComplete: "导出完成",
    exportFailed: "导出失败",
    loadFailedReposError: "加载失败仓库列表出错",
    loadStatsError: "加载统计信息失败",
    loadStatusError: "加载后台状态失败",
  },
} as const;

export type Locale = "en" | "zh";
export type Messages = (typeof translations)["en"];
export type MessageValues = Record<string, string | number>;
export type TFunction = (key: keyof Messages, values?: MessageValues) => string;

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

const getDefaultLocale = (): Locale => {
  return "zh";
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
  const [locale, setLocaleState] = useState<Locale>("zh");

  useEffect(() => {
    const stored = readStoredLocale();
    const initialLocale = stored ?? getDefaultLocale();
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
