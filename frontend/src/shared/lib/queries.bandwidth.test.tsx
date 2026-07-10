import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/api", () => ({
  getBandwidthStatus: vi.fn(),
  updateBandwidthSettings: vi.fn(),
}))

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import * as api from "@/shared/lib/api"
import { toast } from "sonner"

import {
  queryKeys,
  useBandwidthStatus,
  useUpdateBandwidthSettings,
} from "@/shared/lib/queries"
import { setup } from "@/shared/test/query-provider"

beforeEach(() => {
  vi.mocked(api.getBandwidthStatus).mockResolvedValue({
    enabled: false,
    status: "Monitoring only",
    last_run_at: "2026-06-26T20:00:00Z",
    check_interval_seconds: 15,
    qbittorrent: {
      online: true,
      speed_mbps: 0,
      active_downloads: 0,
      queue_size: 0,
    },
    sabnzbd: {
      online: true,
      speed_mbps: 0,
      active_downloads: 0,
      queue_size: 0,
      paused: false,
    },
    recent_downloads: [],
    queue: { qbittorrent: [], sabnzbd: [] },
  })
})

describe("bandwidth hooks", () => {
  it("useBandwidthStatus fetches the live status", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useBandwidthStatus(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.getBandwidthStatus).toHaveBeenCalled()
    expect(result.current.data?.enabled).toBe(false)
  })

  it("useUpdateBandwidthSettings invalidates the status on success", async () => {
    vi.mocked(api.updateBandwidthSettings).mockResolvedValue({
      enabled: true,
      status: "Monitoring only",
      last_run_at: null,
      check_interval_seconds: 30,
      qbittorrent: {
        online: true,
        speed_mbps: 0,
        active_downloads: 0,
        queue_size: 0,
      },
      sabnzbd: {
        online: true,
        speed_mbps: 0,
        active_downloads: 0,
        queue_size: 0,
        paused: false,
      },
      recent_downloads: [],
      queue: { qbittorrent: [], sabnzbd: [] },
    })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useUpdateBandwidthSettings(), {
      wrapper,
    })

    act(() => result.current.mutate({ enabled: true }))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.updateBandwidthSettings).toHaveBeenCalledWith(
      { enabled: true },
      expect.anything(),
    )
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.bandwidthStatus,
    })
  })

  it("useUpdateBandwidthSettings toasts on error", async () => {
    vi.mocked(api.updateBandwidthSettings).mockRejectedValue(new Error("bad"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useUpdateBandwidthSettings(), {
      wrapper,
    })

    act(() => result.current.mutate({ enabled: true }))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith(
      "Could not update bandwidth settings",
      {
        description: "bad",
      },
    )
  })
})
