import { afterEach, describe, expect, it, vi } from "vitest"

import {
  DASHBOARD_RANGES,
  getDashboardHistory,
  getDashboardSummary,
  type DashboardHistory,
  type DashboardSummary,
} from "@/shared/lib/api/dashboard"

const sampleSummary: DashboardSummary = {
  generated_at: "2026-10-27T12:00:00+00:00",
  refresh_seconds: 60,
  latest_snapshot_at: null,
  kpis: [{ key: "movies", label: "Movies", unit: "count", value: 12 }],
  sources: [],
  disks: [],
}

function sampleHistory(days: DashboardHistory["days"]): DashboardHistory {
  return {
    days,
    start_day: "2026-10-21",
    end_day: "2026-10-27",
    latest_snapshot_at: null,
    series: [],
  }
}

function mockFetch(response: Response) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(response)
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe("Dashboard API", () => {
  it("GETs the live summary", async () => {
    const fetchSpy = mockFetch(jsonResponse(sampleSummary))

    await expect(getDashboardSummary()).resolves.toEqual(sampleSummary)
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/dashboard/summary",
      expect.anything(),
    )
  })

  it.each(DASHBOARD_RANGES)("GETs the %i-day history", async (days) => {
    const fetchSpy = mockFetch(jsonResponse(sampleHistory(days)))

    await expect(getDashboardHistory(days)).resolves.toEqual(
      sampleHistory(days),
    )
    expect(fetchSpy).toHaveBeenCalledWith(
      `/api/dashboard/history?days=${days}`,
      expect.anything(),
    )
  })

  it("offers the 7, 30 and 90 day ranges in order", () => {
    expect(DASHBOARD_RANGES).toEqual([7, 30, 90])
  })
})
