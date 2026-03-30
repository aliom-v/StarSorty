export function normalizeRepoPage<T extends { full_name: string }>(
  data: {
    total?: number;
    items?: T[];
    has_more?: boolean;
    next_offset?: number | null;
  },
  offset: number
): {
  total: number;
  items: T[];
  hasMore: boolean;
  nextOffset: number | null;
} {
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

export function mergeRepoItems<T extends { full_name: string }>(
  previous: T[],
  incoming: T[],
  append: boolean
): T[] {
  if (!append) {
    return Array.isArray(incoming) ? incoming : [];
  }

  const existingNames = new Set(previous.map((item) => item.full_name));
  const newItems = incoming.filter((item) => !existingNames.has(item.full_name));
  return [...previous, ...newItems];
}
