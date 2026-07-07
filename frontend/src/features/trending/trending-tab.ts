import type { TrendingSource } from "@/shared/lib/api"

/** localStorage key remembering the active Trending source tab. */
export const TRENDING_TAB_STORAGE_KEY = "aio-arr.trending.active-tab"

/** localStorage key remembering the chosen posters-per-row density. */
export const TRENDING_PER_ROW_STORAGE_KEY = "aio-arr.trending.per-row"

/** Selectable posters-per-row densities (large screens); the first is the default. */
export const VALID_PER_ROW_VALUES = [5, 6, 7] as const

export type PerRow = (typeof VALID_PER_ROW_VALUES)[number]

/** The selectable source tabs, in display order. */
export const VALID_TRENDING_TABS = [
  "trakt",
  "tmdb",
  "seer",
] as const satisfies readonly TrendingSource[]

export type TrendingTab = (typeof VALID_TRENDING_TABS)[number]

/** Human-facing label for each source, shared by the tabs and the card link. */
export const SOURCE_LABELS: Record<TrendingSource, string> = {
  trakt: "Trakt",
  tmdb: "TMDB",
  seer: "Seer",
}
