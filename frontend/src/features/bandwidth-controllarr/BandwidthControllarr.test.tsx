import { render as rtlRender, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useBandwidthStatus: vi.fn(),
  useUpdateBandwidthSettings: vi.fn(),
}))

import {
  useBandwidthStatus,
  useUpdateBandwidthSettings,
} from "@/shared/lib/queries"
import { BandwidthControllarr } from "@/features/bandwidth-controllarr/BandwidthControllarr"
import { BANDWIDTH_CONTROLLARR_TAB_STORAGE_KEY } from "@/features/bandwidth-controllarr/bandwidth-controllarr-tab"
import { TooltipProvider } from "@/shared/components/ui/tooltip"
import type { BandwidthStatus } from "@/shared/lib/api"
import { queryResult } from "@/shared/test/mock-query"
import { expectHelpTooltip } from "@/shared/test/tooltip"

function mutation(mutate: unknown, isPending = false) {
  return { mutate, isPending } as never
}

const STATUS: BandwidthStatus = {
  enabled: false,
  status: "Monitoring only",
  last_run_at: "2026-06-26T20:00:00Z",
  check_interval_seconds: 15,
  qbittorrent: {
    online: true,
    speed_mbps: 5.5,
    active_downloads: 0,
    queue_size: 0,
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

beforeEach(() => {
  localStorage.clear()
  vi.mocked(useBandwidthStatus).mockReturnValue(queryResult(STATUS))
  vi.mocked(useUpdateBandwidthSettings).mockReturnValue(mutation(vi.fn()))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("BandwidthControllarr", () => {
  it("defaults to the Status tab", () => {
    render(<BandwidthControllarr />)
    expect(screen.getByRole("tab", { name: "Status" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    expect(screen.getByText("qBittorrent")).toBeInTheDocument()
    expect(screen.getByText("SABnzbd")).toBeInTheDocument()
  })

  it("switches to the Settings tab and persists the choice", async () => {
    const user = userEvent.setup()
    render(<BandwidthControllarr />)
    await user.click(screen.getByRole("tab", { name: "Settings" }))
    expect(localStorage.getItem(BANDWIDTH_CONTROLLARR_TAB_STORAGE_KEY)).toBe(
      "settings",
    )
    expect(
      screen.getByText((text) => text.includes("Control when SABnzbd pauses")),
    ).toBeInTheDocument()
  })

  it("shows help for settings controls", async () => {
    const user = userEvent.setup()
    render(<BandwidthControllarr />)
    await user.click(screen.getByRole("tab", { name: "Settings" }))
    await expectHelpTooltip(
      user,
      "Explain Check interval",
      "How often the bandwidth loop checks qBittorrent and SABnzbd.",
    )
  })

  it("shows help for the status enable control", async () => {
    const user = userEvent.setup()
    render(<BandwidthControllarr />)
    await expectHelpTooltip(
      user,
      "Explain Enable bandwidth control",
      "Allows SABnzbd to pause while qBittorrent has active torrents and resume when idle.",
    )
  })

  it("restores the Settings tab from localStorage", () => {
    localStorage.setItem(BANDWIDTH_CONTROLLARR_TAB_STORAGE_KEY, "settings")
    render(<BandwidthControllarr />)
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
  })

  it("ignores an unknown stored tab and falls back to Status", () => {
    localStorage.setItem(BANDWIDTH_CONTROLLARR_TAB_STORAGE_KEY, "bogus")
    render(<BandwidthControllarr />)
    expect(screen.getByRole("tab", { name: "Status" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
  })

  it("stays usable when localStorage is unavailable", async () => {
    vi.stubGlobal("localStorage", undefined)
    const user = userEvent.setup()
    render(<BandwidthControllarr />)
    expect(screen.getByRole("tab", { name: "Status" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    await user.click(screen.getByRole("tab", { name: "Settings" }))
    expect(
      screen.getByText((text) => text.includes("Control when SABnzbd pauses")),
    ).toBeInTheDocument()
  })
})
