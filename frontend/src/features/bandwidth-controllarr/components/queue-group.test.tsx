import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import { QueueGroup } from "@/features/bandwidth-controllarr/components/queue-group"
import { downloadItem } from "@/features/bandwidth-controllarr/components/download-test-fixtures"
import type {
  BandwidthDownloadItem,
  BandwidthQueueGroup,
} from "@/shared/lib/api"

function item(index: number): BandwidthDownloadItem {
  return downloadItem({ id: `download-${index}`, name: `Download.${index}` })
}

/** A group of `count` rows; `total` defaults to the row count. */
function group(count: number, total: number = count): BandwidthQueueGroup {
  return {
    items: Array.from({ length: count }, (_, index) => item(index + 1)),
    total,
  }
}

/** The names of the download rows currently on screen (desktop + mobile). */
function visibleNames(): string[] {
  return [
    ...new Set(
      screen
        .getAllByTitle(/^Download\.\d+$/)
        .map((element) => element.textContent ?? ""),
    ),
  ]
}

describe("QueueGroup", () => {
  it("shows only the first five rows of a deeper queue", () => {
    render(<QueueGroup label="qBittorrent" group={group(12)} />)

    expect(visibleNames()).toEqual([
      "Download.1",
      "Download.2",
      "Download.3",
      "Download.4",
      "Download.5",
    ])
    expect(screen.queryByTitle("Download.6")).not.toBeInTheDocument()
  })

  it("badges the cumulative queue depth rather than the visible rows", () => {
    render(<QueueGroup label="qBittorrent" group={group(12)} />)

    expect(screen.getByText("12")).toBeInTheDocument()
    expect(screen.getByText("Showing 1–5 of 12")).toBeInTheDocument()
  })

  it("pages forward and back through the queue", async () => {
    const user = userEvent.setup()
    render(<QueueGroup label="qBittorrent" group={group(12)} />)

    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled()

    await user.click(screen.getByRole("button", { name: "Next page" }))
    expect(visibleNames()).toEqual([
      "Download.6",
      "Download.7",
      "Download.8",
      "Download.9",
      "Download.10",
    ])
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument()

    // The final page is short and ends the run.
    await user.click(screen.getByRole("button", { name: "Next page" }))
    expect(visibleNames()).toEqual(["Download.11", "Download.12"])
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled()

    await user.click(screen.getByRole("button", { name: "Previous page" }))
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument()
  })

  it("falls back to the last surviving page when the queue drains", async () => {
    const user = userEvent.setup()
    const { rerender } = render(
      <QueueGroup label="qBittorrent" group={group(12)} />,
    )

    await user.click(screen.getByRole("button", { name: "Next page" }))
    await user.click(screen.getByRole("button", { name: "Next page" }))
    expect(screen.getByText("Page 3 of 3")).toBeInTheDocument()

    // The status poll refetches every few seconds: page 3 no longer exists.
    rerender(<QueueGroup label="qBittorrent" group={group(6)} />)

    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument()
    expect(visibleNames()).toEqual(["Download.6"])
  })

  it("hides the pager when the queue fits on one page", () => {
    render(<QueueGroup label="qBittorrent" group={group(5)} />)

    expect(
      screen.queryByRole("button", { name: "Next page" }),
    ).not.toBeInTheDocument()
    expect(visibleNames()).toHaveLength(5)
  })

  it("says so when the backend withheld rows beyond its cap", () => {
    render(<QueueGroup label="SABnzbd" group={group(100, 137)} />)

    expect(
      screen.getByText(
        "SABnzbd reports 137 queued; only the first 100 are listed here.",
      ),
    ).toBeInTheDocument()
    const badge = screen.getByText("137")
    expect(badge).toBeInTheDocument()
  })

  it("omits the withheld notice when every row was returned", () => {
    render(<QueueGroup label="qBittorrent" group={group(12)} />)

    expect(screen.queryByText(/only the first/)).not.toBeInTheDocument()
  })

  it("renders an empty group without a pager", () => {
    render(<QueueGroup label="SABnzbd" group={group(0)} />)

    const heading = screen.getByRole("heading", { name: "SABnzbd" })
    expect(heading).toBeInTheDocument()
    expect(within(heading.parentElement!).getByText("0")).toBeInTheDocument()
    expect(screen.getByText("No queued downloads")).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "Next page" }),
    ).not.toBeInTheDocument()
  })
})
