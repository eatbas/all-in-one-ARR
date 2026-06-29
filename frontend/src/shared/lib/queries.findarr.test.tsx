import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/api", () => ({
  getFindarrStatus: vi.fn(),
  getFindarrSettings: vi.fn(),
  getFindarrHistory: vi.fn(),
  updateFindarrSettings: vi.fn(),
  runFindarr: vi.fn(),
  resetFindarrState: vi.fn(),
}))

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import * as api from "@/shared/lib/api"
import { toast } from "sonner"
import {
  queryKeys,
  useFindarrHistory,
  useFindarrSettings,
  useFindarrStatus,
  useResetFindarrState,
  useRunFindarr,
  useUpdateFindarrSettings,
} from "@/shared/lib/queries"
import { setup } from "@/shared/test/query-provider"

const settings = {
  enabled: false,
  interval_minutes: 30,
  hourly_cap: 20,
  queue_limit: -1,
  command_sleep_seconds: 0,
  state_reset_hours: 168,
  apps: {
    sonarr: {
      enabled: true,
      missing_limit: 5,
      upgrade_limit: 5,
      monitored_only: true,
      skip_future: true,
      missing_mode: "episodes",
      upgrade_mode: "episodes",
    },
    radarr: {
      enabled: true,
      missing_limit: 5,
      upgrade_limit: 5,
      monitored_only: true,
      skip_future: true,
      missing_mode: "episodes",
      upgrade_mode: "episodes",
    },
  },
} as const

const status = {
  settings,
  running: false,
  last_run_at: null,
  last_run_status: null,
  last_run_detail: null,
  state: { created_at: null, reset_at: null, reset_hours: 168 },
  apps: {
    sonarr: {
      detail: "ok",
      version: "4.0.0",
      compatible: true,
      processed: { missing: 0, upgrade: 0 },
    },
    radarr: {
      detail: "ok",
      version: "6.0.0",
      compatible: true,
      processed: { missing: 0, upgrade: 0 },
    },
  },
  hourly: { limit: 20, used: 0, remaining: 20 },
} as const

beforeEach(() => {
  vi.mocked(api.getFindarrStatus).mockResolvedValue(status)
  vi.mocked(api.getFindarrSettings).mockResolvedValue(settings)
  vi.mocked(api.getFindarrHistory).mockResolvedValue([])
})

describe("Findarr query hooks", () => {
  it("fetches status, settings, and history", async () => {
    const { wrapper } = setup()
    const statusHook = renderHook(() => useFindarrStatus(), { wrapper })
    const settingsHook = renderHook(() => useFindarrSettings(), { wrapper })
    const historyHook = renderHook(() => useFindarrHistory(), { wrapper })

    await waitFor(() => expect(statusHook.result.current.isSuccess).toBe(true))
    await waitFor(() => expect(settingsHook.result.current.isSuccess).toBe(true))
    await waitFor(() => expect(historyHook.result.current.isSuccess).toBe(true))
    expect(api.getFindarrStatus).toHaveBeenCalled()
    expect(api.getFindarrSettings).toHaveBeenCalled()
    expect(api.getFindarrHistory).toHaveBeenCalled()
  })

  it("invalidates Findarr queries after settings, run, and reset mutations", async () => {
    vi.mocked(api.updateFindarrSettings).mockResolvedValue(status)
    vi.mocked(api.runFindarr).mockResolvedValue({
      status: "completed",
      detail: "done",
      processed: 0,
      results: [],
    })
    vi.mocked(api.resetFindarrState).mockResolvedValue({ status: "reset", removed: 1 })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")

    const updateHook = renderHook(() => useUpdateFindarrSettings(), { wrapper })
    act(() => updateHook.result.current.mutate({ enabled: true }))
    await waitFor(() => expect(updateHook.result.current.isSuccess).toBe(true))

    const runHook = renderHook(() => useRunFindarr(), { wrapper })
    act(() => runHook.result.current.mutate("sonarr"))
    await waitFor(() => expect(runHook.result.current.isSuccess).toBe(true))

    const resetHook = renderHook(() => useResetFindarrState(), { wrapper })
    act(() => resetHook.result.current.mutate())
    await waitFor(() => expect(resetHook.result.current.isSuccess).toBe(true))

    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.findarrStatus })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.findarrSettings })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.findarrHistory })
  })

  it("toasts an error when a Findarr mutation fails", async () => {
    vi.mocked(api.updateFindarrSettings).mockRejectedValue(new Error("save boom"))
    vi.mocked(api.runFindarr).mockRejectedValue(new Error("run boom"))
    vi.mocked(api.resetFindarrState).mockRejectedValue(new Error("reset boom"))
    const { wrapper } = setup()

    const updateHook = renderHook(() => useUpdateFindarrSettings(), { wrapper })
    act(() => updateHook.result.current.mutate({ enabled: true }))
    await waitFor(() => expect(updateHook.result.current.isError).toBe(true))

    const runHook = renderHook(() => useRunFindarr(), { wrapper })
    act(() => runHook.result.current.mutate("sonarr"))
    await waitFor(() => expect(runHook.result.current.isError).toBe(true))

    const resetHook = renderHook(() => useResetFindarrState(), { wrapper })
    act(() => resetHook.result.current.mutate())
    await waitFor(() => expect(resetHook.result.current.isError).toBe(true))

    expect(toast.error).toHaveBeenCalledWith("Could not save Findarr settings", {
      description: "save boom",
    })
    expect(toast.error).toHaveBeenCalledWith("Could not run Findarr", {
      description: "run boom",
    })
    expect(toast.error).toHaveBeenCalledWith("Could not reset Findarr state", {
      description: "reset boom",
    })
  })
})
