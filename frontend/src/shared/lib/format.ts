/**
 * Format an ISO timestamp for display, falling back to the raw value when the
 * input cannot be parsed. Shared by the Dashboard activity feed and the Items
 * table so the formatting stays consistent in one place.
 */
/**
 * Display title for a mirrored item, falling back to "Untitled" when the
 * backend has no title (the `Item.title` field is nullable). Centralising the
 * fallback keeps every consumer — the table, the list grid and the poster
 * thumbnail — consistent.
 */
export function displayTitle(title: string | null): string {
  return title ?? "Untitled"
}

/**
 * Display string for a mirrored item's release year, falling back to an em dash
 * when the backend has no year (the `Item.year` field is nullable). Used by the
 * Lists grid so the fallback stays consistent in one place.
 */
export function formatYear(year: number | null): string {
  return year?.toString() ?? "—"
}

export function formatTimestamp(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return iso
  }
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  })
}

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR
const WEEK = 7 * DAY

/**
 * Format a past ISO timestamp as a coarse "time ago" string ("just now",
 * "45 min ago", "2 hours ago", "3 days ago", "2 weeks ago"). `now` is injectable
 * so the output is deterministic under test. Falls back to the raw value when
 * the input cannot be parsed.
 */
export function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return iso
  }
  const diff = now.getTime() - date.getTime()
  if (diff < MINUTE) {
    return "just now"
  }
  if (diff < HOUR) {
    return `${Math.floor(diff / MINUTE)} min ago`
  }
  if (diff < DAY) {
    const hours = Math.floor(diff / HOUR)
    return `${hours} ${hours === 1 ? "hour" : "hours"} ago`
  }
  if (diff < WEEK) {
    const days = Math.floor(diff / DAY)
    return `${days} ${days === 1 ? "day" : "days"} ago`
  }
  const weeks = Math.floor(diff / WEEK)
  return `${weeks} ${weeks === 1 ? "week" : "weeks"} ago`
}

/**
 * Format the next-sync ISO timestamp as a short, minute-granular countdown
 * ("in 12 min", "in 2 hours", "due now" when overdue, "—" when unknown).
 * Re-evaluated against a fresh `now` each second so it counts down live without
 * a page refresh; the displayed value changes on each minute boundary. `now` is
 * injectable for deterministic tests; an unparseable value falls back to its raw
 * form.
 */
export function formatNextSync(iso: string | null, now: Date = new Date()): string {
  if (iso === null) {
    return "—"
  }
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return iso
  }
  const diff = date.getTime() - now.getTime()
  if (diff <= 0) {
    return "due now"
  }
  if (diff < HOUR) {
    return `in ${Math.max(1, Math.floor(diff / MINUTE))} min`
  }
  const hours = Math.floor(diff / HOUR)
  return `in ${hours} ${hours === 1 ? "hour" : "hours"}`
}
