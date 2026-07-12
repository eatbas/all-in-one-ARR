import type { TrendingSource } from "@/shared/lib/api"

/** localStorage key remembering the active Trending tab. */
export const TRENDING_TAB_STORAGE_KEY = "aio-arr.trending.active-tab"

/** localStorage key remembering the Anime tab's chosen sub-source. */
export const TRENDING_ANIME_SOURCE_STORAGE_KEY = "aio-arr.trending.anime-source"

/** localStorage key remembering the chosen posters-per-row density. */
export const TRENDING_PER_ROW_STORAGE_KEY = "aio-arr.trending.per-row"

/**
 * Selectable posters-per-row densities (large screens); the first is the
 * default and the last is the slider's maximum. Contiguous with step 1, so the
 * range doubles as the density slider's `min`/`max`.
 */
export const VALID_PER_ROW_VALUES = [5, 6, 7, 8, 9, 10, 11] as const

export type PerRow = (typeof VALID_PER_ROW_VALUES)[number]

/**
 * The selectable page tabs, in display order. The first three map 1:1 onto a
 * backend source; the Anime tab toggles between the anime sources instead.
 */
export const VALID_TRENDING_TABS = ["trakt", "tmdb", "seer", "anime"] as const

export type TrendingTab = (typeof VALID_TRENDING_TABS)[number]

/** Human-facing label for each page tab. */
export const TAB_LABELS: Record<TrendingTab, string> = {
  trakt: "Trakt",
  tmdb: "TMDB",
  seer: "Seer",
  anime: "Anime",
}

/**
 * The Anime tab's selectable sources, in display order; the first is the
 * default. AniList leads: its trending sort tracks what the anime community is
 * actually watching, and it needs no credentials.
 */
export const ANIME_SOURCES = [
  "anilist",
  "trakt-anime",
  "tmdb-anime",
] as const satisfies readonly TrendingSource[]

export type AnimeSource = (typeof ANIME_SOURCES)[number]

/** Human-facing label for each source, shared by the toggles and the card link. */
export const SOURCE_LABELS: Record<TrendingSource, string> = {
  trakt: "Trakt",
  tmdb: "TMDB",
  seer: "Seer",
  "trakt-anime": "Trakt",
  "tmdb-anime": "TMDB",
  anilist: "AniList",
}
