import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/api", () => ({
  getItems: vi.fn(),
  getLists: vi.fn(),
  triggerSync: vi.fn(),
  getTraktAuthStatus: vi.fn(),
  getTraktLists: vi.fn(),
  addTraktList: vi.fn(),
  removeTraktList: vi.fn(),
  removeItem: vi.fn(),
  removeAvailable: vi.fn(),
}))

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import * as api from "@/shared/lib/api"
import { toast } from "sonner"

import {
  queryKeys,
  useAddTraktList,
  useListItems,
  useLists,
  useRemoveAvailable,
  useRemoveItem,
  useRemoveTraktList,
  useSyncNow,
  useTraktAuthStatus,
  useTraktLists,
} from "@/shared/lib/queries"
import { setup } from "@/shared/test/query-provider"

const sampleSettings = {
  client_id_hint: "1234",
  client_id_set: true,
  client_secret_set: true,
  connected: true,
  lists: [],
}

beforeEach(() => {
  vi.mocked(api.getItems).mockResolvedValue([])
  vi.mocked(api.getLists).mockResolvedValue([])
  vi.mocked(api.getTraktAuthStatus).mockResolvedValue({
    state: "idle",
    user_code: null,
    verification_url: null,
    message: null,
    connected: false,
  })
  vi.mocked(api.getTraktLists).mockResolvedValue([])
})

describe("list syncarr query hooks", () => {
  it("useLists fetches the synced lists", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useLists(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.getLists).toHaveBeenCalled()
  })

  it("useListItems fetches a list's items when enabled", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useListItems("movies", true), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.getItems).toHaveBeenCalledWith(undefined, "movies")
  })

  it("useListItems stays idle while disabled", () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useListItems("movies", false), { wrapper })

    expect(result.current.fetchStatus).toBe("idle")
    expect(api.getItems).not.toHaveBeenCalled()
  })
})

describe("useSyncNow", () => {
  it("toasts success and awaits invalidation of the affected queries", async () => {
    vi.mocked(api.triggerSync).mockResolvedValue({ status: "completed" })
    const { queryClient, wrapper } = setup()
    const invalidate = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined)
    const { result } = renderHook(() => useSyncNow(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith(
      "Sync complete",
      expect.objectContaining({ description: expect.any(String) }),
    )
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.status })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["items"] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.lists })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("toasts the error message when the sync fails", async () => {
    vi.mocked(api.triggerSync).mockRejectedValue(new Error("backend down"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useSyncNow(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not trigger sync", {
      description: "backend down",
    })
  })
})

describe("trakt connection hooks", () => {
  it("useTraktAuthStatus stops polling once not pending", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useTraktAuthStatus(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.getTraktAuthStatus).toHaveBeenCalled()
  })

  it("useTraktAuthStatus keeps polling while pending", async () => {
    vi.mocked(api.getTraktAuthStatus).mockResolvedValue({
      state: "pending",
      user_code: "ABCD",
      verification_url: "https://trakt.tv/activate",
      message: "waiting",
      connected: false,
    })
    const { wrapper } = setup()
    const { result } = renderHook(() => useTraktAuthStatus(), { wrapper })
    await waitFor(() => expect(result.current.data?.state).toBe("pending"))
  })

  it("useTraktLists fetches only when enabled", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useTraktLists(true), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.getTraktLists).toHaveBeenCalled()
  })

  it("useTraktLists stays idle when disabled", () => {
    const { wrapper } = setup()
    renderHook(() => useTraktLists(false), { wrapper })
    expect(api.getTraktLists).not.toHaveBeenCalled()
  })

  it("useAddTraktList toasts and invalidates on success", async () => {
    vi.mocked(api.addTraktList).mockResolvedValue(sampleSettings)
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useAddTraktList(), { wrapper })

    act(() => result.current.mutate({ url: "https://trakt.tv/users/me/lists/anime" }))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith("List added")
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.traktSettings })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.traktLists })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("useAddTraktList toasts on error", async () => {
    vi.mocked(api.addTraktList).mockRejectedValue(new Error("bad url"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useAddTraktList(), { wrapper })

    act(() => result.current.mutate({ url: "x" }))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not add list", {
      description: "bad url",
    })
  })

  it("useRemoveTraktList removes by owner and slug", async () => {
    vi.mocked(api.removeTraktList).mockResolvedValue(sampleSettings)
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useRemoveTraktList(), { wrapper })

    act(() => result.current.mutate({ owner_user: "me", slug: "movies" }))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.removeTraktList).toHaveBeenCalledWith("me", "movies")
    expect(toast.success).toHaveBeenCalledWith("List removed")
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.traktLists })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("useRemoveTraktList toasts on error", async () => {
    vi.mocked(api.removeTraktList).mockRejectedValue(new Error("nope"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useRemoveTraktList(), { wrapper })

    act(() => result.current.mutate({ owner_user: "me", slug: "movies" }))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not remove list", {
      description: "nope",
    })
  })
})

describe("list item management hooks", () => {
  it("useRemoveItem deletes an item and invalidates queries", async () => {
    vi.mocked(api.removeItem).mockResolvedValue(undefined)
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useRemoveItem(), { wrapper })

    act(() => result.current.mutate({ list_id: "movies", trakt_id: 1 }))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.removeItem).toHaveBeenCalledWith("movies", 1)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["items"] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.lists })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.status })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("useRemoveItem toasts on error", async () => {
    vi.mocked(api.removeItem).mockRejectedValue(new Error("denied"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useRemoveItem(), { wrapper })

    act(() => result.current.mutate({ list_id: "movies", trakt_id: 1 }))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not remove item", {
      description: "denied",
    })
  })

  it("useRemoveAvailable triggers the sweep and invalidates queries", async () => {
    vi.mocked(api.removeAvailable).mockResolvedValue({ status: "triggered" })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useRemoveAvailable(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.removeAvailable).toHaveBeenCalled()
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["items"] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.lists })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.status })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("useRemoveAvailable toasts on error", async () => {
    vi.mocked(api.removeAvailable).mockRejectedValue(new Error("offline"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useRemoveAvailable(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not remove available items", {
      description: "offline",
    })
  })
})
