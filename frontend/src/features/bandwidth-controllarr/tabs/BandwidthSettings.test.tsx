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
  tracking_suspended: false,
  manual_paused_clients: [],
  check_interval_seconds: 15,
  sab_limit_enabled: false,
  sab_limit_mbps: 5,
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
  download_history: [],
  queue: {
    qbittorrent: { items: [], total: 0 },
    sabnzbd: { items: [], total: 0 },
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
    expect(
      screen.getByRole("combobox", { name: "Check interval" }),
    ).toHaveTextContent("15 seconds")
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
    expect(
      screen.getByRole("combobox", { name: "Check interval" }),
    ).toHaveTextContent("60 seconds")
  })

  it("links to /metrics", () => {
    render(<BandwidthSettings />)
    const link = screen.getByRole("link", { name: "Open /metrics" })
    expect(link).toHaveAttribute("href", "/metrics")
    expect(link).toHaveAttribute("target", "_blank")
  })

  it("disables controls while the mutation is pending", () => {
    vi.mocked(useUpdateBandwidthSettings).mockReturnValue(
      mutation(updateMutate, true),
    )
    render(<BandwidthSettings />)
    expect(
      screen.getByRole("combobox", { name: "Check interval" }),
    ).toBeDisabled()
  })

  it("falls back to defaults while loading", () => {
    vi.mocked(useBandwidthStatus).mockReturnValue(
      queryResult<BandwidthStatus>(undefined),
    )
    render(<BandwidthSettings />)
    expect(
      screen.queryByRole("switch", { name: "Enable bandwidth control" }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole("combobox", { name: "Check interval" }),
    ).toHaveTextContent("15 seconds")
    expect(
      screen.getByRole("switch", { name: "SABnzbd download limiter" }),
    ).not.toBeChecked()
    expect(limitInput()).toHaveValue(5)
    expect(limitInput()).toBeDisabled()
  })
})

function limitInput() {
  return screen.getByRole("spinbutton", { name: "Download limit (MB/s)" })
}

/** Status with the limiter switched on, so the MB/s input is editable. */
function limiterOn(overrides: Partial<BandwidthStatus> = {}): BandwidthStatus {
  return { ...BASE, sab_limit_enabled: true, ...overrides }
}

describe("SABnzbd download limiter", () => {
  it("renders the toggle off with a disabled input by default", () => {
    render(<BandwidthSettings />)
    expect(
      screen.getByRole("switch", { name: "SABnzbd download limiter" }),
    ).not.toBeChecked()
    expect(limitInput()).toHaveValue(5)
    expect(limitInput()).toBeDisabled()
  })

  it("enables the limiter through the toggle", async () => {
    const user = userEvent.setup()
    render(<BandwidthSettings />)
    await user.click(
      screen.getByRole("switch", { name: "SABnzbd download limiter" }),
    )
    expect(updateMutate).toHaveBeenCalledWith({ sab_limit_enabled: true })
  })

  it("disables the limiter through the toggle", async () => {
    const user = userEvent.setup()
    vi.mocked(useBandwidthStatus).mockReturnValue(queryResult(limiterOn()))
    render(<BandwidthSettings />)
    await user.click(
      screen.getByRole("switch", { name: "SABnzbd download limiter" }),
    )
    expect(updateMutate).toHaveBeenCalledWith({ sab_limit_enabled: false })
  })

  it("commits an edited limit on blur", async () => {
    const user = userEvent.setup()
    vi.mocked(useBandwidthStatus).mockReturnValue(queryResult(limiterOn()))
    render(<BandwidthSettings />)
    await user.clear(limitInput())
    await user.type(limitInput(), "7.5")
    await user.tab()
    expect(updateMutate).toHaveBeenCalledWith({ sab_limit_mbps: 7.5 })
  })

  it("commits an edited limit on Enter", async () => {
    const user = userEvent.setup()
    vi.mocked(useBandwidthStatus).mockReturnValue(queryResult(limiterOn()))
    render(<BandwidthSettings />)
    await user.clear(limitInput())
    await user.type(limitInput(), "2.5{Enter}")
    expect(updateMutate).toHaveBeenCalledWith({ sab_limit_mbps: 2.5 })
    // The Enter commit cleared the draft, so the following blur is a no-op.
    await user.tab()
    expect(updateMutate).toHaveBeenCalledTimes(1)
  })

  it("clamps the committed limit to the allowed bounds", async () => {
    const user = userEvent.setup()
    vi.mocked(useBandwidthStatus).mockReturnValue(queryResult(limiterOn()))
    render(<BandwidthSettings />)
    await user.clear(limitInput())
    await user.type(limitInput(), "5000{Enter}")
    expect(updateMutate).toHaveBeenCalledWith({ sab_limit_mbps: 1024 })
    await user.clear(limitInput())
    await user.type(limitInput(), "0.05{Enter}")
    expect(updateMutate).toHaveBeenCalledWith({ sab_limit_mbps: 0.1 })
  })

  it("does not mutate for an unchanged, empty, or non-positive value", async () => {
    const user = userEvent.setup()
    vi.mocked(useBandwidthStatus).mockReturnValue(queryResult(limiterOn()))
    render(<BandwidthSettings />)
    // Unchanged: retyping the server value must not issue a PUT.
    await user.clear(limitInput())
    await user.type(limitInput(), "5{Enter}")
    // Empty: clearing and leaving must not issue a PUT.
    await user.clear(limitInput())
    await user.tab()
    // Non-positive: zero is rejected client-side.
    await user.clear(limitInput())
    await user.type(limitInput(), "0{Enter}")
    // Blur without any edit exercises the null-draft no-op path.
    await user.click(limitInput())
    await user.tab()
    expect(updateMutate).not.toHaveBeenCalled()
  })

  it("keeps the draft when a fresh status arrives while editing", async () => {
    const user = userEvent.setup()
    vi.mocked(useBandwidthStatus).mockReturnValue(queryResult(limiterOn()))
    const view = render(<BandwidthSettings />)
    await user.clear(limitInput())
    await user.type(limitInput(), "7.5")
    // A poll lands mid-edit with a different server value…
    vi.mocked(useBandwidthStatus).mockReturnValue(
      queryResult(limiterOn({ sab_limit_mbps: 9 })),
    )
    view.rerender(
      <TooltipProvider>
        <BandwidthSettings />
      </TooltipProvider>,
    )
    // …and the half-typed draft survives instead of being clobbered.
    expect(limitInput()).toHaveValue(7.5)
  })

  it("shows help for the limiter", async () => {
    const user = userEvent.setup()
    render(<BandwidthSettings />)
    await expectHelpTooltip(
      user,
      "Explain Download limit (MB/s)",
      "Caps SABnzbd's download speed at the configured MB/s. The cap is re-applied if SABnzbd loses it, for example after a restart.",
    )
  })

  it("disables the limiter controls while the mutation is pending", () => {
    vi.mocked(useBandwidthStatus).mockReturnValue(queryResult(limiterOn()))
    vi.mocked(useUpdateBandwidthSettings).mockReturnValue(
      mutation(updateMutate, true),
    )
    render(<BandwidthSettings />)
    expect(
      screen.getByRole("switch", { name: "SABnzbd download limiter" }),
    ).toBeDisabled()
    expect(limitInput()).toBeDisabled()
  })
})
