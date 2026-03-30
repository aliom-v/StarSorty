import type { HomeSortMode, HomeTagMode } from "./homePageTypes";

function normalizeTextFilter(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value.trim();
  return normalized || null;
}

export function normalizeQueryInput(value: unknown): string {
  return normalizeTextFilter(value) ?? "";
}

export function hasPendingSearchQuery(queryInput: unknown, query: unknown): boolean {
  return normalizeQueryInput(queryInput) !== normalizeQueryInput(query);
}

export function normalizeMinStars(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number.parseInt(String(value), 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

type BuildRepoSearchParamsArgs = {
  query: string;
  language: string;
  minStars: number | null;
  category: string | null;
  subcategory: string | null;
  selectedTags: string[];
  tagMode: HomeTagMode;
  sortMode: HomeSortMode;
  activePreferenceUser: string;
  sourceUser: string | null;
  limit: number;
  offset: number;
};

export function buildRepoSearchParams({
  query,
  language,
  minStars,
  category,
  subcategory,
  selectedTags,
  tagMode,
  sortMode,
  activePreferenceUser,
  sourceUser,
  limit,
  offset,
}: BuildRepoSearchParamsArgs): URLSearchParams {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    tag_mode: tagMode,
    sort: sortMode,
    user_id: activePreferenceUser,
  });

  const normalizedQuery = normalizeTextFilter(query);
  const normalizedLanguage = normalizeTextFilter(language);
  const normalizedCategory = normalizeTextFilter(category);
  const normalizedSubcategory = normalizeTextFilter(subcategory);
  const normalizedSourceUser = normalizeTextFilter(sourceUser);
  const normalizedMinStars = normalizeMinStars(minStars);

  if (normalizedQuery) params.set("q", normalizedQuery);
  if (normalizedLanguage) params.set("language", normalizedLanguage);
  if (normalizedCategory) params.set("category", normalizedCategory);
  if (normalizedSubcategory) params.set("subcategory", normalizedSubcategory);
  if (normalizedMinStars !== null) {
    params.set("min_stars", String(normalizedMinStars));
  }
  if (selectedTags.length > 0) {
    params.set("tags", selectedTags.join(","));
  }
  if (normalizedSourceUser) params.set("star_user", normalizedSourceUser);

  return params;
}

type CountActiveFiltersArgs = {
  query: string;
  language: string;
  minStars: number | null;
  category: string | null;
  subcategory: string | null;
  selectedTags: string[];
  sourceUser: string | null;
};

export function countActiveFilters({
  query,
  language,
  minStars,
  category,
  subcategory,
  selectedTags,
  sourceUser,
}: CountActiveFiltersArgs): number {
  return [
    normalizeTextFilter(query),
    normalizeTextFilter(language),
    normalizeTextFilter(category),
    normalizeTextFilter(subcategory),
    selectedTags.length > 0,
    normalizeMinStars(minStars) !== null,
    normalizeTextFilter(sourceUser),
  ].filter(Boolean).length;
}
