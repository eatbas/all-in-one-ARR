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
