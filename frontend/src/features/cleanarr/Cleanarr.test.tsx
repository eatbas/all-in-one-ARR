import { render as rtlRender, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useCleanarrStatus: vi.fn(),
  useCleanarrSettings: vi.fn(),
  useCleanarrQueue: vi.fn(),
  useCleanarrHistory: vi.fn(),
  useUpdateCleanarrSettings: vi.fn(),
  useRunCleanarr: vi.fn(),
  useClearCleanarrStrikes: vi.fn(),
  useIgnoreCleanarrDownload: vi.fn(),
}))

import { Cleanarr } from "@/features/cleanarr/Cleanarr"
import { CLEANARR_TAB_STORAGE_KEY } from "@/features/cleanarr/cleanarr-tab"
import { TooltipProvider } from "@/shared/components/ui/tooltip"
import {
  useCleanarrHistory,
  useCleanarrQueue,
  useCleanarrSettings,
  useCleanarrStatus,
  useClearCleanarrStrikes,
  useIgnoreCleanarrDownload,
  useRunCleanarr,
  useUpdateCleanarrSettings,
} from "@/shared/lib/queries"
import {
  CLEANARR_HISTORY,
  CLEANARR_QUEUE,
  CLEANARR_SETTINGS,
  CLEANARR_STATUS,
} from "@/shared/test/cleanarr-fixtures"
import { mutationResult, queryResult } from "@/shared/test/mock-query"

function render(ui: ReactElement) {
  return rtlRender(<TooltipProvider>{ui}</TooltipProvider>)
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(useCleanarrStatus).mockReturnValue(queryResult(CLEANARR_STATUS))
  vi.mocked(useCleanarrSettings).mockReturnValue(queryResult(CLEANARR_SETTINGS))
  vi.mocked(useCleanarrQueue).mockReturnValue(queryResult(CLEANARR_QUEUE))
  vi.mocked(useCleanarrHistory).mockReturnValue(queryResult(CLEANARR_HISTORY))
  for (const hook of [
    useUpdateCleanarrSettings,
    useRunCleanarr,
    useClearCleanarrStrikes,
    useIgnoreCleanarrDownload,
  ]) {
    vi.mocked(hook).mockReturnValue(mutationResult(vi.fn(), false) as never)
  }
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("Cleanarr", () => {
  it("shows the header and defaults to the Status tab", () => {
    render(<Cleanarr />)
    expect(
      screen.getByRole("heading", { level: 1, name: "Cleanarr" }),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        "Clear stuck and failed downloads from Sonarr/Radarr queues and tidy SABnzbd's completed folder.",
      ),
    ).toBeInTheDocument()
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
      "Status",
      "Queue",
      "History",
      "Settings",
    ])
    expect(screen.getByRole("tab", { name: "Status" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    expect(screen.getByText("System Status")).toBeInTheDocument()
  })

  it.each([
    ["Queue", "queue", "No files found are eligible for import"],
    ["History", "history", "Would remove"],
    ["Settings", "settings", "Cleanarr scheduler"],
  ])("switches to %s and persists the tab", async (name, key, text) => {
    const user = userEvent.setup()
    render(<Cleanarr />)
    await user.click(screen.getByRole("tab", { name }))
    expect(localStorage.getItem(CLEANARR_TAB_STORAGE_KEY)).toBe(key)
    expect(screen.getAllByText(text).length).toBeGreaterThan(0)
  })

  it("restores a valid stored tab on mount", () => {
    localStorage.setItem(CLEANARR_TAB_STORAGE_KEY, "history")
    render(<Cleanarr />)
    expect(screen.getByRole("tab", { name: "History" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
  })

  it("ignores bad stored tabs and survives missing localStorage", async () => {
    localStorage.setItem(CLEANARR_TAB_STORAGE_KEY, "bad")
    const first = render(<Cleanarr />)
    expect(screen.getByRole("tab", { name: "Status" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    first.unmount()

    vi.stubGlobal("localStorage", undefined)
    const user = userEvent.setup()
    render(<Cleanarr />)
    await user.click(screen.getByRole("tab", { name: "Settings" }))
    expect(screen.getByText("Cleanarr scheduler")).toBeInTheDocument()
  })
})
