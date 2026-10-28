import { render as rtlRender, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useCleanarrStatus: vi.fn(),
  useUpdateCleanarrSettings: vi.fn(),
  useRunCleanarr: vi.fn(),
  useClearCleanarrStrikes: vi.fn(),
}))

import { Status } from "@/features/cleanarr/tabs/Status"
import { TooltipProvider } from "@/shared/components/ui/tooltip"
import type { CleanarrStatus } from "@/shared/lib/api"
import {
  useCleanarrStatus,
  useClearCleanarrStrikes,
  useRunCleanarr,
  useUpdateCleanarrSettings,
} from "@/shared/lib/queries"
import { CLEANARR_STATUS } from "@/shared/test/cleanarr-fixtures"
import { mutationResult, queryResult } from "@/shared/test/mock-query"
import { expectHelpTooltip } from "@/shared/test/tooltip"

const update = vi.fn()
const run = vi.fn()
const clear = vi.fn()

function render(ui: ReactElement) {
  return rtlRender(<TooltipProvider>{ui}</TooltipProvider>)
}

function withStatus(overrides: Partial<CleanarrStatus> = {}) {
  vi.mocked(useCleanarrStatus).mockReturnValue(
    queryResult({ ...CLEANARR_STATUS, ...overrides }),
  )
}

beforeEach(() => {
  withStatus()
  vi.mocked(useUpdateCleanarrSettings).mockReturnValue(
    mutationResult(update, false),
  )
  vi.mocked(useRunCleanarr).mockReturnValue(mutationResult(run, false))
  vi.mocked(useClearCleanarrStrikes).mockReturnValue(
    mutationResult(clear, false),
  )
})

describe("Cleanarr Status tab", () => {
  it("shows a loading state", () => {
    vi.mocked(useCleanarrStatus).mockReturnValue(
      queryResult<CleanarrStatus>(undefined, true),
    )
    render(<Status />)
    expect(screen.getByText("Loading Cleanarr…")).toBeInTheDocument()
  })

  it("shows a load error", () => {
    vi.mocked(useCleanarrStatus).mockReturnValue(
      queryResult<CleanarrStatus>(undefined, false, {
        isError: true,
        error: new Error("offline"),
      }),
    )
    render(<Status />)
    expect(
      screen.getByText("Could not load Cleanarr: offline"),
    ).toBeInTheDocument()
  })

  it("shows the last run, the dry-run banner and strike counts", () => {
    render(<Status />)
    expect(screen.getByText(/Dry run: 1 would remove$/)).toBeInTheDocument()
    expect(
      screen.getByText("Dry run is on. No changes are made."),
    ).toBeInTheDocument()
    const stats = within(screen.getByRole("region", { name: "Strike counts" }))
    expect(stats.getByText("Sonarr strikes").nextSibling).toHaveTextContent("3")
    expect(stats.getByText("Radarr strikes").nextSibling).toHaveTextContent("1")
    expect(stats.getByText("Failed imports").nextSibling).toHaveTextContent("3")
    expect(stats.getByText("Failed downloads").nextSibling).toHaveTextContent(
      "1",
    )
  })

  it("hides the banner when live and waits for a first run", () => {
    withStatus({ dry_run: false, last_run: null, health: [] })
    render(<Status />)
    expect(screen.queryByText(/Dry run is on/)).not.toBeInTheDocument()
    expect(screen.getByText("Waiting for first run…")).toBeInTheDocument()
    expect(
      screen.getByText("Health checks run with each Cleanarr run."),
    ).toBeInTheDocument()
  })

  it("lists connections in app order with their badges", () => {
    render(<Status />)
    const names = ["Sonarr", "Radarr", "SABnzbd"].map((name) =>
      screen.getByText(name, { selector: "p" }),
    )
    expect(names[0].compareDocumentPosition(names[1])).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    )
    expect(names[1].compareDocumentPosition(names[2])).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    )
    expect(screen.getByTitle("connection refused")).toHaveTextContent("Offline")
    expect(screen.getByTitle("Connected to SABnzbd")).toHaveTextContent(
      "Connected",
    )
  })

  it("asks for a first run when no connection was checked yet", () => {
    withStatus({ connections: [] })
    render(<Status />)
    expect(
      screen.getByText(
        "Connections are checked on each run. Run Cleanarr now to check them.",
      ),
    ).toBeInTheDocument()
  })

  it("toggles the module and explains the switch", async () => {
    const user = userEvent.setup()
    render(<Status />)
    expect(screen.getByText("Enabled")).toBeInTheDocument()
    await user.click(screen.getByRole("switch", { name: "Enable Cleanarr" }))
    expect(update).toHaveBeenCalledWith({ enabled: false })
    await expectHelpTooltip(
      user,
      "Explain Enable Cleanarr",
      "Allows the scheduler to strike and clean stuck Sonarr/Radarr queue items every 10 minutes.",
    )
  })

  it("runs now", async () => {
    const user = userEvent.setup()
    render(<Status />)
    await user.click(screen.getByRole("button", { name: "Run now" }))
    expect(run).toHaveBeenCalledOnce()
  })

  it("disables Run now while disabled and explains why", () => {
    withStatus({ enabled: false })
    render(<Status />)
    expect(screen.getByText("Disabled")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Run now" })).toBeDisabled()
    expect(
      screen.getByText(
        "Cleanarr is disabled. Enable it to run the scheduled clean or to run it now.",
      ),
    ).toBeInTheDocument()
  })

  it.each([
    ["a run is in progress", { running: true }, false],
    ["a manual run is pending", {}, true],
  ])("disables Run now while %s", (_name, overrides, pending) => {
    withStatus(overrides)
    vi.mocked(useRunCleanarr).mockReturnValue(mutationResult(run, pending))
    render(<Status />)
    expect(screen.getByRole("button", { name: "Run now" })).toBeDisabled()
  })

  it("clears strikes only after confirming", async () => {
    const user = userEvent.setup()
    render(<Status />)

    await user.click(screen.getByRole("button", { name: "Clear strikes" }))
    const dialog = screen.getByRole("alertdialog")
    expect(
      within(dialog).getByText("Clear all Cleanarr strikes?"),
    ).toBeInTheDocument()
    expect(
      within(dialog).getByText(/This deletes all 4 strikes/),
    ).toBeInTheDocument()
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }))
    expect(clear).not.toHaveBeenCalled()

    await user.click(screen.getByRole("button", { name: "Clear strikes" }))
    await user.click(
      within(screen.getByRole("alertdialog")).getByRole("button", {
        name: "Clear strikes",
      }),
    )
    expect(clear).toHaveBeenCalledOnce()
  })

  it("disables Clear strikes when there are none", () => {
    withStatus({
      strikes: { sonarr: 0, radarr: 0, failed_import: 0, failed_download: 0 },
    })
    render(<Status />)
    expect(screen.getByRole("button", { name: "Clear strikes" })).toBeDisabled()
  })

  it("lists warnings and unknown values separately", () => {
    render(<Status />)
    expect(screen.getByText("1 warning")).toBeInTheDocument()
    expect(screen.getByLabelText("Warning")).toBeInTheDocument()
    expect(screen.getByLabelText("Unknown")).toBeInTheDocument()
    expect(
      screen.getByText("Could not read Radarr's download handling settings."),
    ).toHaveClass("text-muted-foreground")
  })

  it("counts several warnings and reports a clean run", () => {
    withStatus({
      health: [
        { source: "system", code: "a", detail: "One", level: "warning" },
        { source: "custom", code: "b", detail: "Two", level: "warning" },
      ],
    })
    const view = render(<Status />)
    expect(screen.getByText("2 warnings")).toBeInTheDocument()
    expect(screen.getByText("Cleanarr", { selector: "span" })).toBeVisible()
    expect(screen.getByText("custom")).toBeInTheDocument()
    view.unmount()

    withStatus({ health: [] })
    render(<Status />)
    expect(
      screen.getByText("No warnings from the last run."),
    ).toBeInTheDocument()
    expect(screen.queryByText(/warnings?$/)).not.toBeInTheDocument()
  })
})
