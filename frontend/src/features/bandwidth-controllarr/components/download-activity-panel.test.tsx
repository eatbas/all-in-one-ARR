import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import { DownloadActivityPanel } from "@/features/bandwidth-controllarr/components/download-activity-panel"
import type { BandwidthDownloadItem, BandwidthQueue } from "@/shared/lib/api"

function item(
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

function queue(overrides: Partial<BandwidthQueue> = {}): BandwidthQueue {
  return {
    qbittorrent: [],
    sabnzbd: [],
    ...overrides,
  }
}

describe("DownloadActivityPanel", () => {
  it("renders recent downloads from both clients", () => {
    render(
      <DownloadActivityPanel
        recentDownloads={[
          item({
            client: "qbittorrent",
            id: "torrent-done",
            name: "Finished.Movie",
            status: "uploading",
            progress: 100,
            completed_at: "2026-06-26T21:00:00Z",
          }),
          item({
            client: "sabnzbd",
            id: "sab-done",
            name: "Finished.Show",
            status: "Completed",
            progress: 100,
            completed_at: "2026-06-26T21:05:00Z",
          }),
        ]}
        queue={queue()}
      />,
    )

    expect(screen.getByText("Recent downloads")).toBeInTheDocument()
    expect(screen.getByText("Finished.Movie")).toBeInTheDocument()
    expect(screen.getByText("Finished.Show")).toBeInTheDocument()
    expect(screen.getAllByText("qBittorrent").length).toBeGreaterThan(0)
    expect(screen.getAllByText("SABnzbd").length).toBeGreaterThan(0)
  })

  it("keeps the queue collapsed by default and expands it on demand", async () => {
    const user = userEvent.setup()
    render(
      <DownloadActivityPanel
        recentDownloads={[]}
        queue={queue({
          qbittorrent: [item({ id: "queued-torrent", name: "Queued.Movie" })],
        })}
      />,
    )

    const trigger = screen.getByRole("button", {
      name: "Expand downloader queue",
    })
    expect(trigger).toBeInTheDocument()

    await user.click(trigger)

    expect(
      screen.getByRole("button", { name: "Collapse downloader queue" }),
    ).toBeInTheDocument()
    expect(screen.getByText("Queued.Movie")).toBeInTheDocument()
  })

  it("renders empty states for recent downloads and queue", async () => {
    const user = userEvent.setup()
    render(<DownloadActivityPanel recentDownloads={[]} queue={queue()} />)

    expect(screen.getByText("No recent downloads")).toBeInTheDocument()
    await user.click(
      screen.getByRole("button", { name: "Expand downloader queue" }),
    )
    expect(screen.getByText("Queue is empty")).toBeInTheDocument()
  })

  it("exposes long names through a title attribute", async () => {
    const user = userEvent.setup()
    const longName =
      "Very.Long.Release.Name.With.Many.Sections.2026.2160p.WEB-DL.Atmos"

    render(
      <DownloadActivityPanel
        recentDownloads={[]}
        queue={queue({
          sabnzbd: [
            item({
              client: "sabnzbd",
              id: "long",
              name: longName,
              status: "Queued",
            }),
          ],
        })}
      />,
    )

    await user.click(
      screen.getByRole("button", { name: "Expand downloader queue" }),
    )

    expect(screen.getByText(longName)).toHaveAttribute("title", longName)
  })
})
