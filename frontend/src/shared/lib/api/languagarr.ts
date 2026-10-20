import type {
  LanguagarrAudioLanguage as GeneratedLanguagarrAudioLanguage,
  LanguagarrClearResult,
  LanguagarrDeleteResult as GeneratedLanguagarrDeleteResult,
  LanguagarrEnqueueResult as GeneratedLanguagarrEnqueueResult,
  LanguagarrItem as GeneratedLanguagarrItem,
  LanguagarrQualityProfile as GeneratedLanguagarrQualityProfile,
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

/** A selectable target audio language (`GET /api/languagarr/languages`). */
export type LanguagarrAudioLanguage = GeneratedLanguagarrAudioLanguage

/** A Sonarr quality profile offered in the scope checklist. */
export type LanguagarrQualityProfile = GeneratedLanguagarrQualityProfile

/** Settings, scan summary and queue counts (`GET /api/languagarr/status`). */
export type LanguagarrStatus = GeneratedLanguagarrStatus

/** One anime episode file without an audio track in a target language. */
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

/**
 * Most quality profiles a scope may hold; mirrors the backend's
 * LANGUAGARR_PROFILE_NAMES_MAX, which the settings API enforces (422).
 */
export const LANGUAGARR_MAX_PROFILES = 20

/**
 * Most target audio languages a scope may hold; mirrors the backend's
 * LANGUAGARR_LANGUAGES_MAX, which the settings API enforces (422).
 */
export const LANGUAGARR_MAX_LANGUAGES = 10

/** Most files the backend accepts in one enqueue request. */
export const LANGUAGARR_MAX_ENQUEUE = 500

/**
 * Sonarr's series page for a `titleSlug`, e.g.
 * `http://192.168.0.2:8989/series/log-horizon`.
 */
export function sonarrSeriesUrl(baseUrl: string, titleSlug: string): string {
  const root = baseUrl.replace(/\/+$/, "")
  return `${root}/series/${encodeURIComponent(titleSlug)}`
}

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

/**
 * Join target languages as prose ("English", "English or Turkish", "English,
 * Turkish or German"), naming each code from the catalogue and falling back to
 * the upper-cased code while the catalogue is not loaded.
 */
export function describeLanguages(
  codes: readonly string[],
  catalogue: readonly LanguagarrAudioLanguage[] | undefined,
): string {
  const names = codes.map(
    (code) =>
      catalogue?.find((language) => language.code === code)?.name ??
      code.toUpperCase(),
  )
  if (names.length <= 1) return names.join("")
  return `${names.slice(0, -1).join(", ")} or ${names[names.length - 1]}`
}

/** The selectable audio languages (`GET /api/languagarr/languages`). */
export function getLanguagarrLanguages(): Promise<LanguagarrAudioLanguage[]> {
  return request<LanguagarrAudioLanguage[]>("/api/languagarr/languages")
}

/** Sonarr's quality profiles, sorted by name (`GET /api/languagarr/profiles`). */
export function getLanguagarrProfiles(): Promise<LanguagarrQualityProfile[]> {
  return request<LanguagarrQualityProfile[]>("/api/languagarr/profiles")
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
