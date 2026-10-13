import type {
  FindarrHistoryEntry,
  FindarrHistoryStatus,
} from "@/shared/lib/api"

/**
 * Primary "processed information" text for a history row: the media title, or
 * the system detail when there is no title. Shared by the History list (search
 * filtering) and the row component (cell text + the info-button label), so it
 * lives in a non-component module to keep fast-refresh boundaries clean.
 */
export function processedInformation(entry: FindarrHistoryEntry): string {
  return entry.title ?? entry.detail
}

/** Display label and pill colour for a history row's result. */
export interface HistoryStatusMeta {
  label: string
  className: string
}

const NEUTRAL_PILL = "bg-muted text-muted-foreground"

const STATUS_META: Record<FindarrHistoryStatus, HistoryStatusMeta> = {
  sent: {
    label: "Sent",
    className: "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400",
  },
  grabbed: {
    label: "Grabbed",
    className:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  },
  not_found: {
    label: "Nothing found",
    className:
      "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  },
  unknown: { label: "Unknown", className: NEUTRAL_PILL },
  success: {
    label: "Success",
    className:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  },
  error: {
    label: "Error",
    className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  },
  skipped: { label: "Skipped", className: NEUTRAL_PILL },
}

function isKnownStatus(status: string): status is FindarrHistoryStatus {
  return Object.hasOwn(STATUS_META, status)
}

/**
 * Result label and colour for a history row. A search reads "Sent" until a
 * later run learns from Sonarr/Radarr whether it grabbed something; an
 * unexpected server value falls back to its raw text on a neutral pill.
 */
export function historyStatusMeta(status: string): HistoryStatusMeta {
  return isKnownStatus(status)
    ? STATUS_META[status]
    : { label: status, className: NEUTRAL_PILL }
}
