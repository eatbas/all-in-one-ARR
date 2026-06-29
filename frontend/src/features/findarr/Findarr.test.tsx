import { render as rtlRender, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useFindarrStatus: vi.fn(),
  useFindarrSettings: vi.fn(),
  useFindarrHistory: vi.fn(),
  useUpdateFindarrSettings: vi.fn(),
  useRunFindarr: vi.fn(),
  useResetFindarrState: vi.fn(),
}))

import type { FindarrSettings, FindarrStatus } from "@/shared/lib/api"
import { Findarr } from "@/features/findarr/Findarr"
import { FINDARR_TAB_STORAGE_KEY } from "@/features/findarr/findarr-tab"
import { TooltipProvider } from "@/shared/components/ui/tooltip"
import {
  useFindarrHistory,
  useFindarrSettings,
  useFindarrStatus,
  useResetFindarrState,
  useRunFindarr,
  useUpdateFindarrSettings,
} from "@/shared/lib/queries"
import { mutationResult, queryResult } from "@/shared/test/mock-query"
import { expectHelpTooltip } from "@/shared/test/tooltip"

const SETTINGS: FindarrSettings = {
  enabled: false,
  interval_minutes: 30,
  hourly_cap: 20,
  queue_limit: -1,
  apps: {
    sonarr: {
      enabled: true,
      missing_limit: 5,
      upgrade_limit: 5,
      monitored_only: true,
      skip_future: true,
    },
    radarr: {
      enabled: true,
      missing_limit: 5,
      upgrade_limit: 5,
      monitored_only: true,
      skip_future: true,
    },
  },
}

const STATUS: FindarrStatus = {
  settings: SETTINGS,
  running: false,
  last_run_at: "2026-06-26T20:00:00Z",
  last_run_status: "completed",
  last_run_detail: "Processed 0 Findarr item(s)",
  apps: {
    sonarr: {
      detail: "Connected to Sonarr 4.0.1",
      version: "4.0.1",
      compatible: true,
      processed: { missing: 1, upgrade: 2 },
    },
    radarr: {
      detail: "Connected to Radarr 6.0.0",
      version: "6.0.0",
      compatible: true,
      processed: { missing: 3, upgrade: 4 },
    },
  },
  hourly: { limit: 20, used: 5, remaining: 15 },
}

function render(ui: ReactElement) {
  return rtlRender(<TooltipProvider>{ui}</TooltipProvider>)
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(useFindarrStatus).mockReturnValue(queryResult(STATUS))
  vi.mocked(useFindarrSettings).mockReturnValue(queryResult(SETTINGS))
  vi.mocked(useFindarrHistory).mockReturnValue(
    queryResult([
      {
        id: 1,
        ts: "2026-06-26T20:00:00Z",
        app: "sonarr",
        mode: "missing",
        item_id: "1",
        title: "Series S01E01 - Pilot",
        status: "success",
        detail: "Triggered Sonarr missing search",
      },
    ]),
  )
  vi.mocked(useUpdateFindarrSettings).mockReturnValue(
    mutationResult(vi.fn(), false),
  )
  vi.mocked(useRunFindarr).mockReturnValue(mutationResult(vi.fn(), false))
  vi.mocked(useResetFindarrState).mockReturnValue(mutationResult(vi.fn(), false))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("Findarr", () => {
  it("defaults to the Status tab and shows app cards", () => {
    render(<Findarr />)
    expect(screen.getByRole("tab", { name: "Status" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    expect(screen.getByRole("region", { name: "Sonarr" })).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "Radarr" })).toBeInTheDocument()
  })

  it("switches to Settings and persists the tab", async () => {
    const user = userEvent.setup()
    render(<Findarr />)
    await user.click(screen.getByRole("tab", { name: "Settings" }))
    expect(localStorage.getItem(FINDARR_TAB_STORAGE_KEY)).toBe("settings")
    expect(screen.getByText("Findarr scheduler")).toBeInTheDocument()
  })

  it("shows help for settings controls", async () => {
    const user = userEvent.setup()
    render(<Findarr />)
    await user.click(screen.getByRole("tab", { name: "Settings" }))
    await expectHelpTooltip(
      user,
      "Explain Findarr interval",
      "How often Findarr wakes up to run automatic searches.",
    )
  })

  it("shows help for the status enable control", async () => {
    const user = userEvent.setup()
    render(<Findarr />)
    await expectHelpTooltip(
      user,
      "Explain Enable Findarr",
      "Allows the scheduler to run bounded missing and upgrade searches.",
    )
  })

  it("renders history rows", async () => {
    const user = userEvent.setup()
    render(<Findarr />)
    await user.click(screen.getByRole("tab", { name: "History" }))
    expect(screen.getByText("Series S01E01 - Pilot")).toBeInTheDocument()
    expect(screen.getByText("Triggered Sonarr missing search")).toBeInTheDocument()
  })

  it("ignores bad stored tabs and survives missing localStorage", async () => {
    localStorage.setItem(FINDARR_TAB_STORAGE_KEY, "bad")
    const first = render(<Findarr />)
    expect(screen.getByRole("tab", { name: "Status" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    first.unmount()

    vi.stubGlobal("localStorage", undefined)
    const user = userEvent.setup()
    render(<Findarr />)
    await user.click(screen.getByRole("tab", { name: "Settings" }))
    expect(screen.getAllByText("Findarr scheduler").length).toBeGreaterThan(0)
  })

  it("restores a valid stored tab on mount", () => {
    localStorage.setItem(FINDARR_TAB_STORAGE_KEY, "settings")
    render(<Findarr />)
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
  })
})
