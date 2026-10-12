import type {
  LanguagarrClearResult,
  LanguagarrDeleteResult as GeneratedLanguagarrDeleteResult,
  LanguagarrEnqueueResult as GeneratedLanguagarrEnqueueResult,
  LanguagarrItem as GeneratedLanguagarrItem,
  LanguagarrQueue as GeneratedLanguagarrQueue,
  LanguagarrQueueRow as GeneratedLanguagarrQueueRow,
  LanguagarrResults as GeneratedLanguagarrResults,
  LanguagarrRunResult as GeneratedLanguagarrRunResult,
  LanguagarrScanSummary as GeneratedLanguagarrScanSummary,
  LanguagarrSettings as GeneratedLanguagarrSettings,
  LanguagarrSettingsUpdate as GeneratedLanguagarrSettingsUpdate,
  LanguagarrStatus as GeneratedLanguagarrStatus,
} from "@/shared/lib/generated"
import { postJson, request } from "@/shared/lib/api/client"

/** Persisted Languagarr settings (`GET /api/languagarr/settings`). */
export type LanguagarrSettings = GeneratedLanguagarrSettings

/** Body of `PUT /api/languagarr/settings`; omitted fields stay unchanged. */
export type LanguagarrSettingsUpdate = GeneratedLanguagarrSettingsUpdate

/** Counts and metadata of the latest anime audio scan. */
export type LanguagarrScanSummary = GeneratedLanguagarrScanSummary

/** Settings, scan summary and queue counts (`GET /api/languagarr/status`). */
export type LanguagarrStatus = GeneratedLanguagarrStatus

/** One anime episode file without an English audio track. */
export type LanguagarrItem = GeneratedLanguagarrItem

/** Latest scan results joined with live queue status. */
export type LanguagarrResults = GeneratedLanguagarrResults

/** Outcome of queueing replacement searches. */
export type LanguagarrEnqueueResult = GeneratedLanguagarrEnqueueResult

/** Outcome of a reviewed delete-and-search request. */
export type LanguagarrDeleteResult = GeneratedLanguagarrDeleteResult

/** One persisted replacement-search queue row. */
export type LanguagarrQueueRow = GeneratedLanguagarrQueueRow

/** Queue counts plus the most recent rows (`GET /api/languagarr/queue`). */
export type LanguagarrQueue = GeneratedLanguagarrQueue

/** Outcome of processing one batch of pending searches. */
export type LanguagarrRunResult = GeneratedLanguagarrRunResult

/** Number of pending rows removed by `DELETE /api/languagarr/queue/pending`. */
export type LanguagarrClearPendingResult = LanguagarrClearResult

/** Most files the backend accepts in one delete-and-search request. */
export const LANGUAGARR_MAX_DELETE = 25

/** Most files the backend accepts in one enqueue request. */
export const LANGUAGARR_MAX_ENQUEUE = 500

export function getLanguagarrStatus(): Promise<LanguagarrStatus> {
  return request<LanguagarrStatus>("/api/languagarr/status")
}

export function getLanguagarrSettings(): Promise<LanguagarrSettings> {
  return request<LanguagarrSettings>("/api/languagarr/settings")
}

export function updateLanguagarrSettings(
  body: LanguagarrSettingsUpdate,
): Promise<LanguagarrStatus> {
  return request<LanguagarrStatus>("/api/languagarr/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

export function getLanguagarrResults(): Promise<LanguagarrResults> {
  return request<LanguagarrResults>("/api/languagarr/results")
}

export function scanLanguagarr(): Promise<LanguagarrResults> {
  return postJson<LanguagarrResults>("/api/languagarr/scan", {})
}

export function enqueueLanguagarr(
  episodeFileIds: number[],
): Promise<LanguagarrEnqueueResult> {
  return postJson<LanguagarrEnqueueResult>("/api/languagarr/enqueue", {
    episode_file_ids: episodeFileIds,
  })
}

/** Delete reviewed files through Sonarr, then search each; always confirmed. */
export function deleteLanguagarr(
  episodeFileIds: number[],
): Promise<LanguagarrDeleteResult> {
  return postJson<LanguagarrDeleteResult>("/api/languagarr/delete", {
    episode_file_ids: episodeFileIds,
    confirm: true,
  })
}

export function getLanguagarrQueue(): Promise<LanguagarrQueue> {
  return request<LanguagarrQueue>("/api/languagarr/queue")
}

export function clearLanguagarrPending(): Promise<LanguagarrClearPendingResult> {
  return request<LanguagarrClearPendingResult>(
    "/api/languagarr/queue/pending",
    {
      method: "DELETE",
    },
  )
}

export function runLanguagarr(): Promise<LanguagarrRunResult> {
  return postJson<LanguagarrRunResult>("/api/languagarr/run", {})
}
