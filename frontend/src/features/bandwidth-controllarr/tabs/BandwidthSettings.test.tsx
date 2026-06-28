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
import { BandwidthSettings } from "@/features/bandwidth-controllarr/tabs/BandwidthSettings"
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
    speed_mbps: 0,
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

describe("BandwidthSettings", () => {
  it("renders the interval select without the master switch", () => {
    render(<BandwidthSettings />)
    expect(
      screen.queryByRole("switch", { name: "Enable bandwidth control" }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole("combobox", { name: "Check interval" })).toHaveTextContent(
      "15 seconds",
    )
  })

  it("changes the check interval", async () => {
    const user = userEvent.setup()
    render(<BandwidthSettings />)
    const combobox = screen.getByRole("combobox", { name: "Check interval" })
    await user.click(combobox)
    await user.click(screen.getByRole("option", { name: "30 seconds" }))
    expect(updateMutate).toHaveBeenCalledWith({ check_interval_seconds: 30 })
  })

  it("shows help for the check interval", async () => {
    const user = userEvent.setup()
    render(<BandwidthSettings />)
    await expectHelpTooltip(
      user,
      "Explain Check interval",
      "How often the bandwidth loop checks qBittorrent and SABnzbd.",
    )
  })

  it("reflects the configured interval", () => {
    vi.mocked(useBandwidthStatus).mockReturnValue(
      queryResult({ ...BASE, check_interval_seconds: 60 }),
    )
    render(<BandwidthSettings />)
    expect(screen.getByRole("combobox", { name: "Check interval" })).toHaveTextContent(
      "60 seconds",
    )
  })

  it("links to /metrics", () => {
    render(<BandwidthSettings />)
    const link = screen.getByRole("link", { name: "Open /metrics" })
    expect(link).toHaveAttribute("href", "/metrics")
    expect(link).toHaveAttribute("target", "_blank")
  })

  it("disables controls while the mutation is pending", () => {
    vi.mocked(useUpdateBandwidthSettings).mockReturnValue(mutation(updateMutate, true))
    render(<BandwidthSettings />)
    expect(screen.getByRole("combobox", { name: "Check interval" })).toBeDisabled()
  })

  it("falls back to defaults while loading", () => {
    vi.mocked(useBandwidthStatus).mockReturnValue(
      queryResult<BandwidthStatus>(undefined),
    )
    render(<BandwidthSettings />)
    expect(
      screen.queryByRole("switch", { name: "Enable bandwidth control" }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole("combobox", { name: "Check interval" })).toHaveTextContent(
      "15 seconds",
    )
  })
})
