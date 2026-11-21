import type {
  RemindarrCounts as GeneratedRemindarrCounts,
  RemindarrEpisode as GeneratedRemindarrEpisode,
  RemindarrResults as GeneratedRemindarrResults,
  RemindarrRunResult as GeneratedRemindarrRunResult,
  RemindarrSeriesGroup as GeneratedRemindarrSeriesGroup,
  RemindarrSettings as GeneratedRemindarrSettings,
  RemindarrSettingsUpdate as GeneratedRemindarrSettingsUpdate,
  RemindarrStatus as GeneratedRemindarrStatus,
  RemindarrTag as GeneratedRemindarrTag,
  RemindarrUnmatchedSeries as GeneratedRemindarrUnmatchedSeries,
} from "@/shared/lib/generated"
import { postJson, request } from "@/shared/lib/api/client"

/** Persisted Remindarr settings (`GET /api/remindarr/settings`). */
export type RemindarrSettings = GeneratedRemindarrSettings

/** Body of `PUT /api/remindarr/settings`; omitted fields stay unchanged. */
export type RemindarrSettingsUpdate = GeneratedRemindarrSettingsUpdate

/** A Sonarr tag offered in the tag checklist (`GET /api/remindarr/tags`). */
export type RemindarrTag = GeneratedRemindarrTag

/** Stored unwatched-episode and series counts. */
export type RemindarrCounts = GeneratedRemindarrCounts

/** Settings, run state and stored counts (`GET /api/remindarr/status`). */
export type RemindarrStatus = GeneratedRemindarrStatus

/** One downloaded episode the Plex token owner has not watched. */
export type RemindarrEpisode = GeneratedRemindarrEpisode

/** One series and its unwatched episodes, newest aired first. */
export type RemindarrSeriesGroup = GeneratedRemindarrSeriesGroup

/** A tracked series that could not be matched to a Plex show. */
export type RemindarrUnmatchedSeries = GeneratedRemindarrUnmatchedSeries

/** Stored results grouped by series (`GET /api/remindarr/results`). */
export type RemindarrResults = GeneratedRemindarrResults

/** Outcome of a manual refresh (`POST /api/remindarr/run`). */
export type RemindarrRunResult = GeneratedRemindarrRunResult

/**
 * Most tags the selection may hold; mirrors the backend's
 * REMINDARR_TAG_IDS_MAX, which the settings API enforces (422).
 */
export const REMINDARR_MAX_TAGS = 50

export function getRemindarrStatus(): Promise<RemindarrStatus> {
  return request<RemindarrStatus>("/api/remindarr/status")
}

export function getRemindarrSettings(): Promise<RemindarrSettings> {
  return request<RemindarrSettings>("/api/remindarr/settings")
}

export function updateRemindarrSettings(
  body: RemindarrSettingsUpdate,
): Promise<RemindarrStatus> {
  return request<RemindarrStatus>("/api/remindarr/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

/** Sonarr's tags, sorted by label (a live Sonarr read). */
export function getRemindarrTags(): Promise<RemindarrTag[]> {
  return request<RemindarrTag[]>("/api/remindarr/tags")
}

export function getRemindarrResults(): Promise<RemindarrResults> {
  return request<RemindarrResults>("/api/remindarr/results")
}

export function runRemindarr(): Promise<RemindarrRunResult> {
  return postJson<RemindarrRunResult>("/api/remindarr/run", {})
}
