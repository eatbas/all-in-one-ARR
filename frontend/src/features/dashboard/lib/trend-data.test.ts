import { describe, expect, it } from "vitest"

import type { DashboardHistory } from "@/shared/lib/api"
import {
  buildTrendRows,
  daysBetween,
  formatCompactCount,
  formatDayLabel,
  formatTooltipDay,
  hasTrendData,
  isIsolatedPoint,
  trendValueFormatter,
  type TrendRow,
} from "@/features/dashboard/lib/trend-data"

function history(
  series: Array<{ key: string; points: Array<[string, number]> }>,
): DashboardHistory {
  return {
    days: 7,
    start_day: "2026-10-01",
    end_day: "2026-10-04",
    latest_snapshot_at: "2026-10-04T23:55:00+00:00",
    series: series.map(({ key, points }) => ({
      key,
      label: key,
      unit: "count",
      kind: "gauge",
      points: points.map(([day, value]) => ({ day, value })),
    })),
  }
}

describe("trend data", () => {
  it("lists every day of a window inclusively", () => {
    expect(daysBetween("2026-10-30", "2026-11-02")).toEqual([
      "2026-10-30",
      "2026-10-31",
      "2026-11-01",
      "2026-11-02",
    ])
    expect(daysBetween("2026-10-02", "2026-10-01")).toEqual([])
  })

  it("builds one row per day with null gaps and summed sources", () => {
    const rows = buildTrendRows(
      history([
        {
          key: "a.one",
          points: [
            ["2026-10-01", 1],
            ["2026-10-03", 3],
          ],
        },
        { key: "b.two", points: [["2026-10-01", 10]] },
        { key: "c.three", points: [["2026-10-03", 5]] },
      ]),
      [
        { key: "one", metrics: ["a.one"] },
        { key: "sum", metrics: ["b.two", "c.three", "missing.metric"] },
      ],
    )

    expect(rows).toEqual([
      { day: "2026-10-01", one: 1, sum: 10 },
      { day: "2026-10-02", one: null, sum: null },
      { day: "2026-10-03", one: 3, sum: 5 },
      { day: "2026-10-04", one: null, sum: null },
    ])
  })

  it("detects whether any series has points", () => {
    expect(hasTrendData(history([{ key: "a", points: [] }]))).toBe(false)
    expect(
      hasTrendData(history([{ key: "a", points: [["2026-10-01", 0]] }])),
    ).toBe(true)
  })

  it("formats day labels in UTC", () => {
    expect(formatDayLabel("2026-10-26")).toBe("26 Oct")
    expect(formatTooltipDay("2026-01-05")).toBe("5 Jan")
  })

  it("formats compact counts for axis ticks", () => {
    expect(formatCompactCount(0)).toBe("0")
    expect(formatCompactCount(999.6)).toBe("1000")
    expect(formatCompactCount(1000)).toBe("1k")
    expect(formatCompactCount(18_450)).toBe("18.4k")
  })

  it("formats tooltip values by the chart's unit", () => {
    expect(trendValueFormatter("bytes")(1024)).toBe("1.0 KB")
    expect(trendValueFormatter("count")(1500)).toBe((1500).toLocaleString())
  })

  it("finds observations with no neighbouring value", () => {
    const rows: TrendRow[] = [
      { day: "2026-10-01", a: 1, b: 1 },
      { day: "2026-10-02", a: null, b: 2 },
      { day: "2026-10-03", a: 3, b: null },
      { day: "2026-10-04", a: 4, b: 4 },
      { day: "2026-10-05", a: null, b: null },
      { day: "2026-10-06", a: 6, b: 0 },
    ]

    // First and last rows count the missing outer neighbour as a gap.
    expect(isIsolatedPoint(rows, "a", 0)).toBe(true)
    expect(isIsolatedPoint(rows, "a", 5)).toBe(true)
    // Joined to a neighbour on one side.
    expect(isIsolatedPoint(rows, "a", 2)).toBe(false)
    expect(isIsolatedPoint(rows, "a", 3)).toBe(false)
    // A gap is never a point; a zero is a value.
    expect(isIsolatedPoint(rows, "a", 1)).toBe(false)
    expect(isIsolatedPoint(rows, "b", 5)).toBe(true)
    expect(isIsolatedPoint(rows, "b", 0)).toBe(false)
    // An unknown key has no values at all.
    expect(isIsolatedPoint(rows, "c", 0)).toBe(false)
  })
})
