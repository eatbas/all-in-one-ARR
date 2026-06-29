import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useStatus: vi.fn(() => ({ data: undefined })),
  useActivity: vi.fn(() => ({ data: [], isLoading: false })),
  useLists: vi.fn(() => ({ data: [], isLoading: false })),
  useListItems: vi.fn(() => ({ data: [], isLoading: false })),
  useRemoveItem: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRemoveAvailable: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useServiceStatuses: vi.fn(() => ({
    data: { interval_seconds: 60, last_check_at: null, services: {} },
    isLoading: false,
  })),
  useCheckServiceStatuses: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useSyncNow: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useTraktSettings: vi.fn(() => ({ data: undefined, isLoading: false })),
  useTraktAuthStatus: vi.fn(() => ({ data: undefined })),
  useTraktLists: vi.fn(() => ({ data: [], isLoading: false })),
  useUpdateTraktSettings: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useStartTraktAuth: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useTestTrakt: vi.fn(() => ({ mutate: vi.fn(), isPending: false, data: undefined })),
  useAddTraktList: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRemoveTraktList: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useGeneralSettings: vi.fn(() => ({
    data: { interval_seconds: 60, sync_interval_minutes: 15 },
  })),
  useUpdateStatusInterval: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUpdateSyncInterval: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useServiceSettings: vi.fn(() => ({ data: undefined })),
  useUpdateServiceSettings: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useTestService: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useBandwidthStatus: vi.fn(() => ({ data: undefined, isLoading: false })),
  useUpdateBandwidthSettings: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useFindarrStatus: vi.fn(() => ({
    data: {
      settings: {
        enabled: false,
        interval_minutes: 30,
        hourly_cap: 20,
        queue_limit: -1,
        apps: {
          sonarr: {
            enabled: true,
            missing_limit: 5,
            upgrade_limit: 5,
            monitored_only: true,
            skip_future: true,
          },
          radarr: {
            enabled: true,
            missing_limit: 5,
            upgrade_limit: 5,
            monitored_only: true,
            skip_future: true,
          },
        },
      },
      running: false,
      last_run_at: null,
      last_run_status: null,
      last_run_detail: null,
      apps: {
        sonarr: {
          detail: "Not checked yet",
          version: null,
          compatible: false,
          processed: { missing: 0, upgrade: 0 },
        },
        radarr: {
          detail: "Not checked yet",
          version: null,
          compatible: false,
          processed: { missing: 0, upgrade: 0 },
        },
      },
      hourly: { limit: 20, used: 0, remaining: 20 },
    },
    isLoading: false,
  })),
  useFindarrSettings: vi.fn(() => ({ data: undefined, isLoading: false })),
  useFindarrHistory: vi.fn(() => ({ data: [], isLoading: false })),
  useUpdateFindarrSettings: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRunFindarr: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useResetFindarrState: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useTrending: vi.fn(() => ({ data: [], isLoading: false })),
  useTrendingRating: vi.fn(() => ({ data: undefined })),
  useAddTrending: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}))

import App from "@/App"
import { ThemeProvider } from "@/shared/components/theme-provider"
import { TooltipProvider } from "@/shared/components/ui/tooltip"
import { SETTINGS_TAB_STORAGE_KEY } from "@/features/settings/settings-tab"

function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider defaultTheme="dark" storageKey="app-test-theme">
        <TooltipProvider>
          <MemoryRouter initialEntries={[path]}>
            <App />
          </MemoryRouter>
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>,
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

  it("renders the Trending page with per-source tabs at /trending", () => {
    renderAt("/trending")
    expect(screen.getByRole("tab", { name: "Trakt" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "TMDB" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Seer" })).toBeInTheDocument()
  })

  it("renders the List-Syncarr page with Lists and Settings tabs at /list-syncarr", () => {
    renderAt("/list-syncarr")
    expect(screen.getByRole("tab", { name: "Lists" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Settings" })).toBeInTheDocument()
    // Lists is the default tab, so its content is shown first.
    expect(
      screen.getByText("Trakt lists kept in sync by the engine."),
    ).toBeInTheDocument()
  })

  it("renders the settings page at /settings", () => {
    renderAt("/settings")
    // The General tab is the default landing tab.
    expect(screen.getByText("Status check interval")).toBeInTheDocument()
  })

  it("renders the Bandwidth-Controllarr page at /bandwidth-controllarr", () => {
    renderAt("/bandwidth-controllarr")
    expect(screen.getByRole("tab", { name: "Status" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Settings" })).toBeInTheDocument()
    expect(
      screen.getByText((text) =>
        text.includes("Prioritise BitTorrent over Usenet by pausing SABnzbd while"),
      ),
    ).toBeInTheDocument()
  })

  it("renders the Findarr page at /findarr", () => {
    renderAt("/findarr")
    expect(screen.getByRole("tab", { name: "Status" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Settings" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "History" })).toBeInTheDocument()
    expect(
      screen.getByText("Search missing and cutoff-unmet media in Sonarr 4+ and Radarr 6+."),
    ).toBeInTheDocument()
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
