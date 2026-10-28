import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useCleanarrQueue: vi.fn(),
  useCleanarrStatus: vi.fn(),
  useIgnoreCleanarrDownload: vi.fn(),
}))

import { Queue } from "@/features/cleanarr/tabs/Queue"
import type { CleanarrQueue, CleanarrStatus } from "@/shared/lib/api"
import {
  useCleanarrQueue,
  useCleanarrStatus,
  useIgnoreCleanarrDownload,
} from "@/shared/lib/queries"
import {
  CLEANARR_QUEUE,
  CLEANARR_STATUS,
  cleanarrQueueItem,
} from "@/shared/test/cleanarr-fixtures"
import { mutationResult, queryResult } from "@/shared/test/mock-query"

const ignore = vi.fn()

function withQueue(overrides: Partial<CleanarrQueue> = {}) {
  vi.mocked(useCleanarrQueue).mockReturnValue(
    queryResult({ ...CLEANARR_QUEUE, ...overrides }),
  )
}

function rowFor(title: string) {
  return within(screen.getByText(title).closest("tr") as HTMLElement)
}

beforeEach(() => {
  withQueue()
  vi.mocked(useCleanarrStatus).mockReturnValue(queryResult(CLEANARR_STATUS))
  vi.mocked(useIgnoreCleanarrDownload).mockReturnValue(
    mutationResult(ignore, false),
  )
})

describe("Cleanarr Queue tab", () => {
  it("shows a loading state", () => {
    vi.mocked(useCleanarrQueue).mockReturnValue(
      queryResult<CleanarrQueue>(undefined, true),
    )
    render(<Queue />)
    expect(screen.getByText("Loading queue…")).toBeInTheDocument()
  })

  it("shows a load error", () => {
    vi.mocked(useCleanarrQueue).mockReturnValue(
      queryResult<CleanarrQueue>(undefined, false, {
        isError: true,
        error: new Error("timeout"),
      }),
    )
    render(<Queue />)
    expect(
      screen.getByText("Could not load the queue: timeout"),
    ).toBeInTheDocument()
  })

  it("explains the strike rule with the scheduler settings", () => {
    render(<Queue />)
    expect(
      screen.getByText(
        "Usenet items stuck in a failed import or failed download. An item is removed and blocklisted after 3 strikes (one per run, every 10 minutes); up to 10 removals per run.",
      ),
    ).toBeInTheDocument()
  })

  it("explains the strike rule before the status loads", () => {
    vi.mocked(useCleanarrStatus).mockReturnValue(
      queryResult<CleanarrStatus>(undefined, true),
    )
    withQueue({ items: [], errors: { radarr: "Connection refused." } })
    render(<Queue />)
    expect(
      screen.getByText(/blocklisted after 3 strikes\.$/),
    ).toBeInTheDocument()
    expect(
      screen.getByText("Radarr: queue unavailable. Connection refused."),
    ).toBeInTheDocument()
    expect(
      screen.getByText("No stuck or failed downloads in the queue."),
    ).toBeInTheDocument()
  })

  it("explains why a queue read holds downloads", () => {
    const held =
      "Queue cleaning held: a queue record could not be matched to a download, or the queue was only read in part. Strikes left unchanged."
    withQueue({
      items: [cleanarrQueueItem({ would_remove: false })],
      held: { sonarr: held },
    })
    render(<Queue />)
    expect(screen.getByText(`Sonarr — ${held}`)).toHaveClass("text-amber-600")
    const row = rowFor("The.Last.of.Us.S02E03.1080p")
    expect(row.getByText("3 / 3")).not.toHaveClass("font-medium")
    expect(row.queryByText("Would remove")).not.toBeInTheDocument()
    expect(row.getByText("—")).toBeInTheDocument()
  })

  it("shows the next-run badge for dry run and live", () => {
    const view = render(<Queue />)
    const row = rowFor("The.Last.of.Us.S02E03.1080p")
    expect(row.getByText("Sonarr")).toBeInTheDocument()
    expect(row.getByText("Failed import")).toBeInTheDocument()
    expect(row.getByText("3 / 3")).toHaveClass("font-medium")
    expect(row.getByText("Would remove")).toBeInTheDocument()
    view.unmount()

    withQueue({ dry_run: false })
    render(<Queue />)
    expect(screen.getByText("Will remove next run")).toBeInTheDocument()
  })

  it("lets long message paths wrap inside their cell", () => {
    const message = `Import failed: /downloads/complete/tv/${"Very.Long.Release.Name.".repeat(6)}mkv`
    withQueue({ items: [cleanarrQueueItem({ message })] })
    render(<Queue />)
    // jsdom has no layout, so the wrapping rule is asserted on the cell; the
    // overflow-wrap value keeps an unbroken path from overlapping the strikes.
    expect(screen.getByText(message)).toHaveClass(
      "whitespace-normal",
      "wrap-anywhere",
    )
  })

  it("renders ignored, excluded and building-up items", () => {
    withQueue({
      items: [
        cleanarrQueueItem({
          download_id: "a",
          title: "Ignored.Item",
          ignored: true,
          would_remove: false,
        }),
        cleanarrQueueItem({
          download_id: "b",
          title: "Excluded.Item",
          excluded: true,
          strikes: 0,
          would_remove: false,
        }),
        cleanarrQueueItem({
          download_id: "c",
          app: "radarr",
          title: "Failed.Download",
          reason: "failed_download",
          message: "",
          strikes: 2,
          would_remove: false,
        }),
      ],
    })
    render(<Queue />)

    const ignored = rowFor("Ignored.Item")
    expect(ignored.getByText("Ignored")).toBeInTheDocument()
    expect(ignored.getByText("—")).toHaveClass("text-muted-foreground")
    expect(ignored.queryByRole("button")).not.toBeInTheDocument()

    const excluded = rowFor("Excluded.Item")
    expect(excluded.getByText("Excluded by pattern")).toBeInTheDocument()
    expect(excluded.getByText("0 / 3")).toHaveClass("text-muted-foreground")

    const building = rowFor("Failed.Download")
    expect(building.getByText("Radarr")).toBeInTheDocument()
    expect(building.getByText("Failed download")).toBeInTheDocument()
    expect(building.getByText("2 / 3")).not.toHaveClass("font-medium")
    expect(building.getAllByText("—")).toHaveLength(2)
  })

  it("ignores a download with its title", async () => {
    const user = userEvent.setup()
    render(<Queue />)
    await user.click(screen.getByRole("button", { name: "Ignore" }))
    expect(ignore).toHaveBeenCalledWith({
      downloadId: "SABnzbd_nzo_1",
      title: "The.Last.of.Us.S02E03.1080p",
    })
  })

  it("disables Ignore while one is pending", () => {
    vi.mocked(useIgnoreCleanarrDownload).mockReturnValue(
      mutationResult(ignore, true),
    )
    render(<Queue />)
    expect(screen.getByRole("button", { name: "Ignore" })).toBeDisabled()
  })
})
