import type { TrendingSource } from "@/shared/lib/api"

/** localStorage key remembering the active Trending source tab. */
export const TRENDING_TAB_STORAGE_KEY = "aio-arr.trending.active-tab"

/** The selectable source tabs, in display order. */
export const VALID_TRENDING_TABS = ["trakt", "tmdb", "seer"] as const satisfies readonly TrendingSource[]

export type TrendingTab = (typeof VALID_TRENDING_TABS)[number]

/** Human-facing label for each source, shared by the tabs and the card link. */
export const SOURCE_LABELS: Record<TrendingSource, string> = {
  trakt: "Trakt",
  tmdb: "TMDB",
  seer: "Seer",
}
