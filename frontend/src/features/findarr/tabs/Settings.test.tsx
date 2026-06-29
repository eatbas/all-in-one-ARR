import { render as rtlRender, screen, fireEvent } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useFindarrSettings: vi.fn(),
  useUpdateFindarrSettings: vi.fn(),
}))

import {
  useFindarrSettings,
  useUpdateFindarrSettings,
} from "@/shared/lib/queries"
import { Settings } from "@/features/findarr/tabs/Settings"
import { TooltipProvider } from "@/shared/components/ui/tooltip"
import type { FindarrSettings } from "@/shared/lib/api"
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
  apps: {
    sonarr: { enabled: true, missing_limit: 5, upgrade_limit: 5, monitored_only: true, skip_future: true },
    radarr: { enabled: true, missing_limit: 5, upgrade_limit: 5, monitored_only: true, skip_future: true },
  },
}

function render(ui: ReactElement) {
  return rtlRender(<TooltipProvider>{ui}</TooltipProvider>)
}

let updateMutate: ReturnType<typeof vi.fn>

beforeEach(() => {
  updateMutate = vi.fn()
  vi.mocked(useFindarrSettings).mockReturnValue(queryResult(SETTINGS))
  vi.mocked(useUpdateFindarrSettings).mockReturnValue(mutation(updateMutate, false))
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

  it("edits the hourly cap and queue limit numbers", () => {
    render(<Settings />)
    fireEvent.change(screen.getByLabelText("Hourly cap"), { target: { value: "10" } })
    expect(updateMutate).toHaveBeenCalledWith({ hourly_cap: 10 })
    fireEvent.change(screen.getByLabelText("Queue limit"), { target: { value: "3" } })
    expect(updateMutate).toHaveBeenCalledWith({ queue_limit: 3 })
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
})
