function normalizeTextFilter(value) {
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value.trim();
  return normalized || null;
}

export function normalizeMinStars(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number.parseInt(String(value), 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

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
}) {
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
  if (Array.isArray(selectedTags) && selectedTags.length > 0) {
    params.set("tags", selectedTags.join(","));
  }
  if (normalizedSourceUser) params.set("star_user", normalizedSourceUser);

  return params;
}

export function countActiveFilters({
  query,
  language,
  minStars,
  category,
  subcategory,
  selectedTags,
  sourceUser,
}) {
  return [
    normalizeTextFilter(query),
    normalizeTextFilter(language),
    normalizeTextFilter(category),
    normalizeTextFilter(subcategory),
    Array.isArray(selectedTags) && selectedTags.length > 0,
    normalizeMinStars(minStars) !== null,
    normalizeTextFilter(sourceUser),
  ].filter(Boolean).length;
}
