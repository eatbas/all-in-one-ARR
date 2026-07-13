import type {
  BandwidthClientRequest,
  BandwidthClientStatsResponse,
  BandwidthDownloadItem as GeneratedBandwidthDownloadItem,
  BandwidthQueueGroup as GeneratedBandwidthQueueGroup,
  BandwidthSettingsRequest,
  BandwidthStatusResponse,
} from "@/shared/lib/generated"
import { request } from "@/shared/lib/api/client"

/** Closed download-client domain generated from the backend contract. */
export type BandwidthClient =
  BandwidthStatusResponse["manual_paused_clients"][number]

/** Statistics for one download client shown on the status page. */
export type BandwidthClientStats = BandwidthClientStatsResponse

/** Display-safe activity item with server-defaulted fields present. */
export type BandwidthDownloadItem = Required<GeneratedBandwidthDownloadItem>

/**
 * One downloader's visible queue page plus its uncapped depth. `total` counts
 * the whole queue even when `items` is capped by the backend, so the queue badge
 * stays honest while the page shows a slice of it.
 */
export type BandwidthQueueGroup = Omit<
  Required<GeneratedBandwidthQueueGroup>,
  "items"
> & { items: BandwidthDownloadItem[] }

/** Queue groups keyed by the generated closed client domain. */
export type BandwidthQueue = Record<BandwidthClient, BandwidthQueueGroup>

/** Full live status returned by `GET /api/bandwidth/status`. */
export type BandwidthStatus = Omit<
  BandwidthStatusResponse,
  "download_history" | "queue"
> & {
  download_history: BandwidthDownloadItem[]
  queue: BandwidthQueue
}

/** Body of `PUT /api/bandwidth/settings`; omitted fields stay unchanged. */
export type BandwidthSettingsUpdate = BandwidthSettingsRequest

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

export function setBandwidthClientPaused(
  client: BandwidthClient,
  paused: BandwidthClientRequest["paused"],
): Promise<BandwidthStatus> {
  return request<BandwidthStatus>(
    `/api/bandwidth/clients/${encodeURIComponent(client)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paused } satisfies BandwidthClientRequest),
    },
  )
}
