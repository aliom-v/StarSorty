import { useCallback, useMemo, useState } from "react";
import type { HomeSortMode, HomeTagMode } from "./homePageTypes";
import {
  countActiveFilters,
  hasPendingSearchQuery,
  normalizeQueryInput,
} from "./homePageFilters";

export function useHomePageFilters() {
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [language, setLanguage] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [subcategory, setSubcategory] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagMode, setTagMode] = useState<HomeTagMode>("or");
  const [sortMode, setSortMode] = useState<HomeSortMode>("stars");
  const [minStars, setMinStars] = useState<number | null>(null);
  const [sourceUser, setSourceUser] = useState<string | null>(null);

  const activePreferenceUser = sourceUser || "global";
  const normalizedQuery = normalizeQueryInput(queryInput);
  const searchDirty = hasPendingSearchQuery(queryInput, query);

  const handleTagToggle = useCallback((tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((item) => item !== tag) : [...prev, tag]
    );
  }, []);

  const clearAllFilters = useCallback(() => {
    setQueryInput("");
    setQuery("");
    setLanguage("");
    setCategory(null);
    setSubcategory(null);
    setSelectedTags([]);
    setTagMode("or");
    setSortMode("stars");
    setMinStars(null);
    setSourceUser(null);
  }, []);

  const submitSearch = useCallback(() => {
    if (!searchDirty) return;
    setQuery(normalizedQuery);
  }, [normalizedQuery, searchDirty]);

  const clearSearch = useCallback(() => {
    if (!queryInput && !query) return;
    setQueryInput("");
    setQuery("");
  }, [query, queryInput]);

  const activeFilterCount = useMemo(
    () =>
      countActiveFilters({
        query,
        language,
        minStars,
        category,
        subcategory,
        selectedTags,
        sourceUser,
      }),
    [category, language, minStars, query, selectedTags, sourceUser, subcategory]
  );

  return {
    query,
    queryInput,
    language,
    category,
    subcategory,
    selectedTags,
    tagMode,
    sortMode,
    minStars,
    sourceUser,
    activePreferenceUser,
    searchDirty,
    activeFilterCount,
    hasActiveFilters: activeFilterCount > 0,
    setQuery,
    setQueryInput,
    setLanguage,
    setCategory,
    setSubcategory,
    setSelectedTags,
    setTagMode,
    setSortMode,
    setMinStars,
    setSourceUser,
    clearAllFilters,
    submitSearch,
    clearSearch,
    handleTagToggle,
  };
}
