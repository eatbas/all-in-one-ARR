import { formatBytes, formatRelativeTime } from "@/shared/lib/format"
import type { BandwidthDownloadItem } from "@/shared/lib/api"

/** Display names for the closed download-client domain. */
export const CLIENT_LABELS: Record<BandwidthDownloadItem["client"], string> = {
  qbittorrent: "qBittorrent",
  sabnzbd: "SABnzbd",
}

/**
 * Stable React key for a download row. Ids are unique per client, but the same
 * download can appear in both the queue and the history, so the client and the
 * timestamp are folded in; the index is the last resort for a client that
 * reports neither an id nor a timestamp.
 */
export function rowKey(item: BandwidthDownloadItem, index: number): string {
  return `${item.client}-${item.id}-${item.completed_at ?? item.added_at ?? index}`
}

export function formatProgress(progress: number | null): string {
  return progress === null
    ? "—"
    : `${progress.toFixed(progress % 1 === 0 ? 0 : 1)}%`
}

export function formatSize(item: BandwidthDownloadItem): string {
  if (item.size_label !== null) {
    return item.size_label
  }
  return item.size_bytes === null ? "—" : formatBytes(item.size_bytes)
}

/**
 * Render a download speed. A downloader that reports no speed for a row (an
 * idle, queued or finished download) renders as an em dash rather than a
 * misleading zero. Sub-megabyte rates are shown in KB/s so a slow-but-moving
 * download does not flatten to "0.00 MB/s".
 */
export function formatSpeed(speed: number | null): string {
  if (speed === null) {
    return "—"
  }
  if (speed < 1) {
    return `${Math.round(speed * 1024)} KB/s`
  }
  return `${speed.toFixed(2)} MB/s`
}

export function formatEta(seconds: number | null): string {
  if (seconds === null) {
    return "—"
  }
  if (seconds < 60) {
    return `${seconds}s`
  }
  if (seconds < 3600) {
    return `${Math.floor(seconds / 60)}m`
  }
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return minutes === 0 ? `${hours}h` : `${hours}h ${minutes}m`
}

export function formatFinished(completedAt: string | null): string {
  return completedAt === null ? "—" : formatRelativeTime(completedAt)
}
