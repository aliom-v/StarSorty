import assert from "node:assert/strict";
import test from "node:test";

import {
  buildRepoSearchParams,
  countActiveFilters,
  hasPendingSearchQuery,
  normalizeMinStars,
  normalizeQueryInput,
} from "../app/lib/homePageFilters";

test("buildRepoSearchParams includes trimmed homepage filters", () => {
  const params = buildRepoSearchParams({
    query: "  agents  ",
    language: " TypeScript ",
    minStars: 120,
    category: " AI ",
    subcategory: " SDK ",
    selectedTags: ["rag", "agent"],
    tagMode: "and",
    sortMode: "relevance",
    activePreferenceUser: "demo",
    sourceUser: " alice ",
    limit: 60,
    offset: 120,
  });

  assert.equal(params.get("q"), "agents");
  assert.equal(params.get("language"), "TypeScript");
  assert.equal(params.get("min_stars"), "120");
  assert.equal(params.get("category"), "AI");
  assert.equal(params.get("subcategory"), "SDK");
  assert.equal(params.get("tags"), "rag,agent");
  assert.equal(params.get("tag_mode"), "and");
  assert.equal(params.get("sort"), "relevance");
  assert.equal(params.get("user_id"), "demo");
  assert.equal(params.get("star_user"), "alice");
  assert.equal(params.get("limit"), "60");
  assert.equal(params.get("offset"), "120");
});

test("countActiveFilters counts all supported homepage filters", () => {
  assert.equal(
    countActiveFilters({
      query: "rag",
      language: "TypeScript",
      minStars: 300,
      category: "AI",
      subcategory: "Agent",
      selectedTags: ["tooling", "sdk"],
      sourceUser: "alice",
    }),
    7
  );
});

test("normalizeMinStars ignores zero, empty, and invalid values", () => {
  assert.equal(normalizeMinStars("0"), null);
  assert.equal(normalizeMinStars(""), null);
  assert.equal(normalizeMinStars("abc"), null);
  assert.equal(normalizeMinStars("42"), 42);
});

test("normalizeQueryInput trims and normalizes empty values", () => {
  assert.equal(normalizeQueryInput("  repo search  "), "repo search");
  assert.equal(normalizeQueryInput("    "), "");
  assert.equal(normalizeQueryInput(null), "");
});

test("hasPendingSearchQuery only flags submitted-query changes", () => {
  assert.equal(hasPendingSearchQuery("  rag ", "rag"), false);
  assert.equal(hasPendingSearchQuery("agent", "rag"), true);
});
