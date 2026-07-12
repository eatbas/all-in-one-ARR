import { useMemo } from "react"

import type { Item, ItemStatus } from "@/shared/lib/api"

/**
 * Display order for the item grid: ready/in-progress states first, with
 * already-`removed` items sunk to the bottom. Items sharing a status keep their
 * incoming (newest-first) order because the sort is stable.
 */
const STATUS_ORDER: Record<ItemStatus, number> = {
  available: 0,
  requested: 1,
  synced: 2,
  removed: 3,
}

/**
 * Derive the items to render inside an expanded list row. Filters out removed
 * items unless `showRemoved` is true, then sorts by status without mutating the
 * cached query data.
 */
export function useVisibleItems(
  items: Item[] | undefined,
  showRemoved: boolean,
): Item[] | undefined {
  return useMemo(() => {
    const filtered = showRemoved
      ? items
      : items?.filter((item) => item.status !== "removed")
    return filtered
      ?.slice()
      .sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status])
  }, [items, showRemoved])
}
