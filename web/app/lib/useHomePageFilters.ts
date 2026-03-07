"use client";

import { useCallback, useState } from "react";

import type { SortMode, TagMode } from "./homePageTypes";

export function useHomePageFilters() {
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [subcategory, setSubcategory] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagMode, setTagMode] = useState<TagMode>("or");
  const [sortMode, setSortMode] = useState<SortMode>("stars");
  const [minStars, setMinStars] = useState<number | null>(null);
  const [sourceUser, setSourceUser] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleTagToggle = useCallback((tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((item) => item !== tag) : [...prev, tag]
    );
  }, []);

  const clearAllFilters = useCallback(() => {
    setQueryInput("");
    setQuery("");
    setCategory(null);
    setSubcategory(null);
    setSelectedTags([]);
    setTagMode("or");
    setSortMode("stars");
    setMinStars(null);
    setSourceUser(null);
  }, []);

  return {
    queryInput,
    setQueryInput,
    query,
    setQuery,
    category,
    setCategory,
    subcategory,
    setSubcategory,
    selectedTags,
    setSelectedTags,
    tagMode,
    setTagMode,
    sortMode,
    setSortMode,
    minStars,
    setMinStars,
    sourceUser,
    setSourceUser,
    sidebarOpen,
    setSidebarOpen,
    handleTagToggle,
    clearAllFilters,
  };
}
