import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type * as Recharts from "recharts"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/queries", () => ({
  useDashboardHistory: vi.fn(),
}))

// `vi.mock` is hoisted above the imports, so the helper is loaded inside it.
vi.mock("recharts", async (importOriginal) => {
  const { withFixedResponsiveContainer } =
    await import("@/shared/test/recharts")
  return withFixedResponsiveContainer(await importOriginal<typeof Recharts>())
})

import type { DashboardHistory } from "@/shared/lib/api"
import { useDashboardHistory } from "@/shared/lib/queries"
import { queryResult } from "@/shared/test/mock-query"
import { TrendCharts } from "@/features/dashboard/components/trend-charts"

const PLOTTED = [
  "sonarr.episodes_with_files",
  "sonarr.episodes_missing",
  "radarr.movies_with_files",
  "radarr.movies_missing",
  "sonarr.disk_free_bytes",
  "radarr.disk_free_bytes",
  "seer.requests_pending",
  "seer.requests_approved",
  "seer.requests_available",
  "findarr.sonarr.missing_total",
  "findarr.radarr.upgrade_total",
  "languagarr.non_compliant",
]

function history(days: DashboardHistory["days"], withPoints = true) {
  return {
    days,
    start_day: "2026-10-21",
    end_day: "2026-10-27",
    latest_snapshot_at: "2026-10-27T23:55:00+00:00",
    series: PLOTTED.map((key) => ({
      key,
      label: key,
      unit: "count" as const,
      kind: "gauge" as const,
      points: withPoints
        ? [
            { day: "2026-10-21", value: 5 },
            // 2026-10-22 is a gap.
            { day: "2026-10-23", value: 7 },
            { day: "2026-10-27", value: 9 },
          ]
        : [],
    })),
  } satisfies DashboardHistory
}

/** History with only the given metrics' points (every other series empty). */
function sparseHistory(
  points: Record<string, ReadonlyArray<readonly [string, number]>>,
): DashboardHistory {
  return {
    ...history(30, false),
    series: PLOTTED.map((key) => ({
      key,
      label: key,
      unit: "count" as const,
      kind: "gauge" as const,
      points: (points[key] ?? []).map(([day, value]) => ({ day, value })),
    })),
  }
}

/** The isolated-observation markers drawn in the chart titled `title`. */
function isolatedDots(title: string): SVGCircleElement[] {
  const figure = screen.getByText(title).closest("figure")!
  return Array.from(
    figure.querySelectorAll<SVGCircleElement>("circle.trend-isolated-dot"),
  )
}

beforeEach(() => {
  vi.mocked(useDashboardHistory).mockImplementation((days) =>
    queryResult(history(days), false),
  )
})

describe("TrendCharts", () => {
  it("defaults to 30 days and switches range with the toggle", async () => {
    const user = userEvent.setup()
    render(<TrendCharts latestSnapshotAt="2026-10-27T23:55:00+00:00" />)

    // The summary's snapshot version is handed to the history hook.
    expect(useDashboardHistory).toHaveBeenLastCalledWith(
      30,
      "2026-10-27T23:55:00+00:00",
    )
    expect(screen.getByRole("tab", { name: "30 days" })).toHaveAttribute(
      "aria-selected",
      "true",
    )

    await user.click(screen.getByRole("tab", { name: "7 days" }))
    expect(useDashboardHistory).toHaveBeenLastCalledWith(
      7,
      "2026-10-27T23:55:00+00:00",
    )
    expect(screen.getByRole("tab", { name: "7 days" })).toHaveAttribute(
      "aria-selected",
      "true",
    )

    await user.click(screen.getByRole("tab", { name: "90 days" }))
    expect(useDashboardHistory).toHaveBeenLastCalledWith(
      90,
      "2026-10-27T23:55:00+00:00",
    )
  })

  it("renders the five charts with their legends", () => {
    const { container } = render(<TrendCharts />)

    for (const name of [
      "Sonarr episodes with files and missing episodes per day",
      "Radarr movies with files and missing movies per day",
      "Free disk space per day",
      "Seer requests by status per day",
      "Findarr searches per day and Languagarr non-compliant files",
    ]) {
      expect(screen.getByRole("img", { name })).toBeInTheDocument()
    }
    const modules = screen.getByText("Module activity").closest("figure")!
    expect(modules).toHaveClass("lg:col-span-2")
    expect(
      within(modules).getByText("Findarr searches per day"),
    ).toBeInTheDocument()
    expect(container.querySelectorAll(".recharts-area-area").length).toBe(2)
    expect(
      container.querySelectorAll(".recharts-bar-rectangle").length,
    ).toBeGreaterThan(0)
    // Line series: one each for Sonarr, Radarr and module activity, two for
    // disk free and three for requests.
    expect(
      container.querySelectorAll(".recharts-line .recharts-line-curve").length,
    ).toBe(8)
    expect(screen.getAllByText("21 Oct").length).toBeGreaterThan(0)
  })

  it("shows a loading state before the first response", () => {
    vi.mocked(useDashboardHistory).mockReturnValue(
      queryResult<DashboardHistory>(undefined, true),
    )
    render(<TrendCharts />)

    expect(screen.getByText("Loading trends…")).toBeInTheDocument()
  })

  it("shows the collecting-data state before the first snapshot", () => {
    vi.mocked(useDashboardHistory).mockReturnValue(
      queryResult(history(30, false), false),
    )
    render(<TrendCharts />)

    expect(
      screen.getByText(
        "Collecting data — trends appear after the first daily snapshot",
      ),
    ).toBeInTheDocument()
    expect(screen.queryByRole("img")).not.toBeInTheDocument()
  })

  it("reports a failed history request", () => {
    vi.mocked(useDashboardHistory).mockReturnValue(
      queryResult<DashboardHistory>(undefined, false, {
        isError: true,
        error: new Error("Request failed with status 500"),
      }),
    )
    render(<TrendCharts />)

    expect(
      screen.getByText("Could not load trends: Request failed with status 500"),
    ).toBeInTheDocument()
  })

  it("marks a single observation in area and line series", () => {
    // The first snapshot: one day of data in a 7-day window.
    vi.mocked(useDashboardHistory).mockReturnValue(
      queryResult(
        sparseHistory({
          "sonarr.episodes_with_files": [["2026-10-27", 18_400]],
          "sonarr.episodes_missing": [["2026-10-27", 640]],
          "seer.requests_pending": [["2026-10-27", 9]],
        }),
        false,
      ),
    )
    render(<TrendCharts />)

    const sonarr = isolatedDots("Sonarr library")
    expect(sonarr).toHaveLength(2)
    expect(sonarr.map((dot) => dot.getAttribute("fill")).sort()).toEqual([
      "var(--color-sonarr_episodes_missing)",
      "var(--color-sonarr_episodes_with_files)",
    ])
    for (const dot of sonarr) {
      expect(Number(dot.getAttribute("cx"))).toBeGreaterThan(0)
      expect(Number(dot.getAttribute("cy"))).toBeGreaterThan(0)
      expect(dot).toHaveAttribute("r", "3")
    }
    expect(isolatedDots("Requests")).toHaveLength(1)
    // Series without any observation draw no marker.
    expect(isolatedDots("Radarr library")).toHaveLength(0)
    expect(isolatedDots("Disk free")).toHaveLength(0)
  })

  it("marks only the observations separated by gaps", () => {
    vi.mocked(useDashboardHistory).mockReturnValue(
      queryResult(
        sparseHistory({
          // 21 Oct alone, 23–24 Oct joined, 27 Oct alone.
          "radarr.movies_missing": [
            ["2026-10-21", 90],
            ["2026-10-23", 92],
            ["2026-10-24", 93],
            ["2026-10-27", 95],
          ],
          // A fully joined run needs no marker.
          "radarr.movies_with_files": [
            ["2026-10-25", 2140],
            ["2026-10-26", 2141],
            ["2026-10-27", 2142],
          ],
        }),
        false,
      ),
    )
    const { container } = render(<TrendCharts />)

    const dots = isolatedDots("Radarr library")
    expect(dots).toHaveLength(2)
    expect(new Set(dots.map((dot) => dot.getAttribute("fill")))).toEqual(
      new Set(["var(--color-radarr_movies_missing)"]),
    )
    const [first, last] = dots.map((dot) => Number(dot.getAttribute("cx")))
    expect(first).toBeLessThan(last!)
    // The joined run between the gaps is still drawn as a line.
    expect(
      container.querySelectorAll(".recharts-line .recharts-line-curve").length,
    ).toBeGreaterThan(0)
  })
})
