import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import { DownloadActivityPanel } from "@/features/bandwidth-controllarr/components/download-activity-panel"
import { downloadItem as item } from "@/features/bandwidth-controllarr/components/download-test-fixtures"
import type {
  BandwidthDownloadItem,
  BandwidthQueue,
  BandwidthQueueGroup,
} from "@/shared/lib/api"

/** A queue group; `total` defaults to the row count but may exceed it. */
function group(
  items: BandwidthDownloadItem[] = [],
  total: number = items.length,
): BandwidthQueueGroup {
  return { items, total }
}

function queue(overrides: Partial<BandwidthQueue> = {}): BandwidthQueue {
  return {
    qbittorrent: group(),
    sabnzbd: group(),
    ...overrides,
  }
}

describe("DownloadActivityPanel", () => {
  it("renders Queue first and gives both sections full header triggers", () => {
    render(<DownloadActivityPanel downloadHistory={[]} queue={queue()} />)

    const buttons = screen.getAllByRole("button")
    expect(buttons[0]).toHaveAccessibleName("Collapse downloader queue")
    expect(buttons[0]).toHaveTextContent("Queue")
    expect(buttons[1]).toHaveAccessibleName("Expand download history")
    expect(buttons[1]).toHaveTextContent("Download history")
    expect(screen.getByText("Queue is empty")).toBeInTheDocument()
  })

  it("expands and collapses each complete header independently", async () => {
    const user = userEvent.setup()
    render(
      <DownloadActivityPanel
        downloadHistory={[item({ id: "done", name: "Finished.Movie" })]}
        queue={queue({
          qbittorrent: group([item({ id: "queued", name: "Queued.Movie" })]),
        })}
      />,
    )

    await user.click(screen.getByText("Queue"))
    expect(
      screen.getByRole("button", { name: "Expand downloader queue" }),
    ).toBeInTheDocument()
    expect(screen.queryByText("Queued.Movie")).not.toBeInTheDocument()

    await user.click(screen.getByText("Download history"))
    expect(
      screen.getByRole("button", { name: "Collapse download history" }),
    ).toBeInTheDocument()
    expect(screen.getAllByText("Finished.Movie")).toHaveLength(2)
  })

  it("activates the Queue header with Enter", async () => {
    const user = userEvent.setup()
    render(
      <DownloadActivityPanel
        downloadHistory={[]}
        queue={queue({
          qbittorrent: group([item({ id: "queued", name: "Queued.Movie" })]),
        })}
      />,
    )

    const trigger = screen.getByRole("button", {
      name: "Collapse downloader queue",
    })
    trigger.focus()
    await user.keyboard("{Enter}")

    expect(trigger).toHaveAttribute("aria-expanded", "false")
    expect(trigger).toHaveAccessibleName("Expand downloader queue")
    expect(screen.queryByText("Queued.Movie")).not.toBeInTheDocument()
  })

  it("activates the Download history header with Space", async () => {
    const user = userEvent.setup()
    render(
      <DownloadActivityPanel
        downloadHistory={[item({ id: "done", name: "Finished.Movie" })]}
        queue={queue()}
      />,
    )

    const trigger = screen.getByRole("button", {
      name: "Expand download history",
    })
    trigger.focus()
    await user.keyboard(" ")

    expect(trigger).toHaveAttribute("aria-expanded", "true")
    expect(trigger).toHaveAccessibleName("Collapse download history")
    expect(screen.getAllByText("Finished.Movie")).toHaveLength(2)
  })

  it("shows both clients in download history", async () => {
    const user = userEvent.setup()
    render(
      <DownloadActivityPanel
        downloadHistory={[
          item({
            id: "torrent-done",
            name: "Finished.Movie",
            completed_at: "2026-06-26T21:00:00Z",
          }),
          item({
            client: "sabnzbd",
            id: "sab-done",
            name: "Finished.Show",
            added_at: null,
          }),
        ]}
        queue={queue()}
      />,
    )

    await user.click(
      screen.getByRole("button", { name: "Expand download history" }),
    )
    expect(screen.getAllByText("Finished.Movie")).toHaveLength(2)
    expect(screen.getAllByText("Finished.Show")).toHaveLength(2)
    expect(screen.getAllByText("qBittorrent").length).toBeGreaterThan(0)
    expect(screen.getAllByText("SABnzbd").length).toBeGreaterThan(0)
  })

  it("keeps Speed and ETA in the queue", () => {
    render(
      <DownloadActivityPanel
        downloadHistory={[]}
        queue={queue({ qbittorrent: group([item()]) })}
      />,
    )

    expect(screen.getAllByText("Speed").length).toBeGreaterThan(0)
    expect(screen.getAllByText("1.25 MB/s").length).toBeGreaterThan(0)
    expect(screen.getAllByText("ETA").length).toBeGreaterThan(0)
    expect(screen.getAllByText("2m").length).toBeGreaterThan(0)
    expect(screen.queryByText("Status")).not.toBeInTheDocument()
    expect(screen.queryByText("Added")).not.toBeInTheDocument()
    expect(screen.queryByText("Finished")).not.toBeInTheDocument()
    expect(screen.queryByText("downloading")).not.toBeInTheDocument()
  })

  it("replaces Speed and ETA with Finished in download history", async () => {
    const user = userEvent.setup()
    const completedAt = new Date(Date.now() - 125 * 60_000).toISOString()
    render(
      <DownloadActivityPanel
        downloadHistory={[
          item({
            id: "finished",
            name: "Finished.Movie",
            progress: 100,
            completed_at: completedAt,
          }),
          item({
            id: "unknown-finish",
            name: "Unknown.Finish",
            progress: 100,
            completed_at: null,
          }),
        ]}
        queue={queue()}
      />,
    )

    await user.click(
      screen.getByRole("button", { name: "Expand download history" }),
    )

    expect(screen.queryByText("Speed")).not.toBeInTheDocument()
    expect(screen.queryByText("ETA")).not.toBeInTheDocument()
    expect(screen.getAllByText("Finished")).toHaveLength(3)
    expect(screen.getAllByText("2 hours ago")).toHaveLength(2)
    const unknownFinish = screen
      .getAllByText("Unknown.Finish")[0]
      .closest<HTMLElement>('[role="listitem"]')
    expect(unknownFinish).not.toBeNull()
    expect(within(unknownFinish!).getByText("—")).toBeInTheDocument()
  })

  it("formats responsive row values and missing fallbacks", () => {
    render(
      <DownloadActivityPanel
        downloadHistory={[]}
        queue={queue({
          qbittorrent: group([
            item({
              id: "fallback",
              name: "Fallback.Download",
              progress: null,
              size_label: null,
              size_bytes: null,
              speed_mbps: null,
              eta_seconds: null,
            }),
            item({
              id: "short",
              name: "Short.Download",
              progress: 12.5,
              size_label: null,
              size_bytes: 1024,
              eta_seconds: 45,
            }),
            item({ id: "exact-hour", name: "Exact.Hour", eta_seconds: 3600 }),
            item({
              id: "hour-minute",
              name: "Hour.Minute",
              eta_seconds: 3720,
            }),
          ]),
        })}
      />,
    )

    const fallback = screen
      .getAllByText("Fallback.Download")[0]
      .closest<HTMLElement>('[role="listitem"]')
    expect(fallback).not.toBeNull()
    expect(within(fallback!).getAllByText("—")).toHaveLength(4)
    expect(screen.getAllByText("12.5%").length).toBeGreaterThan(0)
    expect(screen.getAllByText("1.0 KB").length).toBeGreaterThan(0)
    expect(screen.getAllByText("45s").length).toBeGreaterThan(0)
    expect(screen.getAllByText("1h").length).toBeGreaterThan(0)
    expect(screen.getAllByText("1h 2m").length).toBeGreaterThan(0)
  })

  it("renders independent empty states", async () => {
    const user = userEvent.setup()
    render(<DownloadActivityPanel downloadHistory={[]} queue={queue()} />)

    expect(screen.getByText("Queue is empty")).toBeInTheDocument()
    await user.click(
      screen.getByRole("button", { name: "Expand download history" }),
    )
    expect(screen.getByText("No download history")).toBeInTheDocument()
  })

  it("counts the whole queue across both downloaders, not the visible rows", () => {
    render(
      <DownloadActivityPanel
        downloadHistory={[]}
        queue={queue({
          qbittorrent: group([item({ id: "q1" })], 14),
          sabnzbd: group([item({ client: "sabnzbd", id: "s1" })], 9),
        })}
      />,
    )

    const trigger = screen.getByRole("button", {
      name: "Collapse downloader queue",
    })
    // 14 + 9 queued in total, though only two rows are on screen.
    expect(within(trigger).getByText("23")).toBeInTheDocument()
  })

  it("renders the download history without a count badge", async () => {
    const user = userEvent.setup()
    render(
      <DownloadActivityPanel
        downloadHistory={[
          item({ id: "done-1", name: "Finished.One" }),
          item({ id: "done-2", name: "Finished.Two" }),
        ]}
        queue={queue()}
      />,
    )

    const trigger = screen.getByRole("button", {
      name: "Expand download history",
    })
    expect(trigger).toHaveTextContent("Download history")
    expect(within(trigger).queryByText("2")).not.toBeInTheDocument()

    // The rows themselves are unaffected — only the badge is gone.
    await user.click(trigger)
    expect(screen.getAllByText("Finished.One").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Finished.Two").length).toBeGreaterThan(0)
  })

  it("exposes long names through a title attribute", () => {
    const longName =
      "Very.Long.Release.Name.With.Many.Sections.2026.2160p.WEB-DL.Atmos"

    render(
      <DownloadActivityPanel
        downloadHistory={[]}
        queue={queue({
          sabnzbd: group([
            item({ client: "sabnzbd", id: "long", name: longName }),
          ]),
        })}
      />,
    )

    for (const name of screen.getAllByText(longName)) {
      expect(name).toHaveAttribute("title", longName)
    }
  })
})
