import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useStatus: vi.fn(() => ({ data: undefined })),
  useActivity: vi.fn(() => ({ data: [], isLoading: false })),
  useItems: vi.fn(() => ({ data: [], isLoading: false })),
  useLists: vi.fn(() => ({ data: [], isLoading: false })),
  useListItems: vi.fn(() => ({ data: [], isLoading: false })),
  useServiceStatuses: vi.fn(() => ({
    data: { interval_seconds: 60, last_check_at: null, services: {} },
    isLoading: false,
  })),
  useCheckServiceStatuses: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
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
  useGeneralSettings: vi.fn(() => ({ data: { interval_seconds: 60 } })),
  useUpdateStatusInterval: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useServiceSettings: vi.fn(() => ({ data: undefined })),
  useUpdateServiceSettings: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useTestService: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}))

import App from "@/App"
import { ThemeProvider } from "@/shared/components/theme-provider"
import { TooltipProvider } from "@/shared/components/ui/tooltip"
import { SETTINGS_TAB_STORAGE_KEY } from "@/features/settings/settings-tab"

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

  it("renders the List-Syncarr page with Lists and Items tabs at /list-syncarr", () => {
    renderAt("/list-syncarr")
    expect(screen.getByRole("tab", { name: "Lists" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Items" })).toBeInTheDocument()
    // Lists is the default tab, so its content is shown first.
    expect(
      screen.getByText("Trakt lists kept in sync by the engine."),
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
