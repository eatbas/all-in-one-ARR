import { render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useActivity: vi.fn(),
  useDashboardSummary: vi.fn(),
  useServiceStatuses: vi.fn(),
  useCheckServiceStatuses: vi.fn(),
  useServiceSettings: vi.fn(),
}))

// The lazily loaded charts have their own tests; a stub keeps Recharts out and
// exposes the snapshot version the Dashboard hands over.
vi.mock("@/features/dashboard/components/trend-charts", () => ({
  TrendCharts: ({ latestSnapshotAt }: { latestSnapshotAt?: string | null }) => (
    <h2 data-latest-snapshot-at={String(latestSnapshotAt)}>Trends stub</h2>
  ),
}))

import {
  useActivity,
  useCheckServiceStatuses,
  useDashboardSummary,
  useServiceSettings,
  useServiceStatuses,
} from "@/shared/lib/queries"
import type {
  ActivityEntry,
  DashboardSummary,
  ServicesSettings,
  ServicesStatusResponse,
} from "@/shared/lib/api"
import { mutationResult, queryResult } from "@/shared/test/mock-query"
import { Dashboard } from "@/features/dashboard/Dashboard"

const summary: DashboardSummary = {
  generated_at: "2026-10-27T12:00:00Z",
  refresh_seconds: 60,
  latest_snapshot_at: "2026-10-26T23:55:00+00:00",
  kpis: [
    { key: "movies", label: "Movies", unit: "count", value: 2236 },
    {
      key: "pending_requests",
      label: "Pending requests",
      unit: "count",
      value: null,
    },
  ],
  sources: [
    {
      key: "findarr",
      label: "Findarr",
      state: "ok",
      detail: null,
      stale_since: null,
      updated_at: null,
      link: "/findarr",
      metrics: [
        {
          key: "findarr.sonarr.missing_total",
          label: "Sonarr missing searches",
          unit: "count",
          value: 12,
        },
      ],
    },
    {
      key: "seer",
      label: "Seer",
      state: "not_configured",
      detail: null,
      stale_since: null,
      updated_at: null,
      link: "/settings",
      metrics: [],
    },
  ],
  disks: [
    {
      app: "radarr",
      path: "/movies",
      label: "Movies",
      free_bytes: 25,
      total_bytes: 100,
    },
  ],
}

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  )
}

function precedes(first: Element, second: Element): boolean {
  return Boolean(
    first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING,
  )
}

type Queries = typeof import("@/shared/lib/queries")

/** Apply the default hook results to a (possibly freshly imported) mock. */
function mockHooks(queries: Pick<Queries, keyof typeof hooks>) {
  vi.mocked(queries.useActivity).mockReturnValue(
    queryResult<ActivityEntry[]>([], false),
  )
  vi.mocked(queries.useDashboardSummary).mockReturnValue(
    queryResult(summary, false),
  )
  vi.mocked(queries.useServiceStatuses).mockReturnValue(
    queryResult<ServicesStatusResponse>(
      { interval_seconds: 60, last_check_at: null, services: {} },
      false,
    ),
  )
  vi.mocked(queries.useServiceSettings).mockReturnValue(
    queryResult<ServicesSettings>(undefined, false),
  )
  vi.mocked(queries.useCheckServiceStatuses).mockReturnValue(
    mutationResult(vi.fn(), false),
  )
}

const hooks = {
  useActivity,
  useCheckServiceStatuses,
  useDashboardSummary,
  useServiceSettings,
  useServiceStatuses,
}

describe("Dashboard", () => {
  beforeEach(() => {
    mockHooks(hooks)
  })

  it("composes integrations first, then figures, cards, disks, trends and activity", async () => {
    renderDashboard()

    const title = screen.getByRole("heading", { name: "Dashboard", level: 1 })
    expect(
      screen.getByText(
        "Statistics, trends and health for every app All-in-One ARR manages.",
      ),
    ).toBeInTheDocument()
    const integrations = screen.getByRole("heading", { name: "Integrations" })
    const kpis = screen.getByRole("region", { name: "Key figures" })
    const apps = screen.getByRole("region", { name: "Apps" })
    const disks = screen.getByText("Disk space")
    const trends = await screen.findByRole("heading", { name: "Trends stub" })
    const activity = screen.getByText("Recent activity")

    // The trends refresh when the summary reports a newer snapshot.
    expect(trends).toHaveAttribute(
      "data-latest-snapshot-at",
      "2026-10-26T23:55:00+00:00",
    )

    const order = [title, integrations, kpis, apps, disks, trends, activity]
    for (let index = 1; index < order.length; index += 1) {
      expect(precedes(order[index - 1], order[index])).toBe(true)
    }
    // Integrations is the first section after the page heading.
    const sections = screen.getAllByRole("region")
    expect(sections[0]).toContainElement(integrations)
  })

  it("renders source cards in summary order with their links", async () => {
    renderDashboard()

    const apps = screen.getByRole("region", { name: "Apps" })
    const links = within(apps)
      .getAllByRole("link")
      .map((link) => [link.textContent, link.getAttribute("href")])
    expect(links).toEqual([
      ["Findarr", "/findarr"],
      ["Seer", "/settings"],
      ["Set up in Settings", "/settings"],
    ])
    expect(within(apps).getByText("Not configured")).toBeInTheDocument()
    expect(
      screen.getByRole("progressbar", { name: "Radarr Movies used" }),
    ).toHaveAttribute("aria-valuenow", "75")
    expect(
      within(screen.getByRole("region", { name: "Key figures" })).getByText(
        "—",
      ),
    ).toBeInTheDocument()
    await screen.findByRole("heading", { name: "Trends stub" })
  })

  it("shows skeleton figures and a loading line while the summary loads", async () => {
    vi.mocked(useDashboardSummary).mockReturnValue(
      queryResult<DashboardSummary>(undefined, true),
    )
    renderDashboard()

    expect(
      screen.getByRole("region", { name: "Key figures loading" }),
    ).toBeInTheDocument()
    expect(screen.getByText("Loading statistics…")).toBeInTheDocument()
    expect(screen.queryByRole("region", { name: "Apps" })).toBeNull()
    expect(screen.queryByText("Disk space")).toBeNull()
    await screen.findByRole("heading", { name: "Trends stub" })
  })

  it("replaces figures and cards with an error card when the summary fails", async () => {
    vi.mocked(useDashboardSummary).mockReturnValue(
      queryResult<DashboardSummary>(undefined, false, {
        isError: true,
        error: new Error("Request failed with status 502: Bad Gateway"),
      }),
    )
    renderDashboard()

    const alert = screen.getByRole("alert")
    expect(
      within(alert).getByText("Could not load dashboard statistics"),
    ).toBeInTheDocument()
    expect(
      within(alert).getByText("Request failed with status 502: Bad Gateway"),
    ).toBeInTheDocument()
    expect(screen.queryByRole("region", { name: /Key figures/ })).toBeNull()
    expect(screen.queryByRole("region", { name: "Apps" })).toBeNull()
    // Integrations above and trends/activity below still render.
    const integrations = screen.getByRole("heading", { name: "Integrations" })
    expect(precedes(integrations, alert)).toBe(true)
    expect(precedes(alert, screen.getByText("Recent activity"))).toBe(true)
    // Without a summary the snapshot version is unknown, so no refresh fires.
    expect(
      await screen.findByRole("heading", { name: "Trends stub" }),
    ).toHaveAttribute("data-latest-snapshot-at", "undefined")
  })

  it("shows a fallback while the trend charts load", async () => {
    // React.lazy caches its module once resolved, so load a fresh Dashboard.
    vi.resetModules()
    mockHooks(await import("@/shared/lib/queries"))
    const { Dashboard: FreshDashboard } =
      await import("@/features/dashboard/Dashboard")
    render(
      <MemoryRouter>
        <FreshDashboard />
      </MemoryRouter>,
    )

    expect(screen.getByText("Loading trends…")).toBeInTheDocument()
    await screen.findByRole("heading", { name: "Trends stub" })
    expect(screen.queryByText("Loading trends…")).toBeNull()
  })

  it("offers no controls apart from 'Check now'", async () => {
    renderDashboard()
    await screen.findByRole("heading", { name: "Trends stub" })

    expect(
      screen.getAllByRole("button").map((button) => button.textContent),
    ).toEqual(["Check now"])
  })
})
