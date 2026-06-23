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
  getTraktSettings: vi.fn(),
  getTraktAuthStatus: vi.fn(),
  getTraktLists: vi.fn(),
  updateTraktSettings: vi.fn(),
  startTraktAuth: vi.fn(),
  testTrakt: vi.fn(),
  addTraktList: vi.fn(),
  removeTraktList: vi.fn(),
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

import * as api from "@/lib/api"
import { toast } from "sonner"

import {
  queryKeys,
  useActivity,
  useAddTraktList,
  useCheckServiceStatuses,
  useGeneralSettings,
  useItems,
  useRemoveTraktList,
  useServiceSettings,
  useServiceStatuses,
  useSetDryRun,
  useStartTraktAuth,
  useStatus,
  useSyncNow,
  useTestService,
  useTestTrakt,
  useTraktAuthStatus,
  useTraktLists,
  useTraktSettings,
  useUpdateServiceSettings,
  useUpdateStatusInterval,
  useUpdateTraktSettings,
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

const sampleSettings = {
  client_id_hint: "1234",
  client_id_set: true,
  client_secret_set: true,
  user: "me",
  connected: true,
  lists: [],
}

beforeEach(() => {
  vi.mocked(api.getStatus).mockResolvedValue({
    dry_run: true,
    trakt_connected: false,
    counts: { synced: 0, requested: 0, available: 0, removed: 0 },
  })
  vi.mocked(api.getItems).mockResolvedValue([])
  vi.mocked(api.getActivity).mockResolvedValue([])
  vi.mocked(api.getTraktSettings).mockResolvedValue(sampleSettings)
  vi.mocked(api.getTraktAuthStatus).mockResolvedValue({
    state: "idle",
    user_code: null,
    verification_url: null,
    message: null,
    connected: false,
  })
  vi.mocked(api.getTraktLists).mockResolvedValue([])
  vi.mocked(api.getServiceSettings).mockResolvedValue({
    jellyseerr: { url: "http://js", api_key_set: true },
    sonarr: { url: "", api_key_set: false },
    radarr: { url: "", api_key_set: false },
    tmdb: { api_key_set: false },
    omdb: { api_key_set: false },
    sabnzbd: { url: "", api_key_set: false },
    qbittorrent: { url: "", username: "", password_set: false },
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
  vi.mocked(api.getGeneralSettings).mockResolvedValue({ interval_seconds: 60 })
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

describe("trakt connection hooks", () => {
  it("useTraktSettings fetches the settings", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useTraktSettings(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.user).toBe("me")
  })

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

  it("useUpdateTraktSettings toasts and invalidates on success", async () => {
    vi.mocked(api.updateTraktSettings).mockResolvedValue(sampleSettings)
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useUpdateTraktSettings(), { wrapper })

    act(() => result.current.mutate({ user: "bob" }))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith("Trakt settings saved")
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.traktSettings })
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
    const { wrapper } = setup()
    const { result } = renderHook(() => useTestTrakt(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith("Trakt connection OK", {
      description: "Signed in as erena",
    })
  })

  it("useTestTrakt omits the description when no user is returned", async () => {
    vi.mocked(api.testTrakt).mockResolvedValue({
      ok: true,
      user: null,
      message: "Connection OK",
    })
    const { wrapper } = setup()
    const { result } = renderHook(() => useTestTrakt(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith("Trakt connection OK", {
      description: undefined,
    })
  })

  it("useTestTrakt reports a failed test", async () => {
    vi.mocked(api.testTrakt).mockResolvedValue({
      ok: false,
      user: null,
      message: "no token",
    })
    const { wrapper } = setup()
    const { result } = renderHook(() => useTestTrakt(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Trakt connection failed", {
      description: "no token",
    })
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

describe("service connection hooks", () => {
  it("useServiceSettings fetches the service settings", async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useServiceSettings(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.jellyseerr.api_key_set).toBe(true)
  })

  it("useUpdateServiceSettings toasts and invalidates on success", async () => {
    vi.mocked(api.updateServiceSettings).mockResolvedValue({
      jellyseerr: { url: "http://js", api_key_set: true },
      sonarr: { url: "http://sonarr", api_key_set: true },
      radarr: { url: "", api_key_set: false },
      tmdb: { api_key_set: false },
      omdb: { api_key_set: false },
      sabnzbd: { url: "", api_key_set: false },
      qbittorrent: { url: "", username: "", password_set: false },
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
    const { wrapper } = setup()
    const { result } = renderHook(() => useTestService(), { wrapper })

    act(() => result.current.mutate("sonarr"))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.testService).toHaveBeenCalledWith("sonarr")
    expect(toast.success).toHaveBeenCalledWith("Connection OK", {
      description: "Connected to Sonarr 4.0",
    })
  })

  it("useTestService reports a failed test", async () => {
    vi.mocked(api.testService).mockResolvedValue({
      ok: false,
      detail: "HTTP 401",
    })
    const { wrapper } = setup()
    const { result } = renderHook(() => useTestService(), { wrapper })

    act(() => result.current.mutate("radarr"))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Connection failed", {
      description: "HTTP 401",
    })
  })

  it("useTestService toasts on a thrown error", async () => {
    vi.mocked(api.testService).mockRejectedValue(new Error("boom"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useTestService(), { wrapper })

    act(() => result.current.mutate("jellyseerr"))

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
    vi.mocked(api.updateGeneralSettings).mockResolvedValue({ interval_seconds: 30 })
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
  })
})
