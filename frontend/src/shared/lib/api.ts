/**
 * Typed client for the All-in-One ARR backend.
 *
 * All requests are same-origin (no base URL): in production the FastAPI app
 * serves the built SPA and the JSON API from the same host; in development the
 * Vite dev server proxies `/api` and `/webhook` to the backend.
 */

/** Lifecycle status of a mirrored item. */
export type ItemStatus = "synced" | "requested" | "available" | "removed"

/** Media type of a mirrored item. */
export type ItemType = "movie" | "show"

/** Aggregate sync-engine counts shown on the List-Syncarr stat cards. */
export interface StatusCounts {
  synced: number
  requested: number
  available: number
  removed: number
}

/** Response of `GET /api/status`. */
export interface Status {
  trakt_connected: boolean
  counts: StatusCounts
}

/** A single mirrored item as returned by `GET /api/items`. */
export interface Item {
  trakt_id: number
  type: ItemType
  // Nullable to match the backend `Item` model: Trakt may omit a title.
  title: string | null
  year: number | null
  tmdb: number | null
  tvdb: number | null
  imdb: string | null
  list_id: string
  seer_request_id: number | null
  status: ItemStatus
  created_at: string
  updated_at: string
}

/** A single activity-feed entry as returned by `GET /api/activity`. */
export interface ActivityEntry {
  id: number
  ts: string
  action: string
  detail: string
}

/**
 * Response of synchronous actions that queue or await backend work.
 * `POST /api/sync` now waits for the run to finish; `POST /api/items/remove-available`
 * still accepts the job and returns `"triggered"`.
 */
export interface SyncResult {
  status: "completed" | "triggered"
}

/** A Trakt list selected for syncing. */
export interface TrackedListRef {
  owner_user: string
  slug: string
  name: string
}

/** A synced list with its item count and sync timing, from `GET /api/lists`. */
export interface ListSummary {
  owner_user: string
  slug: string
  name: string
  item_count: number
  /** Number of removed items; `item_count - removed_count` is the active count. */
  removed_count: number
  last_synced_at: string | null
  next_sync_at: string | null
  interval_minutes: number
}

/** Response of `GET`/`PUT /api/settings/trakt`. */
export interface TraktSettings {
  client_id: string
  client_id_hint: string
  client_id_set: boolean
  client_secret_set: boolean
  connected: boolean
  lists: TrackedListRef[]
}

/** Body of `PUT /api/settings/trakt`; omitted fields are left unchanged. */
export interface UpdateTraktSettings {
  client_id?: string
  client_secret?: string
}

/** Response of `POST /api/trakt/auth/start`. */
export interface TraktAuthStart {
  state: string
  user_code: string | null
  verification_url: string | null
  message: string | null
}

/** Response of `GET /api/trakt/auth/status`. */
export interface TraktAuthStatus extends TraktAuthStart {
  connected: boolean
}

/** Response of `POST /api/trakt/test`. */
export interface TraktTestResult {
  ok: boolean
  user: string | null
  message: string
}

/** A discoverable Trakt list with its current selection state. */
export interface TraktListEntry {
  name: string | null
  slug: string
  owner_user: string
  item_count: number | null
  selected: boolean
}

/** Reference to a list to add: a Trakt URL, or an explicit owner + slug. */
export interface AddListPayload {
  url?: string
  owner_user?: string
  slug?: string
}

/** The connection services managed from the Settings tabs. */
export type ServiceName =
  | "seer"
  | "sonarr"
  | "radarr"
  | "tmdb"
  | "omdb"
  | "sabnzbd"
  | "qbittorrent"

/**
 * A service's masked connection. Fields are optional because services differ in
 * shape: most carry a URL + API key and TMDB/OMDb are API-key-only (no URL).
 * Secrets are exposed only as `*_set`.
 */
export interface ServiceConnection {
  url?: string
  api_key_set?: boolean
}

/** Response of `GET`/`PUT /api/settings/services[/{name}]`. */
export type ServicesSettings = Record<ServiceName, ServiceConnection>

/** Body of `PUT /api/settings/services/{name}`; omitted fields stay unchanged. */
export interface UpdateServicePayload {
  url?: string
  api_key?: string
}

/** Response of `POST /api/services/{name}/test`. */
export interface ServiceTestResult {
  ok: boolean
  detail: string
}

/** Status snapshot for one integration as returned by `GET /api/status/services`. */
export interface ServiceStatus {
  ok: boolean
  detail: string
  checked_at: string
}

/** Response of `GET /api/status/services` and `POST /api/status/services/check`. */
export interface ServicesStatusResponse {
  interval_seconds: number
  last_check_at: string | null
  services: Partial<Record<ServiceName | "trakt", ServiceStatus>>
}

/** Body of `PUT /api/settings/general`; omitted fields stay unchanged. */
export interface UpdateGeneralSettings {
  interval_seconds?: number
  sync_interval_minutes?: number
  trending_sync_interval_minutes?: number
  auto_remove_when_available?: boolean
}

/** Response of `GET`/`PUT /api/settings/general`. */
export interface GeneralSettings {
  interval_seconds: number
  sync_interval_minutes: number
  trending_sync_interval_minutes: number
  auto_remove_when_available: boolean
}

/** Storage overview returned by `GET /api/settings/database`. */
export interface DatabaseStats {
  db_size_bytes: number
  poster_cache_bytes: number
  item_count: number
  activity_count: number
  list_state_count: number
}

/** Media library handled by Deletarr. */
export type DeletarrLibraryType = "movies" | "tv"

/** Filesystem entry type returned by a Deletarr scan. */
export type DeletarrItemType = "file" | "folder"

/** How a Deletarr scan was produced / where a candidate came from. */
export type DeletarrScanMode = "heuristic" | "arr"

/** Protected video context for a junk item inside a movie folder. */
export interface DeletarrVideoRef {
  name: string
  size: number
}

/** A single Deletarr scan candidate. */
export interface DeletarrScanItem {
  path: string
  name: string
  type: DeletarrItemType
  size: number
  reason: string
  parent: string
  movie_folder: string | null
  movie_folder_path: string | null
  is_checked: boolean
  videos_in_folder: DeletarrVideoRef[]
  origin: DeletarrScanMode
}

/** Per-library Deletarr scan statistics. */
export interface DeletarrStats {
  total_files: number
  total_folders: number
  total_size: number
  is_scanning: boolean
  scan_progress: number
}

/** Status for one configured Deletarr library. */
export interface DeletarrLibraryStatus {
  type: DeletarrLibraryType
  path: string
  last_scan_at: string | null
  last_error: string | null
  scan_mode: DeletarrScanMode
  arr_available: boolean
  arr_detail: string | null
  results_count: number
  stats: DeletarrStats
}

/** Deletarr settings. */
export interface DeletarrSettings {
  movies_path: string
  tv_path: string
  use_arr_source: boolean
}

/** Full Deletarr status response. */
export interface DeletarrStatus {
  settings: DeletarrSettings
  libraries: Record<DeletarrLibraryType, DeletarrLibraryStatus>
}

/** Deletarr results response for one library. */
export interface DeletarrResults {
  type: DeletarrLibraryType
  path: string
  scan_mode: DeletarrScanMode
  arr_available: boolean
  arr_detail: string | null
  results: DeletarrScanItem[]
  stats: DeletarrStats
}

/** Response returned after deleting reviewed Deletarr candidates. */
export interface DeletarrDeleteResult {
  success: boolean
  deleted: number
  failed: number
  freed_bytes: number
  freed_mb: number
  freed_formatted: string
  deleted_paths: string[]
  errors: Array<{ path: string; error: string }>
}

/** Partial Deletarr settings update. */
export interface DeletarrSettingsUpdate {
  movies_path?: string
  tv_path?: string
  use_arr_source?: boolean
}

/** Error raised when the backend returns a non-2xx response. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

/**
 * Build the message for a non-2xx response, preferring the backend's
 * `{ "detail": "..." }` body (FastAPI's convention) so the surfaced error carries
 * the server's reason. Falls back to a generic status message when the body is
 * empty, not JSON, or carries no string detail (e.g. a 422 validation array).
 */
async function errorMessage(input: string, response: Response): Promise<string> {
  try {
    const { detail } = (await response.json()) as { detail?: unknown }
    if (typeof detail === "string") {
      return detail
    }
  } catch {
    // Empty or non-JSON body: fall through to the generic status message.
  }
  return `Request to ${input} failed with status ${response.status}`
}

async function request<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    ...init,
    // Spread `init` first so caller headers (e.g. Content-Type on POST) are
    // merged into — not over — the default Accept header.
    headers: { Accept: "application/json", ...init?.headers },
  })

  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(input, response))
  }

  // 202/204 responses may carry an empty body; guard against that.
  const text = await response.text()
  return (text ? JSON.parse(text) : undefined) as T
}

async function postJson<T>(input: string, body: unknown): Promise<T> {
  return request<T>(input, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

export function getStatus(): Promise<Status> {
  return request<Status>("/api/status")
}

export function getItems(status?: ItemStatus, list?: string): Promise<Item[]> {
  const params = new URLSearchParams()
  if (status) params.set("status", status)
  if (list) params.set("list", list)
  const query = params.toString()
  return request<Item[]>(`/api/items${query ? `?${query}` : ""}`)
}

export function getLists(): Promise<ListSummary[]> {
  return request<ListSummary[]>("/api/lists")
}

/** Build the same-origin URL for an item's cached poster thumbnail. */
export function posterUrl(
  mediaType: ItemType,
  tmdbId: number,
  imdbId?: string | null,
): string {
  const path = `/api/posters/${mediaType}/${tmdbId}`
  if (!imdbId) return path
  const params = new URLSearchParams({ imdb: imdbId })
  return `${path}?${params.toString()}`
}

/**
 * Deep link to an item's media page in Overseerr/Seer, where the Request
 * button lives. `baseUrl` is the configured Seer connection URL (any
 * trailing slashes are trimmed); movies use the `/movie/{tmdb}` route and shows
 * the `/tv/{tmdb}` route, matching Overseerr's and Seer's URL scheme.
 */
export function seerMediaUrl(
  baseUrl: string,
  mediaType: ItemType,
  tmdbId: number,
): string {
  const root = baseUrl.replace(/\/+$/, "")
  const path = mediaType === "movie" ? "movie" : "tv"
  return `${root}/${path}/${tmdbId}`
}

export function getActivity(): Promise<ActivityEntry[]> {
  return request<ActivityEntry[]>("/api/activity")
}

export function triggerSync(): Promise<SyncResult> {
  return postJson<SyncResult>("/api/sync", {})
}

export function getTraktSettings(): Promise<TraktSettings> {
  return request<TraktSettings>("/api/settings/trakt")
}

export function updateTraktSettings(
  body: UpdateTraktSettings,
): Promise<TraktSettings> {
  return request<TraktSettings>("/api/settings/trakt", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

export function startTraktAuth(): Promise<TraktAuthStart> {
  return postJson<TraktAuthStart>("/api/trakt/auth/start", {})
}

export function getTraktAuthStatus(): Promise<TraktAuthStatus> {
  return request<TraktAuthStatus>("/api/trakt/auth/status")
}

export function testTrakt(): Promise<TraktTestResult> {
  return postJson<TraktTestResult>("/api/trakt/test", {})
}

export function getTraktLists(): Promise<TraktListEntry[]> {
  return request<TraktListEntry[]>("/api/trakt/lists")
}

export function addTraktList(payload: AddListPayload): Promise<TraktSettings> {
  return postJson<TraktSettings>("/api/trakt/lists", payload)
}

export function removeTraktList(
  ownerUser: string,
  slug: string,
): Promise<TraktSettings> {
  return request<TraktSettings>(
    `/api/trakt/lists/${encodeURIComponent(ownerUser)}/${encodeURIComponent(slug)}`,
    { method: "DELETE" },
  )
}

export function getServiceSettings(): Promise<ServicesSettings> {
  return request<ServicesSettings>("/api/settings/services")
}

export function updateServiceSettings(
  name: ServiceName,
  body: UpdateServicePayload,
): Promise<ServicesSettings> {
  return request<ServicesSettings>(`/api/settings/services/${name}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

export function testService(name: ServiceName): Promise<ServiceTestResult> {
  return postJson<ServiceTestResult>(`/api/services/${name}/test`, {})
}

export function getServiceStatuses(): Promise<ServicesStatusResponse> {
  return request<ServicesStatusResponse>("/api/status/services")
}

export function checkServiceStatuses(): Promise<ServicesStatusResponse> {
  return postJson<ServicesStatusResponse>("/api/status/services/check", {})
}

export function getGeneralSettings(): Promise<GeneralSettings> {
  return request<GeneralSettings>("/api/settings/general")
}

export function updateGeneralSettings(
  body: UpdateGeneralSettings,
): Promise<GeneralSettings> {
  return request<GeneralSettings>("/api/settings/general", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

export function getDatabaseStats(): Promise<DatabaseStats> {
  return request<DatabaseStats>("/api/settings/database")
}

export function clearActivity(): Promise<DatabaseStats> {
  return postJson<DatabaseStats>("/api/settings/database/clear-activity", {})
}

export function clearItems(): Promise<DatabaseStats> {
  return postJson<DatabaseStats>("/api/settings/database/clear-items", {})
}

export function clearPosters(): Promise<DatabaseStats> {
  return postJson<DatabaseStats>("/api/settings/database/clear-posters", {})
}

export function getDeletarrStatus(): Promise<DeletarrStatus> {
  return request<DeletarrStatus>("/api/deletarr/status")
}

export function getDeletarrSettings(): Promise<DeletarrSettings> {
  return request<DeletarrSettings>("/api/deletarr/settings")
}

export function updateDeletarrSettings(
  body: DeletarrSettingsUpdate,
): Promise<DeletarrStatus> {
  return request<DeletarrStatus>("/api/deletarr/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

export function getDeletarrResults(
  type: DeletarrLibraryType,
): Promise<DeletarrResults> {
  const params = new URLSearchParams({ type })
  return request<DeletarrResults>(`/api/deletarr/results?${params.toString()}`)
}

export function scanDeletarr(
  type: DeletarrLibraryType,
): Promise<DeletarrResults> {
  return postJson<DeletarrResults>("/api/deletarr/scan", { type })
}

export function deleteDeletarrItems(
  type: DeletarrLibraryType,
  paths: string[],
): Promise<DeletarrDeleteResult> {
  return postJson<DeletarrDeleteResult>("/api/deletarr/delete", { type, paths })
}

/** Statistics for one download client shown on the Bandwidth-Controllarr page. */
export interface BandwidthClientStats {
  online: boolean
  speed_mbps: number
  active_downloads: number
  queue_size: number
  paused?: boolean
}

/** Full live status returned by `GET /api/bandwidth/status`. */
export interface BandwidthStatus {
  enabled: boolean
  status: string
  last_run_at: string | null
  check_interval_seconds: number
  qbittorrent: BandwidthClientStats
  sabnzbd: BandwidthClientStats
}

/** Body of `PUT /api/bandwidth/settings`; omitted fields stay unchanged. */
export interface BandwidthSettingsUpdate {
  enabled?: boolean
  check_interval_seconds?: number
}

/**
 * Sonarr search granularity. `episodes` searches each episode, `seasons`
 * issues one season-pack search per season, and `shows` searches a whole
 * series at once. Radarr (movies) ignores this.
 */
export type FindarrSearchMode = "episodes" | "seasons" | "shows"

/** Per-app Findarr settings for Sonarr or Radarr. */
export interface FindarrAppSettings {
  enabled: boolean
  missing_limit: number
  upgrade_limit: number
  monitored_only: boolean
  skip_future: boolean
  missing_mode: FindarrSearchMode
  upgrade_mode: FindarrSearchMode
}

export type FindarrAppName = "sonarr" | "radarr"

/** Full Findarr settings returned by the backend. */
export interface FindarrSettings {
  enabled: boolean
  interval_minutes: number
  hourly_cap: number
  queue_limit: number
  command_sleep_seconds: number
  state_reset_hours: number
  apps: Record<FindarrAppName, FindarrAppSettings>
}

/** Partial Findarr settings update. */
export interface FindarrSettingsUpdate {
  enabled?: boolean
  interval_minutes?: number
  hourly_cap?: number
  queue_limit?: number
  command_sleep_seconds?: number
  state_reset_hours?: number
  apps?: Partial<Record<FindarrAppName, Partial<FindarrAppSettings>>>
}

/** The Findarr stateful-management window, mirroring the backend `state` block. */
export interface FindarrStateWindow {
  created_at: string | null
  reset_at: string | null
  reset_hours: number
}

/**
 * Status for one Findarr-managed app, mirroring the backend
 * `GET /api/findarr/status` response.
 *
 * - `processed` counts the current reset window (wiped on reset).
 * - `lifetime` is the reset-proof all-time tally that drives the headline so it
 *   never collapses to 0 once a window is exhausted.
 * - `wanted` is how many items the last run scanned per mode ("as of last run",
 *   not a live figure).
 * - `activity` is a short summary of what the last run did, so an idle 0 is
 *   explained rather than looking broken.
 */
export interface FindarrAppStatus {
  detail: string
  version: string | null
  compatible: boolean
  processed: {
    missing: number
    upgrade: number
  }
  lifetime: {
    missing: number
    upgrade: number
  }
  wanted: {
    missing: number
    upgrade: number
  }
  activity: string
}

/** Full Findarr status response. */
export interface FindarrStatus {
  settings: FindarrSettings
  running: boolean
  last_run_at: string | null
  last_run_status: string | null
  last_run_detail: string | null
  state: FindarrStateWindow
  apps: Record<FindarrAppName, FindarrAppStatus>
  hourly: {
    limit: number
    used: number
    remaining: number
  }
}

/** Result for a single Findarr app/mode slice. */
export interface FindarrModeResult {
  app: FindarrAppName
  mode: "missing" | "upgrade"
  scanned: number
  selected: number
  processed: number
  skipped: number
  detail: string
}

/** Manual Findarr run response. */
export interface FindarrRunResult {
  status: string
  detail: string
  processed: number
  results: FindarrModeResult[]
}

/** One Findarr history row. */
export interface FindarrHistoryEntry {
  id: number
  ts: string
  app: FindarrAppName
  mode: "missing" | "upgrade" | "system"
  item_id: string | null
  title: string | null
  status: string
  detail: string
}

/**
 * Result of a Findarr mutation reporting how many rows it removed. Shared by the
 * processed-state reset and the history clear, which return the same shape.
 */
export interface FindarrCountResult {
  status: string
  removed: number
}

/** Remove a single tracked item from its Trakt list. */
export function removeItem(listId: string, traktId: number): Promise<void> {
  return request<void>(
    `/api/items/${encodeURIComponent(listId)}/${traktId}`,
    { method: "DELETE" },
  )
}

/** Trigger removal of every Available item from its Trakt list. */
export function removeAvailable(): Promise<SyncResult> {
  return postJson<SyncResult>("/api/items/remove-available", {})
}

export function getBandwidthStatus(): Promise<BandwidthStatus> {
  return request<BandwidthStatus>("/api/bandwidth/status")
}

export function updateBandwidthSettings(
  body: BandwidthSettingsUpdate,
): Promise<BandwidthStatus> {
  return request<BandwidthStatus>("/api/bandwidth/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

export function getFindarrStatus(): Promise<FindarrStatus> {
  return request<FindarrStatus>("/api/findarr/status")
}

export function getFindarrSettings(): Promise<FindarrSettings> {
  return request<FindarrSettings>("/api/findarr/settings")
}

export function updateFindarrSettings(
  body: FindarrSettingsUpdate,
): Promise<FindarrStatus> {
  return request<FindarrStatus>("/api/findarr/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

export function runFindarr(app?: FindarrAppName): Promise<FindarrRunResult> {
  return postJson<FindarrRunResult>("/api/findarr/run", { app })
}

export function resetFindarrState(): Promise<FindarrCountResult> {
  return postJson<FindarrCountResult>("/api/findarr/reset", {})
}

export function getFindarrHistory(): Promise<FindarrHistoryEntry[]> {
  return request<FindarrHistoryEntry[]>("/api/findarr/history")
}

export function clearFindarrHistory(): Promise<FindarrCountResult> {
  return postJson<FindarrCountResult>("/api/findarr/history/clear", {})
}

/** A discovery source backing one tab of the Trending page. */
export type TrendingSource = "trakt" | "tmdb" | "seer"

/** A discovery category exposed by the Trending page. */
export type TrendingCategory = "trending" | "popular"

/** A single trending result, normalised across sources by the backend. */
export interface TrendingItem {
  source: TrendingSource
  media_type: ItemType
  tmdb: number | null
  imdb: string | null
  tvdb: number | null
  trakt: number | null
  /** Trakt list slug, used to deep-link to trakt.tv; only set for Trakt-sourced items. */
  slug: string | null
  title: string | null
  year: number | null
  /** Seer `mediaInfo.status` (Seer tab only), else null. */
  seer_status: number | null
  /** Whether this item's TMDB id is already mirrored in a tracked list. */
  already_tracked: boolean
  /** Whether this item is already present in Radarr (movies) or Sonarr (shows). */
  in_library: boolean
  /**
   * Whether the item's media is actually downloaded (Radarr `hasFile`; Sonarr at
   * least one episode file). An `in_library` item with this `false` has a record but
   * the media is still missing — shown amber rather than green.
   */
  in_library_available: boolean
}

/** Query parameters for `GET /api/trending`. */
export interface TrendingQuery {
  source: TrendingSource
  media: ItemType
  category: TrendingCategory
}

/** IMDb rating overlay returned by `GET /api/trending/rating`. */
export interface TrendingRating {
  imdb_rating: number | null
  imdb_votes: number | null
}

/** Body of `POST /api/trending/add`. */
export interface AddTrendingPayload {
  media_type: ItemType
  owner_user: string
  slug: string
  tmdb?: number | null
  imdb?: string | null
  trakt?: number | null
  tvdb?: number | null
  title?: string | null
}

/** Response of `POST /api/trending/add`. */
export interface TrendingAddResult {
  status: "added" | "added_pending_sync"
}

/** Refresh state of the scheduled trending sync, from `GET /api/trending/status`. */
export interface TrendingStatus {
  last_synced_at: string | null
  interval_minutes: number
  next_sync_at: string | null
}

export function getTrendingStatus(): Promise<TrendingStatus> {
  return request<TrendingStatus>("/api/trending/status")
}

export function getTrending(query: TrendingQuery): Promise<TrendingItem[]> {
  const params = new URLSearchParams({
    source: query.source,
    media: query.media,
    category: query.category,
  })
  return request<TrendingItem[]>(`/api/trending?${params.toString()}`)
}

export function getTrendingRating(params: {
  imdb?: string | null
  media?: ItemType
  tmdb?: number | null
}): Promise<TrendingRating> {
  const query = new URLSearchParams()
  if (params.imdb) {
    query.set("imdb", params.imdb)
  } else if (params.media && params.tmdb != null) {
    query.set("media", params.media)
    query.set("tmdb", String(params.tmdb))
  }
  const qs = query.toString()
  return request<TrendingRating>(`/api/trending/rating${qs ? `?${qs}` : ""}`)
}

export function addTrending(payload: AddTrendingPayload): Promise<TrendingAddResult> {
  return postJson<TrendingAddResult>("/api/trending/add", payload)
}

/**
 * Build the deep link to a trending item's dedicated page on its source site, or
 * `null` when it cannot be resolved. TMDB items link to themoviedb.org by TMDB id
 * (the bare id redirects to the slug page); Trakt items link to trakt.tv by their
 * slug (the only reliable Trakt web route); Seer items link to the configured
 * Overseerr/Seer instance's media page via {@link seerMediaUrl}.
 */
export function trendingSourceUrl(
  item: TrendingItem,
  seerBaseUrl?: string,
): string | null {
  if (item.source === "tmdb") {
    if (item.tmdb === null) return null
    const path = item.media_type === "movie" ? "movie" : "tv"
    return `https://www.themoviedb.org/${path}/${item.tmdb}`
  }
  if (item.source === "trakt") {
    if (!item.slug) return null
    const path = item.media_type === "movie" ? "movies" : "shows"
    return `https://trakt.tv/${path}/${item.slug}`
  }
  // source === "seer"
  if (!seerBaseUrl || item.tmdb === null) return null
  return seerMediaUrl(seerBaseUrl, item.media_type, item.tmdb)
}
