import type {
  CleanarrCountResult as GeneratedCleanarrCountResult,
  CleanarrHealthWarning as GeneratedCleanarrHealthWarning,
  CleanarrHistoryEntry as GeneratedCleanarrHistoryEntry,
  CleanarrQueue as GeneratedCleanarrQueue,
  CleanarrQueueItem as GeneratedCleanarrQueueItem,
  CleanarrRunResult as GeneratedCleanarrRunResult,
  CleanarrSettings as GeneratedCleanarrSettings,
  CleanarrSettingsUpdate as GeneratedCleanarrSettingsUpdate,
  CleanarrStatus as GeneratedCleanarrStatus,
} from "@/shared/lib/generated"
import { ApiError, postJson, request } from "@/shared/lib/api/client"

/** Persisted Cleanarr settings (`GET /api/cleanarr/settings`). */
export type CleanarrSettings = GeneratedCleanarrSettings

/** Body of `PUT /api/cleanarr/settings`; omitted fields stay unchanged. */
export type CleanarrSettingsUpdate = GeneratedCleanarrSettingsUpdate

/** Settings, last run, connections, health and strike counts. */
export type CleanarrStatus = GeneratedCleanarrStatus

/** A read-only health check result; `level: "info"` means "unknown". */
export type CleanarrHealthWarning = GeneratedCleanarrHealthWarning

/** One stuck queue item joined with its strikes. */
export type CleanarrQueueItem = GeneratedCleanarrQueueItem

/**
 * Stuck queue items plus per-app read errors and hold reasons
 * (`GET /api/cleanarr/queue`).
 */
export type CleanarrQueue = GeneratedCleanarrQueue

/** One Cleanarr history row (removals, file actions, dry-run reports). */
export type CleanarrHistoryEntry = GeneratedCleanarrHistoryEntry

/** Outcome of `POST /api/cleanarr/run`. */
export type CleanarrRunResult = GeneratedCleanarrRunResult

/** Number of strikes removed by `POST /api/cleanarr/strikes/clear`. */
export type CleanarrCountResult = GeneratedCleanarrCountResult

// Bounds mirror the backend's CLEANARR_* constants in
// backend/core/settings_normalisers.py, which the settings API enforces (422).
export const CLEANARR_INTERVAL_MIN = 5
export const CLEANARR_INTERVAL_MAX = 1440
export const CLEANARR_MIN_STRIKES = 3
export const CLEANARR_MAX_STRIKES = 20
export const CLEANARR_REMOVALS_MIN = 1
export const CLEANARR_REMOVALS_MAX = 50
export const CLEANARR_MIN_AGE_HOURS_MIN = 1
export const CLEANARR_MIN_AGE_HOURS_MAX = 720
export const CLEANARR_RETENTION_DAYS_MIN = 1
export const CLEANARR_RETENTION_DAYS_MAX = 365
export const CLEANARR_PATTERNS_MAX = 50
export const CLEANARR_PATTERN_LENGTH_MAX = 200
export const CLEANARR_EXTENSIONS_MAX = 100
export const CLEANARR_IGNORE_MAX = 500
export const CLEANARR_IGNORE_LENGTH_MAX = 200
export const CLEANARR_PATH_LENGTH_MAX = 1024
/** A blocked extension as the API accepts it: lower case with a leading dot. */
export const CLEANARR_EXTENSION_PATTERN = /^\.[a-z0-9]{1,10}$/

export function getCleanarrStatus(): Promise<CleanarrStatus> {
  return request<CleanarrStatus>("/api/cleanarr/status")
}

export function getCleanarrSettings(): Promise<CleanarrSettings> {
  return request<CleanarrSettings>("/api/cleanarr/settings")
}

export function updateCleanarrSettings(
  body: CleanarrSettingsUpdate,
): Promise<CleanarrStatus> {
  return request<CleanarrStatus>("/api/cleanarr/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

export function getCleanarrQueue(): Promise<CleanarrQueue> {
  return request<CleanarrQueue>("/api/cleanarr/queue")
}

export function getCleanarrHistory(): Promise<CleanarrHistoryEntry[]> {
  return request<CleanarrHistoryEntry[]>("/api/cleanarr/history")
}

export function runCleanarr(): Promise<CleanarrRunResult> {
  return postJson<CleanarrRunResult>("/api/cleanarr/run", {})
}

export function clearCleanarrStrikes(): Promise<CleanarrCountResult> {
  return postJson<CleanarrCountResult>("/api/cleanarr/strikes/clear", {})
}

/** Add a download id to the ignore list; returns the updated settings. */
export function ignoreCleanarrDownload(
  downloadId: string,
): Promise<CleanarrSettings> {
  return postJson<CleanarrSettings>("/api/cleanarr/ignore", {
    download_id: downloadId,
  })
}

/** Settings field labels, keyed by their API location below the body. */
const CLEANARR_FIELD_LABELS: Record<string, string> = {
  enabled: "Enable Cleanarr",
  dry_run: "Dry run",
  interval_minutes: "Interval (minutes)",
  max_strikes: "Max strikes",
  max_removals_per_run: "Removal cap",
  "queue.pattern_mode": "Pattern mode",
  "queue.patterns": "Patterns",
  "malware.extensions": "Blocked extensions",
  "orphans.min_age_hours": "Minimum age (hours)",
  "orphans.quarantine_retention_days": "Keep in quarantine (days)",
  "paths.completed_root": "Completed folder",
  "paths.quarantine_dir": "Quarantine folder",
  "ignore.download_ids": "Download IDs",
  "ignore.categories": "Categories",
  "ignore.title_contains": "Title contains",
  download_id: "Download ID",
}

/** One entry of FastAPI's 422 `detail` array. */
interface ValidationIssue {
  loc: (string | number)[]
  msg: string
}

function isValidationIssue(value: unknown): value is ValidationIssue {
  if (typeof value !== "object" || value === null) return false
  const { loc, msg } = value as Record<string, unknown>
  return Array.isArray(loc) && typeof msg === "string"
}

function issueMessage({ loc, msg }: ValidationIssue): string {
  // `loc` starts with "body"; list indices are dropped to find the field.
  const field = loc
    .slice(loc[0] === "body" ? 1 : 0)
    .filter((part): part is string => typeof part === "string")
    .join(".")
  const label = CLEANARR_FIELD_LABELS[field] ?? field
  return label ? `${label}: ${msg}` : msg
}

/**
 * A readable message for a failed Cleanarr request: FastAPI's 422
 * validation array becomes "Field: reason" per problem, joined with "; ";
 * any other error keeps its own message.
 */
export function cleanarrErrorMessage(error: Error): string {
  if (!(error instanceof ApiError) || !Array.isArray(error.detail)) {
    return error.message
  }
  const issues = error.detail.filter(isValidationIssue)
  return issues.length > 0 ? issues.map(issueMessage).join("; ") : error.message
}
