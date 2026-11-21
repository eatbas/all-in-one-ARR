import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/api", () => ({
  getRemindarrStatus: vi.fn(),
  getRemindarrSettings: vi.fn(),
  getRemindarrTags: vi.fn(),
  getRemindarrResults: vi.fn(),
  updateRemindarrSettings: vi.fn(),
  runRemindarr: vi.fn(),
}))

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import * as api from "@/shared/lib/api"
import type { RemindarrResults, RemindarrStatus } from "@/shared/lib/api"
import { toast } from "sonner"
import { queryKeys } from "@/shared/lib/queries/keys"
import {
  useRemindarrBadgeCount,
  useRemindarrResults,
  useRemindarrSettings,
  useRemindarrStatus,
  useRemindarrTags,
  useRunRemindarr,
  useUpdateRemindarrSettings,
} from "@/shared/lib/queries/remindarr"
import { setup } from "@/shared/test/query-provider"

function status(enabled: boolean, unwatched: number): RemindarrStatus {
  return {
    settings: {
      enabled,
      interval_minutes: 60,
      tag_ids: [1],
      monitored_only: true,
    },
    running: false,
    plex_configured: true,
    last_success_at: null,
    last_attempt_at: null,
    last_error: null,
    stale: false,
    missing_tag_ids: [],
    counts: {
      unwatched,
      series_with_unwatched: 1,
      tracked_series: 1,
      unmatched_series: 0,
    },
  }
}

beforeEach(() => {
  vi.mocked(api.getRemindarrStatus).mockResolvedValue(status(true, 14))
  vi.mocked(api.getRemindarrSettings).mockResolvedValue(
    status(true, 0).settings,
  )
  vi.mocked(api.getRemindarrTags).mockResolvedValue([{ id: 1, label: "anime" }])
  vi.mocked(api.getRemindarrResults).mockResolvedValue({
    last_success_at: null,
    series: [],
    unmatched: [],
  })
})

describe("Remindarr queries", () => {
  it.each([
    ["status", useRemindarrStatus, api.getRemindarrStatus],
    ["settings", useRemindarrSettings, api.getRemindarrSettings],
    ["tags", useRemindarrTags, api.getRemindarrTags],
    ["results", useRemindarrResults, api.getRemindarrResults],
  ] as const)("fetches the %s", async (_name, hook, fetcher) => {
    const { wrapper } = setup()
    const { result } = renderHook(() => hook(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(fetcher).toHaveBeenCalled()
  })

  it("keeps every key under the remindarr prefix", () => {
    for (const key of [
      queryKeys.remindarrStatus,
      queryKeys.remindarrSettings,
      queryKeys.remindarrTags,
      queryKeys.remindarrResults,
    ]) {
      expect(key[0]).toBe("remindarr")
    }
  })
})

describe("useRemindarrBadgeCount", () => {
  it("returns the unwatched count once loaded", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useRemindarrBadgeCount(), { wrapper })
    expect(result.current).toBeNull()
    await waitFor(() => expect(result.current).toBe(14))
  })

  it.each([
    ["disabled", status(false, 14)],
    ["at zero", status(true, 0)],
  ])("is null while %s", async (_case, value) => {
    vi.mocked(api.getRemindarrStatus).mockResolvedValue(value)
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useRemindarrBadgeCount(), { wrapper })
    await waitFor(() =>
      expect(queryClient.getQueryData(queryKeys.remindarrStatus)).toEqual(
        value,
      ),
    )
    expect(result.current).toBeNull()
  })

  it("is null when the status request fails", async () => {
    vi.mocked(api.getRemindarrStatus).mockRejectedValue(new Error("down"))
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useRemindarrBadgeCount(), { wrapper })
    await waitFor(() =>
      expect(queryClient.getQueryState(queryKeys.remindarrStatus)?.status).toBe(
        "error",
      ),
    )
    expect(result.current).toBeNull()
  })

  it("hides a cached count once a later status request fails", async () => {
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useRemindarrBadgeCount(), { wrapper })
    await waitFor(() => expect(result.current).toBe(14))

    vi.mocked(api.getRemindarrStatus).mockRejectedValue(new Error("down"))
    await act(() =>
      queryClient.refetchQueries({ queryKey: queryKeys.remindarrStatus }),
    )

    // TanStack Query keeps the cached status beside the refetch error.
    expect(queryClient.getQueryState(queryKeys.remindarrStatus)?.status).toBe(
      "error",
    )
    expect(queryClient.getQueryData(queryKeys.remindarrStatus)).toEqual(
      status(true, 14),
    )
    await waitFor(() => expect(result.current).toBeNull())

    // The badge returns once the status can be read again.
    vi.mocked(api.getRemindarrStatus).mockResolvedValue(status(true, 9))
    await act(() =>
      queryClient.refetchQueries({ queryKey: queryKeys.remindarrStatus }),
    )
    await waitFor(() => expect(result.current).toBe(9))
  })

  it("keeps the stored count of a stale but successful status", async () => {
    vi.mocked(api.getRemindarrStatus).mockResolvedValue({
      ...status(true, 14),
      stale: true,
      last_error: "Plex rejected the token",
    })
    const { wrapper } = setup()
    const { result } = renderHook(() => useRemindarrBadgeCount(), { wrapper })
    await waitFor(() => expect(result.current).toBe(14))
  })
})

describe("useRemindarrResults", () => {
  const FIRST_RUN = "2026-11-21T09:00:00Z"
  const SECOND_RUN = "2026-11-21T10:00:00Z"

  function generation(lastSuccessAt: string | null): RemindarrStatus {
    return { ...status(true, 14), last_success_at: lastSuccessAt }
  }

  function results(
    lastSuccessAt: string,
    titles: string[],
    newToday: boolean,
    unmatchedTitles: string[] = [],
  ): RemindarrResults {
    return {
      last_success_at: lastSuccessAt,
      series: titles.map((title, index) => ({
        series_id: index + 1,
        series_title: title,
        series_slug: null,
        tvdb_id: null,
        episodes_not_in_plex: 0,
        latest_added_at: "2026-11-21T06:00:00Z",
        new_today: newToday ? 1 : 0,
        episodes: [
          {
            episode_id: index + 10,
            series_id: index + 1,
            episode_file_id: index + 100,
            season_number: 1,
            episode_number: 1,
            label: "S01E01",
            title: "Pilot",
            air_date_utc: null,
            added_at: "2026-11-21T06:00:00Z",
            new_today: newToday,
          },
        ],
      })),
      unmatched: unmatchedTitles.map((title, index) => ({
        series_id: index + 50,
        series_title: title,
        series_slug: null,
        tvdb_id: null,
        reason: "no_tvdb_id",
        reason_label: "No TVDB id in Sonarr",
      })),
    }
  }

  /** The page's pair: the polled status and the results that follow it. */
  function renderPage() {
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(
      () => ({
        status: useRemindarrStatus(),
        results: useRemindarrResults(),
      }),
      { wrapper },
    )
    return { queryClient, result }
  }

  afterEach(() => {
    vi.useRealTimers()
  })

  it("waits for the status before reading the results", async () => {
    let resolveStatus: (value: RemindarrStatus) => void = () => undefined
    vi.mocked(api.getRemindarrStatus).mockReturnValue(
      new Promise((resolve) => {
        resolveStatus = resolve
      }),
    )
    const { result } = renderPage()
    expect(result.current.results.isPending).toBe(true)
    expect(api.getRemindarrResults).not.toHaveBeenCalled()

    act(() => resolveStatus(generation(null)))
    await waitFor(() => expect(result.current.results.isSuccess).toBe(true))
    expect(api.getRemindarrResults).toHaveBeenCalledTimes(1)
  })

  it("stays pending when the first status request fails", async () => {
    vi.mocked(api.getRemindarrStatus).mockRejectedValue(new Error("down"))
    const { result } = renderPage()
    await waitFor(() => expect(result.current.status.isError).toBe(true))
    expect(result.current.results.isPending).toBe(true)
    expect(api.getRemindarrResults).not.toHaveBeenCalled()
  })

  it("re-reads the rows when a scheduled refresh completes", async () => {
    vi.mocked(api.getRemindarrStatus).mockResolvedValue(generation(FIRST_RUN))
    vi.mocked(api.getRemindarrResults).mockResolvedValue(
      results(FIRST_RUN, ["Starfall Academy"], true, ["Paper Cranes"]),
    )
    const { queryClient, result } = renderPage()
    await waitFor(() =>
      expect(result.current.results.data?.last_success_at).toBe(FIRST_RUN),
    )

    // A scheduled refresh replaced the results; no mutation ran on this page,
    // so only the status poll can notice.
    let resolveResults: (value: RemindarrResults) => void = () => undefined
    vi.mocked(api.getRemindarrResults).mockReturnValue(
      new Promise((resolve) => {
        resolveResults = resolve
      }),
    )
    vi.mocked(api.getRemindarrStatus).mockResolvedValue(generation(SECOND_RUN))
    await act(() =>
      queryClient.refetchQueries({ queryKey: queryKeys.remindarrStatus }),
    )

    // The previous rows stay on screen while the new generation loads.
    await waitFor(() =>
      expect(result.current.results.isPlaceholderData).toBe(true),
    )
    expect(result.current.results.isPending).toBe(false)
    expect(result.current.results.data?.last_success_at).toBe(FIRST_RUN)

    act(() => resolveResults(results(SECOND_RUN, ["Harbour Lights"], false)))
    await waitFor(() =>
      expect(result.current.results.data?.last_success_at).toBe(SECOND_RUN),
    )
    const data = result.current.results.data
    expect(data?.series.map((group) => group.series_title)).toEqual([
      "Harbour Lights",
    ])
    expect(data?.series[0].episodes[0].new_today).toBe(false)
    expect(data?.unmatched).toEqual([])
    expect(result.current.status.data?.last_success_at).toBe(SECOND_RUN)
    expect(result.current.results.isPlaceholderData).toBe(false)
  })

  it("keeps the rows of a failed refresh's unchanged generation", async () => {
    vi.mocked(api.getRemindarrStatus).mockResolvedValue(generation(FIRST_RUN))
    vi.mocked(api.getRemindarrResults).mockResolvedValue(
      results(FIRST_RUN, ["Starfall Academy"], true),
    )
    const { queryClient, result } = renderPage()
    await waitFor(() => expect(result.current.results.isSuccess).toBe(true))

    vi.mocked(api.getRemindarrStatus).mockResolvedValue({
      ...generation(FIRST_RUN),
      stale: true,
      last_error: "Plex rejected the token",
    })
    await act(() =>
      queryClient.refetchQueries({ queryKey: queryKeys.remindarrStatus }),
    )

    await waitFor(() => expect(result.current.status.data?.stale).toBe(true))
    expect(api.getRemindarrResults).toHaveBeenCalledTimes(1)
    expect(result.current.results.data?.last_success_at).toBe(FIRST_RUN)
  })

  it("re-reads new-today flags on an open page after local midnight", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.mocked(api.getRemindarrStatus).mockResolvedValue(generation(FIRST_RUN))
    vi.mocked(api.getRemindarrResults).mockResolvedValue(
      results(FIRST_RUN, ["Starfall Academy"], true),
    )
    const { result } = renderPage()
    await waitFor(() =>
      expect(result.current.results.data?.series[0].new_today).toBe(1),
    )

    // Same refresh generation, but the server's local date has rolled over.
    vi.mocked(api.getRemindarrResults).mockResolvedValue(
      results(FIRST_RUN, ["Starfall Academy"], false),
    )
    await act(() => vi.advanceTimersByTimeAsync(60_000))

    await waitFor(() =>
      expect(result.current.results.data?.series[0].new_today).toBe(0),
    )
    expect(result.current.results.data?.series[0].episodes[0].new_today).toBe(
      false,
    )
  })
})

describe("Remindarr mutations", () => {
  it("settings save toasts and invalidates", async () => {
    vi.mocked(api.updateRemindarrSettings).mockResolvedValue(status(true, 0))
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useUpdateRemindarrSettings(), {
      wrapper,
    })
    act(() => result.current.mutate({ enabled: true }))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith("Remindarr settings saved")
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["remindarr"] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("settings save failure toasts the reason", async () => {
    vi.mocked(api.updateRemindarrSettings).mockRejectedValue(
      new Error("Unknown Sonarr tag id: 12"),
    )
    const { wrapper } = setup()
    const { result } = renderHook(() => useUpdateRemindarrSettings(), {
      wrapper,
    })
    act(() => result.current.mutate({ tag_ids: [12] }))
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith(
      "Could not save Remindarr settings",
      { description: "Unknown Sonarr tag id: 12" },
    )
  })

  it.each([
    [14, 5, "14 unwatched episodes in 5 series"],
    [1, 1, "1 unwatched episode in 1 series"],
  ])(
    "refresh success toasts %i episodes in %i series",
    async (unwatched, seriesCount, description) => {
      vi.mocked(api.runRemindarr).mockResolvedValue({
        status: "success",
        unwatched,
        series_with_unwatched: seriesCount,
        tracked_series: 7,
        unmatched_series: 2,
      })
      const { queryClient, wrapper } = setup()
      const invalidate = vi.spyOn(queryClient, "invalidateQueries")
      const { result } = renderHook(() => useRunRemindarr(), { wrapper })
      act(() => result.current.mutate())
      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(toast.success).toHaveBeenCalledWith("Remindarr refreshed", {
        description,
      })
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["remindarr"] })
    },
  )

  it("refresh while disabled toasts a skip", async () => {
    vi.mocked(api.runRemindarr).mockResolvedValue({
      status: "disabled",
      unwatched: 0,
      series_with_unwatched: 0,
      tracked_series: 0,
      unmatched_series: 0,
    })
    const { wrapper } = setup()
    const { result } = renderHook(() => useRunRemindarr(), { wrapper })
    act(() => result.current.mutate())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith("Remindarr refresh skipped", {
      description: "Enable Remindarr on the Settings tab to refresh.",
    })
  })

  it.each([
    "A Remindarr refresh is already running.",
    "Plex rejected the token",
  ])("refresh failure toasts %s and refreshes the status", async (message) => {
    vi.mocked(api.runRemindarr).mockRejectedValue(new Error(message))
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useRunRemindarr(), { wrapper })
    act(() => result.current.mutate())
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Remindarr refresh failed", {
      description: message,
    })
    // The status now carries the stale flag and the error.
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["remindarr"] })
  })
})
