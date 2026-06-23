/**
 * Format an ISO timestamp for display, falling back to the raw value when the
 * input cannot be parsed. Shared by the Dashboard activity feed and the Items
 * table so the formatting stays consistent in one place.
 */
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
