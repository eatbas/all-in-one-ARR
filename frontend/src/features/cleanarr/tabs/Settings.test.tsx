import { render as rtlRender, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useCleanarrSettings: vi.fn(),
  useUpdateCleanarrSettings: vi.fn(),
}))

import { Settings } from "@/features/cleanarr/tabs/Settings"
import { TooltipProvider } from "@/shared/components/ui/tooltip"
import type { CleanarrSettings } from "@/shared/lib/api"
import {
  useCleanarrSettings,
  useUpdateCleanarrSettings,
} from "@/shared/lib/queries"
import { CLEANARR_SETTINGS } from "@/shared/test/cleanarr-fixtures"
import { mutationResult, queryResult } from "@/shared/test/mock-query"
import { expectHelpTooltip } from "@/shared/test/tooltip"

const save = vi.fn()

function render(ui: ReactElement) {
  return rtlRender(<TooltipProvider>{ui}</TooltipProvider>)
}

function saveButton() {
  return screen.getByRole("button", { name: "Save" })
}

beforeEach(() => {
  vi.mocked(useCleanarrSettings).mockReturnValue(queryResult(CLEANARR_SETTINGS))
  vi.mocked(useUpdateCleanarrSettings).mockReturnValue(
    mutationResult(save, false),
  )
})

describe("Cleanarr Settings tab", () => {
  it("shows a loading state", () => {
    vi.mocked(useCleanarrSettings).mockReturnValue(
      queryResult<CleanarrSettings>(undefined, true),
    )
    render(<Settings />)
    expect(screen.getByText("Loading Cleanarr settings…")).toBeInTheDocument()
  })

  it("shows a load error", () => {
    vi.mocked(useCleanarrSettings).mockReturnValue(
      queryResult<CleanarrSettings>(undefined, false, {
        isError: true,
        error: new Error("nope"),
      }),
    )
    render(<Settings />)
    expect(
      screen.getByText("Could not load Cleanarr settings: nope"),
    ).toBeInTheDocument()
  })

  it("renders the saved values and keeps Save disabled until a change", () => {
    render(<Settings />)
    expect(
      screen.getByRole("switch", { name: "Enable Cleanarr" }),
    ).toBeChecked()
    expect(screen.getByRole("switch", { name: "Dry run" })).toBeChecked()
    expect(screen.getByLabelText("Interval (minutes)")).toHaveValue(10)
    expect(screen.getByLabelText("Patterns")).toHaveValue(
      "matched to series by ID\nmatched to movie by ID",
    )
    expect(screen.getByLabelText("Blocked extensions")).toHaveValue(".exe .scr")
    expect(screen.getByLabelText("Download IDs")).toHaveValue("SABnzbd_nzo_x")
    expect(
      screen.getByRole("switch", { name: "Enable malware blocker" }),
    ).not.toBeChecked()
    expect(screen.getAllByText("Off")).toHaveLength(2)
    expect(saveButton()).toBeDisabled()
  })

  it("saves every section in one update", async () => {
    const user = userEvent.setup()
    render(<Settings />)

    await user.click(screen.getByRole("switch", { name: "Enable Cleanarr" }))
    await user.click(screen.getByRole("switch", { name: "Dry run" }))
    await user.click(
      screen.getByRole("switch", { name: "Enable queue cleaning" }),
    )
    await user.click(
      screen.getByRole("switch", { name: "Enable malware blocker" }),
    )
    await user.click(
      screen.getByRole("switch", { name: "Enable orphan quarantine" }),
    )
    await user.click(screen.getByRole("switch", { name: "Enable Radarr" }))
    await user.click(screen.getByRole("combobox", { name: "Pattern mode" }))
    await user.click(
      screen.getByRole("option", {
        name: "Include: strike only when a message matches",
      }),
    )
    const strikes = screen.getByLabelText("Max strikes")
    await user.clear(strikes)
    await user.type(strikes, "5")
    const extensions = screen.getByLabelText("Blocked extensions")
    await user.clear(extensions)
    await user.type(extensions, "EXE lnk")
    const quarantine = screen.getByLabelText("Quarantine folder")
    await user.clear(quarantine)
    await user.type(quarantine, "/downloads/complete/q/")
    await user.type(screen.getByLabelText("Title contains"), "Sample")

    await user.click(saveButton())

    expect(save).toHaveBeenCalledWith({
      enabled: false,
      dry_run: false,
      interval_minutes: 10,
      max_strikes: 5,
      max_removals_per_run: 10,
      queue: {
        enabled: false,
        pattern_mode: "include",
        patterns: ["matched to series by ID", "matched to movie by ID"],
      },
      malware: { enabled: true, extensions: [".exe", ".lnk"] },
      orphans: {
        enabled: true,
        min_age_hours: 24,
        quarantine_retention_days: 14,
      },
      paths: {
        completed_root: "/downloads/complete",
        quarantine_dir: "/downloads/complete/q",
      },
      apps: { sonarr: { enabled: true }, radarr: { enabled: false } },
      ignore: {
        download_ids: ["SABnzbd_nzo_x"],
        categories: [],
        title_contains: ["Sample"],
      },
    })
  })

  it("flags an out-of-range number inline and blocks Save", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    const strikes = screen.getByLabelText("Max strikes")
    await user.clear(strikes)
    await user.type(strikes, "2")

    expect(strikes).toHaveAttribute("aria-invalid", "true")
    expect(screen.getByText("Enter a whole number from 3 to 20.")).toHaveClass(
      "text-destructive",
    )
    expect(saveButton()).toBeDisabled()
  })

  it("flags a quarantine folder outside the completed folder", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    const quarantine = screen.getByLabelText("Quarantine folder")
    await user.clear(quarantine)
    await user.type(quarantine, "/elsewhere")

    expect(quarantine).toHaveAttribute("aria-invalid", "true")
    expect(
      screen.getByText("Enter an absolute path inside the completed folder."),
    ).toBeInTheDocument()
    expect(saveButton()).toBeDisabled()
  })

  it("blocks Save for paths longer than the backend accepts", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    // A 1,035-character completed folder with its quarantine inside it.
    const longRoot = `/downloads/${"x".repeat(1024)}`
    const root = screen.getByLabelText("Completed folder")
    const quarantine = screen.getByLabelText("Quarantine folder")
    await user.clear(root)
    await user.click(root)
    await user.paste(longRoot)
    await user.clear(quarantine)
    await user.click(quarantine)
    await user.paste(`${longRoot}/q`)

    expect(root).toHaveAttribute("aria-invalid", "true")
    expect(quarantine).toHaveAttribute("aria-invalid", "true")
    expect(
      screen.getAllByText("Use a path of at most 1024 characters."),
    ).toHaveLength(2)
    expect(saveButton()).toBeDisabled()
  })

  it("disables the form while saving", () => {
    vi.mocked(useUpdateCleanarrSettings).mockReturnValue(
      mutationResult(save, true),
    )
    render(<Settings />)
    expect(screen.getByLabelText("Patterns")).toBeDisabled()
    expect(screen.getByLabelText("Completed folder")).toBeDisabled()
    expect(screen.getByRole("switch", { name: "Dry run" })).toBeDisabled()
    expect(saveButton()).toBeDisabled()
  })

  it("explains the scheduler switch", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await expectHelpTooltip(
      user,
      "Explain Enable Cleanarr",
      "Allows the scheduler to strike and clean stuck Sonarr/Radarr queue items.",
    )
  })

  it("explains the per-app switches", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await expectHelpTooltip(
      user,
      "Explain Process Radarr",
      "Includes Radarr's queue in Cleanarr processing.",
    )
  })
})
