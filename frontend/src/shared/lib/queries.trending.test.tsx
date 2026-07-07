import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/api", () => ({
  getTrending: vi.fn(),
  getTrendingRating: vi.fn(),
  getTrendingStatus: vi.fn(),
  addTrending: vi.fn(),
}))

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import * as api from "@/shared/lib/api"
import { toast } from "sonner"
import {
  queryKeys,
  useAddTrending,
  useTrending,
  useTrendingRating,
  useTrendingStatus,
} from "@/shared/lib/queries"
import type { TrendingItem, TrendingQuery } from "@/shared/lib/api"
import { setup } from "@/shared/test/query-provider"

const QUERY: TrendingQuery = {
  source: "trakt",
  media: "movie",
  category: "trending",
}

const ITEM: TrendingItem = {
  source: "trakt",
  media_type: "movie",
  tmdb: 100,
  imdb: "tt1",
  tvdb: null,
  trakt: 1,
  slug: null,
  title: "Dune",
  year: 2021,
  seer_status: null,
  already_tracked: false,
  in_library: false,
  in_library_available: false,
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.getTrending).mockResolvedValue([ITEM])
  vi.mocked(api.getTrendingRating).mockResolvedValue({
    imdb_rating: 8.6,
    imdb_votes: 10,
  })
})

describe("useTrending", () => {
  it("fetches trending items for a query", async () => {
    const { wrapper } = setup()
    const hook = renderHook(() => useTrending(QUERY), { wrapper })
    await waitFor(() => expect(hook.result.current.isSuccess).toBe(true))
    expect(api.getTrending).toHaveBeenCalledWith(QUERY)
    expect(hook.result.current.data).toEqual([ITEM])
  })
})

describe("useTrendingStatus", () => {
  it("fetches the scheduled-sync status", async () => {
    vi.mocked(api.getTrendingStatus).mockResolvedValue({
      last_synced_at: "2026-06-30T12:00:00+00:00",
      interval_minutes: 60,
      next_sync_at: "2026-06-30T13:00:00+00:00",
    })
    const { wrapper } = setup()
    const hook = renderHook(() => useTrendingStatus(), { wrapper })
    await waitFor(() => expect(hook.result.current.isSuccess).toBe(true))
    expect(api.getTrendingStatus).toHaveBeenCalled()
    expect(hook.result.current.data?.interval_minutes).toBe(60)
  })
})

describe("useTrendingRating", () => {
  it("fetches the rating when enabled and an id is present", async () => {
    const { wrapper } = setup()
    const hook = renderHook(() => useTrendingRating(ITEM, true), { wrapper })
    await waitFor(() => expect(hook.result.current.isSuccess).toBe(true))
    expect(api.getTrendingRating).toHaveBeenCalledWith({
      imdb: "tt1",
      media: "movie",
      tmdb: 100,
    })
  })

  it("does not fetch when the item carries no id", async () => {
    const { wrapper } = setup()
    const noId = { imdb: null, media_type: "movie" as const, tmdb: null }
    renderHook(() => useTrendingRating(noId, true), { wrapper })
    await Promise.resolve()
    expect(api.getTrendingRating).not.toHaveBeenCalled()
  })

  it("does not fetch when disabled", async () => {
    const { wrapper } = setup()
    renderHook(() => useTrendingRating(ITEM, false), { wrapper })
    await Promise.resolve()
    expect(api.getTrendingRating).not.toHaveBeenCalled()
  })
})

describe("useAddTrending", () => {
  it("invalidates queries and toasts on a normal add", async () => {
    vi.mocked(api.addTrending).mockResolvedValue({ status: "added" })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const hook = renderHook(() => useAddTrending(), { wrapper })

    act(() =>
      hook.result.current.mutate({
        media_type: "movie",
        owner_user: "me",
        slug: "my-list",
        tmdb: 100,
      }),
    )
    await waitFor(() => expect(hook.result.current.isSuccess).toBe(true))

    expect(toast.success).toHaveBeenCalledWith(
      "Added to Trakt list",
      expect.objectContaining({
        description: "Syncing now to request it in Seer.",
      }),
    )
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.status })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.lists })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["trending"] })
  })

  it("toasts the pending-sync variant when a sync is already running", async () => {
    vi.mocked(api.addTrending).mockResolvedValue({
      status: "added_pending_sync",
    })
    const { wrapper } = setup()
    const hook = renderHook(() => useAddTrending(), { wrapper })

    act(() =>
      hook.result.current.mutate({
        media_type: "movie",
        owner_user: "me",
        slug: "my-list",
        tmdb: 100,
      }),
    )
    await waitFor(() => expect(hook.result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith(
      "Added to Trakt list",
      expect.objectContaining({
        description: expect.stringContaining("already running"),
      }),
    )
  })

  it("toasts an error when the add fails", async () => {
    vi.mocked(api.addTrending).mockRejectedValue(new Error("nope"))
    const { wrapper } = setup()
    const hook = renderHook(() => useAddTrending(), { wrapper })

    act(() =>
      hook.result.current.mutate({
        media_type: "movie",
        owner_user: "me",
        slug: "my-list",
        tmdb: 100,
      }),
    )
    await waitFor(() => expect(hook.result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not add to list", {
      description: "nope",
    })
  })
})
