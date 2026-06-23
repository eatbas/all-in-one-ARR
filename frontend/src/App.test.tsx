import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/lib/queries", () => ({
  useStatus: vi.fn(() => ({ data: undefined })),
  useActivity: vi.fn(() => ({ data: [], isLoading: false })),
  useItems: vi.fn(() => ({ data: [], isLoading: false })),
  useSyncNow: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useSetDryRun: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useTraktSettings: vi.fn(() => ({ data: undefined, isLoading: false })),
  useTraktAuthStatus: vi.fn(() => ({ data: undefined })),
  useTraktLists: vi.fn(() => ({ data: [], isLoading: false })),
  useUpdateTraktSettings: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useStartTraktAuth: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useTestTrakt: vi.fn(() => ({ mutate: vi.fn(), isPending: false, data: undefined })),
  useAddTraktList: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRemoveTraktList: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}))

import App from "@/App"
import { ThemeProvider } from "@/components/theme-provider"
import { TooltipProvider } from "@/components/ui/tooltip"
import { SETTINGS_TAB_STORAGE_KEY } from "@/lib/settings-tab"

function renderAt(path: string) {
  return render(
    <ThemeProvider defaultTheme="dark" storageKey="app-test-theme">
      <TooltipProvider>
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      </TooltipProvider>
    </ThemeProvider>,
  )
}

beforeEach(() => {
  localStorage.removeItem(SETTINGS_TAB_STORAGE_KEY)
})

describe("App routing", () => {
  it("renders the dashboard at /", () => {
    renderAt("/")
    expect(screen.getByText("Recent activity")).toBeInTheDocument()
  })

  it("renders the items page at /items", () => {
    renderAt("/items")
    expect(
      screen.getByText("Every movie and show mirrored from Trakt."),
    ).toBeInTheDocument()
  })

  it("renders the settings page at /settings", () => {
    renderAt("/settings")
    // The General tab is the default landing tab.
    expect(screen.getByText("Dry-run mode")).toBeInTheDocument()
  })

  it("redirects unknown routes back to the dashboard", () => {
    renderAt("/does-not-exist")
    expect(screen.getByText("Recent activity")).toBeInTheDocument()
  })
})

describe("Settings tab persistence across navigation", () => {
  it("remembers the active tab when leaving and returning to Settings", async () => {
    const user = userEvent.setup()
    renderAt("/settings")
    await user.click(screen.getByRole("tab", { name: "Trakt" }))
    await user.click(screen.getByRole("link", { name: "Dashboard" }))
    expect(screen.getByText("Recent activity")).toBeInTheDocument()
    await user.click(screen.getByRole("link", { name: "Settings" }))
    expect(screen.getByRole("tab", { name: "Trakt" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    expect(screen.getByText("Trakt credentials")).toBeInTheDocument()
  })
})
