import { render as rtlRender, screen, fireEvent, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useFindarrSettings: vi.fn(),
  useFindarrStatus: vi.fn(),
  useUpdateFindarrSettings: vi.fn(),
  useResetFindarrState: vi.fn(),
}))

import {
  useFindarrSettings,
  useFindarrStatus,
  useResetFindarrState,
  useUpdateFindarrSettings,
} from "@/shared/lib/queries"
import { Settings } from "@/features/findarr/tabs/Settings"
import { TooltipProvider } from "@/shared/components/ui/tooltip"
import type { FindarrSettings, FindarrStatus } from "@/shared/lib/api"
import { queryResult } from "@/shared/test/mock-query"

/** Build a mutation-shaped stub; typed loosely as these are test doubles. */
function mutation(mutate: unknown, isPending = false) {
  return { mutate, isPending } as never
}

const SETTINGS: FindarrSettings = {
  enabled: false,
  interval_minutes: 30,
  hourly_cap: 20,
  queue_limit: -1,
  command_sleep_seconds: 0,
  state_reset_hours: 168,
  apps: {
    sonarr: {
      enabled: true,
      missing_limit: 5,
      upgrade_limit: 5,
      monitored_only: true,
      skip_future: true,
      missing_mode: "episodes",
      upgrade_mode: "episodes",
    },
    radarr: {
      enabled: true,
      missing_limit: 5,
      upgrade_limit: 5,
      monitored_only: true,
      skip_future: true,
      missing_mode: "episodes",
      upgrade_mode: "episodes",
    },
  },
}

const STATUS: FindarrStatus = {
  settings: SETTINGS,
  running: false,
  last_run_at: null,
  last_run_status: null,
  last_run_detail: null,
  state: {
    created_at: "2026-06-26T20:00:00Z",
    reset_at: "2026-07-03T20:00:00Z",
    reset_hours: 168,
  },
  apps: {
    sonarr: { detail: "ok", version: "4.0.1", compatible: true, processed: { missing: 0, upgrade: 0 } },
    radarr: { detail: "ok", version: "6.0.0", compatible: true, processed: { missing: 0, upgrade: 0 } },
  },
  hourly: { limit: 20, used: 0, remaining: 20 },
}

function render(ui: ReactElement) {
  return rtlRender(<TooltipProvider>{ui}</TooltipProvider>)
}

let updateMutate: ReturnType<typeof vi.fn>
let resetMutate: ReturnType<typeof vi.fn>

beforeEach(() => {
  updateMutate = vi.fn()
  resetMutate = vi.fn()
  vi.mocked(useFindarrSettings).mockReturnValue(queryResult(SETTINGS))
  vi.mocked(useFindarrStatus).mockReturnValue(queryResult(STATUS))
  vi.mocked(useUpdateFindarrSettings).mockReturnValue(mutation(updateMutate, false))
  vi.mocked(useResetFindarrState).mockReturnValue(mutation(resetMutate, false))
})

describe("Findarr Settings tab", () => {
  it("shows a loading state until settings arrive", () => {
    vi.mocked(useFindarrSettings).mockReturnValue(queryResult<FindarrSettings>(undefined, true))
    render(<Settings />)
    expect(screen.getByText("Loading settings…")).toBeInTheDocument()
  })

  it("toggles the scheduler enable switch", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("switch", { name: "Enable Findarr" }))
    expect(updateMutate).toHaveBeenCalledWith({ enabled: true })
  })

  it("reflects the enabled state in the label", () => {
    vi.mocked(useFindarrSettings).mockReturnValue(
      queryResult({ ...SETTINGS, enabled: true }),
    )
    render(<Settings />)
    expect(screen.getByText("Enabled")).toBeInTheDocument()
  })

  it("changes the interval via the select", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("combobox", { name: "Interval" }))
    await user.click(screen.getByRole("option", { name: "45 minutes" }))
    expect(updateMutate).toHaveBeenCalledWith({ interval_minutes: 45 })
  })

  it("edits the hourly cap, queue limit, and sleep duration numbers", () => {
    render(<Settings />)
    fireEvent.change(screen.getByLabelText("Hourly cap"), { target: { value: "10" } })
    expect(updateMutate).toHaveBeenCalledWith({ hourly_cap: 10 })
    fireEvent.change(screen.getByLabelText("Queue limit"), { target: { value: "3" } })
    expect(updateMutate).toHaveBeenCalledWith({ queue_limit: 3 })
    fireEvent.change(screen.getByLabelText("Sleep duration"), { target: { value: "5" } })
    expect(updateMutate).toHaveBeenCalledWith({ command_sleep_seconds: 5 })
  })

  it("toggles the per-app switches for Sonarr", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("switch", { name: "Enable Sonarr" }))
    expect(updateMutate).toHaveBeenCalledWith({ apps: { sonarr: { enabled: false } } })
    await user.click(screen.getByRole("switch", { name: "Sonarr monitored only" }))
    expect(updateMutate).toHaveBeenCalledWith({ apps: { sonarr: { monitored_only: false } } })
    await user.click(screen.getByRole("switch", { name: "Sonarr skip future" }))
    expect(updateMutate).toHaveBeenCalledWith({ apps: { sonarr: { skip_future: false } } })
  })

  it("edits the per-app cycle limits", () => {
    render(<Settings />)
    // Two apps share each label; index 0 is Sonarr, 1 is Radarr.
    fireEvent.change(screen.getAllByLabelText("Missing per cycle")[0], {
      target: { value: "7" },
    })
    expect(updateMutate).toHaveBeenCalledWith({ apps: { sonarr: { missing_limit: 7 } } })
    fireEvent.change(screen.getAllByLabelText("Upgrades per cycle")[1], {
      target: { value: "9" },
    })
    expect(updateMutate).toHaveBeenCalledWith({ apps: { radarr: { upgrade_limit: 9 } } })
  })

  it("offers the Sonarr search modes only for Sonarr", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    // The mode selectors are Sonarr-only, so each label appears exactly once.
    expect(screen.getAllByText("Missing search mode")).toHaveLength(1)
    expect(screen.getAllByText("Upgrade mode")).toHaveLength(1)

    await user.click(screen.getByRole("combobox", { name: "Missing search mode" }))
    await user.click(screen.getByRole("option", { name: "Seasons" }))
    expect(updateMutate).toHaveBeenCalledWith({ apps: { sonarr: { missing_mode: "seasons" } } })

    await user.click(screen.getByRole("combobox", { name: "Upgrade mode" }))
    await user.click(screen.getByRole("option", { name: "Shows" }))
    expect(updateMutate).toHaveBeenCalledWith({ apps: { sonarr: { upgrade_mode: "shows" } } })
  })

  it("shows the stateful-management window and edits the reset hours", () => {
    render(<Settings />)
    expect(screen.getByText("Initial state created")).toBeInTheDocument()
    expect(screen.getByText("State reset date")).toBeInTheDocument()
    expect(screen.queryByText("Not created yet")).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText("State reset (hours)"), {
      target: { value: "72" },
    })
    expect(updateMutate).toHaveBeenCalledWith({ state_reset_hours: 72 })
  })

  it("shows placeholders when no state window exists yet", () => {
    vi.mocked(useFindarrStatus).mockReturnValue(queryResult<FindarrStatus>(undefined))
    render(<Settings />)
    expect(screen.getByText("Not created yet")).toBeInTheDocument()
    expect(screen.getByText("—")).toBeInTheDocument()
  })

  it("triggers an emergency reset after confirmation", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("button", { name: "Emergency reset" }))
    const dialog = await screen.findByRole("alertdialog")
    await user.click(within(dialog).getByRole("button", { name: "Reset" }))
    expect(resetMutate).toHaveBeenCalled()
  })
})
