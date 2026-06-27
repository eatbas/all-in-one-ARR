import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/api", () => ({
  getStatus: vi.fn(),
  getActivity: vi.fn(),
  getDatabaseStats: vi.fn(),
  clearActivity: vi.fn(),
  clearItems: vi.fn(),
  clearPosters: vi.fn(),
}))

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import * as api from "@/shared/lib/api"
import { toast } from "sonner"

import {
  queryKeys,
  useActivity,
  useClearActivity,
  useClearItems,
  useClearPosters,
  useDatabaseStats,
  useStatus,
} from "@/shared/lib/queries"
import { setup } from "@/shared/test/query-provider"

beforeEach(() => {
  vi.mocked(api.getStatus).mockResolvedValue({
    trakt_connected: false,
    counts: { synced: 0, requested: 0, available: 0, removed: 0 },
  })
  vi.mocked(api.getActivity).mockResolvedValue([])
  vi.mocked(api.getDatabaseStats).mockResolvedValue({
    db_size_bytes: 1024,
    poster_cache_bytes: 2048,
    item_count: 5,
    activity_count: 12,
    list_state_count: 2,
  })
})

describe("dashboard status hooks", () => {
  it("useStatus fetches the app status (counts)", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useStatus(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.getStatus).toHaveBeenCalled()
    expect(result.current.data?.trakt_connected).toBe(false)
  })

  it("useActivity fetches the activity feed", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useActivity(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.getActivity).toHaveBeenCalled()
  })
})

describe("database hooks", () => {
  it("useDatabaseStats fetches the storage overview", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useDatabaseStats(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.getDatabaseStats).toHaveBeenCalled()
    expect(result.current.data?.db_size_bytes).toBe(1024)
  })

  it("useClearActivity toasts and invalidates on success", async () => {
    vi.mocked(api.clearActivity).mockResolvedValue({
      db_size_bytes: 512,
      poster_cache_bytes: 2048,
      item_count: 5,
      activity_count: 1,
      list_state_count: 2,
    })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useClearActivity(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith("Activity log cleared")
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.database })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("useClearActivity toasts on error", async () => {
    vi.mocked(api.clearActivity).mockRejectedValue(new Error("denied"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useClearActivity(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not clear activity log", {
      description: "denied",
    })
  })

  it("useClearItems toasts and invalidates affected queries", async () => {
    vi.mocked(api.clearItems).mockResolvedValue({
      db_size_bytes: 512,
      poster_cache_bytes: 2048,
      item_count: 0,
      activity_count: 1,
      list_state_count: 0,
    })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useClearItems(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith(
      "Synced items cleared",
      expect.objectContaining({ description: expect.any(String) }),
    )
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.database })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.lists })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.status })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["items"] })
  })

  it("useClearItems toasts on error", async () => {
    vi.mocked(api.clearItems).mockRejectedValue(new Error("denied"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useClearItems(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not clear synced items", {
      description: "denied",
    })
  })

  it("useClearPosters toasts and invalidates on success", async () => {
    vi.mocked(api.clearPosters).mockResolvedValue({
      db_size_bytes: 1024,
      poster_cache_bytes: 0,
      item_count: 5,
      activity_count: 13,
      list_state_count: 2,
    })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useClearPosters(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith("Poster cache cleared")
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.database })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("useClearPosters toasts on error", async () => {
    vi.mocked(api.clearPosters).mockRejectedValue(new Error("denied"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useClearPosters(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not clear poster cache", {
      description: "denied",
    })
  })
})
