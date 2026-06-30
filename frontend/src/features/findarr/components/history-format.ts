import type { FindarrHistoryEntry } from "@/shared/lib/api"

/**
 * Primary "processed information" text for a history row: the media title, or
 * the system detail when there is no title. Shared by the History list (search
 * filtering) and the row component (cell text + the info-button label), so it
 * lives in a non-component module to keep fast-refresh boundaries clean.
 */
export function processedInformation(entry: FindarrHistoryEntry): string {
  return entry.title ?? entry.detail
}
