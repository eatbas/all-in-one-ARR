import { readStoredItem, writeStoredItem } from "@/shared/lib/storage"

/**
 * Shared contract for adjustable poster-grid density.
 *
 * Both Trending and ListSyncarr expose the same 5–11 posters-per-row selector.
 * Keeping the allow-list, responsive grid recipes, and storage validation in one
 * place guarantees the two pages stay visually consistent and that Tailwind's JIT
 * scanner sees every literal grid class.
 */

/** Selectable large-screen posters-per-row densities. */
export const VALID_POSTER_DENSITIES = [5, 6, 7, 8, 9, 10, 11] as const

/** A valid posters-per-row density (large screens). */
export type PosterDensity = (typeof VALID_POSTER_DENSITIES)[number]

/** Trending's default density, also used when no preference is stored. */
export const DEFAULT_TRENDING_DENSITY: PosterDensity = 5

/** ListSyncarr's default density, matching its original wide-screen layout. */
export const DEFAULT_LIST_SYNCARR_DENSITY: PosterDensity = 8

/**
 * Responsive grid column classes per density. The selector varies only the
 * large-screen count; base/sm/md stay responsive so narrow viewports are not crammed.
 * Full literal class strings — Tailwind JIT does not compile interpolated names.
 */
export const GRID_COLS: Record<PosterDensity, string> = {
  5: "grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5",
  6: "grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6",
  7: "grid grid-cols-3 gap-4 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-7",
  8: "grid grid-cols-3 gap-4 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8",
  9: "grid grid-cols-3 gap-4 sm:grid-cols-5 md:grid-cols-6 lg:grid-cols-9",
  10: "grid grid-cols-4 gap-4 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-10",
  11: "grid grid-cols-4 gap-4 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-11",
}

function parseDensity(raw: string): PosterDensity | undefined {
  const value = Number(raw)
  return (VALID_POSTER_DENSITIES as readonly number[]).includes(value)
    ? (value as PosterDensity)
    : undefined
}

/**
 * Read a persisted density for the given key, falling back to the supplied
 * default when the value is missing, malformed, outside the allowed range, or
 * `localStorage` is unavailable or denied. This mirrors the resilient behaviour
 * already used by the Trending page.
 */
export function readStoredDensity(
  key: string,
  defaultValue: PosterDensity,
): PosterDensity {
  return readStoredItem(key, defaultValue, parseDensity)
}

/**
 * Persist a valid density to `localStorage`. Does nothing when `localStorage`
 * is unavailable or denied, so the control still works in test environments,
 * private browsing, or with restrictive privacy settings without throwing.
 */
export function writeStoredDensity(key: string, value: PosterDensity): void {
  writeStoredItem(key, value)
}
