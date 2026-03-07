/**
 * Normalize repo list pagination, preferring explicit server paging fields.
 *
 * @template {{ full_name: string }} T
 * @param {{
 *   total?: number,
 *   items?: T[],
 *   has_more?: boolean,
 *   next_offset?: number | null,
 * }} data
 * @param {number} offset
 * @returns {{
 *   total: number,
 *   items: T[],
 *   hasMore: boolean,
 *   nextOffset: number | null,
 * }}
 */
export function normalizeRepoPage(data, offset) {
  const total = Number(data?.total || 0);
  const items = Array.isArray(data?.items) ? data.items : [];
  const hasMore =
    typeof data?.has_more === "boolean"
      ? data.has_more
      : offset + items.length < total;
  const nextOffset = hasMore
    ? typeof data?.next_offset === "number" && Number.isFinite(data.next_offset)
      ? data.next_offset
      : offset + items.length
    : null;

  return {
    total,
    items,
    hasMore,
    nextOffset,
  };
}

/**
 * Merge repo pages while keeping append mode stable and duplicate-free.
 *
 * @template {{ full_name: string }} T
 * @param {T[]} previous
 * @param {T[]} incoming
 * @param {boolean} append
 * @returns {T[]}
 */
export function mergeRepoItems(previous, incoming, append) {
  if (!append) {
    return Array.isArray(incoming) ? incoming : [];
  }

  const existingNames = new Set(previous.map((item) => item.full_name));
  const newItems = incoming.filter((item) => !existingNames.has(item.full_name));
  return [...previous, ...newItems];
}
