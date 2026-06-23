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

/** Aggregate counts shown on the dashboard stat cards. */
export interface StatusCounts {
  synced: number
  requested: number
  available: number
  removed: number
}

/** Response of `GET /api/status`. */
export interface Status {
  dry_run: boolean
  trakt_connected: boolean
  counts: StatusCounts
}

/** A single mirrored item as returned by `GET /api/items`. */
export interface Item {
  trakt_id: number
  type: ItemType
  title: string
  year: number | null
  tmdb: number | null
  tvdb: number | null
  imdb: string | null
  list_id: string
  jellyseerr_request_id: number | null
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

/** Response of `POST /api/sync`. */
export interface SyncResult {
  status: "triggered"
}

/** Response of `POST /api/settings/dry-run`. */
export interface DryRunResult {
  dry_run: boolean
}

/** A Trakt list selected for syncing. */
export interface TrackedListRef {
  owner_user: string
  slug: string
  name: string
}

/** Response of `GET`/`PUT /api/settings/trakt`. */
export interface TraktSettings {
  client_id_hint: string
  client_id_set: boolean
  client_secret_set: boolean
  user: string
  connected: boolean
  lists: TrackedListRef[]
}

/** Body of `PUT /api/settings/trakt`; omitted fields are left unchanged. */
export interface UpdateTraktSettings {
  client_id?: string
  client_secret?: string
  user?: string
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
  | "jellyseerr"
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

/** Body of `PUT /api/settings/general`. */
export interface UpdateGeneralSettings {
  interval_seconds: number
}

/** Response of `PUT /api/settings/general`. */
export interface GeneralSettings {
  interval_seconds: number
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

async function request<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    ...init,
    // Spread `init` first so caller headers (e.g. Content-Type on POST) are
    // merged into — not over — the default Accept header.
    headers: { Accept: "application/json", ...init?.headers },
  })

  if (!response.ok) {
    throw new ApiError(
      response.status,
      `Request to ${input} failed with status ${response.status}`,
    )
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

export function getItems(status?: ItemStatus): Promise<Item[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : ""
  return request<Item[]>(`/api/items${query}`)
}

export function getActivity(): Promise<ActivityEntry[]> {
  return request<ActivityEntry[]>("/api/activity")
}

export function triggerSync(): Promise<SyncResult> {
  return postJson<SyncResult>("/api/sync", {})
}

export function setDryRun(enabled: boolean): Promise<DryRunResult> {
  return postJson<DryRunResult>("/api/settings/dry-run", { enabled })
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
