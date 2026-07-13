import type { BandwidthDownloadItem } from "@/shared/lib/api"

/**
 * Baseline download item shared by the Bandwidth-Controllarr component tests.
 * Each test overrides only the fields it asserts on, so the display-safe item
 * shape lives in one place instead of being repeated per test file.
 */
export function downloadItem(
  overrides: Partial<BandwidthDownloadItem> = {},
): BandwidthDownloadItem {
  return {
    client: "qbittorrent",
    id: "download-1",
    name: "Download.One",
    status: "downloading",
    progress: 50,
    size_bytes: 2 * 1024 * 1024,
    size_label: "2.0 MB",
    speed_mbps: 1.25,
    eta_seconds: 125,
    added_at: "2026-06-26T20:00:00Z",
    completed_at: null,
    ...overrides,
  }
}
