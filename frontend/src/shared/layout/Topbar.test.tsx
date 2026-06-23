import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/shared/components/mode-toggle", () => ({
  ModeToggle: () => <div data-testid="mode-toggle" />,
}))
vi.mock("@/shared/lib/queries", () => ({
  useStatus: vi.fn(),
  useSyncNow: vi.fn(),
  useSetDryRun: vi.fn(),
}))

import { useSetDryRun, useStatus, useSyncNow } from "@/shared/lib/queries"
import { Topbar } from "@/shared/layout/Topbar"
import { TooltipProvider } from "@/shared/components/ui/tooltip"
import type { DryRunResult, Status, SyncResult } from "@/shared/lib/api"
import { mutationResult, queryResult } from "@/shared/test/mock-query"

/** Topbar uses a Tooltip, which the app mounts under a TooltipProvider. */
function renderTopbar() {
  return render(<Topbar />, { wrapper: TooltipProvider })
}

const liveStatus: Status = {
  dry_run: false,
  trakt_connected: true,
  counts: { synced: 0, requested: 0, available: 0, removed: 0 },
}

const asStatus = (data: Status | undefined) => queryResult<Status>(data)
const asSync = (mutate: () => void, isPending: boolean) =>
  mutationResult<SyncResult, void>(mutate, isPending)
const asSetDryRun = (mutate: (value: boolean) => void, isPending: boolean) =>
  mutationResult<DryRunResult, boolean>(mutate, isPending)

describe("Topbar", () => {
  it("falls back to dry-run on and disconnected when status is unavailable", () => {
    vi.mocked(useStatus).mockReturnValue(asStatus(undefined))
    vi.mocked(useSyncNow).mockReturnValue(asSync(vi.fn(), false))
    vi.mocked(useSetDryRun).mockReturnValue(asSetDryRun(vi.fn(), false))

    renderTopbar()

    expect(screen.getByText("DRY_RUN ON")).toBeInTheDocument()
    expect(screen.getByText("Trakt needs auth")).toBeInTheDocument()
    // Disabled via the `status === undefined` side of the guard.
    expect(screen.getByRole("switch")).toBeDisabled()
  })

  it("reflects live mode and forwards the toggle and sync actions", async () => {
    const user = userEvent.setup()
    const syncMutate = vi.fn()
    const dryRunMutate = vi.fn()
    vi.mocked(useStatus).mockReturnValue(asStatus(liveStatus))
    vi.mocked(useSyncNow).mockReturnValue(asSync(syncMutate, false))
    vi.mocked(useSetDryRun).mockReturnValue(asSetDryRun(dryRunMutate, false))

    renderTopbar()

    expect(screen.getByText("LIVE")).toBeInTheDocument()
    expect(screen.getByText("Trakt connected")).toBeInTheDocument()

    const toggle = screen.getByRole("switch")
    expect(toggle).not.toBeDisabled()
    await user.click(toggle)
    expect(dryRunMutate).toHaveBeenCalledWith(true)

    await user.click(screen.getByRole("button", { name: "Sync now" }))
    expect(syncMutate).toHaveBeenCalled()
  })

  it("disables controls and spins the icon while actions are pending", () => {
    vi.mocked(useStatus).mockReturnValue(asStatus(liveStatus))
    vi.mocked(useSyncNow).mockReturnValue(asSync(vi.fn(), true))
    vi.mocked(useSetDryRun).mockReturnValue(asSetDryRun(vi.fn(), true))

    const { container } = renderTopbar()

    expect(screen.getByRole("switch")).toBeDisabled()
    expect(screen.getByRole("button", { name: "Sync now" })).toBeDisabled()
    expect(container.querySelector(".animate-spin")).toBeInTheDocument()
  })
})
