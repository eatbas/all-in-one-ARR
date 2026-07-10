import { render as rtlRender, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useBandwidthStatus: vi.fn(),
  useUpdateBandwidthSettings: vi.fn(),
}))

import {
  useBandwidthStatus,
  useUpdateBandwidthSettings,
} from "@/shared/lib/queries"
import { Status } from "@/features/bandwidth-controllarr/tabs/Status"
import { TooltipProvider } from "@/shared/components/ui/tooltip"
import type { BandwidthStatus } from "@/shared/lib/api"
import { queryResult } from "@/shared/test/mock-query"
import { expectHelpTooltip } from "@/shared/test/tooltip"

function mutation(mutate: unknown, isPending = false) {
  return { mutate, isPending } as never
}

const BASE: BandwidthStatus = {
  enabled: false,
  status: "Monitoring only",
  last_run_at: "2026-06-26T20:00:00Z",
  check_interval_seconds: 15,
  qbittorrent: {
    online: true,
    speed_mbps: 5.5,
    active_downloads: 0,
    queue_size: 1,
  },
  sabnzbd: {
    online: true,
    speed_mbps: 0,
    active_downloads: 0,
    queue_size: 0,
    paused: false,
  },
  recent_downloads: [],
  queue: { qbittorrent: [], sabnzbd: [] },
}

function render(ui: ReactElement) {
  return rtlRender(<TooltipProvider>{ui}</TooltipProvider>)
}

let updateMutate: ReturnType<typeof vi.fn>

beforeEach(() => {
  updateMutate = vi.fn()
  vi.mocked(useBandwidthStatus).mockReturnValue(queryResult(BASE))
  vi.mocked(useUpdateBandwidthSettings).mockReturnValue(mutation(updateMutate))
})

describe("Status", () => {
  it("renders both client cards", () => {
    const { container } = render(<Status />)
    const statusTab = container.firstElementChild

    expect(statusTab?.children).toHaveLength(3)
    expect(statusTab?.firstElementChild).toContainElement(
      screen.getByText("System Status"),
    )
    expect(statusTab?.firstElementChild).toContainElement(
      screen.getByText("Disabled"),
    )
    expect(screen.getByText("Monitoring only (Disabled)")).toBeInTheDocument()
    expect(screen.getByText("qBittorrent")).toBeInTheDocument()
    expect(screen.getByText("SABnzbd")).toBeInTheDocument()
    expect(screen.getByText("5.50 MB/s")).toBeInTheDocument()
    expect(screen.getByText("RESUMED")).toBeInTheDocument()
    expect(screen.getByText("Recent downloads")).toBeInTheDocument()
    expect(screen.getByText("No recent downloads")).toBeInTheDocument()
  })

  it("uses safe defaults before status data is available", () => {
    vi.mocked(useBandwidthStatus).mockReturnValue(
      queryResult<BandwidthStatus>(undefined),
    )
    render(<Status />)
    expect(screen.getByText("Monitoring only (Disabled)")).toBeInTheDocument()
    expect(screen.getByText("Waiting for first check…")).toBeInTheDocument()
    expect(screen.getAllByText("0.00 MB/s")).toHaveLength(2)
    expect(screen.getAllByText("0").length).toBeGreaterThanOrEqual(4)
    expect(screen.getByText("No recent downloads")).toBeInTheDocument()
  })

  it("renders recent downloads and expandable queue details", async () => {
    const user = userEvent.setup()
    vi.mocked(useBandwidthStatus).mockReturnValue(
      queryResult({
        ...BASE,
        recent_downloads: [
          {
            client: "sabnzbd",
            id: "done",
            name: "Finished.Show",
            status: "Completed",
            progress: 100,
            size_bytes: 1024,
            size_label: "1.0 KB",
            speed_mbps: null,
            eta_seconds: null,
            added_at: "2026-06-26T20:00:00Z",
            completed_at: "2026-06-26T20:30:00Z",
          },
        ],
        queue: {
          qbittorrent: [
            {
              client: "qbittorrent",
              id: "queued",
              name: "Queued.Movie",
              status: "queuedDL",
              progress: 25,
              size_bytes: 2048,
              size_label: "2.0 KB",
              speed_mbps: 0.5,
              eta_seconds: 60,
              added_at: "2026-06-26T20:00:00Z",
              completed_at: null,
            },
          ],
          sabnzbd: [],
        },
      }),
    )

    render(<Status />)

    expect(screen.getByText("Finished.Show")).toBeInTheDocument()
    await user.click(
      screen.getByRole("button", { name: "Expand downloader queue" }),
    )
    expect(screen.getByText("Queued.Movie")).toBeInTheDocument()
  })

  it("shows the active-torrents danger state", () => {
    vi.mocked(useBandwidthStatus).mockReturnValue(
      queryResult({
        ...BASE,
        enabled: true,
        status: "Active torrents — SABnzbd paused",
        qbittorrent: { ...BASE.qbittorrent, active_downloads: 3 },
        sabnzbd: { ...BASE.sabnzbd, paused: true },
      }),
    )
    render(<Status />)
    expect(
      screen.getByText("Active torrents — SABnzbd paused"),
    ).toBeInTheDocument()
    expect(screen.getByText("Enabled")).toBeInTheDocument()
    expect(screen.getByText("PAUSED")).toBeInTheDocument()
  })

  it("toggles bandwidth control on", async () => {
    const user = userEvent.setup()
    render(<Status />)
    const toggle = screen.getByRole("switch", {
      name: "Enable bandwidth control",
    })
    expect(toggle).not.toBeChecked()
    await user.click(toggle)
    expect(updateMutate).toHaveBeenCalledWith({ enabled: true })
  })

  it("shows help for the enable switch", async () => {
    const user = userEvent.setup()
    render(<Status />)
    await expectHelpTooltip(
      user,
      "Explain Enable bandwidth control",
      "Allows SABnzbd to pause while qBittorrent has active torrents and resume when idle.",
    )
  })

  it("reflects the enabled state", () => {
    vi.mocked(useBandwidthStatus).mockReturnValue(
      queryResult({ ...BASE, enabled: true }),
    )
    render(<Status />)
    expect(
      screen.getByRole("switch", { name: "Enable bandwidth control" }),
    ).toBeChecked()
  })

  it("shows a waiting message before the first check", () => {
    vi.mocked(useBandwidthStatus).mockReturnValue(
      queryResult({ ...BASE, last_run_at: null }),
    )
    render(<Status />)
    expect(screen.getByText("Waiting for first check…")).toBeInTheDocument()
  })

  it("disables the switch while the mutation is pending", () => {
    vi.mocked(useUpdateBandwidthSettings).mockReturnValue(
      mutation(updateMutate, true),
    )
    render(<Status />)
    expect(
      screen.getByRole("switch", { name: "Enable bandwidth control" }),
    ).toBeDisabled()
  })
})
