/**
 * Display labels and pill colours shared by the Cleanarr tabs. Kept in a
 * non-component module so the tab files only export components (React Fast
 * Refresh boundaries).
 */

/** Pill colours matching the Findarr history pills. */
export const PILL_STYLES = {
  amber: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  red: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  emerald:
    "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  sky: "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400",
  neutral: "bg-muted text-muted-foreground",
} as const

export type PillTone = keyof typeof PILL_STYLES

/** Common classes of every Cleanarr pill. */
export const PILL_BASE =
  "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium"

const SOURCE_LABELS: Record<string, string> = {
  sonarr: "Sonarr",
  radarr: "Radarr",
  sabnzbd: "SABnzbd",
  system: "Cleanarr",
}

/** Human label for an app, health source or history app column. */
export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source
}

/** The two strike reasons with their label and pill tone. */
export const REASON_META = {
  failed_import: { label: "Failed import", tone: "amber" },
  failed_download: { label: "Failed download", tone: "red" },
} as const satisfies Record<string, { label: string; tone: PillTone }>

interface ActionMeta {
  label: string
  tone: PillTone
}

const ACTION_META: Record<string, ActionMeta> = {
  would_remove: { label: "Would remove", tone: "amber" },
  removed: { label: "Removed", tone: "emerald" },
  already_gone: { label: "Already gone", tone: "neutral" },
  remove_failed: { label: "Remove failed", tone: "red" },
  would_delete_malware: { label: "Would delete file", tone: "red" },
  malware_deleted: { label: "Deleted file", tone: "red" },
  malware_delete_failed: { label: "Delete failed", tone: "red" },
  would_quarantine: { label: "Would quarantine", tone: "sky" },
  quarantined: { label: "Quarantined", tone: "sky" },
  quarantine_failed: { label: "Quarantine failed", tone: "red" },
  would_purge: { label: "Would purge", tone: "neutral" },
  purged: { label: "Purged", tone: "neutral" },
  purge_failed: { label: "Purge failed", tone: "red" },
}

/** Label and tone of a history action; unknown actions render as-is. */
export function actionMeta(action: string): ActionMeta {
  return ACTION_META[action] ?? { label: action, tone: "neutral" }
}

function reasonText(detail: string): string {
  return detail in REASON_META
    ? REASON_META[detail as keyof typeof REASON_META].label.toLowerCase()
    : detail
}

/**
 * Detail column text of a history row. Queue rows carry the strike reason
 * (or the error for a failed removal); file rows carry a file name or a short
 * failure reason.
 */
export function historyDetail(action: string, detail: string): string {
  switch (action) {
    case "removed":
      return `Blocklisted and searching again · ${reasonText(detail)}`
    case "would_remove":
      return reasonText(detail)
    case "already_gone":
      return "Item had already left the queue"
    case "remove_failed":
      return `${detail}; strike kept`
    default:
      return detail || "—"
  }
}
