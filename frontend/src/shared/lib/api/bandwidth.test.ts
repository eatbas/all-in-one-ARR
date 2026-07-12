import { afterEach, describe, expect, it, vi } from "vitest"

import {
  getBandwidthStatus,
  setBandwidthClientPaused,
  updateBandwidthSettings,
  type BandwidthStatus,
} from "@/shared/lib/api/bandwidth"

const sampleBandwidthStatus: BandwidthStatus = {
  enabled: false,
  status: "Monitoring only",
  last_run_at: "2026-06-26T20:00:00Z",
  tracking_suspended: false,
  manual_paused_clients: [],
  check_interval_seconds: 15,
  qbittorrent: {
    online: true,
    speed_mbps: 12.5,
    active_downloads: 2,
    queue_size: 1,
  },
  sabnzbd: {
    online: true,
    speed_mbps: 0,
    active_downloads: 0,
    queue_size: 0,
    paused: false,
  },
  download_history: [],
  queue: { qbittorrent: [], sabnzbd: [] },
}

function mockFetch(response: Response) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(response)
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe("Bandwidth-Controllarr API", () => {
  it("GETs the bandwidth status", async () => {
    const fetchSpy = mockFetch(jsonResponse(sampleBandwidthStatus))

    await expect(getBandwidthStatus()).resolves.toEqual(sampleBandwidthStatus)
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/bandwidth/status",
      expect.anything(),
    )
  })

  it("PUTs bandwidth settings", async () => {
    const fetchSpy = mockFetch(jsonResponse(sampleBandwidthStatus))

    await expect(updateBandwidthSettings({ enabled: true })).resolves.toEqual(
      sampleBandwidthStatus,
    )
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/bandwidth/settings",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ enabled: true }),
      }),
    )
  })

  it("PUTs a downloader's desired pause state", async () => {
    const fetchSpy = mockFetch(jsonResponse(sampleBandwidthStatus))

    await expect(
      setBandwidthClientPaused("qbittorrent", true),
    ).resolves.toEqual(sampleBandwidthStatus)
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/bandwidth/clients/qbittorrent",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ paused: true }),
      }),
    )
  })
})
