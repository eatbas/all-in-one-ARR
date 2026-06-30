/**
 * Number of pages needed to show `totalItems` rows at `pageSize` rows per page,
 * never fewer than one (so an empty list still reads as "Page 1 of 1"). Shared by
 * any paginated view — the parent uses it both to clamp the active page and to feed
 * the pagination bar's display, so the page-count rule lives in one place rather than
 * being recomputed in both. Kept in a non-component module to keep fast-refresh
 * boundaries clean.
 */
export function pageCount(totalItems: number, pageSize: number): number {
  return Math.max(1, Math.ceil(totalItems / pageSize))
}
