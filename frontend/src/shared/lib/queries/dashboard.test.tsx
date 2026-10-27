import { act, renderHook, waitFor } from "@testing-library/react"
import { focusManager } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/api", () => ({
  getDashboardHistory: vi.fn(),
  getDashboardSummary: vi.fn(),
}))

import * as api from "@/shared/lib/api"
import type {
  DashboardHistory,
  DashboardRange,
  DashboardSummary,
} from "@/shared/lib/api"

import {
  useDashboardHistory,
  useDashboardSummary,
} from "@/shared/lib/queries/dashboard"
import { queryKeys } from "@/shared/lib/queries/keys"
import { setup } from "@/shared/test/query-provider"

const BOOT_SNAPSHOT = "2026-10-27T08:00:05+00:00"
const EVENING_SNAPSHOT = "2026-10-27T23:55:00+00:00"

function summaryAt(latestSnapshotAt: string | null): DashboardSummary {
  return {
    generated_at: "2026-10-27T12:00:00+00:00",
    refresh_seconds: 60,
    latest_snapshot_at: latestSnapshotAt,
    kpis: [],
    sources: [],
    disks: [],
  }
}

/** History as stored at `latestSnapshotAt`: one point per snapshot so far. */
function historyAt(
  days: DashboardRange,
  latestSnapshotAt: string | null,
  values: number[] = [],
): DashboardHistory {
  return {
    days,
    start_day: "2026-10-21",
    end_day: "2026-10-27",
    latest_snapshot_at: latestSnapshotAt,
    series: [
      {
        key: "sonarr.series_total",
        label: "Series",
        unit: "count",
        kind: "gauge",
        points: values.map((value) => ({ day: "2026-10-27", value })),
      },
    ],
  }
}

/** Serve history as the server would after the snapshot at `version`. */
function serveHistory(version: string | null, values: number[] = []) {
  vi.mocked(api.getDashboardHistory).mockImplementation(async (days) =>
    historyAt(days, version, values),
  )
}

function points(history: DashboardHistory | undefined): number[] {
  return history?.series[0]?.points.map((point) => point.value) ?? []
}

beforeEach(() => {
  vi.mocked(api.getDashboardSummary).mockResolvedValue(summaryAt(null))
  vi.mocked(api.getDashboardHistory).mockImplementation(async (days) => ({
    days,
    start_day: "2026-10-21",
    end_day: "2026-10-27",
    latest_snapshot_at: null,
    series: [],
  }))
})

afterEach(() => {
  focusManager.setFocused(undefined)
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe("dashboard hooks", () => {
  it("useDashboardSummary polls every minute, only while visible", async () => {
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useDashboardSummary(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.getDashboardSummary).toHaveBeenCalledTimes(1)
    const query = queryClient
      .getQueryCache()
      .find({ queryKey: queryKeys.dashboardSummary })
    const options = query?.observers[0]?.options
    expect(options?.refetchInterval).toBe(60_000)
    expect(options?.refetchIntervalInBackground).toBe(false)
  })

  it("useDashboardHistory keeps one cache entry per range", async () => {
    const { queryClient, wrapper } = setup()
    const { result, rerender } = renderHook(
      ({ days }: { days: DashboardRange }) => useDashboardHistory(days),
      { wrapper, initialProps: { days: 30 } },
    )

    await waitFor(() => expect(result.current.data?.days).toBe(30))
    rerender({ days: 7 })
    // The previous range stays visible while the new one loads.
    expect(result.current.data?.days).toBe(30)
    await waitFor(() => expect(result.current.data?.days).toBe(7))

    expect(api.getDashboardHistory).toHaveBeenNthCalledWith(1, 30)
    expect(api.getDashboardHistory).toHaveBeenNthCalledWith(2, 7)
    expect(
      queryClient.getQueryData(queryKeys.dashboardHistory(30)),
    ).toMatchObject({ days: 30 })
    expect(
      queryClient.getQueryData(queryKeys.dashboardHistory(7)),
    ).toMatchObject({ days: 7 })

    rerender({ days: 30 })
    expect(result.current.data?.days).toBe(30)
    expect(api.getDashboardHistory).toHaveBeenCalledTimes(2)
  })

  it("useDashboardHistory does not refetch on window focus", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useDashboardHistory(90), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    act(() => {
      focusManager.setFocused(false)
      focusManager.setFocused(true)
    })

    expect(api.getDashboardHistory).toHaveBeenCalledTimes(1)
  })

  it("useDashboardHistory refetches when the summary reports a newer snapshot", async () => {
    const { wrapper } = setup()
    serveHistory(null)
    const initialProps: { latest: string | null } = { latest: null }
    const { result, rerender } = renderHook(
      ({ latest }) => useDashboardHistory(30, latest),
      { wrapper, initialProps },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    // Versions agree: nothing to refresh.
    rerender({ latest: null })
    expect(api.getDashboardHistory).toHaveBeenCalledTimes(1)
    expect(points(result.current.data)).toEqual([])

    // The start-up catch-up lands after the empty history was cached.
    serveHistory(BOOT_SNAPSHOT, [40])
    rerender({ latest: BOOT_SNAPSHOT })
    await waitFor(() => expect(points(result.current.data)).toEqual([40]))
    expect(api.getDashboardHistory).toHaveBeenCalledTimes(2)

    // A later snapshot refreshes an already populated range.
    serveHistory(EVENING_SNAPSHOT, [41])
    rerender({ latest: EVENING_SNAPSHOT })
    await waitFor(() => expect(points(result.current.data)).toEqual([41]))
    expect(api.getDashboardHistory).toHaveBeenCalledTimes(3)
    expect(result.current.data?.latest_snapshot_at).toBe(EVENING_SNAPSHOT)
  })

  it("useDashboardHistory refreshes a range cached before the snapshot when shown again", async () => {
    const { wrapper } = setup()
    serveHistory(null)
    const { result, rerender } = renderHook(
      ({ days, latest }: { days: DashboardRange; latest?: string | null }) =>
        useDashboardHistory(days, latest),
      { wrapper, initialProps: { days: 30 } },
    )
    // The 30-day history beat the boot snapshot and cached an empty result.
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(points(result.current.data)).toEqual([])

    serveHistory(BOOT_SNAPSHOT, [40])
    rerender({ days: 7, latest: BOOT_SNAPSHOT })
    await waitFor(() => expect(result.current.data?.days).toBe(7))
    expect(points(result.current.data)).toEqual([40])

    rerender({ days: 30, latest: BOOT_SNAPSHOT })
    await waitFor(() => expect(points(result.current.data)).toEqual([40]))
    expect(result.current.data?.days).toBe(30)
    expect(api.getDashboardHistory).toHaveBeenNthCalledWith(3, 30)
    expect(api.getDashboardHistory).toHaveBeenCalledTimes(3)
  })

  it("useDashboardHistory ignores an unknown summary version", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useDashboardHistory(30, undefined), {
      wrapper,
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(api.getDashboardHistory).toHaveBeenCalledTimes(1)
  })

  it("the summary poll picks up the boot snapshot and refreshes history", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    focusManager.setFocused(true)
    const { wrapper } = setup()
    // Both first responses predate the start-up catch-up snapshot.
    serveHistory(null)
    const { result } = renderHook(
      () => {
        const summary = useDashboardSummary()
        return useDashboardHistory(30, summary.data?.latest_snapshot_at)
      },
      { wrapper },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(points(result.current.data)).toEqual([])

    // The catch-up finishes; the next minute's summary poll reports it.
    vi.mocked(api.getDashboardSummary).mockResolvedValue(
      summaryAt(BOOT_SNAPSHOT),
    )
    serveHistory(BOOT_SNAPSHOT, [40])
    await act(() => vi.advanceTimersByTimeAsync(60_000))

    await waitFor(() => expect(points(result.current.data)).toEqual([40]))
    expect(api.getDashboardSummary).toHaveBeenCalledTimes(2)
    expect(api.getDashboardHistory).toHaveBeenCalledTimes(2)
  })
})
