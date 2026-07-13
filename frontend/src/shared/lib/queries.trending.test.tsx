import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/api", () => ({
  getTrending: vi.fn(),
  getTrendingStatus: vi.fn(),
  addTrending: vi.fn(),
  searchTrending: vi.fn(),
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
  useTrendingSearch,
  useTrendingStatus,
} from "@/shared/lib/queries"
import type {
  TrendingItem,
  TrendingQuery,
  TrendingSearchQuery,
} from "@/shared/lib/api"
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
  anilist: null,
  poster_url: null,
  seer_status: null,
  imdb_rating: null,
  already_tracked: false,
  in_library: false,
  in_library_available: false,
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.getTrending).mockResolvedValue([ITEM])
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

describe("useTrendingSearch", () => {
  const SEARCH: TrendingSearchQuery = {
    source: "trakt",
    media: "movie",
    query: "dune",
  }

  it("fetches search results when enabled", async () => {
    vi.mocked(api.searchTrending).mockResolvedValue([ITEM])
    const { wrapper } = setup()
    const hook = renderHook(() => useTrendingSearch(SEARCH, true), { wrapper })
    await waitFor(() => expect(hook.result.current.isSuccess).toBe(true))
    expect(api.searchTrending).toHaveBeenCalledWith(SEARCH)
    expect(hook.result.current.data).toEqual([ITEM])
  })

  it("does not fetch while disabled", () => {
    const { wrapper } = setup()
    renderHook(() => useTrendingSearch(SEARCH, false), { wrapper })
    expect(api.searchTrending).not.toHaveBeenCalled()
  })

  it("keeps the previous results as placeholder data while a new query fetches", async () => {
    vi.mocked(api.searchTrending).mockResolvedValue([ITEM])
    const { wrapper } = setup()
    const hook = renderHook(
      ({ query }: { query: TrendingSearchQuery }) =>
        useTrendingSearch(query, true),
      { wrapper, initialProps: { query: SEARCH } },
    )
    await waitFor(() => expect(hook.result.current.isSuccess).toBe(true))

    hook.rerender({ query: { ...SEARCH, query: "dune part" } })
    // The old results remain visible (flagged as placeholder) mid-fetch.
    expect(hook.result.current.data).toEqual([ITEM])
    expect(hook.result.current.isPlaceholderData).toBe(true)
    await waitFor(() =>
      expect(hook.result.current.isPlaceholderData).toBe(false),
    )
    expect(api.searchTrending).toHaveBeenLastCalledWith({
      ...SEARCH,
      query: "dune part",
    })
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
