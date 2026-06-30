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

/** Format a byte count as a human-readable size (B, KB, or MB). */
export function formatBytes(bytes: number): string {
  if (bytes === 0) {
    return "0 B"
  }
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * Shared countdown core for {@link formatNextSync} and {@link formatCountdown}:
 * formats the gap to a future `iso` as "in N min" / "in N hours" / "in N days"
 * ("due now" when overdue, "—" when null, the raw value when unparseable).
 * `maxUnit` caps the coarsest unit used — "hour" keeps the minute-scale sync
 * cadence terse, "day" suits the multi-day Findarr reset window.
 */
function formatCountdownTo(
  iso: string | null,
  now: Date,
  maxUnit: "hour" | "day",
): string {
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
  if (maxUnit === "day" && diff >= DAY) {
    const days = Math.floor(diff / DAY)
    return `in ${days} ${days === 1 ? "day" : "days"}`
  }
  const hours = Math.floor(diff / HOUR)
  return `in ${hours} ${hours === 1 ? "hour" : "hours"}`
}

/**
 * Format the next-sync ISO timestamp as a short, minute-granular countdown
 * ("in 12 min", "in 2 hours", "due now" when overdue, "—" when unknown). Tops
 * out at hours for the minute-scale sync cadence. Re-evaluated against a fresh
 * `now` each second so it counts down live; `now` is injectable for tests.
 */
export function formatNextSync(iso: string | null, now: Date = new Date()): string {
  return formatCountdownTo(iso, now, "hour")
}

/**
 * Format a future ISO timestamp as a coarse, day-granular countdown ("in 5
 * days", "in 6 hours", "in 12 min", "due now", "—" when unknown). Used for the
 * Findarr stateful-reset window, whose horizon spans days. `now` is injectable
 * for deterministic tests; an unparseable value falls back to its raw form.
 */
export function formatCountdown(iso: string | null, now: Date = new Date()): string {
  return formatCountdownTo(iso, now, "day")
}
