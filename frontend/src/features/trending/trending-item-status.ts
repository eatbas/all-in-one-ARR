import type { TrendingItem } from "@/shared/lib/api"

/** Seer `mediaInfo.status` meaning the title is fully available in the library. */
export const SEER_AVAILABLE_STATUS = 5

/**
 * Whether the item's media is actually available to watch now: downloaded in
 * Radarr/Sonarr (`in_library_available`) or reported Available by Seer. These are the
 * only items "Hide available" drops, and the only ones shown green.
 */
export function isAvailable(
  item: Pick<TrendingItem, "in_library_available" | "seer_status">,
): boolean {
  return item.in_library_available || item.seer_status === SEER_AVAILABLE_STATUS
}

/**
 * Whether the item is on its way but not yet available: it has a library record with
 * the media still missing, or Seer reports it Requested (2) / Processing (3) /
 * Partial (4). These read amber rather than green and survive "Hide available".
 */
export function isPending(
  item: Pick<TrendingItem, "in_library" | "in_library_available" | "seer_status">,
): boolean {
  if (isAvailable(item)) {
    return false
  }
  const requestedOrProcessing =
    item.seer_status !== null && item.seer_status >= 2 && item.seer_status <= 4
  return (item.in_library && !item.in_library_available) || requestedOrProcessing
}
