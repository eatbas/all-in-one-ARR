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
    enabled: false,
    interval_minutes: 30,
    hourly_cap: 20,
    queue_limit: -1,
    apps: {
      sonarr: { enabled: true, missing_limit: 5, upgrade_limit: 5, monitored_only: true, skip_future: true },
      radarr: { enabled: true, missing_limit: 5, upgrade_limit: 5, monitored_only: true, skip_future: true },
    },
  },
  running: false,
  last_run_at: "2026-06-26T20:00:00Z",
  last_run_status: "completed",
  last_run_detail: "Processed 0 Findarr item(s)",
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

  it("renders the last-run details and per-app cards", () => {
    render(<Status />)
    expect(screen.getByText(/Last run:/)).toBeInTheDocument()
    expect(screen.getByText("Processed 0 Findarr item(s)")).toBeInTheDocument()
    expect(screen.getByText("Connected to Sonarr 4.0.1")).toBeInTheDocument()
    expect(screen.getByText("15")).toBeInTheDocument() // hourly remaining
  })

  it("falls back to placeholders and a Running badge when a run is in progress", () => {
    vi.mocked(useFindarrStatus).mockReturnValue(
      queryResult({
        ...BASE_STATUS,
        running: true,
        last_run_at: null,
        last_run_status: null,
        last_run_detail: null,
        apps: {
          ...BASE_STATUS.apps,
          sonarr: { ...BASE_STATUS.apps.sonarr, compatible: false },
        },
      }),
    )
    render(<Status />)
    expect(screen.getByText("Waiting for first run…")).toBeInTheDocument()
    expect(screen.getByText("No run details yet")).toBeInTheDocument()
    expect(screen.getByText("Running")).toBeInTheDocument()
    expect(screen.getByText("Unchecked")).toBeInTheDocument()
  })

  it("shows Idle when not running and there is no last-run status", () => {
    vi.mocked(useFindarrStatus).mockReturnValue(
      queryResult({ ...BASE_STATUS, running: false, last_run_status: null }),
    )
    render(<Status />)
    expect(screen.getByText("Idle")).toBeInTheDocument()
  })

  it("toggles the enable switch", async () => {
    const user = userEvent.setup()
    render(<Status />)
    await user.click(screen.getByRole("switch", { name: "Enable Findarr" }))
    expect(updateMutate).toHaveBeenCalledWith({ enabled: true })
  })

  it("reflects the enabled label when Findarr is on", () => {
    vi.mocked(useFindarrStatus).mockReturnValue(
      queryResult({ ...BASE_STATUS, settings: { ...BASE_STATUS.settings, enabled: true } }),
    )
    render(<Status />)
    expect(screen.getByText("Enabled")).toBeInTheDocument()
  })

  it("triggers manual runs for all, Sonarr, and Radarr", async () => {
    const user = userEvent.setup()
    render(<Status />)
    await user.click(screen.getByRole("button", { name: "Run all" }))
    expect(runMutate).toHaveBeenCalledWith(undefined)
    await user.click(screen.getByRole("button", { name: "Run Sonarr" }))
    expect(runMutate).toHaveBeenCalledWith("sonarr")
    await user.click(screen.getByRole("button", { name: "Run Radarr" }))
    expect(runMutate).toHaveBeenCalledWith("radarr")
  })

  it("resets processed state after confirmation", async () => {
    const user = userEvent.setup()
    render(<Status />)
    await user.click(screen.getByRole("button", { name: "Reset state" }))
    const dialog = await screen.findByRole("alertdialog")
    await user.click(within(dialog).getByRole("button", { name: "Reset state" }))
    expect(resetMutate).toHaveBeenCalled()
  })
})
