import { render as rtlRender, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useFindarrStatus: vi.fn(),
  useUpdateFindarrSettings: vi.fn(),
  useRunFindarr: vi.fn(),
  useResetFindarrState: vi.fn(),
}))

import {
  useFindarrStatus,
  useResetFindarrState,
  useRunFindarr,
  useUpdateFindarrSettings,
} from "@/shared/lib/queries"
import { Status } from "@/features/findarr/tabs/Status"
import { TooltipProvider } from "@/shared/components/ui/tooltip"
import type { FindarrStatus } from "@/shared/lib/api"
import { queryResult } from "@/shared/test/mock-query"

/** Build a mutation-shaped stub; typed loosely as these are test doubles. */
function mutation(mutate: unknown, isPending = false) {
  return { mutate, isPending } as never
}

const BASE_STATUS: FindarrStatus = {
  settings: {
    enabled: true,
    interval_minutes: 30,
    hourly_cap: 20,
    queue_limit: -1,
    command_sleep_seconds: 0,
    state_reset_hours: 168,
    apps: {
      sonarr: { enabled: true, missing_limit: 5, upgrade_limit: 5, monitored_only: true, skip_future: true, missing_mode: "episodes", upgrade_mode: "episodes" },
      radarr: { enabled: true, missing_limit: 5, upgrade_limit: 5, monitored_only: true, skip_future: true, missing_mode: "episodes", upgrade_mode: "episodes" },
    },
  },
  running: false,
  last_run_at: "2026-06-26T20:00:00Z",
  last_run_status: "completed",
  last_run_detail: "Processed 0 Findarr item(s)",
  state: { created_at: "2026-06-26T20:00:00Z", reset_at: "2026-07-03T20:00:00Z", reset_hours: 168 },
  apps: {
    sonarr: { detail: "Connected to Sonarr 4.0.1", version: "4.0.1", compatible: true, processed: { missing: 1, upgrade: 2 } },
    radarr: { detail: "Connected to Radarr 6.0.0", version: "6.0.0", compatible: true, processed: { missing: 3, upgrade: 4 } },
  },
  hourly: { limit: 20, used: 5, remaining: 15 },
}

function render(ui: ReactElement) {
  return rtlRender(<TooltipProvider>{ui}</TooltipProvider>)
}

let updateMutate: ReturnType<typeof vi.fn>
let runMutate: ReturnType<typeof vi.fn>
let resetMutate: ReturnType<typeof vi.fn>

beforeEach(() => {
  updateMutate = vi.fn()
  runMutate = vi.fn()
  resetMutate = vi.fn()
  vi.mocked(useFindarrStatus).mockReturnValue(queryResult(BASE_STATUS))
  vi.mocked(useUpdateFindarrSettings).mockReturnValue(mutation(updateMutate, false))
  vi.mocked(useRunFindarr).mockReturnValue(mutation(runMutate, false))
  vi.mocked(useResetFindarrState).mockReturnValue(mutation(resetMutate, false))
})

describe("Findarr Status tab", () => {
  it("shows a loading state until the status arrives", () => {
    vi.mocked(useFindarrStatus).mockReturnValue(queryResult<FindarrStatus>(undefined, true))
    render(<Status />)
    expect(screen.getByText("Loading Findarr…")).toBeInTheDocument()
  })

  it("renders the system status and the Live Finds panel", () => {
    render(<Status />)
    expect(screen.getByText(/Last run:/)).toBeInTheDocument()
    expect(screen.getByText("Live Finds Executed")).toBeInTheDocument()
    expect(screen.getByText("20/15 Left")).toBeInTheDocument()
  })

  it("renders each app card with its logo, pills, and counters", () => {
    render(<Status />)

    const sonarrRegion = screen.getByRole("region", { name: "Sonarr" })
    const sonarr = within(sonarrRegion)
    expect(sonarrRegion.querySelector("img")).toHaveAttribute(
      "src",
      "/brand/sonarr.svg",
    )
    expect(sonarr.getByText("Active")).toBeInTheDocument()
    expect(sonarr.getByText("API 5 / 20")).toBeInTheDocument()
    // Pair each counter with its caption so a missing<->upgrade swap is caught.
    expect(sonarr.getByText("Searches Triggered").closest("div")).toHaveTextContent("1")
    expect(sonarr.getByText("Upgrades Triggered").closest("div")).toHaveTextContent("2")

    const radarrRegion = screen.getByRole("region", { name: "Radarr" })
    const radarr = within(radarrRegion)
    expect(radarrRegion.querySelector("img")).toHaveAttribute(
      "src",
      "/brand/radarr.svg",
    )
    expect(radarr.getByText("API 5 / 20")).toBeInTheDocument()
    expect(radarr.getByText("Searches Triggered").closest("div")).toHaveTextContent("3")
    expect(radarr.getByText("Upgrades Triggered").closest("div")).toHaveTextContent("4")
  })

  it("shows the waiting placeholder and pauses a disabled app", () => {
    vi.mocked(useFindarrStatus).mockReturnValue(
      queryResult({
        ...BASE_STATUS,
        last_run_at: null,
        settings: {
          ...BASE_STATUS.settings,
          apps: {
            ...BASE_STATUS.settings.apps,
            sonarr: { ...BASE_STATUS.settings.apps.sonarr, enabled: false },
          },
        },
      }),
    )
    render(<Status />)
    expect(screen.getByText("Waiting for first run…")).toBeInTheDocument()
    const sonarr = within(screen.getByRole("region", { name: "Sonarr" }))
    expect(sonarr.getByText("Paused")).toBeInTheDocument()
    const radarr = within(screen.getByRole("region", { name: "Radarr" }))
    expect(radarr.getByText("Active")).toBeInTheDocument()
  })

  it("pauses every app and shows Disabled when Findarr is globally off", () => {
    vi.mocked(useFindarrStatus).mockReturnValue(
      queryResult({
        ...BASE_STATUS,
        settings: { ...BASE_STATUS.settings, enabled: false },
      }),
    )
    render(<Status />)
    expect(screen.getByText("Disabled")).toBeInTheDocument()
    expect(
      within(screen.getByRole("region", { name: "Sonarr" })).getByText("Paused"),
    ).toBeInTheDocument()
    expect(
      within(screen.getByRole("region", { name: "Radarr" })).getByText("Paused"),
    ).toBeInTheDocument()
  })

  it("toggles the enable switch", async () => {
    const user = userEvent.setup()
    render(<Status />)
    await user.click(screen.getByRole("switch", { name: "Enable Findarr" }))
    expect(updateMutate).toHaveBeenCalledWith({ enabled: false })
  })

  it("reflects the enabled label when Findarr is on", () => {
    render(<Status />)
    expect(screen.getByText("Enabled")).toBeInTheDocument()
  })

  it("runs all apps from the panel header", async () => {
    const user = userEvent.setup()
    render(<Status />)
    await user.click(screen.getByRole("button", { name: "Run all" }))
    expect(runMutate).toHaveBeenCalledWith(undefined)
  })

  it("runs a single app from its card", async () => {
    const user = userEvent.setup()
    render(<Status />)
    await user.click(screen.getByRole("button", { name: "Run Sonarr" }))
    expect(runMutate).toHaveBeenCalledWith("sonarr")
    await user.click(screen.getByRole("button", { name: "Run Radarr" }))
    expect(runMutate).toHaveBeenCalledWith("radarr")
  })

  it("resets processed state from the panel header after confirmation", async () => {
    const user = userEvent.setup()
    render(<Status />)
    await user.click(screen.getByRole("button", { name: "Reset" }))
    const dialog = await screen.findByRole("alertdialog")
    await user.click(within(dialog).getByRole("button", { name: "Reset" }))
    expect(resetMutate).toHaveBeenCalled()
  })

  it("disables the header controls while a run or reset is pending", () => {
    vi.mocked(useRunFindarr).mockReturnValue(mutation(runMutate, true))
    vi.mocked(useResetFindarrState).mockReturnValue(mutation(resetMutate, true))
    render(<Status />)
    expect(screen.getByRole("button", { name: "Run all" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Reset" })).toBeDisabled()
  })
})
