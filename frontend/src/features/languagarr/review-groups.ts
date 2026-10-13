import type { LanguagarrItem } from "@/shared/lib/api"

/** Non-compliant files of one series, in scan order. */
export interface SeriesGroup {
  seriesId: number
  title: string
  /** Sonarr `titleSlug` for the series link, when Sonarr reported one. */
  slug: string | null
  items: LanguagarrItem[]
}

/** Group scan results by series, keeping the backend's series/episode order. */
export function groupBySeries(items: LanguagarrItem[]): SeriesGroup[] {
  const groups = new Map<number, SeriesGroup>()
  for (const item of items) {
    const group = groups.get(item.series_id)
    if (group) {
      group.items.push(item)
    } else {
      groups.set(item.series_id, {
        seriesId: item.series_id,
        title: item.series_title,
        slug: item.series_slug,
        items: [item],
      })
    }
  }
  return [...groups.values()]
}

/** Display labels for the audio verdicts. */
export const VERDICT_LABELS: Record<LanguagarrItem["verdict"], string> = {
  compliant: "Compliant",
  missing_english: "No English",
  unknown: "Unknown audio",
}

/** Display labels for the recommended fix. */
export const ACTION_LABELS: Record<
  LanguagarrItem["recommended_action"],
  string
> = {
  search: "Search",
  delete_and_search: "Delete & search",
}

/** Display labels for an item's replacement-queue state. */
export const QUEUE_LABELS: Record<LanguagarrItem["queue_status"], string> = {
  none: "Not queued",
  pending: "Queued",
  searched: "Searched",
  failed: "Failed",
}
