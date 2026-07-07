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
  useTestTrakt: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    data: undefined,
  })),
  useAddTraktList: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRemoveTraktList: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useGeneralSettings: vi.fn(() => ({
    data: { interval_seconds: 60, sync_interval_minutes: 15 },
  })),
  useUpdateStatusInterval: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUpdateSyncInterval: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useServiceSettings: vi.fn(() => ({ data: undefined })),
  useUpdateServiceSettings: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
  })),
  useTestService: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useBandwidthStatus: vi.fn(() => ({ data: undefined, isLoading: false })),
  useUpdateBandwidthSettings: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
  })),
  useDeletarrStatus: vi.fn(() => ({
    data: {
      settings: { movies_path: "/media/movies", tv_path: "/media/tv" },
      libraries: {
        movies: {
          type: "movies",
          path: "/media/movies",
          last_scan_at: null,
          last_error: null,
          results_count: 0,
          stats: {
            total_files: 0,
            total_folders: 0,
            total_size: 0,
            is_scanning: false,
            scan_progress: 0,
          },
        },
        tv: {
          type: "tv",
          path: "/media/tv",
          last_scan_at: null,
          last_error: null,
          results_count: 0,
          stats: {
            total_files: 0,
            total_folders: 0,
            total_size: 0,
            is_scanning: false,
            scan_progress: 0,
          },
        },
      },
    },
    isLoading: false,
  })),
  useDeletarrResults: vi.fn(() => ({
    data: {
      type: "movies",
      path: "/media/movies",
      results: [],
      stats: {
        total_files: 0,
        total_folders: 0,
        total_size: 0,
        is_scanning: false,
        scan_progress: 0,
      },
    },
    isLoading: false,
  })),
  useUpdateDeletarrSettings: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
  })),
  useScanDeletarr: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDeleteDeletarrItems: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useFindarrStatus: vi.fn(() => ({
    data: {
      settings: {
        enabled: false,
        interval_minutes: 30,
        hourly_cap: 20,
        queue_limit: -1,
        command_sleep_seconds: 0,
        state_reset_hours: 168,
        apps: {
          sonarr: {
            enabled: true,
            missing_limit: 5,
            upgrade_limit: 5,
            monitored_only: true,
            skip_future: true,
            missing_mode: "episodes",
            upgrade_mode: "episodes",
          },
          radarr: {
            enabled: true,
            missing_limit: 5,
            upgrade_limit: 5,
            monitored_only: true,
            skip_future: true,
            missing_mode: "episodes",
            upgrade_mode: "episodes",
          },
        },
      },
      running: false,
      last_run_at: null,
      last_run_status: null,
      last_run_detail: null,
      state: { created_at: null, reset_at: null, reset_hours: 168 },
      apps: {
        sonarr: {
          detail: "Not checked yet",
          version: null,
          compatible: false,
          processed: { missing: 0, upgrade: 0 },
          lifetime: { missing: 0, upgrade: 0 },
          wanted: { missing: 0, upgrade: 0 },
          activity: "Not run yet",
        },
        radarr: {
          detail: "Not checked yet",
          version: null,
          compatible: false,
          processed: { missing: 0, upgrade: 0 },
          lifetime: { missing: 0, upgrade: 0 },
          wanted: { missing: 0, upgrade: 0 },
          activity: "Not run yet",
        },
      },
      hourly: { limit: 20, used: 0, remaining: 20 },
    },
    isLoading: false,
  })),
  useFindarrSettings: vi.fn(() => ({ data: undefined, isLoading: false })),
  useFindarrHistory: vi.fn(() => ({ data: [], isLoading: false })),
  useClearFindarrHistory: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUpdateFindarrSettings: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
  })),
  useRunFindarr: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useResetFindarrState: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useTrending: vi.fn(() => ({ data: [], isLoading: false })),
  useTrendingRating: vi.fn(() => ({ data: undefined })),
  useAddTrending: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}))

vi.mock("@/features/findarr/Findarr", () => ({
  Findarr: () => <div>Findarr route</div>,
}))

vi.mock("@/features/dashboard/Dashboard", () => ({
  Dashboard: () => <div>Dashboard route</div>,
}))

vi.mock("@/features/trending/Trending", () => ({
  Trending: () => <div>Trending route</div>,
}))

vi.mock("@/features/list-syncarr/ListSyncarr", () => ({
  ListSyncarr: () => <div>List-Syncarr route</div>,
}))

vi.mock("@/features/bandwidth-controllarr/BandwidthControllarr", () => ({
  BandwidthControllarr: () => <div>Bandwidth-Controllarr route</div>,
}))

vi.mock("@/features/deletarr/Deletarr", () => ({
  Deletarr: () => <div>Deletarr route</div>,
}))

vi.mock("@/features/settings/Settings", () => ({
  Settings: () => <div>Settings route</div>,
}))

import App from "@/App"
import { ThemeProvider } from "@/shared/components/theme-provider"
import { TooltipProvider } from "@/shared/components/ui/tooltip"

function renderAt(path: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
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
  localStorage.clear()
})

describe("App routing", () => {
  it("renders the dashboard at /", () => {
    renderAt("/")
    expect(screen.getByText("Dashboard route")).toBeInTheDocument()
  })

  it("renders the Trending page at /trending", () => {
    renderAt("/trending")
    expect(screen.getByText("Trending route")).toBeInTheDocument()
  })

  it("renders the List-Syncarr page at /list-syncarr", () => {
    renderAt("/list-syncarr")
    expect(screen.getByText("List-Syncarr route")).toBeInTheDocument()
  })

  it("renders the settings page at /settings", () => {
    renderAt("/settings")
    expect(screen.getByText("Settings route")).toBeInTheDocument()
  })

  it("renders the Bandwidth-Controllarr page at /bandwidth-controllarr", () => {
    renderAt("/bandwidth-controllarr")
    expect(screen.getByText("Bandwidth-Controllarr route")).toBeInTheDocument()
  })

  it("renders the Findarr page at /findarr", () => {
    renderAt("/findarr")
    expect(screen.getByText("Findarr route")).toBeInTheDocument()
  })

  it("renders the Deletarr page at /deletarr", () => {
    renderAt("/deletarr")
    expect(screen.getByText("Deletarr route")).toBeInTheDocument()
  })

  it("redirects unknown routes back to the dashboard", () => {
    renderAt("/does-not-exist")
    expect(screen.getByText("Dashboard route")).toBeInTheDocument()
  })
})

describe("route navigation", () => {
  it("navigates between sidebar links", async () => {
    const user = userEvent.setup()
    renderAt("/settings")
    await user.click(screen.getByRole("link", { name: "Dashboard" }))
    expect(screen.getByText("Dashboard route")).toBeInTheDocument()
    await user.click(screen.getByRole("link", { name: "Settings" }))
    expect(screen.getByText("Settings route")).toBeInTheDocument()
  })
})
