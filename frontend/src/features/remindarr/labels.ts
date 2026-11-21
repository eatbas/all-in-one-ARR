import type { RemindarrTag } from "@/shared/lib/api"

/** Refresh intervals offered on the Settings tab, in minutes. */
export const REMINDARR_INTERVALS: readonly number[] = [
  15, 30, 60, 120, 360, 720, 1440,
]

/** "15 minutes", "1 hour", "6 hours", "1 day" for an interval in minutes. */
export function intervalLabel(minutes: number): string {
  if (minutes % 1440 === 0) {
    const days = minutes / 1440
    return `${days} ${days === 1 ? "day" : "days"}`
  }
  if (minutes % 60 === 0) {
    const hours = minutes / 60
    return `${hours} ${hours === 1 ? "hour" : "hours"}`
  }
  return `${minutes} ${minutes === 1 ? "minute" : "minutes"}`
}

/**
 * A tag id's Sonarr label, or "tag <id>" while the tags are unknown or for a
 * tag Sonarr no longer reports.
 */
export function tagLabel(
  tagId: number,
  tags: readonly RemindarrTag[] | undefined,
): string {
  return tags?.find((tag) => tag.id === tagId)?.label ?? `tag ${tagId}`
}
