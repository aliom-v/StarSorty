import assert from "node:assert/strict";
import test from "node:test";

import { mergeRepoItems, normalizeRepoPage } from "../app/lib/repoListState.js";

test("normalizeRepoPage uses server pagination fields when present", () => {
  const page = normalizeRepoPage(
    {
      total: 9,
      items: [{ full_name: "owner/repo-1" }],
      has_more: true,
      next_offset: 7,
    },
    0
  );

  assert.deepStrictEqual(page, {
    total: 9,
    items: [{ full_name: "owner/repo-1" }],
    hasMore: true,
    nextOffset: 7,
  });
});

test("normalizeRepoPage falls back to total-based pagination when explicit fields are missing", () => {
  const page = normalizeRepoPage(
    {
      total: 5,
      items: [{ full_name: "owner/repo-2" }, { full_name: "owner/repo-3" }],
    },
    2
  );

  assert.deepStrictEqual(page, {
    total: 5,
    items: [{ full_name: "owner/repo-2" }, { full_name: "owner/repo-3" }],
    hasMore: true,
    nextOffset: 4,
  });
});

test("mergeRepoItems deduplicates append results by full_name", () => {
  const merged = mergeRepoItems(
    [{ full_name: "owner/repo-1" }, { full_name: "owner/repo-2" }],
    [{ full_name: "owner/repo-2" }, { full_name: "owner/repo-3" }],
    true
  );

  assert.deepStrictEqual(merged, [
    { full_name: "owner/repo-1" },
    { full_name: "owner/repo-2" },
    { full_name: "owner/repo-3" },
  ]);
});

test("mergeRepoItems replaces the list on non-append refresh", () => {
  const merged = mergeRepoItems(
    [{ full_name: "owner/repo-1" }],
    [{ full_name: "owner/repo-9" }],
    false
  );

  assert.deepStrictEqual(merged, [{ full_name: "owner/repo-9" }]);
});
