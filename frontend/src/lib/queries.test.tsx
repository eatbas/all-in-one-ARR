import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/lib/api", () => ({
  getStatus: vi.fn(),
  getItems: vi.fn(),
  getActivity: vi.fn(),
  triggerSync: vi.fn(),
  setDryRun: vi.fn(),
}))

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import * as api from "@/lib/api"
import { toast } from "sonner"

import {
  queryKeys,
  useActivity,
  useItems,
  useSetDryRun,
  useStatus,
  useSyncNow,
} from "@/lib/queries"

/** A fresh client (retries disabled so failures surface immediately) plus its
 * matching provider wrapper. */
function setup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return { queryClient, wrapper }
}

beforeEach(() => {
  vi.mocked(api.getStatus).mockResolvedValue({
    dry_run: true,
    trakt_connected: false,
    counts: { synced: 0, requested: 0, available: 0, removed: 0 },
  })
  vi.mocked(api.getItems).mockResolvedValue([])
  vi.mocked(api.getActivity).mockResolvedValue([])
})

describe("query hooks", () => {
  it("useStatus fetches the dashboard status", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useStatus(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.getStatus).toHaveBeenCalled()
    expect(result.current.data?.dry_run).toBe(true)
  })

  it("useItems forwards the status argument to the API", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useItems("available"), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.getItems).toHaveBeenCalledWith("available")
  })

  it("useItems passes undefined when unfiltered", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useItems(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.getItems).toHaveBeenCalledWith(undefined)
  })

  it("useActivity fetches the activity feed", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useActivity(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.getActivity).toHaveBeenCalled()
  })
})

describe("useSyncNow", () => {
  it("toasts success and invalidates the affected queries", async () => {
    vi.mocked(api.triggerSync).mockResolvedValue({ status: "triggered" })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useSyncNow(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith(
      "Sync triggered",
      expect.objectContaining({ description: expect.any(String) }),
    )
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.status })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["items"] })
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

describe("useSetDryRun", () => {
  it("announces dry-run enabled and invalidates status", async () => {
    vi.mocked(api.setDryRun).mockResolvedValue({ dry_run: true })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useSetDryRun(), { wrapper })

    act(() => result.current.mutate(true))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith(
      "Dry-run mode enabled",
      expect.objectContaining({
        description: "Side-effecting actions are only logged, not executed.",
      }),
    )
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.status })
  })

  it("announces dry-run disabled on the false branch", async () => {
    vi.mocked(api.setDryRun).mockResolvedValue({ dry_run: false })
    const { wrapper } = setup()
    const { result } = renderHook(() => useSetDryRun(), { wrapper })

    act(() => result.current.mutate(false))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith(
      "Dry-run mode disabled",
      expect.objectContaining({
        description: "Live mode: requests and removals will be executed.",
      }),
    )
  })

  it("toasts the error message when the toggle fails", async () => {
    vi.mocked(api.setDryRun).mockRejectedValue(new Error("nope"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useSetDryRun(), { wrapper })

    act(() => result.current.mutate(true))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not change dry-run mode", {
      description: "nope",
    })
  })
})
