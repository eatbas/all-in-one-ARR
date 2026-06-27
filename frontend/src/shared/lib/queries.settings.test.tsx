import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/api", () => ({
  getTraktSettings: vi.fn(),
  updateTraktSettings: vi.fn(),
  startTraktAuth: vi.fn(),
  testTrakt: vi.fn(),
  getServiceSettings: vi.fn(),
  updateServiceSettings: vi.fn(),
  testService: vi.fn(),
  getServiceStatuses: vi.fn(),
  checkServiceStatuses: vi.fn(),
  getGeneralSettings: vi.fn(),
  updateGeneralSettings: vi.fn(),
}))

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import * as api from "@/shared/lib/api"
import { toast } from "sonner"

import {
  queryKeys,
  useCheckServiceStatuses,
  useGeneralSettings,
  useServiceSettings,
  useServiceStatuses,
  useStartTraktAuth,
  useTestService,
  useTestTrakt,
  useTraktSettings,
  useUpdateAutoRemoveWhenAvailable,
  useUpdateServiceSettings,
  useUpdateStatusInterval,
  useUpdateSyncInterval,
  useUpdateTraktSettings,
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
  vi.mocked(api.getTraktSettings).mockResolvedValue(sampleSettings)
  vi.mocked(api.getServiceSettings).mockResolvedValue({
    seer: { url: "http://js", api_key_set: true },
    sonarr: { url: "", api_key_set: false },
    radarr: { url: "", api_key_set: false },
    tmdb: { api_key_set: false },
    omdb: { api_key_set: false },
    sabnzbd: { url: "", api_key_set: false },
    qbittorrent: { url: "", api_key_set: false },
  })
  vi.mocked(api.getServiceStatuses).mockResolvedValue({
    interval_seconds: 60,
    last_check_at: null,
    services: {},
  })
  vi.mocked(api.checkServiceStatuses).mockResolvedValue({
    interval_seconds: 60,
    last_check_at: "2026-06-23T13:22:46Z",
    services: {},
  })
  vi.mocked(api.getGeneralSettings).mockResolvedValue({
    interval_seconds: 60,
    sync_interval_minutes: 15,
    auto_remove_when_available: false,
  })
})

describe("trakt settings hooks", () => {
  it("useTraktSettings fetches the settings", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useTraktSettings(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.client_id_hint).toBe("1234")
  })

  it("useUpdateTraktSettings toasts and invalidates on success", async () => {
    vi.mocked(api.updateTraktSettings).mockResolvedValue(sampleSettings)
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useUpdateTraktSettings(), { wrapper })

    act(() => result.current.mutate({ client_id: "newid1234" }))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith("Trakt settings saved")
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.traktSettings })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("useUpdateTraktSettings toasts on error", async () => {
    vi.mocked(api.updateTraktSettings).mockRejectedValue(new Error("bad"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useUpdateTraktSettings(), { wrapper })

    act(() => result.current.mutate({}))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not save Trakt settings", {
      description: "bad",
    })
  })

  it("useStartTraktAuth toasts and invalidates the status on success", async () => {
    vi.mocked(api.startTraktAuth).mockResolvedValue({
      state: "pending",
      user_code: "ABCD",
      verification_url: "u",
      message: "m",
    })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useStartTraktAuth(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith(
      "Authorisation started",
      expect.objectContaining({ description: expect.any(String) }),
    )
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.traktAuthStatus,
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("useStartTraktAuth toasts on error", async () => {
    vi.mocked(api.startTraktAuth).mockRejectedValue(new Error("net"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useStartTraktAuth(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not start authorisation", {
      description: "net",
    })
  })

  it("useTestTrakt announces a successful test with the user", async () => {
    vi.mocked(api.testTrakt).mockResolvedValue({
      ok: true,
      user: "erena",
      message: "Connection OK",
    })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useTestTrakt(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith("Trakt connection OK", {
      description: "Signed in as erena",
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("useTestTrakt omits the description when no user is returned", async () => {
    vi.mocked(api.testTrakt).mockResolvedValue({
      ok: true,
      user: null,
      message: "Connection OK",
    })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useTestTrakt(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith("Trakt connection OK", {
      description: undefined,
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("useTestTrakt reports a failed test", async () => {
    vi.mocked(api.testTrakt).mockResolvedValue({
      ok: false,
      user: null,
      message: "no token",
    })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useTestTrakt(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Trakt connection failed", {
      description: "no token",
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("useTestTrakt toasts on a thrown error", async () => {
    vi.mocked(api.testTrakt).mockRejectedValue(new Error("boom"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useTestTrakt(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not test connection", {
      description: "boom",
    })
  })
})

describe("service connection hooks", () => {
  it("useServiceSettings fetches the service settings", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useServiceSettings(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.seer.api_key_set).toBe(true)
  })

  it("useUpdateServiceSettings toasts and invalidates on success", async () => {
    vi.mocked(api.updateServiceSettings).mockResolvedValue({
      seer: { url: "http://js", api_key_set: true },
      sonarr: { url: "http://sonarr", api_key_set: true },
      radarr: { url: "", api_key_set: false },
      tmdb: { api_key_set: false },
      omdb: { api_key_set: false },
      sabnzbd: { url: "", api_key_set: false },
      qbittorrent: { url: "", api_key_set: false },
    })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useUpdateServiceSettings(), { wrapper })

    act(() =>
      result.current.mutate({ name: "sonarr", body: { url: "http://sonarr" } }),
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.updateServiceSettings).toHaveBeenCalledWith("sonarr", {
      url: "http://sonarr",
    })
    expect(toast.success).toHaveBeenCalledWith("Connection saved")
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.services })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("useUpdateServiceSettings toasts on error", async () => {
    vi.mocked(api.updateServiceSettings).mockRejectedValue(new Error("bad"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useUpdateServiceSettings(), { wrapper })

    act(() => result.current.mutate({ name: "sonarr", body: {} }))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not save connection", {
      description: "bad",
    })
  })

  it("useTestService announces a successful test", async () => {
    vi.mocked(api.testService).mockResolvedValue({
      ok: true,
      detail: "Connected to Sonarr 4.0",
    })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useTestService(), { wrapper })

    act(() => result.current.mutate("sonarr"))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.testService).toHaveBeenCalledWith("sonarr")
    expect(toast.success).toHaveBeenCalledWith("Connection OK", {
      description: "Connected to Sonarr 4.0",
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("useTestService reports a failed test", async () => {
    vi.mocked(api.testService).mockResolvedValue({
      ok: false,
      detail: "HTTP 401",
    })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useTestService(), { wrapper })

    act(() => result.current.mutate("radarr"))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Connection failed", {
      description: "HTTP 401",
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("useTestService toasts on a thrown error", async () => {
    vi.mocked(api.testService).mockRejectedValue(new Error("boom"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useTestService(), { wrapper })

    act(() => result.current.mutate("seer"))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not test connection", {
      description: "boom",
    })
  })
})

describe("service status hooks", () => {
  it("useServiceStatuses fetches the service status snapshot", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useServiceStatuses(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.getServiceStatuses).toHaveBeenCalled()
    expect(result.current.data?.interval_seconds).toBe(60)
  })

  it("useServiceStatuses derives the polling interval from the response", async () => {
    vi.mocked(api.getServiceStatuses).mockResolvedValue({
      interval_seconds: 30,
      last_check_at: null,
      services: {},
    })
    const { wrapper } = setup()
    const { result } = renderHook(() => useServiceStatuses(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.interval_seconds).toBe(30)
  })

  it("useCheckServiceStatuses triggers a fresh check and invalidates the cache", async () => {
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useCheckServiceStatuses(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.checkServiceStatuses).toHaveBeenCalled()
    expect(toast.success).toHaveBeenCalledWith("Status check complete")
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.serviceStatuses })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("useCheckServiceStatuses toasts on error", async () => {
    vi.mocked(api.checkServiceStatuses).mockRejectedValue(new Error("offline"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useCheckServiceStatuses(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Status check failed", {
      description: "offline",
    })
  })
})

describe("general settings hooks", () => {
  it("useGeneralSettings fetches the interval", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useGeneralSettings(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.getGeneralSettings).toHaveBeenCalled()
    expect(result.current.data?.interval_seconds).toBe(60)
  })

  it("useUpdateStatusInterval saves the new interval and invalidates queries", async () => {
    vi.mocked(api.updateGeneralSettings).mockResolvedValue({
      interval_seconds: 30,
      sync_interval_minutes: 15,
      auto_remove_when_available: false,
    })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useUpdateStatusInterval(), { wrapper })

    act(() => result.current.mutate({ interval_seconds: 30 }))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.updateGeneralSettings).toHaveBeenCalledWith(
      { interval_seconds: 30 },
      expect.anything(),
    )
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.serviceStatuses })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.generalSettings })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("useUpdateStatusInterval toasts on error", async () => {
    vi.mocked(api.updateGeneralSettings).mockRejectedValue(new Error("nope"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useUpdateStatusInterval(), { wrapper })

    act(() => result.current.mutate({ interval_seconds: 45 }))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not update interval", {
      description: "nope",
    })
  })

  it("useUpdateSyncInterval saves the sync interval and invalidates queries", async () => {
    vi.mocked(api.updateGeneralSettings).mockResolvedValue({
      interval_seconds: 60,
      sync_interval_minutes: 30,
      auto_remove_when_available: false,
    })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useUpdateSyncInterval(), { wrapper })

    act(() => result.current.mutate(30))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.updateGeneralSettings).toHaveBeenCalledWith({
      sync_interval_minutes: 30,
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.generalSettings })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.lists })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("useUpdateSyncInterval toasts on error", async () => {
    vi.mocked(api.updateGeneralSettings).mockRejectedValue(new Error("boom"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useUpdateSyncInterval(), { wrapper })

    act(() => result.current.mutate(45))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not update sync interval", {
      description: "boom",
    })
  })

  it("useUpdateAutoRemoveWhenAvailable announces enabled and invalidates general settings", async () => {
    vi.mocked(api.updateGeneralSettings).mockResolvedValue({
      interval_seconds: 60,
      sync_interval_minutes: 15,
      auto_remove_when_available: true,
    })
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useUpdateAutoRemoveWhenAvailable(), { wrapper })

    act(() => result.current.mutate(true))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.updateGeneralSettings).toHaveBeenCalledWith({
      auto_remove_when_available: true,
    })
    expect(toast.success).toHaveBeenCalledWith(
      "Auto-remove when available enabled",
      expect.objectContaining({ description: expect.any(String) }),
    )
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.generalSettings,
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("useUpdateAutoRemoveWhenAvailable announces disabled on the false branch", async () => {
    vi.mocked(api.updateGeneralSettings).mockResolvedValue({
      interval_seconds: 60,
      sync_interval_minutes: 15,
      auto_remove_when_available: false,
    })
    const { wrapper } = setup()
    const { result } = renderHook(() => useUpdateAutoRemoveWhenAvailable(), { wrapper })

    act(() => result.current.mutate(false))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith(
      "Auto-remove when available disabled",
      expect.objectContaining({ description: expect.any(String) }),
    )
  })

  it("useUpdateAutoRemoveWhenAvailable toasts on error", async () => {
    vi.mocked(api.updateGeneralSettings).mockRejectedValue(new Error("boom"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useUpdateAutoRemoveWhenAvailable(), { wrapper })

    act(() => result.current.mutate(true))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not update auto-remove", {
      description: "boom",
    })
  })
})
