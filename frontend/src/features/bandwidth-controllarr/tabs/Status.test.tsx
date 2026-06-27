import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
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
import type { BandwidthStatus } from "@/shared/lib/api"
import { queryResult } from "@/shared/test/mock-query"

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
}

let updateMutate: ReturnType<typeof vi.fn>

beforeEach(() => {
  updateMutate = vi.fn()
  vi.mocked(useBandwidthStatus).mockReturnValue(queryResult(BASE))
  vi.mocked(useUpdateBandwidthSettings).mockReturnValue(mutation(updateMutate))
})

describe("Status", () => {
  it("renders both client cards", () => {
    render(<Status />)
    expect(screen.getByText("qBittorrent")).toBeInTheDocument()
    expect(screen.getByText("SABnzbd")).toBeInTheDocument()
    expect(screen.getByText("5.50 MB/s")).toBeInTheDocument()
    expect(screen.getByText("RESUMED")).toBeInTheDocument()
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
    expect(screen.getByText("Active torrents — SABnzbd paused")).toBeInTheDocument()
    expect(screen.getByText("PAUSED")).toBeInTheDocument()
    expect(screen.getByText("Control active")).toBeInTheDocument()
  })

  it("toggles bandwidth control on", async () => {
    const user = userEvent.setup()
    render(<Status />)
    const toggle = screen.getByRole("switch", { name: "Enable bandwidth control" })
    expect(toggle).not.toBeChecked()
    await user.click(toggle)
    expect(updateMutate).toHaveBeenCalledWith({ enabled: true })
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
    vi.mocked(useUpdateBandwidthSettings).mockReturnValue(mutation(updateMutate, true))
    render(<Status />)
    expect(
      screen.getByRole("switch", { name: "Enable bandwidth control" }),
    ).toBeDisabled()
  })
})
