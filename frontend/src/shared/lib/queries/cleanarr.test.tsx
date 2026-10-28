import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/shared/lib/api", async () => ({
  // The real error class, so the 409 branch is exercised with `instanceof`.
  ApiError: (
    await vi.importActual<typeof import("@/shared/lib/api/client")>(
      "@/shared/lib/api/client",
    )
  ).ApiError,
  // The real formatter, so a FastAPI 422 body is decoded as in production.
  cleanarrErrorMessage: (
    await vi.importActual<typeof import("@/shared/lib/api/cleanarr")>(
      "@/shared/lib/api/cleanarr",
    )
  ).cleanarrErrorMessage,
  getCleanarrStatus: vi.fn(),
  getCleanarrSettings: vi.fn(),
  getCleanarrQueue: vi.fn(),
  getCleanarrHistory: vi.fn(),
  updateCleanarrSettings: vi.fn(),
  runCleanarr: vi.fn(),
  clearCleanarrStrikes: vi.fn(),
  ignoreCleanarrDownload: vi.fn(),
}))

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

import * as api from "@/shared/lib/api"
import { updateCleanarrSettings as realUpdateCleanarrSettings } from "@/shared/lib/api/cleanarr"
import { ApiError } from "@/shared/lib/api/client"
import { toast } from "sonner"
import { queryKeys } from "@/shared/lib/queries/keys"
import {
  useCleanarrHistory,
  useCleanarrQueue,
  useCleanarrSettings,
  useCleanarrStatus,
  useClearCleanarrStrikes,
  useIgnoreCleanarrDownload,
  useRunCleanarr,
  useUpdateCleanarrSettings,
} from "@/shared/lib/queries/cleanarr"
import {
  CLEANARR_HISTORY,
  CLEANARR_QUEUE,
  CLEANARR_SETTINGS,
  CLEANARR_STATUS,
} from "@/shared/test/cleanarr-fixtures"
import { setup } from "@/shared/test/query-provider"

afterEach(() => {
  vi.unstubAllGlobals()
})

beforeEach(() => {
  vi.mocked(api.getCleanarrStatus).mockResolvedValue(CLEANARR_STATUS)
  vi.mocked(api.getCleanarrSettings).mockResolvedValue(CLEANARR_SETTINGS)
  vi.mocked(api.getCleanarrQueue).mockResolvedValue(CLEANARR_QUEUE)
  vi.mocked(api.getCleanarrHistory).mockResolvedValue(CLEANARR_HISTORY)
})

describe("Cleanarr queries", () => {
  it.each([
    ["status", useCleanarrStatus, api.getCleanarrStatus],
    ["settings", useCleanarrSettings, api.getCleanarrSettings],
    ["queue", useCleanarrQueue, api.getCleanarrQueue],
    ["history", useCleanarrHistory, api.getCleanarrHistory],
  ] as const)("fetches the %s", async (_name, hook, fetcher) => {
    const { wrapper } = setup()
    const { result } = renderHook(() => hook(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(fetcher).toHaveBeenCalled()
  })
})

describe("Cleanarr mutations", () => {
  it("saving settings toasts and invalidates", async () => {
    vi.mocked(api.updateCleanarrSettings).mockResolvedValue(CLEANARR_STATUS)
    const { queryClient, wrapper } = setup()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const { result } = renderHook(() => useUpdateCleanarrSettings(), {
      wrapper,
    })

    act(() => result.current.mutate({ dry_run: false }))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.updateCleanarrSettings).toHaveBeenCalledWith(
      { dry_run: false },
      expect.anything(),
    )
    expect(toast.success).toHaveBeenCalledWith("Cleanarr settings saved")
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["cleanarr"] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.activity })
  })

  it("a rejected save surfaces the server detail", async () => {
    vi.mocked(api.updateCleanarrSettings).mockRejectedValue(
      new ApiError(
        422,
        "The quarantine folder must be inside the completed folder.",
      ),
    )
    const { wrapper } = setup()
    const { result } = renderHook(() => useUpdateCleanarrSettings(), {
      wrapper,
    })

    act(() => result.current.mutate({}))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith(
      "Could not save Cleanarr settings",
      {
        description:
          "The quarantine folder must be inside the completed folder.",
      },
    )
  })

  it("a FastAPI validation 422 names the field and the reason", async () => {
    // A real-shaped FastAPI body, through the real wrapper and fetch client.
    const body = {
      detail: [
        {
          type: "string_too_long",
          loc: ["body", "paths", "completed_root"],
          msg: "String should have at most 1024 characters",
          input: "/x",
          ctx: { max_length: 1024 },
        },
        {
          type: "string_too_long",
          loc: ["body", "queue", "patterns", 3],
          msg: "String should have at most 200 characters",
        },
        {
          loc: ["body", "unknown_field"],
          msg: "Extra inputs are not permitted",
        },
        { msg: "not a validation issue" },
      ],
    }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(body), {
        status: 422,
        headers: { "Content-Type": "application/json" },
      }),
    )
    vi.stubGlobal("fetch", fetchMock)
    vi.mocked(api.updateCleanarrSettings).mockImplementation(
      realUpdateCleanarrSettings,
    )
    const { wrapper } = setup()
    const { result } = renderHook(() => useUpdateCleanarrSettings(), {
      wrapper,
    })

    act(() => result.current.mutate({}))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cleanarr/settings",
      expect.objectContaining({ method: "PUT" }),
    )
    expect(toast.error).toHaveBeenCalledWith(
      "Could not save Cleanarr settings",
      {
        description:
          "Completed folder: String should have at most 1024 characters; " +
          "Patterns: String should have at most 200 characters; " +
          "unknown_field: Extra inputs are not permitted",
      },
    )
  })

  it.each([
    ["no validation issues", [{ msg: "no location" }]],
    ["a detail that is not an array", { reason: "x" }],
  ])("a 422 with %s keeps the generic message", async (_name, detail) => {
    vi.mocked(api.updateCleanarrSettings).mockRejectedValue(
      new ApiError(422, "Request failed with status 422", detail),
    )
    const { wrapper } = setup()
    const { result } = renderHook(() => useUpdateCleanarrSettings(), {
      wrapper,
    })

    act(() => result.current.mutate({}))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith(
      "Could not save Cleanarr settings",
      { description: "Request failed with status 422" },
    )
  })

  it("a validation issue without a field shows just the reason", async () => {
    vi.mocked(api.updateCleanarrSettings).mockRejectedValue(
      new ApiError(422, "x", [{ loc: ["body"], msg: "Field required" }]),
    )
    const { wrapper } = setup()
    const { result } = renderHook(() => useUpdateCleanarrSettings(), {
      wrapper,
    })

    act(() => result.current.mutate({}))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith(
      "Could not save Cleanarr settings",
      { description: "Field required" },
    )
  })

  it.each([
    ["completed", "Cleanarr run complete"],
    ["skipped", "Cleanarr run skipped"],
  ] as const)("a %s run toasts its detail", async (status, title) => {
    vi.mocked(api.runCleanarr).mockResolvedValue({
      status,
      detail: "1 struck",
      counts: {},
    })
    const { wrapper } = setup()
    const { result } = renderHook(() => useRunCleanarr(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith(title, {
      description: "1 struck",
    })
  })

  it("a run rejected with 409 warns that Cleanarr is busy", async () => {
    vi.mocked(api.runCleanarr).mockRejectedValue(
      new ApiError(409, "Cleanarr is already running"),
    )
    const { wrapper } = setup()
    const { result } = renderHook(() => useRunCleanarr(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.warning).toHaveBeenCalledWith("Cleanarr is already running", {
      description: "Try again when the current run finishes.",
    })
    expect(toast.error).not.toHaveBeenCalled()
  })

  it("other run failures are errors", async () => {
    vi.mocked(api.runCleanarr).mockRejectedValue(new Error("boom"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useRunCleanarr(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not run Cleanarr", {
      description: "boom",
    })
  })

  it("clearing strikes toasts the count", async () => {
    vi.mocked(api.clearCleanarrStrikes).mockResolvedValue({ count: 4 })
    const { wrapper } = setup()
    const { result } = renderHook(() => useClearCleanarrStrikes(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith("Cleared 4 strike(s)")
  })

  it.each([
    [new ApiError(409, "busy"), "warning"],
    [new ApiError(500, "broken"), "error"],
  ] as const)("a failed strike reset is a %s", async (error, kind) => {
    vi.mocked(api.clearCleanarrStrikes).mockRejectedValue(error)
    const { wrapper } = setup()
    const { result } = renderHook(() => useClearCleanarrStrikes(), { wrapper })

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isError).toBe(true))
    if (kind === "warning") {
      expect(toast.warning).toHaveBeenCalled()
    } else {
      expect(toast.error).toHaveBeenCalledWith("Could not clear strikes", {
        description: "broken",
      })
    }
  })

  it("ignoring a download names it in the toast", async () => {
    vi.mocked(api.ignoreCleanarrDownload).mockResolvedValue(CLEANARR_SETTINGS)
    const { wrapper } = setup()
    const { result } = renderHook(() => useIgnoreCleanarrDownload(), {
      wrapper,
    })

    act(() =>
      result.current.mutate({ downloadId: "nzo_1", title: "Severance.S02E10" }),
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.ignoreCleanarrDownload).toHaveBeenCalledWith("nzo_1")
    expect(toast.success).toHaveBeenCalledWith("Ignoring download", {
      description: "Cleanarr will skip Severance.S02E10 from now on.",
    })
  })

  it("an ignore rejected with 409 warns that Cleanarr is busy", async () => {
    vi.mocked(api.ignoreCleanarrDownload).mockRejectedValue(
      new ApiError(409, "Cleanarr is already running"),
    )
    const { wrapper } = setup()
    const { result } = renderHook(() => useIgnoreCleanarrDownload(), {
      wrapper,
    })

    act(() => result.current.mutate({ downloadId: "nzo_1", title: "t" }))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.warning).toHaveBeenCalledWith("Cleanarr is already running", {
      description: "Try again when the current run finishes.",
    })
    expect(toast.success).not.toHaveBeenCalled()
  })

  it("an ignore refused for a full list shows the server's reason", async () => {
    const reason =
      "The ignore list already holds 500 download IDs. Remove some in Settings before ignoring another download."
    vi.mocked(api.ignoreCleanarrDownload).mockRejectedValue(
      new ApiError(422, reason),
    )
    const { wrapper } = setup()
    const { result } = renderHook(() => useIgnoreCleanarrDownload(), {
      wrapper,
    })

    act(() => result.current.mutate({ downloadId: "nzo_1", title: "t" }))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not ignore download", {
      description: reason,
    })
    expect(toast.success).not.toHaveBeenCalled()
  })

  it("a failed ignore is an error", async () => {
    vi.mocked(api.ignoreCleanarrDownload).mockRejectedValue(new Error("nope"))
    const { wrapper } = setup()
    const { result } = renderHook(() => useIgnoreCleanarrDownload(), {
      wrapper,
    })

    act(() => result.current.mutate({ downloadId: "nzo_1", title: "t" }))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith("Could not ignore download", {
      description: "nope",
    })
  })
})
